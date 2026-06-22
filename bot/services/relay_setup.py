from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_RELAY_CATEGORY = "Loki Relay"
DEFAULT_RELAY_CHANNELS = {
    "messages": "loki-messages",
    "pictures": "loki-pictures",
    "gifs": "loki-gifs",
    "emotes": "loki-emotes",
    "music": "loki-music-relay",
}
RELAY_CHANNEL_TOPIC = "Loki relay output channel. Originals stay untouched in phase 1."


@dataclass(slots=True)
class RelaySetupStep:
    action: str
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelaySetupResult:
    dry_run: bool
    category_name: str
    steps: list[RelaySetupStep]

    def summary_lines(self) -> list[str]:
        prefix = "DRY RUN" if self.dry_run else "APPLIED"
        lines = [f"{prefix}: Loki relay setup for category {self.category_name!r}"]
        for step in self.steps:
            lines.append(f"- {step.action}: {step.name} [{step.status}]")
        return lines


def _name_matches(actual: str, expected: str) -> bool:
    return actual.casefold() == expected.casefold()


def _find_by_name(items: list[Any], name: str) -> Any | None:
    for item in items:
        if _name_matches(getattr(item, "name", ""), name):
            return item
    return None


async def plan_relay_setup(
    guild: Any,
    *,
    dry_run: bool = True,
    category_name: str = DEFAULT_RELAY_CATEGORY,
    channel_names: dict[str, str] | None = None,
    create_webhooks: bool = True,
    reason: str = "Loki relay setup",
) -> RelaySetupResult:
    names = channel_names or DEFAULT_RELAY_CHANNELS
    steps: list[RelaySetupStep] = []

    category = _find_by_name(list(getattr(guild, "categories", [])), category_name)
    if category is None:
        steps.append(RelaySetupStep("create_category", category_name, "planned" if dry_run else "created"))
        if not dry_run:
            category = await guild.create_category(category_name, reason=reason)
    else:
        steps.append(RelaySetupStep("reuse_category", category_name, "exists", {"id": getattr(category, "id", None)}))

    existing_channels = list(getattr(guild, "text_channels", []))
    for key, channel_name in names.items():
        channel = _find_by_name(existing_channels, channel_name)
        if channel is None:
            steps.append(RelaySetupStep("create_text_channel", channel_name, "planned" if dry_run else "created", {"key": key}))
            if not dry_run:
                channel = await guild.create_text_channel(channel_name, category=category, topic=RELAY_CHANNEL_TOPIC, reason=reason)
                existing_channels.append(channel)
        else:
            steps.append(RelaySetupStep("reuse_text_channel", channel_name, "exists", {"key": key, "id": getattr(channel, "id", None)}))

        if create_webhooks and channel is None and dry_run:
            steps.append(RelaySetupStep("create_webhook", channel_name, "planned", {"webhook": "Loki Relay"}))
        elif create_webhooks and channel is not None:
            webhooks = await channel.webhooks() if hasattr(channel, "webhooks") else []
            webhook = _find_by_name(list(webhooks), "Loki Relay")
            if webhook is None:
                steps.append(RelaySetupStep("create_webhook", channel_name, "planned" if dry_run else "created", {"webhook": "Loki Relay"}))
                if not dry_run and hasattr(channel, "create_webhook"):
                    await channel.create_webhook(name="Loki Relay", reason=reason)
            else:
                steps.append(RelaySetupStep("reuse_webhook", channel_name, "exists", {"webhook_id": getattr(webhook, "id", None)}))

    return RelaySetupResult(dry_run=dry_run, category_name=category_name, steps=steps)
