from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import discord

from cogs import relay as relay_module
from cogs.relay import Relay
from utils.link_previews import LinkPreview


def visible_embed_text(embeds) -> str:
    parts = []
    for embed in embeds:
        data = embed.to_dict()
        for key in ("title", "description"):
            if data.get(key):
                parts.append(data[key])
        author = data.get("author") or {}
        if author.get("name"):
            parts.append(author["name"])
        footer = data.get("footer") or {}
        if footer.get("text"):
            parts.append(footer["text"])
        for field in data.get("fields") or []:
            parts.append(field.get("name") or "")
            parts.append(field.get("value") or "")
    return "\n".join(parts)


class FakeChannel:
    id = 222
    name = "target"

    def history(self, *, limit: int):
        async def _empty_history():
            if False:
                yield None

        return _empty_history()


class FakeHistoryChannel:
    id = 333
    name = "source"

    def __init__(self, messages):
        self.messages = messages
        self.history_kwargs = None

    def history(self, **kwargs):
        self.history_kwargs = kwargs

        async def _history():
            for message in self.messages:
                yield message

        return _history()


class FakeAttachment:
    url = "https://cdn.discordapp.com/image.png"
    content_type = "image/png"


def make_message(
    body: str,
    *,
    mentions=None,
    role_mentions=None,
    channel_mentions=None,
):
    return SimpleNamespace(
        id=123,
        guild=SimpleNamespace(id=999),
        jump_url="https://discord.com/channels/999/111/123",
        content=body,
        mentions=mentions or [],
        role_mentions=role_mentions or [],
        channel_mentions=channel_mentions or [],
    )


class RelayPreviewSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_link_post_sends_embeds_without_raw_content(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return [
                LinkPreview(
                    url="https://open.spotify.com/track/abc",
                    title="Battles",
                    description="Alpine Universe",
                    image_url="https://i.scdn.co/image/cover.jpg",
                    site_name="Spotify",
                )
            ]

        relay = Relay(SimpleNamespace())
        body = "listen https://open.spotify.com/track/abc?si=123"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #share-that-musik",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        self.assertEqual(sent_kwargs[0].get("content"), None)
        self.assertGreaterEqual(len(sent_kwargs[0]["embeds"]), 2)
        self.assertEqual(
            sent_kwargs[0]["embeds"][1].to_dict()["fields"],
            [{"inline": False, "name": "Artists", "value": "Alpine Universe"}],
        )
        visible = visible_embed_text(sent_kwargs[0]["embeds"])
        self.assertIn("listen", visible)
        self.assertIn("Artists", visible)
        self.assertIn("Alpine Universe", visible)
        self.assertNotIn("open.spotify.com", visible)
        self.assertNotIn("discord.com/channels", visible)
        self.assertNotIn("LOKI THE SUN GOD relay source", visible)
        self.assertNotIn("footer", sent_kwargs[0]["embeds"][0].to_dict())
        self.assertEqual(sent_kwargs[0]["embeds"][0].to_dict()["url"], "https://discord.com/channels/999/111/123")

    async def test_user_mentions_are_relayed_as_names(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return []

        relay = Relay(SimpleNamespace())
        body = "<@478634821959024641> <@!294709392798908417> yall wanna game later"
        message = make_message(
            body,
            mentions=[
                SimpleNamespace(id=478634821959024641, display_name="gaspackjim"),
                SimpleNamespace(id=294709392798908417, display_name="zuxas"),
            ],
        )

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=message,
                author_name="gaspackjim in #The Vibez 101 FM 🦆",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        description = sent_kwargs[0]["embeds"][0].description
        self.assertEqual(description, "@gaspackjim @zuxas yall wanna game later")
        self.assertNotIn("478634821959024641", description)
        self.assertNotIn("294709392798908417", description)

    async def test_role_and_channel_mentions_are_relayed_as_names(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return []

        relay = Relay(SimpleNamespace())
        body = "<@&111222333444555666> meet in <#777888999000111222>"
        message = make_message(
            body,
            role_mentions=[SimpleNamespace(id=111222333444555666, name="Friends")],
            channel_mentions=[SimpleNamespace(id=777888999000111222, name="general-chat")],
        )

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=message,
                author_name="gaspackjim in #The Vibez 101 FM 🦆",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        self.assertEqual(sent_kwargs[0]["embeds"][0].description, "@Friends meet in #general-chat")

    async def test_custom_animated_emoji_markup_is_preserved(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return []

        relay = Relay(SimpleNamespace())
        body = "<a:funnyanimalscrazy:1500929712522793132> https://example.com/context"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #The Vibez 101 FM 🦆",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        self.assertEqual(sent_kwargs[0]["embeds"][0].description, "<a:funnyanimalscrazy:1500929712522793132>")
        self.assertEqual(
            sent_kwargs[0]["embeds"][0].image.url,
            "https://cdn.discordapp.com/emojis/1500929712522793132.gif?size=96&quality=lossless",
        )

    async def test_custom_static_emoji_markup_is_preserved(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return []

        relay = Relay(SimpleNamespace())
        body = "<:funnyanimalscrazy:1500929712522793132>"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #The Vibez 101 FM 🦆",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        self.assertEqual(sent_kwargs[0]["embeds"][0].description, "<:funnyanimalscrazy:1500929712522793132>")
        self.assertEqual(
            sent_kwargs[0]["embeds"][0].image.url,
            "https://cdn.discordapp.com/emojis/1500929712522793132.webp?size=96&quality=lossless",
        )

    async def test_url_only_post_still_sends_source_context_and_preview_embed(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return [LinkPreview(url="https://example.com/photo.jpg", title="example.com", image_url="https://example.com/photo.jpg")]

        relay = Relay(SimpleNamespace())
        body = "https://example.com/photo.jpg"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #general-chat",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        self.assertEqual(sent_kwargs[0].get("content"), None)
        self.assertEqual(len(sent_kwargs[0]["embeds"]), 2)
        self.assertEqual(sent_kwargs[0]["embeds"][0].description, None)
        self.assertEqual(sent_kwargs[0]["embeds"][1].image.url, "https://example.com/photo.jpg")

    async def test_preview_metadata_urls_are_not_visible_text(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return [
                LinkPreview(
                    url="https://asdjfk.com/post/1",
                    title="https://asdjfk.com/post/1",
                    description="watch this at https://asdjfk.com/post/1",
                    image_url="https://asdjfk.com/image.jpg",
                    site_name="https://asdjfk.com",
                )
            ]

        relay = Relay(SimpleNamespace())
        body = "https://asdjfk.com/post/1"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #general-chat",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=None,
                attachment_type="",
            )

        visible = visible_embed_text(sent_kwargs[0]["embeds"])
        self.assertNotIn("https://", visible)
        self.assertIn("asdjfk.com", visible)

    async def test_image_attachment_post_strips_url_text_and_keeps_image(self):
        sent_kwargs = []

        async def fake_safe_send(_target, **kwargs):
            sent_kwargs.append(kwargs)
            return object()

        async def fake_resolve(_urls):
            return []

        relay = Relay(SimpleNamespace())
        body = "photo from last night https://example.com/context"

        with (
            patch.object(relay_module, "safe_send", fake_safe_send),
            patch.object(relay_module, "resolve_link_previews", fake_resolve, create=True),
        ):
            await relay._send_message_to_targets(
                destinations=[FakeChannel()],
                message=make_message(body),
                author_name="Cannibal in #general-chat",
                avatar_url="https://cdn.discordapp.com/avatar.png",
                body=body,
                attachment=FakeAttachment(),
                attachment_type="image/png",
            )

        self.assertEqual(sent_kwargs[0].get("content"), None)
        self.assertEqual(len(sent_kwargs[0]["embeds"]), 1)
        embed = sent_kwargs[0]["embeds"][0]
        self.assertEqual(embed.description, "photo from last night")
        self.assertEqual(embed.image.url, FakeAttachment.url)
        self.assertNotIn("example.com", visible_embed_text(sent_kwargs[0]["embeds"]))


class RelayBackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_destination_history_detects_hidden_source_url(self):
        source_url = "https://discord.com/channels/999/111/123"
        embed = discord.Embed(url=source_url)
        channel = FakeHistoryChannel([SimpleNamespace(content="", embeds=[embed])])
        relay = Relay(SimpleNamespace())

        self.assertTrue(await relay._destination_already_has_source(channel, (source_url,)))

    async def test_destination_history_detects_legacy_source_footer(self):
        legacy_marker = "LOKI THE SUN GOD relay source 999:123"
        embed = discord.Embed()
        embed.set_footer(text=legacy_marker)
        channel = FakeHistoryChannel([SimpleNamespace(content="", embeds=[embed])])
        relay = Relay(SimpleNamespace())

        self.assertTrue(await relay._destination_already_has_source(channel, (legacy_marker,)))

    async def test_backfill_history_scans_oldest_first_and_skips_command_message(self):
        handled = []
        command_message_id = 2
        messages = [
            SimpleNamespace(id=1),
            SimpleNamespace(id=command_message_id),
            SimpleNamespace(id=3),
        ]
        channel = FakeHistoryChannel(messages)
        relay = Relay(SimpleNamespace())

        async def fake_handle(message):
            handled.append(message.id)
            return 1 if message.id == 3 else 0

        relay._handle_message = fake_handle

        result = await relay._backfill_history([channel], limit=2, skip_message_id=command_message_id)

        self.assertEqual(channel.history_kwargs, {"limit": 2, "oldest_first": True})
        self.assertEqual(handled, [1, 3])
        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.relays_sent, 1)
        self.assertEqual(result.failed_sources, 0)


if __name__ == "__main__":
    unittest.main()
