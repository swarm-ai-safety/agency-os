"""Password hashing and verification helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 260_000


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{_ALGO}${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded_hash: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False
    try:
        algo, iterations_raw, salt_b64, digest_b64 = encoded_hash.split("$", maxsplit=3)
        if algo != _ALGO:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate, expected_digest)
