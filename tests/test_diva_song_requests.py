from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import discord

from cogs import COG_MODULES
from cogs.diva_song_requests import (
    DEFAULT_AUTHOR_ID,
    DEFAULT_CHANNEL_ID,
    DEFAULT_SOURCE_MESSAGE_ID,
    MANAGED_MARKER,
    DivaSongRequestsConfig,
    DivaSongRequestsMirror,
    build_diva_song_requests_payload,
    diva_source_fingerprint,
    is_diva_source_message,
    is_managed_dashboard_fallback_message,
    is_managed_mirror_message,
    managed_message_fingerprint,
    missing_diva_mirror_permissions,
    select_diva_source_message,
)

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)


def make_message(
    message_id: int,
    *,
    content: str = "",
    embeds: list[discord.Embed] | None = None,
    seconds_old: int = 0,
    channel_id: int = DEFAULT_CHANNEL_ID,
    author_id: int | None = DEFAULT_AUTHOR_ID,
    application_id: int | None = None,
    webhook_id: int | None = None,
):
    return SimpleNamespace(
        id=message_id,
        content=content,
        embeds=embeds or [],
        created_at=NOW - timedelta(seconds=seconds_old),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=author_id) if author_id is not None else None,
        application_id=application_id,
        webhook_id=webhook_id,
    )


class DivaSongRequestsPayloadTests(unittest.TestCase):
    def test_cog_is_registered_for_bot_startup(self):
        self.assertIn("diva_song_requests", COG_MODULES)

    def test_build_payload_copies_only_source_content_and_embeds(self):
        source_embed = discord.Embed(title="Now Playing", description="Lydia - Highly Suspect", color=0xEBBF0F)
        source = make_message(
            DEFAULT_SOURCE_MESSAGE_ID,
            content="4. SHALLOW - Magnolia Park",
            embeds=[source_embed],
        )
        config = DivaSongRequestsConfig(enabled=True)

        payload = build_diva_song_requests_payload(source, config)

        self.assertEqual(payload["content"], "4. SHALLOW - Magnolia Park")
        self.assertEqual(len(payload["embeds"]), 1)
        self.assertEqual(payload["embeds"][0].title, "Now Playing")
        self.assertEqual(payload["embeds"][0].description, "Lydia - Highly Suspect")
        self.assertIsInstance(payload["allowed_mentions"], discord.AllowedMentions)

    def test_managed_marker_is_detected_from_footer(self):
        embed = discord.Embed(title="Diva Song Requests", url="https://example.test")
        embed.set_footer(text=f"{MANAGED_MARKER} | source:1 | fp:abc123")
        message = make_message(10, embeds=[embed], author_id=999)

        self.assertTrue(is_managed_mirror_message(message, bot_user_id=999))
        self.assertFalse(is_managed_mirror_message(message, bot_user_id=111))
        self.assertEqual(managed_message_fingerprint(message), "abc123")
        self.assertFalse(is_managed_dashboard_fallback_message(message))

    def test_managed_dashboard_fallback_is_detected_from_footer(self):
        embed = discord.Embed(title="Diva Song Requests", url="https://example.test")
        embed.set_footer(text=f"{MANAGED_MARKER} | source:0 | fp:abc123")
        message = make_message(10, embeds=[embed], author_id=999)

        self.assertTrue(is_managed_dashboard_fallback_message(message))

    def test_select_source_message_uses_newest_matching_diva_post(self):
        older = make_message(1, seconds_old=30)
        newest = make_message(2, seconds_old=10, application_id=DEFAULT_AUTHOR_ID, author_id=111)
        ignored_channel = make_message(3, seconds_old=5, channel_id=123)
        ignored_author = make_message(4, seconds_old=1, author_id=222)

        selected = select_diva_source_message(
            [older, newest, ignored_channel, ignored_author],
            DivaSongRequestsConfig(enabled=True, source_message_id=0),
        )

        self.assertEqual(selected.id, 2)

    def test_configured_source_message_id_is_trusted(self):
        source = make_message(DEFAULT_SOURCE_MESSAGE_ID, author_id=111, application_id=None, webhook_id=None)

        self.assertTrue(is_diva_source_message(source, DivaSongRequestsConfig(enabled=True)))

    def test_configured_source_message_id_restricts_other_diva_posts(self):
        source = make_message(DEFAULT_SOURCE_MESSAGE_ID + 1, author_id=DEFAULT_AUTHOR_ID)

        self.assertFalse(is_diva_source_message(source, DivaSongRequestsConfig(enabled=True)))

    def test_from_env_reads_config(self):
        with patch.dict(
            "os.environ",
            {
                "DIVA_SONG_EMBED_ENABLED": "true",
                "DIVA_SONG_EMBED_CHANNEL_ID": "1499435617971343491",
                "DIVA_SONG_EMBED_AUTHOR_ID": "983091121569804359",
                "DIVA_SONG_EMBED_SOURCE_MESSAGE_ID": "1503116743793574009",
                "DIVA_SONG_EMBED_MANAGED_MESSAGE_ID": "1504000000000000000",
                "DIVA_SONG_EMBED_HISTORY_LIMIT": "150",
            },
        ):
            config = DivaSongRequestsConfig.from_env()

        self.assertTrue(config.enabled)
        self.assertEqual(config.channel_id, DEFAULT_CHANNEL_ID)
        self.assertEqual(config.author_id, DEFAULT_AUTHOR_ID)
        self.assertEqual(config.source_message_id, DEFAULT_SOURCE_MESSAGE_ID)
        self.assertEqual(config.managed_message_id, 1504000000000000000)
        self.assertEqual(config.history_limit, 150)

    def test_missing_permission_check_reports_required_channel_permissions(self):
        permissions = SimpleNamespace(
            send_messages=True,
            embed_links=False,
            read_message_history=True,
            manage_messages=False,
        )
        channel = SimpleNamespace(permissions_for=lambda member: permissions)

        missing = missing_diva_mirror_permissions(channel, SimpleNamespace(id=999))

        self.assertEqual(missing, ["Embed Links", "Manage Messages"])


