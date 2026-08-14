"""Windows Credential Manager access for approved LOKI runtime secrets."""

from __future__ import annotations

import os
from typing import Any

try:
    import win32cred
except ImportError:  # pragma: no cover - exercised through the explicit None test double
    win32cred = None

TARGET_PREFIX = "LOKI/LokiTHESunGod"
SUPPORTED_SECRET_NAMES = (
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


def credential_target(name: str) -> str:
    """Return the reviewed Generic Credential target for a secret name."""

    if name not in SUPPORTED_SECRET_NAMES:
        raise ValueError(f"Unsupported credential name: {name}")
    return f"{TARGET_PREFIX}/{name}"


def _credential_was_not_found(error: Exception) -> bool:
    winerror = getattr(error, "winerror", None)
    if winerror is None and error.args:
        winerror = error.args[0]
    return winerror == 1168


def _decode_blob(blob: Any) -> str:
    if isinstance(blob, str):
        return blob
    if isinstance(blob, (bytes, bytearray)):
        return bytes(blob).decode("utf-8")
    raise TypeError("CredentialBlob must be text or UTF-8 bytes")


def read_credential(name: str) -> str | None:
    """Read one approved Generic Credential without emitting its value."""

    target = credential_target(name)
    if win32cred is None:
        return None
    try:
        credential = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception as error:
        if _credential_was_not_found(error):
            return None
        raise
    return _decode_blob(credential["CredentialBlob"])


def write_credential(name: str, value: str) -> None:
    """Write one approved secret as a persistent Generic Credential."""

    target = credential_target(name)
    if win32cred is None:
        raise RuntimeError("Windows Credential Manager support requires pywin32")
    if not isinstance(value, str) or not value:
        raise ValueError("Credential value must be non-empty text")
    win32cred.CredWrite(
        {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "UserName": os.getenv("USERNAME", ""),
            "CredentialBlob": value.encode("utf-8"),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        },
        0,
    )


def load_credentials() -> dict[str, str]:
    """Return available approved secrets, keyed by environment variable name."""

    if win32cred is None:
        return {}
    loaded: dict[str, str] = {}
    for name in SUPPORTED_SECRET_NAMES:
        value = read_credential(name)
        if value:
            loaded[name] = value
    return loaded
