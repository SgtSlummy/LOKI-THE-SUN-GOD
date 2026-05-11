from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from utils.command_descriptions import (
    PLACEHOLDER,
    command_description_for,
    humanize_identifier,
    option_description_for,
)

MISSING = object()
_CATALOG_CACHE: dict[str, tuple[tuple[tuple[str, int, int], ...], list[dict]]] = {}


def parse_command_catalog(root: Path) -> list[dict]:
    catalog = []
    cogs_dir = root / "cogs"
    if not cogs_dir.exists():
        return catalog

    snapshot = _catalog_snapshot(cogs_dir)
    cache_key = str(cogs_dir.resolve())
    cached = _CATALOG_CACHE.get(cache_key)
    if cached and cached[0] == snapshot:
        return cached[1]

    for path in sorted(cogs_dir.glob("*.py")):
        if path.suffix != ".py" or path.name.endswith((".bak.py", ".trim.py")):
            continue
        if path.name.endswith(".bak") or path.name.endswith(".trim.bak"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        autocomplete_map = collect_autocomplete_targets(tree)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            command_meta = None
            for decorator in node.decorator_list:
                meta = parse_command_decorator(decorator)
                if meta:
                    command_meta = meta
                    break
            if not command_meta:
                continue

            description = command_meta["description"] or first_docstring_line(node)
            command_name = command_meta["name"] or node.name.replace("_", "-")
            category = path.stem.replace("_", " ").title()
            full_name = f"{command_meta['group']} {command_name}".strip() if command_meta["group"] else command_name
            aliases = command_meta["aliases"] if isinstance(command_meta["aliases"], list) else []
            description = command_description_for(full_name, category, command_meta["kind"], description or PLACEHOLDER)
            options = extract_command_options(node, full_name, autocomplete_map.get(node.name, set()))
            permissions = extract_permissions(node.decorator_list)
            permission_labels = [humanize_identifier(permission) for permission in permissions]
            option_search = " ".join(option["search"] for option in options)
            search_terms = " ".join(
                filter(
                    None,
                    [
                        full_name,
                        command_name,
                        " ".join(aliases),
                        description or "",
                        path.stem.replace("_", " "),
                        option_search,
                        " ".join(permissions),
                        " ".join(permission_labels),
                    ],
                )
            ).lower()
            catalog.append(
                {
                    "id": f"{path.stem}:{node.name}",
                    "command": command_name,
                    "full_name": full_name,
                    "group": command_meta["group"],
                    "kind": command_meta["kind"],
                    "category": category,
                    "description": description or PLACEHOLDER,
                    "aliases": aliases,
                    "file": path.name,
                    "permissions": permissions,
                    "permission_labels": permission_labels,
                    "options": options,
                    "option_count": len(options),
                    "search": search_terms,
                }
            )

    slash_roots = {item["command"] for item in catalog if item["kind"] in {"slash", "hybrid", "hybrid_group"}}
    for item in catalog:
        item["slash_enabled"] = item["kind"] in {"slash", "hybrid", "hybrid_group"} or (
            item["kind"] == "subcommand" and item["group"] in slash_roots
        )

    catalog = sorted(catalog, key=lambda item: (item["category"], item["full_name"]))
    _CATALOG_CACHE[cache_key] = (snapshot, catalog)
    return catalog


def _catalog_snapshot(cogs_dir: Path) -> tuple[tuple[str, int, int], ...]:
    snapshot: list[tuple[str, int, int]] = []
    for path in sorted(cogs_dir.glob("*.py")):
        if path.name.endswith((".bak", ".trim.bak", ".bak.py", ".trim.py")):
            continue
        stat = path.stat()
        snapshot.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(snapshot)


def collect_autocomplete_targets(tree: ast.AST) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            meta = parse_autocomplete_decorator(decorator)
            if not meta:
                continue
            targets.setdefault(meta["target"], set()).add(meta["option"])
    return targets


def parse_command_decorator(decorator) -> Optional[dict]:
    if not isinstance(decorator, ast.Call):
        return None

    func = decorator.func
    func_name = decorator_name(func)
    group = None
    kind = "prefix"
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        owner = func.value.id
        if owner not in {"commands", "app_commands"} and func.attr == "command":
            group = owner

    supported = {
        "commands.command": "prefix",
        "commands.hybrid_command": "hybrid",
        "commands.hybrid_group": "hybrid_group",
        "app_commands.command": "slash",
    }
    if func_name in supported:
        kind = supported[func_name]
    elif func_name.endswith(".command"):
        kind = "subcommand"
    else:
        return None

    name = None
    description = None
    aliases = []
    for kw in decorator.keywords:
        if kw.arg == "name":
            name = literal_value(kw.value)
        elif kw.arg == "description":
            description = literal_value(kw.value)
        elif kw.arg == "aliases":
            aliases = literal_value(kw.value) or []

    return {"name": name, "description": description, "aliases": aliases, "kind": kind, "group": group}


def parse_autocomplete_decorator(decorator) -> Optional[dict]:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "autocomplete":
        return None
    if not isinstance(decorator.func.value, ast.Name):
        return None
    option = literal_value(decorator.args[0]) if decorator.args else None
    if not option:
        return None
    return {"target": decorator.func.value.id, "option": str(option)}


def extract_command_options(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    full_name: str,
    autocomplete_names: set[str],
) -> list[dict]:
    described = parse_describe_decorators(node.decorator_list)
    options = []
    for arg_name, annotation, default in iter_command_parameters(node):
        if arg_name in {"self", "ctx", "interaction"}:
            continue

        option_type, annotation_text, choices = annotation_details(annotation, arg_name)
        required = default is MISSING
        default_value = literal_value(default) if default is not MISSING else None
        default_display = default_value_repr(default)
        description = option_description_for(
            full_name,
            arg_name,
            option_type,
            described.get(arg_name),
            choices,
        )
        search = " ".join(
            filter(
                None,
                [
                    arg_name,
                    humanize_identifier(arg_name),
                    option_type,
                    annotation_text,
                    description,
                    " ".join(str(choice) for choice in choices),
                    default_display,
                    "autocomplete" if arg_name in autocomplete_names else "",
                    "required" if required else "optional",
                ],
            )
        ).lower()
        options.append(
            {
                "name": arg_name,
                "label": humanize_identifier(arg_name),
                "type": option_type,
                "annotation": annotation_text,
                "description": description,
                "required": required,
                "default": default_value,
                "default_display": default_display,
                "choices": choices,
                "autocomplete": arg_name in autocomplete_names,
                "search": search,
            }
        )
    return options


def iter_command_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef):
    args = list(node.args.args)
    defaults = [MISSING] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
    for arg, default in zip(args, defaults):
        yield arg.arg, arg.annotation, default
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        yield arg.arg, arg.annotation, default if default is not None else MISSING


