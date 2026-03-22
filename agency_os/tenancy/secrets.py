"""Encrypted per-tenant secret storage using Fernet symmetric encryption."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional, cast

from cryptography.fernet import Fernet


class SecretStore:
    """
    Per-tenant encrypted secret storage using Fernet (AES-128-CBC + HMAC-SHA256).

    Each tenant gets a unique encryption key derived from the master key
    and the tenant ID.
    """

    def __init__(self, master_key: str | None = None):
        raw_key = master_key or os.environ.get("AGENCY_OS_SECRET_KEY")
        if not raw_key:
            raise ValueError(
                "No encryption key provided. Set AGENCY_OS_SECRET_KEY or "
                "pass master_key to SecretStore."
            )
        self._master_key = raw_key.encode()
        self._stores: dict[
            str, dict[str, str]
        ] = {}  # tenant_id -> {key -> encrypted_value}

    def set_secret(self, tenant_id: str, key: str, value: str) -> None:
        """Store an encrypted secret for a tenant."""
        if tenant_id not in self._stores:
            self._stores[tenant_id] = {}
        self._stores[tenant_id][key] = self._encrypt(value, tenant_id)

    def get_secret(self, tenant_id: str, key: str) -> Optional[str]:
        """Retrieve a decrypted secret for a tenant."""
        encrypted = self._stores.get(tenant_id, {}).get(key)
        if encrypted is None:
            return None
        return self._decrypt(encrypted, tenant_id)

    def delete_secret(self, tenant_id: str, key: str) -> bool:
        """Delete a secret."""
        if tenant_id in self._stores and key in self._stores[tenant_id]:
            del self._stores[tenant_id][key]
            return True
        return False

    def list_keys(self, tenant_id: str) -> list[str]:
        """List secret keys for a tenant (not values)."""
        return list(self._stores.get(tenant_id, {}).keys())

    def _derive_fernet_key(self, tenant_id: str) -> bytes:
        """Derive a per-tenant Fernet key from master key + tenant ID using PBKDF2."""
        # PBKDF2-HMAC-SHA256 with tenant_id as salt; 480k iterations per OWASP 2023.
        # Produces 32 bytes; Fernet needs url-safe base64-encoded 32 bytes.
        raw = hashlib.pbkdf2_hmac(
            "sha256",
            self._master_key,
            tenant_id.encode(),
            iterations=480_000,
            dklen=32,
        )
        return base64.urlsafe_b64encode(raw)

    def _encrypt(self, plaintext: str, tenant_id: str) -> str:
        """Encrypt a secret using Fernet."""
        f = Fernet(self._derive_fernet_key(tenant_id))
        return cast(str, f.encrypt(plaintext.encode()).decode())

    def _decrypt(self, ciphertext: str, tenant_id: str) -> str:
        """Decrypt a secret using Fernet."""
        f = Fernet(self._derive_fernet_key(tenant_id))
        return cast(str, f.decrypt(ciphertext.encode()).decode())
