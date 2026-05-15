from __future__ import annotations

DISCORD_CUSTOM_ID_MAX_LENGTH = 100
MAX_DISCORD_SNOWFLAKE_DIGITS = 20
FORM_CUSTOM_ID_PREFIX = "form::"
FORM_CUSTOM_ID_SEPARATOR = "::"
MAX_FORM_NAME_LENGTH = (
    DISCORD_CUSTOM_ID_MAX_LENGTH
    - len(FORM_CUSTOM_ID_PREFIX)
    - MAX_DISCORD_SNOWFLAKE_DIGITS
    - len(FORM_CUSTOM_ID_SEPARATOR)
)


def normalize_form_name(name: str) -> str:
    normalized = str(name or "").strip().lower()
    if not normalized:
        raise ValueError("Form name is required.")
    if len(normalized) > MAX_FORM_NAME_LENGTH:
        raise ValueError(f"Form names must be {MAX_FORM_NAME_LENGTH} characters or fewer.")
    return normalized


def form_custom_id(guild_id: int, form_name: str) -> str:
    normalized = normalize_form_name(form_name)
    custom_id = f"{FORM_CUSTOM_ID_PREFIX}{int(guild_id)}{FORM_CUSTOM_ID_SEPARATOR}{normalized}"
    if len(custom_id) > DISCORD_CUSTOM_ID_MAX_LENGTH:
        raise ValueError(
            f"Form button custom_id must be {DISCORD_CUSTOM_ID_MAX_LENGTH} characters or fewer."
        )
    return custom_id
