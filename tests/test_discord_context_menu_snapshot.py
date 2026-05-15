from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "docs" / "schemas" / "discord-context-menu-snapshot.json"


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _string_literal(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise AssertionError(f"Expected string literal, got {ast.dump(node)}")


def _callback_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    raise AssertionError(f"Expected callback reference, got {ast.dump(node)}")


def _annotation_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    return _dotted_name(node) or ast.unparse(node)


def _target_type(annotation: str) -> str:
    if annotation.endswith(("discord.Member", "discord.User", "Member", "User")):
        return "user"
    if annotation.endswith(("discord.Message", "Message")):
        return "message"
    return ""


def _callback_targets(tree: ast.AST) -> dict[str, str]:
    targets: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        positional = list(node.args.posonlyargs) + list(node.args.args)
        target_index = 2 if positional and positional[0].arg == "self" else 1
        if len(positional) <= target_index:
            continue
        annotation = _annotation_name(positional[target_index].annotation)
        target_type = _target_type(annotation)
        if target_type:
            targets[node.name] = target_type
    return targets


def _discover_context_menus() -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for rel_path in ("cogs/context_menus.py", "cogs/translate.py"):
        source_path = ROOT / rel_path
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        targets = _callback_targets(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _dotted_name(node.func) not in {"app_commands.ContextMenu", "discord.app_commands.ContextMenu"}:
                continue
            name = _string_literal(_keyword(node, "name"))
            callback = _callback_name(_keyword(node, "callback"))
            commands.append(
                {
                    "name": name,
                    "type": targets[callback],
                    "callback": callback,
                    "source": rel_path,
                }
            )
    return commands


def _contract_hash(commands: list[dict[str, str]]) -> str:
    payload = json.dumps(commands, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_discord_context_menu_snapshot_matches_static_registry() -> None:
    snapshot = _snapshot()
    discovered = _discover_context_menus()
    expected_totals = dict(Counter(command["type"] for command in discovered))
    expected_totals["total"] = len(discovered)

    assert discovered == snapshot["commands"]
    assert expected_totals == snapshot["expected_totals"]
    assert len({(command["type"], command["name"]) for command in discovered}) == len(discovered)
    assert snapshot["context_menu_contract_hash_alg"] == "sha256"
    assert _contract_hash(discovered) == snapshot["context_menu_contract_hash"]


if __name__ == "__main__":
    test_discord_context_menu_snapshot_matches_static_registry()
    print("discord context menu snapshot passed")