def parse_describe_decorators(decorators: list[ast.expr]) -> dict[str, str]:
    described: dict[str, str] = {}
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        if decorator_name(decorator.func) != "app_commands.describe":
            continue
        for keyword in decorator.keywords:
            if keyword.arg:
                value = literal_value(keyword.value)
                if isinstance(value, str) and value.strip():
                    described[keyword.arg] = value.strip()
    return described


def extract_permissions(decorators: list[ast.expr]) -> list[str]:
    permissions = []
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        if not decorator_name(decorator.func).endswith("has_permissions"):
            continue
        for keyword in decorator.keywords:
            if keyword.arg and literal_value(keyword.value):
                permissions.append(keyword.arg)
    return sorted(set(permissions))


def annotation_details(annotation, arg_name: str) -> tuple[str, str, list[str]]:
    if annotation is None:
        return inferred_type_from_name(arg_name), "", []

    optional, inner = unwrap_optional_annotation(annotation)
    if is_literal_annotation(inner):
        choices = literal_choices(inner)
        annotation_text = annotation_to_text(annotation)
        return ("choice", annotation_text + (" optional" if optional else ""), choices)

    annotation_text = annotation_to_text(annotation)
    inner_text = annotation_to_text(inner).lower()
    option_type = inferred_type_from_annotation(inner_text, arg_name)
    if optional and option_type == "text":
        return ("text", annotation_text, [])
    return (option_type, annotation_text, [])


def unwrap_optional_annotation(annotation) -> tuple[bool, ast.AST]:
    if isinstance(annotation, ast.Subscript):
        base_name = decorator_name(annotation.value)
        if base_name in {"Optional", "typing.Optional"}:
            return True, annotation.slice
        if base_name in {"Union", "typing.Union"} and isinstance(annotation.slice, ast.Tuple):
            values = [elt for elt in annotation.slice.elts if not is_none_annotation(elt)]
            if len(values) == 1 and len(values) != len(annotation.slice.elts):
                return True, values[0]
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        if is_none_annotation(annotation.left):
            return True, annotation.right
        if is_none_annotation(annotation.right):
            return True, annotation.left
    return False, annotation


def inferred_type_from_annotation(annotation_text: str, arg_name: str) -> str:
    if any(
        token in annotation_text for token in ["textchannel", "voicechannel", "forumchannel", "stagechannel", "channel"]
    ):
        return "channel"
    if annotation_text.endswith("member"):
        return "member"
    if annotation_text.endswith("user"):
        return "user"
    if annotation_text.endswith("role"):
        return "role"
    if annotation_text in {"int", "integer"}:
        return "integer"
    if annotation_text in {"float", "number"}:
        return "number"
    if annotation_text in {"bool", "boolean"}:
        return "boolean"
    if annotation_text in {"str", "string"}:
        return inferred_type_from_name(arg_name)
    return inferred_type_from_name(arg_name)


def inferred_type_from_name(arg_name: str) -> str:
    normalized = (arg_name or "").lower()
    if normalized in {"message_ref", "message_link", "message_url", "jump_url"}:
        return "message"
    if normalized.endswith("_id") or normalized == "id":
        return "id"
    if "channel" in normalized or normalized == "target":
        return "channel"
    if "member" in normalized:
        return "member"
    if "role" in normalized or normalized == "ping":
        return "role"
    if normalized in {"count", "amount", "threshold", "seconds", "minutes_before", "days"}:
        return "integer"
    if normalized in {"duration", "when"}:
        return "duration"
    return "text"


def is_literal_annotation(annotation) -> bool:
    if not isinstance(annotation, ast.Subscript):
        return False
    return decorator_name(annotation.value) in {"Literal", "typing.Literal"}


def literal_choices(annotation) -> list[str]:
    slice_node = annotation.slice
    values = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
    choices = []
    for value in values:
        literal = literal_value(value)
        if literal is not None:
            choices.append(str(literal))
    return choices


def is_none_annotation(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def annotation_to_text(annotation) -> str:
    try:
        return ast.unparse(annotation)
    except Exception:
        return ""


def first_docstring_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    doc = (ast.get_docstring(node) or "").strip().splitlines()
    return doc[0].strip() if doc else ""


def default_value_repr(node) -> str:
    if node is MISSING:
        return ""
    value = literal_value(node)
    if value is None:
        return "None"
    if isinstance(value, str):
        return value
    return str(value)


def decorator_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = decorator_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def literal_value(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None
