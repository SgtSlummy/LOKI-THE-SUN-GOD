from __future__ import annotations

from pathlib import Path

from loki_memory.adapters import available_adapters


def _project(root: Path, relative: str, title: str) -> None:
    project = root.joinpath(*relative.split("/"))
    project.mkdir(parents=True)
    project.joinpath("README.md").write_text(f"# {title}\n\nProject notes.\n", encoding="utf-8")


def test_available_adapters_discovers_other_codex_agi_projects(tmp_path: Path):
    _project(tmp_path, "SuperAGI", "SuperAGI")
    _project(tmp_path, "temporal", "Temporal")
    _project(tmp_path, "world_codex", "World Codex")
    _project(tmp_path, "cosmicos_codex_export", "CosmicOS")
    _project(tmp_path, "OpenMythos", "OpenMythos")
    _project(tmp_path, "skills/obliteratus", "Obliteratus")
    _project(tmp_path, "sources/swarm-brain-research", "Swarm Brain Research")

    adapters = {adapter.key: adapter for adapter in available_adapters(root=tmp_path)}

    assert {
        "superagi",
        "temporal",
        "world_codex",
        "cosmicos",
        "openmythos",
        "skills_obliteratus",
        "sources_swarm_brain_research",
    }.issubset(adapters)
    assert adapters["superagi"].label == "SuperAGI"
    assert adapters["cosmicos"].label == "CosmicOS"
    assert adapters["cosmicos"].source_path.endswith("cosmicos_codex_export")
    assert adapters["openmythos"].label == "OpenMythos"
    assert adapters["openmythos"].source_path.endswith("OpenMythos")
    assert "Recurrent-Depth Transformer" in adapters["openmythos"].purpose
    assert adapters["skills_obliteratus"].source_path.endswith("skills/obliteratus")
    assert all(adapter.mode == "advisory" for adapter in adapters.values())


def test_available_adapters_uses_directory_name_when_readme_starts_with_html(tmp_path: Path):
    project = tmp_path / "SuperAGI"
    project.mkdir()
    project.joinpath("README.md").write_text('<p align="center">\n  <a href="x" target="blank">\n', encoding="utf-8")

    adapters = {adapter.key: adapter for adapter in available_adapters(root=tmp_path)}

    assert adapters["superagi"].label == "SuperAGI"


def test_available_adapters_keeps_hand_curated_labels_for_core_projects(tmp_path: Path):
    _project(tmp_path, "noophyte", "Noophyte")
    _project(tmp_path, "quantum_roots", "Quantum Roots")
    _project(tmp_path, "digital_brain", "Digital Brain")
    _project(tmp_path, "micro_projects/slime_god", "SLIME GOD")
    _project(tmp_path, "Camelot", "Camelot")

    adapters = {adapter.key: adapter for adapter in available_adapters(root=tmp_path)}

    assert adapters["noophyte"].label == "NOO / Noophyte"
    assert adapters["quantum_roots"].purpose.startswith("Confidence decay")
    assert adapters["swarm_brain"].source_path.endswith("digital_brain")
    assert adapters["slime_god"].source_path.endswith("micro_projects/slime_god")
    assert adapters["camelot"].label == "Camelot / MemPalace"
