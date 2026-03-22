"""Per-tenant encrypted storage for BYOK (Bring Your Own Key) provider API keys."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from agency_os import models
from agency_os.storage import Database
from agency_os.tenancy.secrets import SecretStore

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = frozenset(
    {
        "openai",
        "anthropic",
        "together",
        "fireworks",
        "groq",
        "custom_openai",
        "ollama",
    }
)


def _key_fingerprint(api_key: str) -> str:
    """Return first 8 hex chars of SHA-256 hash of the key (for display, not security)."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:8]


class TenantProviderKeyStore:
    """Encrypted per-tenant storage for provider API keys (BYOK).

    Uses the existing SecretStore (Fernet / PBKDF2) for encryption,
    with each tenant's own derived key.  Keys are persisted to the
    ``tenant_provider_keys`` table.
    """

    def __init__(self, db: Database, secret_store: SecretStore) -> None:
        self._db = db
        self._secrets = secret_store

    def set_key(self, tenant_id: str, provider: str, api_key: str) -> str:
        """Store (or overwrite) an encrypted provider key for a tenant.

        Returns the key fingerprint.
        """
        provider = provider.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{provider}'. "
                f"Supported: {sorted(SUPPORTED_PROVIDERS)}"
            )
        if not api_key.strip():
            raise ValueError("api_key must not be empty")

        now = datetime.now(timezone.utc).isoformat()
        encrypted = self._secrets._encrypt(api_key, tenant_id)
        fingerprint = _key_fingerprint(api_key)

        with self._db._engine.begin() as conn:
            stmt = self._db._dialect_insert(conn, models.tenant_provider_keys).values(
                tenant_id=tenant_id,
                provider=provider,
                secret_encrypted=encrypted,
                key_fingerprint=fingerprint,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "provider"],
                set_={
                    "secret_encrypted": stmt.excluded.secret_encrypted,
                    "key_fingerprint": stmt.excluded.key_fingerprint,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            conn.execute(stmt)

        logger.info(
            "Stored BYOK key for tenant=%s provider=%s fingerprint=%s",
            tenant_id,
            provider,
            fingerprint,
        )
        return fingerprint

    def get_key(self, tenant_id: str, provider: str) -> str | None:
        """Return the decrypted provider key, or None if not set."""
        provider = provider.strip().lower()
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(models.tenant_provider_keys.c.secret_encrypted).where(
                    models.tenant_provider_keys.c.tenant_id == tenant_id,
                    models.tenant_provider_keys.c.provider == provider,
                )
            ).fetchone()
        if row is None:
            return None
        try:
            return self._secrets._decrypt(row.secret_encrypted, tenant_id)
        except Exception:
            logger.warning(
                "Failed to decrypt BYOK key for tenant=%s provider=%s",
                tenant_id,
                provider,
                exc_info=True,
            )
            return None

    def delete_key(self, tenant_id: str, provider: str) -> bool:
        """Remove a stored provider key. Returns True if a key was deleted."""
        provider = provider.strip().lower()
        with self._db._engine.begin() as conn:
            result = conn.execute(
                delete(models.tenant_provider_keys).where(
                    models.tenant_provider_keys.c.tenant_id == tenant_id,
                    models.tenant_provider_keys.c.provider == provider,
                )
            )
        deleted = result.rowcount > 0
        if deleted:
            logger.info(
                "Deleted BYOK key for tenant=%s provider=%s",
                tenant_id,
                provider,
            )
        return deleted

    def list_providers(self, tenant_id: str) -> list[dict[str, str]]:
        """List provider key metadata for a tenant (never returns secrets)."""
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.tenant_provider_keys.c.provider,
                    models.tenant_provider_keys.c.key_fingerprint,
                    models.tenant_provider_keys.c.created_at,
                    models.tenant_provider_keys.c.updated_at,
                )
                .where(models.tenant_provider_keys.c.tenant_id == tenant_id)
                .order_by(models.tenant_provider_keys.c.provider.asc())
            ).fetchall()
        return [
            {
                "provider": str(row.provider),
                "key_fingerprint": str(row.key_fingerprint),
                "created_at": str(row.created_at),
                "updated_at": str(row.updated_at),
            }
            for row in rows
        ]

    def has_key(self, tenant_id: str, provider: str) -> bool:
        """Check if a tenant has a key stored for a provider."""
        provider = provider.strip().lower()
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(models.tenant_provider_keys.c.provider).where(
                    models.tenant_provider_keys.c.tenant_id == tenant_id,
                    models.tenant_provider_keys.c.provider == provider,
                )
            ).fetchone()
        return row is not None
