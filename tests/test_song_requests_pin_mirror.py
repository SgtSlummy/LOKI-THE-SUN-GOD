from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from cogs import COG_MODULES
from cogs.song_requests_pin_mirror import (
    IS_COMPONENTS_V2,
    MESSAGE_REFERENCE_TYPE_FORWARD,
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


if __name__ == "__main__":
    unittest.main()
