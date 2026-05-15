from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMPONENT_SNAPSHOT_PATH = ROOT / "docs" / "schemas" / "discord-component-custom-id-snapshot.json"
REGISTRATION_SNAPSHOT_PATH = ROOT / "docs" / "schemas" / "discord-persistent-view-registration-snapshot.json"


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return ""


def _is_bot_add_view(call: ast.Call) -> bool:
    return _dotted_name(call.func).endswith(".bot.add_view")


def _registered_view_name(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first_arg = call.args[0]
    if isinstance(first_arg, ast.Call):
        return _dotted_name(first_arg.func)
    return None


def _assigned_view_names(method: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for node in ast.walk(method):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if isinstance(node.value, ast.Call):
            assignments[node.targets[0].id] = _dotted_name(node.value.func)
    return assignments


def _persistent_component_views() -> set[tuple[str, str]]:
    snapshot = json.loads(COMPONENT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {
        (str(component["source"]), str(component["view"]))
        for component in snapshot["components"]
        if component["persistent_view"]
    }


def _discover_startup_registrations() -> list[dict[str, str]]:
    persistent_views = _persistent_component_views()
    registrations: list[dict[str, str]] = []
    for source_path in sorted({ROOT / source for source, _view in persistent_views}):
        rel_path = source_path.relative_to(ROOT).as_posix()
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            for method in [
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]:
                if method.name not in {"__init__", "cog_load"}:
                    continue
                for call in [node for node in ast.walk(method) if isinstance(node, ast.Call)]:
                    if not _is_bot_add_view(call):
                        continue
                    view_name = _registered_view_name(call)
                    if view_name and (rel_path, view_name) in persistent_views:
                        registrations.append(
                            {
                                "cog": class_node.name,
                                "method": method.name,
                                "source": rel_path,
                                "view": view_name,
                            }
                        )
    return sorted(
        registrations,
        key=lambda item: (item["source"], item["cog"], item["method"], item["view"]),
    )


def _discover_runtime_panel_registrations() -> list[dict[str, str]]:
    persistent_views = _persistent_component_views()
    registrations: list[dict[str, str]] = []
    for source_path in sorted({ROOT / source for source, _view in persistent_views}):
        rel_path = source_path.relative_to(ROOT).as_posix()
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            for method in [
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]:
                if method.name in {"__init__", "cog_load"}:
                    continue
                assigned_views = _assigned_view_names(method)
                for call in [node for node in ast.walk(method) if isinstance(node, ast.Call)]:
                    if not _is_bot_add_view(call) or not call.args:
                        continue
                    first_arg = call.args[0]
                    view_name = (
                        assigned_views.get(first_arg.id)
                        if isinstance(first_arg, ast.Name)
                        else _registered_view_name(call)
                    )
                    if view_name and (rel_path, view_name) in persistent_views:
                        registrations.append(
                            {
                                "cog": class_node.name,
                                "method": method.name,
                                "source": rel_path,
                                "view": view_name,
                            }
                        )
    return sorted(
        registrations,
        key=lambda item: (item["source"], item["cog"], item["method"], item["view"]),
    )


def _contract_hash(registrations: list[dict[str, str]]) -> str:
    payload = json.dumps(registrations, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _snapshot() -> dict:
    return json.loads(REGISTRATION_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_discord_persistent_view_registration_snapshot_matches_startup_paths() -> None:
    snapshot = _snapshot()
    registrations = _discover_startup_registrations()
    runtime_registrations = _discover_runtime_panel_registrations()
    persistent_views = _persistent_component_views()

    assert registrations == snapshot["registrations"]
    assert runtime_registrations == snapshot["runtime_panel_registrations"]
    assert {(item["source"], item["view"]) for item in registrations} == persistent_views
    assert snapshot["expected_totals"] == {
        "persistent_view_classes": len(persistent_views),
        "startup_registrations": len(registrations),
        "cog_load_registrations": sum(1 for item in registrations if item["method"] == "cog_load"),
        "constructor_registrations": sum(1 for item in registrations if item["method"] == "__init__"),
        "runtime_panel_registrations": len(runtime_registrations),
    }
    assert snapshot["registration_contract_hash_alg"] == "sha256"
    assert _contract_hash(registrations) == snapshot["registration_contract_hash"]


if __name__ == "__main__":
    test_discord_persistent_view_registration_snapshot_matches_startup_paths()
    print("discord persistent view registration snapshot passed")
