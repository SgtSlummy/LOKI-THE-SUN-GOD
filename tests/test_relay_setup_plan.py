from types import SimpleNamespace

import pytest

from bot.services.relay_setup import DEFAULT_RELAY_CHANNELS, plan_relay_setup


class FakeChannel:
    def __init__(self, name):
        self.name = name
        self.topic = None
        self.id = abs(hash(name)) % 100000
        self.created_webhooks = []

    async def webhooks(self):
        return []

    async def create_webhook(self, name, reason=None):
        self.created_webhooks.append((name, reason))
        return SimpleNamespace(name=name, id=999)


class FakeGuild:
    def __init__(self, categories=None, channels=None):
        self.categories = categories or []
        self.text_channels = channels or []
        self.created_categories = []
        self.created_channels = []
        self.me = SimpleNamespace(guild_permissions=SimpleNamespace(manage_channels=True, manage_webhooks=True))

    async def create_category(self, name, reason=None):
        category = SimpleNamespace(name=name, id=123)
        self.categories.append(category)
        self.created_categories.append((name, reason))
        return category

    async def create_text_channel(self, name, category=None, topic=None, reason=None):
        channel = FakeChannel(name)
        channel.topic = topic
        self.text_channels.append(channel)
        self.created_channels.append((name, category.name if category else None, topic, reason))
        return channel


@pytest.mark.asyncio
async def test_setup_dry_run_reports_missing_category_channels_and_webhooks_without_mutating_guild():
    guild = FakeGuild()

    result = await plan_relay_setup(guild, dry_run=True)

    assert result.dry_run is True
    assert any(step.action == "create_category" and step.name == "Loki Relay" for step in result.steps)
    for name in DEFAULT_RELAY_CHANNELS.values():
        assert any(step.action == "create_text_channel" and step.name == name for step in result.steps)
    assert guild.created_categories == []
    assert guild.created_channels == []


@pytest.mark.asyncio
async def test_setup_plan_reuses_existing_category_channels_and_webhooks():
    category = SimpleNamespace(name="Loki Relay", id=1)
    channel = FakeChannel("loki-messages")
    guild = FakeGuild(categories=[category], channels=[channel])

    result = await plan_relay_setup(guild, dry_run=True)

    assert any(step.action == "reuse_category" and step.name == "Loki Relay" for step in result.steps)
    assert any(step.action == "reuse_text_channel" and step.name == "loki-messages" for step in result.steps)
    assert any(step.action == "create_text_channel" and step.name == "loki-pictures" for step in result.steps)


@pytest.mark.asyncio
async def test_setup_live_applies_only_missing_create_steps():
    category = SimpleNamespace(name="Loki Relay", id=1)
    channel = FakeChannel("loki-messages")
    guild = FakeGuild(categories=[category], channels=[channel])

    result = await plan_relay_setup(guild, dry_run=False, create_webhooks=False)

    assert result.dry_run is False
    assert guild.created_categories == []
    created_names = [call[0] for call in guild.created_channels]
    assert "loki-messages" not in created_names
    assert set(created_names) == set(DEFAULT_RELAY_CHANNELS.values()) - {"loki-messages"}
