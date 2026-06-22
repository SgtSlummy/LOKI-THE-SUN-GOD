from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.services.wreckingball_cleanup import cleanup_wreckingball_messages, select_wreckingball_deletes


class FakeMessage:
    def __init__(self, message_id, created_at, *, channel_id=10, author_name="Wreckingball", bot=True, content="now playing"):
        self.id = message_id
        self.created_at = created_at
        self.channel = SimpleNamespace(id=channel_id)
        self.author = SimpleNamespace(name=author_name, display_name=author_name, bot=bot, id=999)
        self.content = content
        self.delete_calls = 0

    async def delete(self, reason=None):
        self.delete_calls += 1
        self.delete_reason = reason


def make_messages(count, *, channel_id=10):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [FakeMessage(i + 1, base + timedelta(minutes=i), channel_id=channel_id) for i in range(count)]


def test_keep_last_two_selects_older_wreckingball_messages_for_delete_per_channel():
    messages = make_messages(5)

    selected = select_wreckingball_deletes(messages, keep=2)

    assert [message.id for message in selected] == [1, 2, 3]


def test_keep_last_two_is_per_channel_not_global():
    messages = make_messages(3, channel_id=10) + make_messages(3, channel_id=20)

    selected = select_wreckingball_deletes(messages, keep=2)

    assert [(message.channel.id, message.id) for message in selected] == [(10, 1), (20, 1)]


def test_cleanup_selection_ignores_non_wreckingball_and_user_messages():
    messages = make_messages(3)
    messages.append(FakeMessage(10, datetime.now(timezone.utc), author_name="Wreckingball", bot=False))
    messages.append(FakeMessage(11, datetime.now(timezone.utc), author_name="Other Bot", bot=True))

    selected = select_wreckingball_deletes(messages, keep=2)

    assert [message.id for message in selected] == [1]


@pytest.mark.asyncio
async def test_cleanup_dry_run_returns_delete_plan_without_calling_delete():
    messages = make_messages(4)

    result = await cleanup_wreckingball_messages(messages, dry_run=True, keep=2)

    assert result.planned_delete_ids == [1, 2]
    assert result.deleted_ids == []
    assert all(message.delete_calls == 0 for message in messages)


@pytest.mark.asyncio
async def test_cleanup_live_deletes_only_selected_messages():
    messages = make_messages(4)

    result = await cleanup_wreckingball_messages(messages, dry_run=False, keep=2)

    assert result.planned_delete_ids == [1, 2]
    assert result.deleted_ids == [1, 2]
    assert [message.delete_calls for message in messages] == [1, 1, 0, 0]
