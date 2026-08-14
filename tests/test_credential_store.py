from __future__ import annotations

import pytest

from utils import credential_store


class MissingCredentialError(Exception):
    winerror = 1168


class FakeWin32Cred:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        self.credentials: dict[str, bytes] = {}
        self.writes: list[tuple[dict[str, object], int]] = []

    def CredRead(self, target: str, credential_type: int, flags: int) -> dict[str, bytes]:
        assert credential_type == self.CRED_TYPE_GENERIC
        assert flags == 0
        if target not in self.credentials:
            raise MissingCredentialError
        return {"CredentialBlob": self.credentials[target]}

    def CredWrite(self, credential: dict[str, object], flags: int) -> None:
        self.writes.append((credential, flags))
        blob = credential["CredentialBlob"]
        assert isinstance(blob, str)
        self.credentials[str(credential["TargetName"])] = blob.encode("utf-16-le")


def test_supported_secret_names_are_exact() -> None:
    assert credential_store.SUPPORTED_SECRET_NAMES == (
        "DISCORD_TOKEN",
        "DISCORD_CLIENT_SECRET",
        "DASHBOARD_SECRET_KEY",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "TAROT_ROUTER_API_KEY",
        "AUTODM_DISCORD_BACKEND_TOKEN",
        "LAVALINK_PASSWORD",
        "ACTIVITY_BRIDGE_TOKEN",
        "OBS_WEBSOCKET_PASSWORD",
        "TWITCH_CLIENT_SECRET",
    )


def test_credential_target_rejects_unknown_names() -> None:
    assert credential_store.credential_target("DISCORD_TOKEN") == "LOKI/LokiTHESunGod/DISCORD_TOKEN"
    with pytest.raises(ValueError, match="Unsupported credential name"):
        credential_store.credential_target("UNREVIEWED_SECRET")


def test_read_and_write_generic_credential_without_output(monkeypatch, capsys) -> None:
    backend = FakeWin32Cred()
    monkeypatch.setattr(credential_store, "win32cred", backend)

    credential_store.write_credential("DISCORD_TOKEN", "managed-☀-value")

    target = "LOKI/LokiTHESunGod/DISCORD_TOKEN"
    assert credential_store.read_credential("DISCORD_TOKEN") == "managed-☀-value"
    written, flags = backend.writes[0]
    assert written["Type"] == backend.CRED_TYPE_GENERIC
    assert written["TargetName"] == target
    assert written["Persist"] == backend.CRED_PERSIST_LOCAL_MACHINE
    assert written["CredentialBlob"] == "managed-☀-value"
    assert isinstance(written["CredentialBlob"], str)
    assert flags == 0
    assert capsys.readouterr() == ("", "")


def test_missing_or_unavailable_credential_manager_returns_no_values(monkeypatch) -> None:
    backend = FakeWin32Cred()
    monkeypatch.setattr(credential_store, "win32cred", backend)
    assert credential_store.read_credential("DISCORD_TOKEN") is None

    monkeypatch.setattr(credential_store, "win32cred", None)
    assert credential_store.read_credential("DISCORD_TOKEN") is None
    assert credential_store.load_credentials() == {}


def test_load_credentials_only_returns_present_supported_values(monkeypatch) -> None:
    backend = FakeWin32Cred()
    backend.credentials["LOKI/LokiTHESunGod/OPENAI_API_KEY"] = "managed-key".encode("utf-16-le")
    monkeypatch.setattr(credential_store, "win32cred", backend)

    assert credential_store.load_credentials() == {"OPENAI_API_KEY": "managed-key"}


def test_read_credential_removes_only_one_optional_trailing_nul(monkeypatch) -> None:
    backend = FakeWin32Cred()
    backend.credentials["LOKI/LokiTHESunGod/DISCORD_TOKEN"] = "managed-value\0\0".encode("utf-16-le")
    monkeypatch.setattr(credential_store, "win32cred", backend)

    assert credential_store.read_credential("DISCORD_TOKEN") == "managed-value\0"