class FakeManagedMessage:
    id = 300

    def __init__(self):
        self.author = SimpleNamespace(id=999)
        self.channel = SimpleNamespace(id=DEFAULT_CHANNEL_ID)
        self.content = "old"
        self.embeds = []
        self.edits = []
        self.deleted = False

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        self.content = kwargs.get("content")
        self.embeds = kwargs.get("embeds", [])

    async def delete(self):
        self.deleted = True


class FakeChannel:
    id = DEFAULT_CHANNEL_ID

    def __init__(self, messages, *, fetch_messages=None):
        self.messages = messages
        self.fetch_messages = fetch_messages if fetch_messages is not None else messages
        self.sent = []

    def history(self, *, limit):
        async def iterator():
            for message in self.messages[:limit]:
                yield message

        return iterator()

    async def fetch_message(self, message_id):
        for message in self.fetch_messages:
            if message.id == message_id:
                return message
        raise discord.NotFound(response=SimpleNamespace(status=404, reason="missing"), message="missing")

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return make_message(400, content=kwargs.get("content") or "", embeds=kwargs.get("embeds") or [], author_id=999)


class FakeBot:
    user = SimpleNamespace(id=999)

    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if channel_id == DEFAULT_CHANNEL_ID else None

    async def fetch_channel(self, channel_id):
        return self.get_channel(channel_id)


