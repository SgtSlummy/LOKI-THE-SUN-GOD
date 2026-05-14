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


def test_slash_command_sync_is_enabled_by_default_for_dual_natural_and_slash_ux(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path)

    assert bot_module.should_sync_slash_commands() is True


def test_slash_command_sync_can_be_disabled_by_operator(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path, LOKI_ENABLE_SLASH_SYNC="false", LOKI_NATURAL_LANGUAGE_ONLY="true")

    assert bot_module.should_sync_slash_commands() is False


def test_presence_prompts_members_to_talk_or_use_slash_commands(monkeypatch, tmp_path):
    bot_module = reload_bot(monkeypatch, tmp_path, PREFIX="!")

    assert bot_module.presence_activity_name() == "Talk to LOKI or use / commands | LOKI THE SUN GOD"
    assert "/ commands" in bot_module.presence_activity_name()
    assert "!" not in bot_module.presence_activity_name()
