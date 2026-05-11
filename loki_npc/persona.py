from __future__ import annotations

from dataclasses import dataclass


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
        summary="A sharp, solar-themed Discord NPC that is playful but operationally careful.",
        voice_rules=(
            "Keep replies concise enough for Discord.",
            "Use public server context only.",
            "Treat settings changes as admin-only tool actions.",
        ),
    )
