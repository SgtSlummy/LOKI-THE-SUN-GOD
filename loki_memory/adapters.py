from __future__ import annotations

from dataclasses import dataclass

CODEX_AGI_ROOT = "/mnt/c/Codex AGI"


@dataclass(frozen=True)
class CodexAgiAdapter:
    key: str
    label: str
    source_path: str
    mode: str
    purpose: str


def available_adapters() -> list[CodexAgiAdapter]:
    return [
        CodexAgiAdapter(
            key="noophyte",
            label="NOO / Noophyte",
            source_path=f"{CODEX_AGI_ROOT}/noophyte",
            mode="advisory",
            purpose="Absence-trace and community-interest hypothesis generation.",
        ),
        CodexAgiAdapter(
            key="quantum_roots",
            label="Quantum Roots",
            source_path=f"{CODEX_AGI_ROOT}/quantum_roots",
            mode="advisory",
            purpose="Confidence decay, corroboration, contradiction, and source-health checks.",
        ),
        CodexAgiAdapter(
            key="swarm_brain",
            label="Swarm Brain",
            source_path=f"{CODEX_AGI_ROOT}/digital_brain",
            mode="advisory",
            purpose="Planner, critic, verifier, memory, and risk specialist loop.",
        ),
        CodexAgiAdapter(
            key="slime_god",
            label="SLIME GOD",
            source_path=f"{CODEX_AGI_ROOT}/micro_projects/slime_god",
            mode="advisory",
            purpose="Memory/control graph and Mythos bridge adapter.",
        ),
        CodexAgiAdapter(
            key="camelot",
            label="Camelot / MemPalace",
            source_path=f"{CODEX_AGI_ROOT}/Camelot",
            mode="advisory",
            purpose="Local-first project memory and capture workspace.",
        ),
    ]
