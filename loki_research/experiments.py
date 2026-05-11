from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from loki_npc.memory import redact_discord_content
from utils import db

BLOCKED_TARGET_GLOBS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "data/**",
    ".git/**",
    ".venv/**",
    "__pycache__/**",
    "bot.py",
    "dashboard_app.py",
    "cogs/**",
)


@dataclass(frozen=True)
class ExperimentConfig:
    enabled: bool = False
    dry_run: bool = True
    lab_root: Path = Path(".loki_lab")
    sandbox_path: Path = Path(".loki_lab/current")
    max_iterations: int = 100
    max_candidates_per_run: int = 10
    max_patch_bytes: int = 50_000
    max_files_changed: int = 8
    max_runtime_seconds: int = 600
    allowed_target_globs: tuple[str, ...] = ("docs/**", "tests/**", "loki_research/**", "loki_npc/**")
    blocked_target_globs: tuple[str, ...] = BLOCKED_TARGET_GLOBS
    allowed_commands: tuple[str, ...] = ("python -m pytest", "python -m ruff check", "python scripts/secret_scan.py")


@dataclass(frozen=True)
class ExperimentDecision:
    ok: bool
    reason: str


@dataclass(frozen=True)
class MutationCandidate:
    candidate_id: str
    title: str
    target_paths: tuple[str, ...]
    patch_bytes: int
    safety_status: str
    source_confidence: float
    rollback_plan: str
    verification_commands: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CandidateScore:
    accepted: bool
    score: float
    reasons: tuple[str, ...]


def assert_safe_experiment_config(config: ExperimentConfig) -> ExperimentDecision:
    if not config.enabled:
        return ExperimentDecision(False, "Experiment harness is disabled.")
    if not config.dry_run:
        return ExperimentDecision(False, "Only dry-run experiments are allowed in this build.")
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("LOKI_EXPERIMENT_ENV", "").lower() == "production":
        return ExperimentDecision(False, "Experiments are blocked in production environments.")
    if config.max_iterations < 1 or config.max_iterations > 1000:
        return ExperimentDecision(False, "max_iterations must be between 1 and 1000.")
    if config.max_candidates_per_run < 1 or config.max_candidates_per_run > 50:
        return ExperimentDecision(False, "max_candidates_per_run must be between 1 and 50.")
    if config.max_patch_bytes <= 0 or config.max_patch_bytes > 500_000:
        return ExperimentDecision(False, "max_patch_bytes is outside the bounded lab range.")

    lab_root = config.lab_root.resolve()
    sandbox_path = config.sandbox_path.resolve()
    if lab_root == sandbox_path:
        return ExperimentDecision(False, "Sandbox path must be a child of the lab root, not the root itself.")
    try:
        sandbox_path.relative_to(lab_root)
    except ValueError:
        return ExperimentDecision(False, "Sandbox path must stay inside the configured lab root.")
    return ExperimentDecision(True, "Experiment config is bounded to a dry-run lab.")


def score_mutation_candidate(config: ExperimentConfig, candidate: MutationCandidate) -> CandidateScore:
    reasons: list[str] = []
    if candidate.safety_status not in {"pending_review", "approved_for_lab"}:
        reasons.append("candidate safety status is not reviewable")
    if not candidate.rollback_plan.strip():
        reasons.append("rollback plan is required")
    if candidate.patch_bytes <= 0 or candidate.patch_bytes > config.max_patch_bytes:
        reasons.append("patch size exceeds configured bound")
    if len(candidate.target_paths) > config.max_files_changed:
        reasons.append("too many target files")
    if candidate.source_confidence < 0.5:
        reasons.append("source confidence is too low")

    for path in candidate.target_paths:
        normalized = path.replace("\\", "/").lstrip("/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in config.blocked_target_globs):
            reasons.append(f"blocked target path: {normalized}")
        if config.allowed_target_globs and not any(
            fnmatch.fnmatch(normalized, pattern) for pattern in config.allowed_target_globs
        ):
            reasons.append(f"target path outside allowlist: {normalized}")

    command_score = 0.1 if candidate.verification_commands else 0.0
    rollback_score = 0.2 if candidate.rollback_plan.strip() else 0.0
    confidence_score = min(0.4, max(0.0, candidate.source_confidence) * 0.4)
    size_score = 0.2 if 0 < candidate.patch_bytes <= config.max_patch_bytes else 0.0
    path_score = 0.1 if not reasons else 0.0
    score = round(confidence_score + rollback_score + size_score + command_score + path_score, 3)
    return CandidateScore(accepted=not reasons and score >= 0.7, score=score, reasons=tuple(reasons))


def append_experiment_audit(
    *,
    run_id: str,
    candidate_id: str = "",
    event_type: str,
    details: str = "",
    created_at: int | None = None,
) -> None:
    db.sync_exec(
        """
        INSERT INTO loki_experiment_audit(run_id, candidate_id, event_type, details, created_at)
        VALUES(?,?,?,?,?)
        """,
        (
            run_id[:120],
            candidate_id[:120],
            event_type[:80],
            redact_discord_content(details)[:4000],
            int(created_at or time.time()),
        ),
    )
