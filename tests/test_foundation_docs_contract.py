from pathlib import Path

FOUNDATION_DOCS = [
    Path("docs/upgrades/10-sector-upgrade-plan.md"),
    Path("docs/architecture/mythos-swarm-architecture.md"),
    Path("docs/QUALITY_GATES.md"),
    Path("docs/rollback/reset-and-restore-plan.md"),
]

REQUIRED_TERMS = [
    "natural-language",
    "admin",
    "Lavalink",
    "Hermes",
    "rollback",
    "approval",
]


def test_foundation_docs_preserve_autonomous_upgrade_invariants():
    missing = []

    for doc_path in FOUNDATION_DOCS:
        text = doc_path.read_text(encoding="utf-8").lower()
        for term in REQUIRED_TERMS:
            if term.lower() not in text:
                missing.append(f"{doc_path}: {term}")

    assert not missing, "Missing foundation contract terms:\n" + "\n".join(missing)
