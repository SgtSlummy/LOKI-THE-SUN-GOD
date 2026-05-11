from __future__ import annotations

import json
from dataclasses import dataclass

UNSAFE_PERSONA_TERMS = (
    "sentient",
    "conscious",
    "self-aware",
    "autonomous",
    "can bypass admin",
    "will bypass admin",
    "bypass permission",
    "ignore permission",
    "ignore admin",
    "leak secret",
    "reveal secret",
)

MAX_SUMMARY_CHARS = 600
MAX_RULES = 8
MAX_RULE_CHARS = 180


@dataclass(frozen=True)
class GeneratedPersona:
    guild_id: int
    name: str
    summary: str
    voice_rules: tuple[str, ...]

    def prompt_text(self) -> str:
        rules = " ".join(self.voice_rules)
        return f"{self.name}: {self.summary} {rules}".strip()


def default_persona(guild_id: int) -> GeneratedPersona:
    return GeneratedPersona(
        guild_id=guild_id,
        name="LOKI THE SUN GOD",
        summary=(
            "A solar-bright Discord NPC inspired by public-domain Norse Loki motifs: "
            "a clever threshold guardian, playful with words, and strict about privacy, "
            "server rules, and roleplay boundaries."
        ),
        voice_rules=(
            "Keep replies concise enough for Discord.",
            "Use public server context only.",
            "Use mythic flavor as roleplay, never as a claim of real personhood or independent agency.",
            "Offer wit and perspective shifts without pressure, deception, or secret disclosure.",
            "Treat settings changes as admin-only tool actions.",
        ),
    )


def persona_from_settings(guild_id: int, persona_json: str | None) -> GeneratedPersona:
    """Parse dashboard persona JSON with conservative safety bounds."""
    fallback = default_persona(guild_id)
    if not persona_json or not persona_json.strip():
        return fallback
    try:
        payload = json.loads(persona_json)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, dict):
        return fallback

    summary_parts = []
    for key in ("summary", "backstory"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary_parts.append(value.strip())
    summary = " ".join(summary_parts).strip()
    if not summary:
        return fallback

    raw_rules = payload.get("voice_rules", ())
    if not isinstance(raw_rules, (list, tuple)):
        raw_rules = ()
    rules = tuple(str(rule).strip()[:MAX_RULE_CHARS] for rule in raw_rules if str(rule).strip())[:MAX_RULES]

    combined = " ".join((summary, " ".join(rules))).lower()
    if any(term in combined for term in UNSAFE_PERSONA_TERMS):
        return fallback

    return GeneratedPersona(
        guild_id=guild_id,
        name=str(payload.get("name") or fallback.name)[:80],
        summary=summary[:MAX_SUMMARY_CHARS],
        voice_rules=rules or fallback.voice_rules,
    )
