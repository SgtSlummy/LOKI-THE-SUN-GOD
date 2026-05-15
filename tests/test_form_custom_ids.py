from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.form_ids import (  # noqa: E402
    DISCORD_CUSTOM_ID_MAX_LENGTH,
    MAX_FORM_NAME_LENGTH,
    form_custom_id,
    normalize_form_name,
)


def test_form_custom_id_allows_longest_safe_discord_snowflake() -> None:
    guild_id = int("9" * 20)
    form_name = "a" * MAX_FORM_NAME_LENGTH

    custom_id = form_custom_id(guild_id, form_name)

    assert custom_id == f"form::{guild_id}::{form_name}"
    assert len(custom_id) == DISCORD_CUSTOM_ID_MAX_LENGTH


def test_form_name_rejects_values_that_would_overflow_component_custom_id() -> None:
    with pytest.raises(ValueError, match=str(MAX_FORM_NAME_LENGTH)):
        normalize_form_name("a" * (MAX_FORM_NAME_LENGTH + 1))


def test_form_name_normalization_preserves_existing_lowercase_contract() -> None:
    assert normalize_form_name(" IntakeForm ") == "intakeform"


if __name__ == "__main__":
    test_form_custom_id_allows_longest_safe_discord_snowflake()
    test_form_name_rejects_values_that_would_overflow_component_custom_id()
    test_form_name_normalization_preserves_existing_lowercase_contract()
    print("form custom_id bounds passed")
