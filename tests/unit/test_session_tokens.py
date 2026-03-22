"""Unit tests for tenant session token helpers."""

from __future__ import annotations

import pytest

from agency_os.service.api.middleware.session_tokens import (
    create_persistent_session_token,
    create_tenant_session_token,
    hash_persistent_session_token,
    verify_tenant_session_token,
)


def test_create_uses_default_ttl_when_none() -> None:
    token = create_tenant_session_token("tenant-123", ttl_seconds=None)
    payload = verify_tenant_session_token(token)
    assert payload is not None
    assert payload["exp"] - payload["iat"] == 8 * 60 * 60


def test_create_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValueError):
        create_tenant_session_token("tenant-123", ttl_seconds=0)
    with pytest.raises(ValueError):
        create_tenant_session_token("tenant-123", ttl_seconds=-5)


def test_verify_returns_none_for_non_string_token_input() -> None:
    assert verify_tenant_session_token("") is None
    assert verify_tenant_session_token(None) is None  # type: ignore[arg-type]
    assert verify_tenant_session_token(123) is None  # type: ignore[arg-type]


def test_persistent_token_generation_and_hashing() -> None:
    token_a = create_persistent_session_token()
    token_b = create_persistent_session_token()
    assert token_a.startswith("ts-")
    assert token_b.startswith("ts-")
    assert token_a != token_b
    assert hash_persistent_session_token(token_a) != hash_persistent_session_token(
        token_b
    )
