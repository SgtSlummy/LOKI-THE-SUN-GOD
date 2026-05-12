from __future__ import annotations

import json

from utils import operator_surface


def test_external_legacy_library_search_reads_indexes_outside_loki(tmp_path, monkeypatch):
    root = tmp_path / "loki-libraries"
    library = root / "ralph-wiggum-legacy"
    docs = library / "docs"
    docs.mkdir(parents=True)
    (docs / "legacy_capabilities.md").write_text(
        "# Ralph Wiggum legacy library\nAutomod and tickets.\n",
        encoding="utf-8",
    )
    (library / "ralph_wiggum_legacy_library.json").write_text(
        json.dumps(
            {
                "library": "ralph-wiggum-legacy",
                "source_root": "C:/Ralph Wiggum",
                "purpose": "External legacy reference for LOKI.",
                "generated_at": "2026-05-12T00:00:00+00:00",
                "overview": {
                    "command_count": 263,
                    "file_count": 909,
                    "components": ["discord.py bot", "Flask dashboard"],
                    "command_categories": {"Automod": 12, "Tickets": 8},
                },
                "commands": [{"command": "ticket", "description": "Create tickets"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOKI_EXTERNAL_LIBRARY_ROOT", str(root))
    monkeypatch.delenv("LOKI_EXTERNAL_LIBRARY_PATHS", raising=False)

    libraries = operator_surface.search_external_legacy_libraries("ticket")

    assert len(libraries) == 1
    assert libraries[0]["library"] == "ralph-wiggum-legacy"
    assert libraries[0]["command_count"] == 263
    assert "content" not in libraries[0]


def test_ai_doc_library_includes_external_legacy_markdown(tmp_path, monkeypatch):
    root = tmp_path / "loki-libraries"
    library = root / "ralph-wiggum-legacy"
    docs = library / "docs"
    docs.mkdir(parents=True)
    (docs / "legacy_capabilities.md").write_text(
        "# Ralph Wiggum legacy library\nTickets continue here.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LOKI_EXTERNAL_LIBRARY_ROOT", str(root))
    monkeypatch.delenv("LOKI_EXTERNAL_LIBRARY_PATHS", raising=False)

    matches = operator_surface.search_ai_docs("Ralph Wiggum", include_content=True)

    assert any(match["file"] == "ralph-wiggum-legacy/docs/legacy_capabilities.md" for match in matches)
    assert any("Tickets continue here" in match.get("content", "") for match in matches)
