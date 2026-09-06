from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_vapid_keys_must_be_configured_as_a_pair() -> None:
    with pytest.raises(ValidationError, match="Both VAPID"):
        Settings(vapid_public_key="public-only")


def test_push_is_enabled_only_with_both_vapid_keys() -> None:
    disabled = Settings()
    enabled = Settings(
        vapid_public_key="public",
        vapid_private_key="private",
    )

    assert disabled.push_enabled is False
    assert enabled.push_enabled is True
