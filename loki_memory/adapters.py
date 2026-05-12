from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

CODEX_AGI_ROOT = "C:/Codex AGI"
_DISCOVER_COLLECTIONS = ("micro_projects", "skills", "sources")
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".venv", "venv"}


@dataclass(frozen=True)
class CodexAgiAdapter:
    key: str
    label: str
    source_path: str
    mode: str
    purpose: str


@dataclass(frozen=True)
class _CuratedAdapter:
    key: str
    label: str
    relative_path: str
    purpose: str


_CURATED_ADAPTERS = (
    _CuratedAdapter(
        key="noophyte",
        label="NOO / Noophyte",
        relative_path="noophyte",
        purpose="Absence-trace and community-interest hypothesis generation.",
    ),
    _CuratedAdapter(
        key="quantum_roots",
        label="Quantum Roots",
        relative_path="quantum_roots",
        purpose="Confidence decay, corroboration, contradiction, and source-health checks.",
    ),
    _CuratedAdapter(
        key="swarm_brain",
        label="Swarm Brain",
        relative_path="digital_brain",
        purpose="Planner, critic, verifier, memory, and risk specialist loop.",
    ),
    _CuratedAdapter(
        key="cosmicos",
        label="CosmicOS",
        relative_path="cosmicos_codex_export",
        purpose=(
            "CosmicOS prototype export for governance, runtime contracts, observability, "
            "and Codex handoff context."
        ),
    ),
    _CuratedAdapter(
        key="superagi",
        label="SuperAGI",
        relative_path="SuperAGI",
        purpose="Autonomous-agent framework context for agent orchestration and tool execution patterns.",
    ),
    _CuratedAdapter(
        key="openmythos",
        label="OpenMythos",
        relative_path="OpenMythos",
        purpose=(
            "Open-source theoretical Claude Mythos implementation with a Recurrent-Depth Transformer, "
            "switchable MLA/GQA attention, and sparse MoE experiments."
        ),
    ),
    _CuratedAdapter(
        key="slime_god",
        label="SLIME GOD",
        relative_path="micro_projects/slime_god",
        purpose="Memory/control graph and Mythos bridge adapter.",
    ),
    _CuratedAdapter(
        key="camelot",
        label="Camelot / MemPalace",
        relative_path="Camelot",
        purpose="Local-first project memory and capture workspace.",
    ),
)


def _default_root() -> Path:
    return Path(os.environ.get("LOKI_CODEX_AGI_ROOT", CODEX_AGI_ROOT))


def _adapter_path(path: Path) -> str:
    return path.as_posix()


def _key_for_relative_path(relative_path: Path) -> str:
    raw = "_".join(relative_path.parts)
    key = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    return key or "codex_agi_project"


def _title_from_readme(project_path: Path) -> str | None:
    readme = project_path / "README.md"
    if not readme.exists():
        return None
    for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip().strip("#").strip()
        if not text or text.startswith("<") or "<" in text or ">" in text:
            continue
        return text[:80]
    return None


def _directory_label(name: str) -> str:
    cleaned = name.replace("_", " ").replace("-", " ").strip()
    if any(char.isupper() for char in cleaned):
        return cleaned
    return cleaned.title()


def _label_for_path(relative_path: Path, project_path: Path) -> str:
    return _title_from_readme(project_path) or _directory_label(relative_path.name)


def _discovered_project_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []

    paths: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name in _SKIP_DIRS:
            continue
        if child.name in _DISCOVER_COLLECTIONS:
            for nested in sorted(child.iterdir(), key=lambda item: item.name.lower()):
                if nested.is_dir() and nested.name not in _SKIP_DIRS:
                    paths.append(nested.relative_to(root))
            continue
        paths.append(child.relative_to(root))
    return paths


def _curated_adapter(root: Path, spec: _CuratedAdapter) -> CodexAgiAdapter:
    return CodexAgiAdapter(
        key=spec.key,
        label=spec.label,
        source_path=_adapter_path(root / spec.relative_path),
        mode="advisory",
        purpose=spec.purpose,
    )


def available_adapters(root: str | Path | None = None) -> list[CodexAgiAdapter]:
    codex_root = Path(root) if root is not None else _default_root()

    adapters_by_path: dict[str, CodexAgiAdapter] = {}
    for spec in _CURATED_ADAPTERS:
        adapters_by_path[Path(spec.relative_path).as_posix().lower()] = _curated_adapter(codex_root, spec)

    for relative_path in _discovered_project_paths(codex_root):
        path_key = relative_path.as_posix().lower()
        if path_key in adapters_by_path:
            continue
        project_path = codex_root / relative_path
        key = _key_for_relative_path(relative_path)
        adapters_by_path[path_key] = CodexAgiAdapter(
            key=key,
            label=_label_for_path(relative_path, project_path),
            source_path=_adapter_path(project_path),
            mode="advisory",
            purpose="Discovered Codex AGI project adapter for read-only context, planning, and auditable handoff.",
        )

    return sorted(adapters_by_path.values(), key=lambda adapter: adapter.label.lower())
