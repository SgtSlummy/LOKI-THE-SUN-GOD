from __future__ import annotations

from utils.discord_migration import bot_role_delta, identify_old_loki_bot, render_legacy_bot_report
from utils.hermes_loki_bridge import normalize_hermes_prompt, should_post_transcript_to_discord


def test_hermes_prompt_normalizes_to_loki_address():
    assert normalize_hermes_prompt("are you online?") == "Hermes operator says: are you online?"
    assert normalize_hermes_prompt("  LOKI check status  ") == "Hermes operator says: LOKI check status"


def test_hermes_transcript_posting_requires_channel_and_opt_in():
    assert not should_post_transcript_to_discord(channel_id="", post=False)
    assert not should_post_transcript_to_discord(channel_id="123", post=False)
    assert should_post_transcript_to_discord(channel_id="123", post=True)


def test_identify_old_loki_bot_ignores_current_and_finds_legacy_loki():
    members = [
        {"user": {"id": "983", "username": "Diva Premium", "bot": True}, "roles": ["dj"]},
        {
            "user": {"id": "old", "username": "LOKI (┛◉Д◉)┛彡┻━┻ THE SUN GOD", "bot": True},
            "roles": ["ralph", "sun", "robots"],
        },
        {"user": {"id": "new", "username": "LOKI THE SUN GOD", "bot": True}, "roles": ["robots", "loki"]},
    ]

    old_bot = identify_old_loki_bot(members, current_bot_id="new")

    assert old_bot is not None
    assert old_bot["user"]["id"] == "old"


def test_bot_role_delta_assumes_old_roles_without_duplicate_current_roles():
    assert bot_role_delta(old_role_ids=["ralph", "sun", "robots"], current_role_ids=["robots", "loki"]) == [
        "ralph",
        "sun",
    ]


def test_render_legacy_bot_report_includes_researched_messages_and_actions():
    report = render_legacy_bot_report(
        guild_name="VIBEZ",
        old_bot={"user": {"id": "old", "username": "Old LOKI"}, "roles": ["ralph"]},
        current_bot={"user": {"id": "new", "username": "LOKI THE SUN GOD"}, "roles": ["loki"]},
        roles_by_id={"ralph": {"name": "Ralph Wiggum"}, "loki": {"name": "LOKI THE SUN GOD"}},
        old_messages=[{"channel_name": "gen-chat", "content": "old behavior"}],
        roles_to_assume=["ralph"],
        executed=True,
    )

    assert "Old LOKI" in report
    assert "Ralph Wiggum" in report
    assert "old behavior" in report
    assert "Executed: yes" in report
