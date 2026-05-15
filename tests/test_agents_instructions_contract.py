from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"

REQUIRED_PHRASES = [
    "Use Context7 first when available",
    "Conventional Commits",
    "Never commit secrets",
    "PEP 8",
    "PEP 257",
    "strict TypeScript",
    "Discord API",
    "gofmt",
    "Rust API Guidelines",
    "PSR-12",
    "WCAG 2.2",
    "Dockerfile best practices",
    "readiness/liveness/startup probes",
    "Camelot-style memory entries",
]

REQUIRED_SOURCES = [
    "https://peps.python.org/pep-0008/",
    "https://peps.python.org/pep-0257/",
    "https://www.conventionalcommits.org/en/v1.0.0/",
    "https://google.github.io/styleguide/",
    "https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/coding-style/coding-conventions",
    "https://go.dev/doc/effective_go",
    "https://go.dev/wiki/CodeReviewComments",
    "https://rust-lang.github.io/api-guidelines/",
    "https://www.php-fig.org/psr/psr-12/",
    "https://kotlinlang.org/docs/coding-conventions.html",
    "https://www.swift.org/documentation/api-design-guidelines/",
    "https://www.w3.org/TR/wcag/",
    "https://docs.docker.com/engine/userguide/eng-image/dockerfile_best-practices/",
    "https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/",
]


def test_agents_instructions_exist() -> None:
    assert AGENTS.is_file()


def test_agents_instructions_keep_required_standards() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    assert not missing, f"AGENTS.md is missing required guidance: {missing}"


def test_agents_instructions_keep_primary_sources() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    missing = [source for source in REQUIRED_SOURCES if source not in text]
    assert not missing, f"AGENTS.md is missing source anchors: {missing}"


if __name__ == "__main__":
    test_agents_instructions_exist()
    test_agents_instructions_keep_required_standards()
    test_agents_instructions_keep_primary_sources()
    print("AGENTS instruction contract passed")
