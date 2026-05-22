from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import cogs.song_requests_pin_mirror as pin_mirror_module
from cogs import COG_MODULES
from cogs.song_requests_pin_mirror import (
    IS_COMPONENTS_V2,
    MESSAGE_REFERENCE_TYPE_FORWARD,
    SongRequestsPinMirror,
    SongRequestsPinMirrorConfig,
    control_url_from_source,
    forward_fingerprint,
    forward_payload_from_source,
    is_command_cleanup_candidate,
    mirror_components_from_source,
    mirror_fingerprint,
    mirror_payload_from_source,
    sanitize_components_for_mirror,
)
from utils.link_previews import LinkPreview

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
WEBPLAYER_URL = "https://divabot.xyz/dashboard/1463393482306486387/webplayer?botId=983091121569804359"


def make_message(
    message_id: int,
    *,
    content: str = "",
    author_id: int = 111,
    bot: bool = False,
    seconds_old: int = 0,
    pinned: bool = False,
    message_type: int = 0,
):
    return {
        "id": str(message_id),
        "content": content,
        "author": {"id": str(author_id), "bot": bot},
        "timestamp": (NOW - timedelta(seconds=seconds_old)).isoformat(),
        "pinned": pinned,
        "type": message_type,
    }


class SongRequestsPinMirrorPayloadTests(unittest.TestCase):
    def test_cog_is_registered_for_bot_startup(self):
        self.assertIn("song_requests_pin_mirror", COG_MODULES)

    def test_sanitizes_diva_components_for_components_v2_mirror(self):
        source_components = [
            {
                "type": 10,
                "id": 1,
                "content": "**1.** [Track](https://example.test)",
            },
            {
                "type": 17,
                "id": 2,
                "accent_color": 123,
                "components": [
                    {"type": 10, "id": 3, "content": f"### [Now Playing]({WEBPLAYER_URL})"},
                    {
                        "type": 12,
                        "id": 4,
                        "items": [
                            {
                                "media": {
                                    "url": "https://i.scdn.co/image/cover",
                                    "proxy_url": "https://proxy.invalid/cover",
                                    "width": 640,
                                },
                                "description": "cover",
                            }
                        ],
                    },
                    {
                        "type": 1,
                        "id": 5,
                        "components": [
                            {"type": 2, "id": 6, "style": 2, "label": "Pause", "custom_id": "PAUSE_BUT"}
                        ],
                    },
                ],
            },
        ]

        sanitized = mirror_components_from_source({"components": source_components})

        self.assertEqual(sanitized[0]["content"], "**1.** [Track](https://example.test)")
        container = sanitized[1]
        self.assertEqual(container["accent_color"], 123)
        self.assertEqual(container["components"][1]["items"][0]["media"], {"url": "https://i.scdn.co/image/cover"})
        self.assertEqual(len(container["components"]), 2)
        button = sanitized[2]["components"][0]
        self.assertEqual(button["label"], "Open Diva Webplayer")
        self.assertEqual(button["style"], 5)
        self.assertEqual(button["url"], WEBPLAYER_URL)
        self.assertNotIn("custom_id", button)
        self.assertNotIn("disabled", button)

    def test_custom_id_buttons_stay_disabled_when_source_has_no_control_url(self):
        sanitized = sanitize_components_for_mirror(
            [
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "style": 2, "label": "Pause", "custom_id": "PAUSE_BUT"},
                    ],
                }
            ]
        )

        button = sanitized[0]["components"][0]
        self.assertEqual(button["custom_id"], "PAUSE_BUT")
        self.assertTrue(button["disabled"])

    def test_control_url_prefers_diva_webplayer_links(self):
        source = {
            "components": [
                {"type": 10, "content": "[Song](https://open.spotify.com/track/example)"},
                {"type": 10, "content": f"Open the [web player]({WEBPLAYER_URL})."},
            ]
        }

        self.assertEqual(control_url_from_source(source), WEBPLAYER_URL)

    def test_mirror_payload_sets_components_v2_flags_on_create(self):
        source = {"components": [{"type": 10, "content": "Songs"}]}

        payload = mirror_payload_from_source(source, include_flags=True)

        self.assertIsNone(payload["content"])
        self.assertIsNone(payload["embeds"])
        self.assertEqual(payload["components"], [{"type": 10, "content": "Songs"}])
        self.assertEqual(payload["flags"], IS_COMPONENTS_V2)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_forward_payload_references_source_message(self):
        config = SongRequestsPinMirrorConfig(
            guild_id=1463393482306486387,
            source_channel_id=1503116743793574009,
        )
        source = {"id": "1503116745106391131"}

        payload = forward_payload_from_source(source, config)

        self.assertEqual(
            payload,
            {
                "message_reference": {
                    "type": MESSAGE_REFERENCE_TYPE_FORWARD,
                    "guild_id": "1463393482306486387",
                    "channel_id": "1503116743793574009",
                    "message_id": "1503116745106391131",
                },
                "allowed_mentions": {"parse": []},
            },
        )

    def test_enriched_forward_payload_omits_discord_forward_reference(self):
        config = SongRequestsPinMirrorConfig(
            guild_id=1463393482306486387,
            source_channel_id=1503116743793574009,
        )
        source = {"id": "1503116745106391131"}
        embeds = [{"title": "Battles"}]

        payload = forward_payload_from_source(source, config, embeds=embeds)

        self.assertEqual(payload, {"embeds": embeds, "allowed_mentions": {"parse": []}})

    def test_forward_fingerprint_matches_snapshot_message(self):
        source = {
            "content": "",
            "embeds": [],
            "components": [
                {"type": 10, "content": "Songs"},
                {"type": 1, "components": [{"type": 2, "style": 2, "label": "Pause", "custom_id": "PAUSE_BUT"}]},
            ],
        }
        forwarded = {
            "message_snapshots": [
                {
                    "message": {
                        "content": "",
                        "embeds": [],
                        "components": [
                            {"type": 10, "content": "Songs"},
                            {
                                "type": 1,
                                "components": [
                                    {
                                        "type": 2,
                                        "style": 2,
                                        "label": "Pause",
                                        "custom_id": "PAUSE_BUT",
                                        "disabled": False,
                                    }
                                ],
                            },
                        ],
                    }
                }
            ]
        }

        self.assertEqual(forward_fingerprint(source), forward_fingerprint(forwarded))

    def test_plain_source_message_falls_back_to_text_display(self):
        source = {"content": "plain list", "embeds": []}

        self.assertEqual(mirror_components_from_source(source), [{"type": 10, "content": "plain list"}])

    def test_fingerprint_matches_equivalent_sanitized_components(self):
        source = {
            "components": [
                {
                    "type": 12,
                    "id": 4,
                    "items": [
                        {
                            "media": {
                                "url": "https://i.scdn.co/image/cover",
                                "proxy_url": "https://proxy.invalid/cover",
                            }
                        }
                    ],
                }
            ]
        }
        mirror = {"components": [{"type": 12, "id": 4, "items": [{"media": {"url": "https://i.scdn.co/image/cover"}}]}]}

        self.assertEqual(mirror_fingerprint(source), mirror_fingerprint(mirror))

    def test_song_queue_embed_payloads_show_artist_cover_and_source_marker(self):
        builder = getattr(pin_mirror_module, "song_queue_embed_payloads", None)
        self.assertIsNotNone(builder)

        embeds = builder(
            [
                LinkPreview(
                    url="https://open.spotify.com/track/abc",
                    title="Battles",
                    description="Alpine Universe · Album · Song · 2026",
                    image_url="https://i.scdn.co/image/cover.jpg",
                    site_name="Spotify",
                )
            ],
            source_marker="LOKI song-request source 1463393482306486387:1503116743793574009:222",
        )

        self.assertEqual(embeds[0]["title"], "Battles")
        self.assertEqual(embeds[0]["url"], "https://open.spotify.com/track/abc")
        self.assertEqual(embeds[0]["thumbnail"], {"url": "https://i.scdn.co/image/cover.jpg"})
        self.assertIn({"name": "Artist", "value": "Alpine Universe", "inline": True}, embeds[0]["fields"])
        self.assertEqual(
            embeds[0]["footer"],
            {"text": "LOKI song-request source 1463393482306486387:1503116743793574009:222"},
        )


