from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.form_ids import (  # noqa: E402
    DISCORD_CUSTOM_ID_MAX_LENGTH,
    MAX_DISCORD_SNOWFLAKE_DIGITS,
    MAX_FORM_NAME_LENGTH,
)

SNAPSHOT_PATH = ROOT / "docs" / "schemas" / "discord-component-custom-id-snapshot.json"


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return ""


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _literal_or_pattern(node: ast.AST | None) -> tuple[str, bool]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, False
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{" + ast.unparse(value.value) + "}")
            else:
                raise AssertionError(f"Unsupported f-string part: {ast.dump(value)}")
        return "".join(parts), True
    if isinstance(node, ast.Call) and _dotted_name(node.func) == "form_custom_id":
        if len(node.args) != 2:
            raise AssertionError(f"Unexpected form_custom_id call: {ast.dump(node)}")
        return f"form::{{{ast.unparse(node.args[0])}}}::{{{ast.unparse(node.args[1])}}}", True
    raise AssertionError(f"Expected string literal or f-string, got {ast.dump(node)}")


def _display_value(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _literal_or_pattern(node)[0]
    if node is not None:
        return ast.unparse(node)
    return ""


def _is_view_class(node: ast.ClassDef) -> bool:
    return any(_dotted_name(base).endswith(("discord.ui.View", "ui.View", "View")) for base in node.bases)


def _class_uses_persistent_timeout(node: ast.ClassDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _dotted_name(child.func) != "super.__init__":
            continue
        timeout = _keyword(child, "timeout")
        if isinstance(timeout, ast.Constant) and timeout.value is None:
            return True
    return False


def _button_decorator(function: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Call) and _dotted_name(decorator.func).endswith(
            ("discord.ui.button", "ui.button")
        ):
            return decorator
    return None


def _button_constructor_calls(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for child in ast.walk(function):
        if not isinstance(child, ast.Call):
            continue
        if _dotted_name(child.func).endswith(("discord.ui.Button", "ui.Button")) and _keyword(child, "custom_id"):
            calls.append(child)
    return calls


def _discover_components() -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for source_path in sorted((ROOT / "cogs").glob("*.py")):
        rel_path = source_path.relative_to(ROOT).as_posix()
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef) and _is_view_class(node)]:
            persistent = _class_uses_persistent_timeout(class_node)
            for item in class_node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                decorator = _button_decorator(item)
                if decorator is not None:
                    custom_id, dynamic = _literal_or_pattern(_keyword(decorator, "custom_id"))
                    label = _display_value(_keyword(decorator, "label"))
                    components.append(
                        {
                            "custom_id": custom_id,
                            "dynamic": dynamic,
                            "kind": "button_decorator",
                            "label": label,
                            "source": rel_path,
                            "view": class_node.name,
                            "callback": item.name,
                            "persistent_view": persistent,
                        }
                    )
                for call in _button_constructor_calls(item):
                    custom_id, dynamic = _literal_or_pattern(_keyword(call, "custom_id"))
                    label = _display_value(_keyword(call, "label"))
                    components.append(
                        {
                            "custom_id": custom_id,
                            "dynamic": dynamic,
                            "kind": "button_constructor",
                            "label": label,
                            "source": rel_path,
                            "view": class_node.name,
                            "callback": item.name,
                            "persistent_view": persistent,
                        }
                    )
    return components


def _contract_hash(components: list[dict[str, object]]) -> str:
    payload = json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_discord_component_custom_id_snapshot_matches_static_registry() -> None:
    snapshot = _snapshot()
    discovered = _discover_components()
    expected_totals = dict(Counter(component["kind"] for component in discovered))
    expected_totals["total"] = len(discovered)
    expected_totals["dynamic"] = sum(1 for component in discovered if component["dynamic"])
    expected_totals["persistent_view"] = sum(1 for component in discovered if component["persistent_view"])

    assert discovered == snapshot["components"]
    assert expected_totals == snapshot["expected_totals"]
    assert len({component["custom_id"] for component in discovered}) == len(discovered)
    assert all(component["persistent_view"] for component in discovered)
    assert all(len(str(component["custom_id"])) <= 100 for component in discovered if not component["dynamic"])
    assert snapshot["dynamic_constraints"]["form::{guild_id}::{form_name}"] == {
        "max_custom_id_length": DISCORD_CUSTOM_ID_MAX_LENGTH,
        "max_snowflake_digits": MAX_DISCORD_SNOWFLAKE_DIGITS,
        "max_form_name_length": MAX_FORM_NAME_LENGTH,
    }
    assert snapshot["component_custom_id_contract_hash_alg"] == "sha256"
    assert _contract_hash(discovered) == snapshot["component_custom_id_contract_hash"]


if __name__ == "__main__":
    test_discord_component_custom_id_snapshot_matches_static_registry()
    print("discord component custom_id snapshot passed")