class DivaSongRequestsSyncTests(unittest.TestCase):
    async def _safe_send(self, channel, **kwargs):
        kwargs.pop("dedupe_key", None)
        kwargs.pop("dedupe_window", None)
        kwargs.pop("dedupe_required", None)
        return await channel.send(**kwargs)

    def test_sync_edits_existing_managed_message_when_source_changes(self):
        source = make_message(
            DEFAULT_SOURCE_MESSAGE_ID,
            content="Upcoming\nG.O.A.T. - Polyphia",
            embeds=[discord.Embed(title="Now Playing", description="Lydia - Highly Suspect")],
        )
        managed = FakeManagedMessage()
        marker_embed = discord.Embed(title="Diva Song Requests", url="https://example.test")
        marker_embed.set_footer(text=f"{MANAGED_MARKER} | source:1 | fp:oldfingerprint")
        managed.embeds = [marker_embed]
        channel = FakeChannel([managed, source])
        mirror = object.__new__(DivaSongRequestsMirror)
        mirror.bot = FakeBot(channel)
        mirror.config = DivaSongRequestsConfig(enabled=True)
        mirror._sync_lock = asyncio.Lock()

        asyncio.run(mirror._sync_once(reason="test"))

        self.assertEqual(channel.sent, [])
        self.assertEqual(len(managed.edits), 1)
        self.assertEqual(managed.content, "Upcoming\nG.O.A.T. - Polyphia")
        self.assertEqual(len(managed.embeds), 1)
        self.assertEqual(managed.embeds[0].title, "Now Playing")
        self.assertEqual(diva_source_fingerprint(managed), diva_source_fingerprint(source))

    def test_sync_fetches_seed_source_when_history_misses_it(self):
        source = make_message(
            DEFAULT_SOURCE_MESSAGE_ID,
            content="4. SHALLOW - Magnolia Park",
            embeds=[discord.Embed(title="Now Playing", description="Lydia - Highly Suspect")],
            author_id=111,
        )
        channel = FakeChannel([], fetch_messages=[source])
        mirror = object.__new__(DivaSongRequestsMirror)
        mirror.bot = FakeBot(channel)
        mirror.config = DivaSongRequestsConfig(enabled=True)
        mirror._sync_lock = asyncio.Lock()

        with patch("cogs.diva_song_requests.safe_send", self._safe_send):
            asyncio.run(mirror._sync_once(reason="test"))

        self.assertEqual(len(channel.sent), 1)
        self.assertEqual(channel.sent[0]["content"], "4. SHALLOW - Magnolia Park")
        self.assertEqual(len(channel.sent[0]["embeds"]), 1)
        self.assertEqual(channel.sent[0]["embeds"][0].title, "Now Playing")

    def test_sync_does_not_post_when_source_is_unavailable(self):
        channel = FakeChannel([])
        mirror = object.__new__(DivaSongRequestsMirror)
        mirror.bot = FakeBot(channel)
        mirror.config = DivaSongRequestsConfig(enabled=True)
        mirror._sync_lock = asyncio.Lock()

        with patch("cogs.diva_song_requests.safe_send", self._safe_send):
            asyncio.run(mirror._sync_once(reason="test"))

        self.assertEqual(channel.sent, [])

    def test_sync_keeps_existing_mirror_when_source_is_unavailable(self):
        managed = FakeManagedMessage()
        managed.embeds = [discord.Embed(title="Existing Mirror")]
        channel = FakeChannel([], fetch_messages=[managed])
        mirror = object.__new__(DivaSongRequestsMirror)
        mirror.bot = FakeBot(channel)
        mirror.config = DivaSongRequestsConfig(enabled=True, managed_message_id=managed.id)
        mirror._sync_lock = asyncio.Lock()

        asyncio.run(mirror._sync_once(reason="test"))

        self.assertEqual(channel.sent, [])
        self.assertEqual(managed.edits, [])
        self.assertEqual(managed.embeds[0].title, "Existing Mirror")
        self.assertFalse(managed.deleted)

    def test_sync_deletes_old_dashboard_fallback_when_source_is_unavailable(self):
        managed = FakeManagedMessage()
        marker_embed = discord.Embed(title="Smuggler Jukebox Player", url="https://example.test")
        marker_embed.set_footer(text=f"{MANAGED_MARKER} | source:0 | fp:oldfingerprint")
        managed.embeds = [marker_embed]
        channel = FakeChannel([], fetch_messages=[managed])
        mirror = object.__new__(DivaSongRequestsMirror)
        mirror.bot = FakeBot(channel)
        mirror.config = DivaSongRequestsConfig(enabled=True, managed_message_id=managed.id)
        mirror._sync_lock = asyncio.Lock()

        asyncio.run(mirror._sync_once(reason="test"))

        self.assertEqual(channel.sent, [])
        self.assertEqual(managed.edits, [])
        self.assertTrue(managed.deleted)


if __name__ == "__main__":
    unittest.main()