class SongRequestsCommandCleanupTests(unittest.TestCase):
    def test_cleanup_selects_old_command_messages(self):
        message = make_message(1, content="/play something", seconds_old=61)
        config = SongRequestsPinMirrorConfig(command_cleanup_age_seconds=60)

        self.assertTrue(
            is_command_cleanup_candidate(
                message,
                config=config,
                managed_message_id=999,
                bot_user_id=42,
                now=NOW,
            )
        )

    def test_cleanup_keeps_fresh_pinned_and_managed_messages(self):
        config = SongRequestsPinMirrorConfig(command_cleanup_age_seconds=60)
        for message in (
            make_message(1, content="/play something", seconds_old=59),
            make_message(2, content="/play something", seconds_old=61, pinned=True),
            make_message(999, content="/play something", seconds_old=61),
        ):
            self.assertFalse(
                is_command_cleanup_candidate(
                    message,
                    config=config,
                    managed_message_id=999,
                    bot_user_id=42,
                    now=NOW,
                )
            )

    def test_cleanup_selects_old_non_loki_bot_messages_and_system_messages(self):
        config = SongRequestsPinMirrorConfig(command_cleanup_age_seconds=60)
        bot_message = make_message(1, content="", author_id=77, bot=True, seconds_old=61)
        system_message = make_message(2, content="", seconds_old=61, message_type=6)

        self.assertTrue(
            is_command_cleanup_candidate(
                bot_message,
                config=config,
                managed_message_id=999,
                bot_user_id=42,
                now=NOW,
            )
        )
        self.assertTrue(
            is_command_cleanup_candidate(
                system_message,
                config=config,
                managed_message_id=999,
                bot_user_id=42,
                now=NOW,
            )
        )

    def test_cleanup_keeps_old_normal_user_chat_and_loki_messages(self):
        config = SongRequestsPinMirrorConfig(command_cleanup_age_seconds=60)
        normal = make_message(1, content="hello", seconds_old=61)
        loki = make_message(2, content="", author_id=42, bot=True, seconds_old=61)

        self.assertFalse(
            is_command_cleanup_candidate(
                normal,
                config=config,
                managed_message_id=999,
                bot_user_id=42,
                now=NOW,
            )
        )
        self.assertFalse(
            is_command_cleanup_candidate(
                loki,
                config=config,
                managed_message_id=999,
                bot_user_id=42,
                now=NOW,
            )
        )


class SongRequestsPinMirrorForwardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_forwards_every_dashboard_post_with_song_embeds_before_pin_mirror(self):
        source_messages = [
            {
                "id": "222",
                "content": "queue https://open.spotify.com/track/two",
                "author": {"id": "77", "bot": True},
                "timestamp": NOW.isoformat(),
                "embeds": [],
                "components": [{"type": 10, "content": "Queued second song"}],
            },
            {
                "id": "111",
                "content": "queue https://open.spotify.com/track/one",
                "author": {"id": "77", "bot": True},
                "timestamp": (NOW - timedelta(seconds=30)).isoformat(),
                "embeds": [],
                "components": [{"type": 10, "content": "Queued first song"}],
            },
        ]
        posted_payloads: list[dict] = []

        async def fake_resolve(urls):
            return [
                LinkPreview(
                    url=url,
                    title="Song " + url.rsplit("/", 1)[-1],
                    description="Alpine Universe · Album · Song · 2026",
                    image_url=f"https://i.scdn.co/image/{url.rsplit('/', 1)[-1]}.jpg",
                    site_name="Spotify",
                )
                for url in urls
            ]

        async def fake_api(method, path, *, payload=None, audit_reason=None):
            if method == "GET" and path == "/channels/1503116743793574009/messages?limit=10":
                return list(source_messages)
            if method == "GET" and path == "/channels/1499435617971343491/messages?limit=50":
                return []
            if method == "GET" and path == "/channels/1499435617971343491/pins?limit=50":
                return []
            if method == "POST" and path == "/channels/1499435617971343491/messages":
                posted_payloads.append(payload)
                return {
                    "id": str(9000 + len(posted_payloads)),
                    "author": {"id": "42", "bot": True},
                    "pinned": False,
                    **(payload or {}),
                }
            if method == "PUT" and path.startswith("/channels/1499435617971343491/messages/pins/"):
                return None
            self.fail(f"unexpected API call: {method} {path}")

        mirror = SongRequestsPinMirror.__new__(SongRequestsPinMirror)
        mirror.bot = SimpleNamespace(user=SimpleNamespace(id=42))
        mirror.config = SimpleNamespace(
            enabled=True,
            guild_id=1463393482306486387,
            source_channel_id=1503116743793574009,
            source_message_id=0,
            target_channel_id=1499435617971343491,
            managed_message_id=0,
            forward_source_message=False,
            forward_all_source_messages=True,
            refresh_seconds=30,
            source_history_limit=10,
            target_history_limit=50,
            command_cleanup_age_seconds=0,
            command_prefixes=("/", "!", ".", "?", "$", "-"),
        )
        mirror._managed_message_id = None
        mirror._sync_lock = __import__("asyncio").Lock()
        mirror._bot_user_id = 42
        mirror._api_request = fake_api

        with patch.object(pin_mirror_module, "resolve_link_previews", fake_resolve, create=True):
            await mirror._sync_once(reason="test")

        forward_posts = [
            payload
            for payload in posted_payloads
            if payload.get("embeds") and not payload.get("components")
        ]
        self.assertEqual(
            [payload["embeds"][0]["footer"]["text"].rsplit(":", 1)[-1] for payload in forward_posts],
            ["111", "222"],
        )
        for payload in forward_posts:
            self.assertNotIn("message_reference", payload)
            self.assertEqual(payload["allowed_mentions"], {"parse": []})
            self.assertEqual(payload["embeds"][0]["author"], {"name": "Spotify"})
            self.assertIn("Artist", {field["name"] for field in payload["embeds"][0]["fields"]})

        pinned_mirrors = [payload for payload in posted_payloads if payload.get("components")]
        self.assertEqual(len(pinned_mirrors), 1)
        self.assertEqual(pinned_mirrors[0]["components"][0]["content"], "Queued second song")


if __name__ == "__main__":
    unittest.main()
