import pytest

from bot.settings import Settings


def test_relay_media_channel_ids_parse_from_env_json(monkeypatch):
    monkeypatch.setenv("RELAY_MEDIA_CHANNEL_IDS_JSON", '{"messages": "10", "pictures": 20, "gifs": 30, "emotes": 40}')

    settings = Settings.from_env()

    assert settings.relay_media_channel_ids == {"messages": 10, "pictures": 20, "gifs": 30, "emotes": 40}


def test_relay_media_channel_ids_reject_unknown_keys():
    settings = Settings(relay_media_channel_ids_json='{"unknown": 1}')

    with pytest.raises(RuntimeError, match="Unsupported relay media channel key"):
        settings.relay_media_channel_ids
