from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_SOURCE = ROOT / "services" / "activity-bridge" / "shared" / "src" / "index.ts"
ROOM_ROUTES_SOURCE = ROOT / "services" / "activity-bridge" / "server" / "src" / "routes" / "rooms.ts"
SNAPSHOT = ROOT / "docs" / "schemas" / "activity-bridge-payload-snapshot.json"


def test_activity_bridge_payload_snapshot_matches_shared_types() -> None:
    snapshot = _read_snapshot()
    shared_source = SHARED_SOURCE.read_text(encoding="utf-8")

    assert _literal_union("PlaybackStatus", shared_source) == snapshot["playback_statuses"]
    assert _type_fields("QueueItem", shared_source) == snapshot["queue_item_fields"]
    assert _type_fields("RoomState", shared_source) == snapshot["room_state_fields"]
    assert _message_types("ServerToClientMessage", "ClientToServerMessage", shared_source) == snapshot[
        "server_to_client_message_types"
    ]
    assert _message_types("ClientToServerMessage", "CommandResult", shared_source) == snapshot[
        "client_to_server_message_types"
    ]


def test_activity_bridge_payload_snapshot_matches_control_actions() -> None:
    snapshot = _read_snapshot()
    routes_source = ROOM_ROUTES_SOURCE.read_text(encoding="utf-8")

    assert re.findall(r'body\.action === "([^"]+)"', routes_source) == snapshot["http_control_actions"]


def test_activity_bridge_payload_snapshot_references_existing_sources() -> None:
    snapshot = _read_snapshot()

    for rel_path in snapshot["source_files"]:
        assert (ROOT / rel_path).is_file(), f"{rel_path} should exist"


def _read_snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _literal_union(type_name: str, source: str) -> list[str]:
    match = re.search(rf"export type {type_name} = (?P<body>[^;]+);", source)
    assert match, f"Missing type alias {type_name}"
    return re.findall(r'"([^"]+)"', match.group("body"))


def _message_types(type_name: str, next_type_name: str, source: str) -> list[str]:
    block = _source_between(source, f"export type {type_name} =", f"export type {next_type_name}")
    return re.findall(r'type: "([^"]+)"', block)


def _type_fields(type_name: str, source: str) -> list[str]:
    block = _type_block(type_name, source)
    fields: list[str] = []
    depth = 0

    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if depth == 0:
            match = re.match(r"([A-Za-z][A-Za-z0-9]*)(?:\?)?:", line)
            if match:
                fields.append(match.group(1))
        depth += line.count("{") - line.count("}")

    return fields


def _type_block(type_name: str, source: str) -> str:
    marker = f"export type {type_name} = {{"
    start_index = source.find(marker)
    assert start_index >= 0, f"Missing type alias {type_name}"
    body_start = start_index + len(marker)
    depth = 1
    index = body_start

    while index < len(source):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:index]
        index += 1

    raise AssertionError(f"Missing closing brace for {type_name}")


def _source_between(source: str, start: str, end: str) -> str:
    start_index = source.find(start)
    assert start_index >= 0, f"Missing start marker {start!r}"
    body_start = start_index + len(start)
    end_index = source.find(end, body_start)
    assert end_index >= 0, f"Missing end marker {end!r}"
    return source[body_start:end_index]


if __name__ == "__main__":
    test_activity_bridge_payload_snapshot_matches_shared_types()
    test_activity_bridge_payload_snapshot_matches_control_actions()
    test_activity_bridge_payload_snapshot_references_existing_sources()
    print("activity bridge payload snapshot passed")
