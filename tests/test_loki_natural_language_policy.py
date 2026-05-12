from __future__ import annotations

import importlib


def reload_bot(monkeypatch, tmp_path, **env):
    tmp_path.joinpath(".env").write_text("", encoding="utf-8")
    monkeypatch.setenv("LOKI_APP_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for name in ("LOKI_ENABLE_SLASH_SYNC", "LOKI_NATURAL_LANGUAGE_ONLY", "PREFIX"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import bot

    return importlib.reload(bot)


def test_slash_command_sync_is_disabled_by_default_for_natural_language_discord_ux(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path)

    assert bot_module.should_sync_slash_commands() is False


def test_slash_command_sync_requires_explicit_operator_opt_in(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path, LOKI_ENABLE_SLASH_SYNC="true", LOKI_NATURAL_LANGUAGE_ONLY="false")

    assert bot_module.should_sync_slash_commands() is True


def test_presence_prompts_members_to_talk_naturally_not_use_slash_commands(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path, PREFIX="!")

    assert bot_module.presence_activity_name() == "Talk to LOKI naturally | LOKI THE SON GOD"
    assert "/" not in bot_module.presence_activity_name()
    assert "!" not in bot_module.presence_activity_name()
