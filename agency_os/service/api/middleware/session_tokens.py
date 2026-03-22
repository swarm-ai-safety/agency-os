"""Signed tenant session tokens for dashboard authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

_DEFAULT_TTL_SECONDS = 8 * 60 * 60


def _secret() -> bytes:
    value = os.environ.get("AGENCY_OS_SESSION_TOKEN_SECRET", "").strip()
    if not value:
        env = os.environ.get("ENV", "").lower()
        if env in ("production", "prod"):
            raise RuntimeError(
                "AGENCY_OS_SESSION_TOKEN_SECRET must be set in production"
            )
        # Dev/test fallback only.
        value = "agency-os-dev-session-secret"
    return value.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_tenant_session_token(tenant_id: str, ttl_seconds: int | None = None) -> str:
    if ttl_seconds is not None and ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer")

    now = int(time.time())
    ttl = _DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    payload: dict[str, Any] = {
        "sub": tenant_id,
        "iat": now,
        "exp": now + ttl,
        "iss": "agency-os",
        "type": "tenant_session",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_segment = _b64url_encode(payload_bytes)
    signature = hmac.new(
        _secret(), payload_segment.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload_segment}.{_b64url_encode(signature)}"


def verify_tenant_session_token(token: str) -> dict[str, Any] | None:
    if not isinstance(token, str) or not token:
        return None

    try:
        payload_segment, signature_segment = token.split(".", maxsplit=1)
    except ValueError:
        return None

    expected = hmac.new(
        _secret(), payload_segment.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        actual = _b64url_decode(signature_segment)
    except Exception:
        return None

    if not hmac.compare_digest(expected, actual):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_segment))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    if payload.get("iss") != "agency-os" or payload.get("type") != "tenant_session":
        return None

    exp = payload.get("exp")
    sub = payload.get("sub")
    if not isinstance(exp, int) or not isinstance(sub, str) or not sub.strip():
        return None
    if exp <= int(time.time()):
        return None
    return payload


def create_persistent_session_token() -> str:
    """Create an opaque token for DB-backed persistent sessions."""
    return f"ts-{secrets.token_urlsafe(48)}"


def hash_persistent_session_token(token: str) -> str:
    """Hash opaque session tokens before storing/lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
