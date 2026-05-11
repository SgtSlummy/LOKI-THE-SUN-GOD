from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from cogs.wreckingball_cleanup import (
    DEFAULT_AUTHOR_ID,
    DEFAULT_CHANNEL_ID,
    WreckingballCleanup,
    WreckingballCleanupConfig,
    WreckingballCleanupRule,
    is_wreckingball_cleanup_candidate,
    matching_wreckingball_cleanup_rule,
    select_wreckingball_cleanup_messages,
)

NOW = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
MUSIC_LIST_CHANNEL_ID = 1499435617971343491


def make_message(
    message_id: int,
    *,
    seconds_old: int,
    channel_id: int = DEFAULT_CHANNEL_ID,
    author_id: int | None = DEFAULT_AUTHOR_ID,
    application_id: int | None = None,
    webhook_id: int | None = None,
):
    return SimpleNamespace(
        id=message_id,
        created_at=NOW - timedelta(seconds=seconds_old),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=author_id) if author_id is not None else None,
        application_id=application_id,
        webhook_id=webhook_id,
    )


class WreckingballCleanupSelectionTests(unittest.TestCase):
    def setUp(self):
        self.config = WreckingballCleanupConfig(
            enabled=True,
            channel_id=DEFAULT_CHANNEL_ID,
            author_id=DEFAULT_AUTHOR_ID,
            max_age_seconds=180,
            max_visible=2,
            scan_limit=50,
            interval_seconds=30,
        )

    def selected_ids(self, messages):
        selected = select_wreckingball_cleanup_messages(messages, now=NOW, config=self.config)
        return {message.id for message in selected}

    def test_keeps_two_fresh_matching_posts(self):
        messages = [
            make_message(1, seconds_old=20),
            make_message(2, seconds_old=40),
        ]

        self.assertEqual(self.selected_ids(messages), set())

    def test_deletes_third_and_older_matching_posts_even_when_fresh(self):
        messages = [
            make_message(1, seconds_old=10),
            make_message(2, seconds_old=20),
            make_message(3, seconds_old=30),
            make_message(4, seconds_old=40),
        ]

        self.assertEqual(self.selected_ids(messages), {3, 4})

    def test_deletes_matching_posts_older_than_age_limit(self):
        messages = [
            make_message(1, seconds_old=10),
            make_message(2, seconds_old=181),
        ]

        self.assertEqual(self.selected_ids(messages), {2})

    def test_ignores_other_authors_and_channels(self):
        messages = [
            make_message(1, seconds_old=181, author_id=111),
            make_message(2, seconds_old=181, channel_id=222),
            make_message(3, seconds_old=10),
            make_message(4, seconds_old=20),
        ]

        self.assertEqual(self.selected_ids(messages), set())

    def test_matches_application_or_webhook_identity_with_safe_getattr(self):
        app_message = make_message(1, seconds_old=10, author_id=111, application_id=DEFAULT_AUTHOR_ID)
        webhook_message = make_message(2, seconds_old=10, author_id=111, webhook_id=DEFAULT_AUTHOR_ID)

        self.assertTrue(is_wreckingball_cleanup_candidate(app_message, self.config))
        self.assertTrue(is_wreckingball_cleanup_candidate(webhook_message, self.config))
        self.assertFalse(is_wreckingball_cleanup_candidate(object(), self.config))

    def test_multi_channel_rules_keep_latest_three_music_list_posts(self):
        config = WreckingballCleanupConfig(
            enabled=True,
            channel_id=DEFAULT_CHANNEL_ID,
            author_id=DEFAULT_AUTHOR_ID,
            max_age_seconds=180,
            max_visible=2,
            scan_limit=50,
            interval_seconds=30,
            channel_rules=(
                WreckingballCleanupRule(
                    channel_id=DEFAULT_CHANNEL_ID,
                    max_age_seconds=180,
                    max_visible=2,
                    scan_limit=50,
                ),
                WreckingballCleanupRule(
                    channel_id=MUSIC_LIST_CHANNEL_ID,
                    max_age_seconds=0,
                    max_visible=3,
                    scan_limit=50,
                ),
            ),
        )
        messages = [
            make_message(1, seconds_old=1000, channel_id=MUSIC_LIST_CHANNEL_ID),
            make_message(2, seconds_old=1010, channel_id=MUSIC_LIST_CHANNEL_ID),
            make_message(3, seconds_old=1020, channel_id=MUSIC_LIST_CHANNEL_ID),
            make_message(4, seconds_old=1030, channel_id=MUSIC_LIST_CHANNEL_ID),
        ]

        selected = select_wreckingball_cleanup_messages(messages, now=NOW, config=config)

        self.assertEqual({message.id for message in selected}, {4})

    def test_finds_second_channel_rule_for_application_identity(self):
        config = WreckingballCleanupConfig(
            enabled=True,
            author_id=DEFAULT_AUTHOR_ID,
            channel_rules=(
                WreckingballCleanupRule(channel_id=DEFAULT_CHANNEL_ID),
                WreckingballCleanupRule(
                    channel_id=MUSIC_LIST_CHANNEL_ID,
                    max_age_seconds=0,
                    max_visible=3,
                    scan_limit=50,
                ),
            ),
        )
        message = make_message(
            1,
            seconds_old=10,
            channel_id=MUSIC_LIST_CHANNEL_ID,
            author_id=111,
            application_id=DEFAULT_AUTHOR_ID,
        )

        rule = matching_wreckingball_cleanup_rule(message, config)

        self.assertIsNotNone(rule)
        self.assertEqual(rule.channel_id, MUSIC_LIST_CHANNEL_ID)

    def test_from_env_builds_per_channel_overrides(self):
        with patch.dict(
            "os.environ",
            {
                "WRECKINGBALL_CLEANUP_CHANNEL_IDS": (
                    f"{DEFAULT_CHANNEL_ID},{MUSIC_LIST_CHANNEL_ID}"
                ),
                "WRECKINGBALL_CLEANUP_MAX_VISIBLE_BY_CHANNEL": (
                    f"{MUSIC_LIST_CHANNEL_ID}:3"
                ),
                "WRECKINGBALL_CLEANUP_MAX_AGE_SECONDS_BY_CHANNEL": (
                    f"{MUSIC_LIST_CHANNEL_ID}:0"
                ),
            },
        ):
            config = WreckingballCleanupConfig.from_env()

        rules = {rule.channel_id: rule for rule in config.rules}

        self.assertEqual(rules[DEFAULT_CHANNEL_ID].max_visible, 2)
        self.assertEqual(rules[DEFAULT_CHANNEL_ID].max_age_seconds, 180)
        self.assertEqual(rules[MUSIC_LIST_CHANNEL_ID].max_visible, 3)
        self.assertEqual(rules[MUSIC_LIST_CHANNEL_ID].max_age_seconds, 0)


class WreckingballCleanupDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_retries_without_reason_for_partial_messages(self):
        class PartialDeleteMessage:
            id = 123

            def __init__(self):
                self.calls = []

            async def delete(self, **kwargs):
                self.calls.append(kwargs)
                if "reason" in kwargs:
                    raise TypeError("reason is not supported")

        message = PartialDeleteMessage()
        cleanup = SimpleNamespace(config=WreckingballCleanupConfig())

        deleted = await WreckingballCleanup._delete_messages(cleanup, [message], "test")

        self.assertEqual(deleted, 1)
        self.assertEqual(message.calls, [{"reason": "LOKI THE SUN GOD Wreckingball cleanup: test"}, {}])


if __name__ == "__main__":
    unittest.main()
