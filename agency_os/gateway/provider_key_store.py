"""Encrypted storage for gateway provider API keys."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select

from agency_os import models
from agency_os.storage import Database
from agency_os.tenancy.secrets import SecretStore

logger = logging.getLogger(__name__)

# Secret namespace used for encrypting global gateway provider keys.
_PROVIDER_SECRET_NAMESPACE = "gateway-provider-keys"

_PROVIDER_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "groq": "GROQ_API_KEY",
    "custom_openai": "CUSTOM_OPENAI_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}

SUPPORTED_PROVIDER_KEYS = frozenset(_PROVIDER_ENV_MAP.keys())


class GatewayProviderKeyStore:
    """Database-backed encrypted key storage for provider credentials."""

    def __init__(self, db: Database, secret_store: SecretStore) -> None:
        self._db = db
        self._secrets = secret_store

    def set_key(self, provider: str, api_key: str) -> None:
        """Upsert encrypted key material for a provider."""
        provider_name = provider.strip().lower()
        if not provider_name:
            raise ValueError("provider must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")

        now = datetime.now(timezone.utc).isoformat()
        encrypted = self._secrets._encrypt(api_key, _PROVIDER_SECRET_NAMESPACE)

        with self._db._engine.begin() as conn:
            stmt = self._db._dialect_insert(conn, models.gateway_provider_keys).values(
                provider=provider_name,
                secret_encrypted=encrypted,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["provider"],
                set_={
                    "secret_encrypted": stmt.excluded.secret_encrypted,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            conn.execute(stmt)

    def has_key(self, provider: str) -> bool:
        """Return whether an encrypted key exists for provider."""
        provider_name = provider.strip().lower()
        if not provider_name:
            return False
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(models.gateway_provider_keys.c.provider).where(
                    models.gateway_provider_keys.c.provider == provider_name
                )
            ).fetchone()
        return row is not None

    def list_key_metadata(self) -> list[dict[str, str]]:
        """Return provider key metadata without decrypting secrets."""
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.gateway_provider_keys.c.provider,
                    models.gateway_provider_keys.c.created_at,
                    models.gateway_provider_keys.c.updated_at,
                ).order_by(models.gateway_provider_keys.c.provider.asc())
            ).fetchall()
        return [
            {
                "provider": str(row.provider),
                "created_at": str(row.created_at),
                "updated_at": str(row.updated_at),
            }
            for row in rows
        ]

    def get_key(self, provider: str) -> str | None:
        """Return decrypted key for provider if one is stored."""
        provider_name = provider.strip().lower()
        if not provider_name:
            return None
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(models.gateway_provider_keys.c.secret_encrypted).where(
                    models.gateway_provider_keys.c.provider == provider_name
                )
            ).fetchone()
        if row is None:
            return None
        try:
            return self._secrets._decrypt(
                row.secret_encrypted,
                _PROVIDER_SECRET_NAMESPACE,
            )
        except Exception:
            logger.warning(
                "Failed to decrypt gateway provider key for provider=%s",
                provider_name,
                exc_info=True,
            )
            return None

    def bootstrap_from_env(self) -> int:
        """Seed missing provider keys from env vars without overwriting stored keys."""
        imported = 0
        for provider, env_var in _PROVIDER_ENV_MAP.items():
            if self.get_key(provider):
                continue
            api_key = os.environ.get(env_var, "").strip()
            if not api_key:
                continue
            self.set_key(provider, api_key)
            imported += 1
        if imported:
            logger.info(
                "Bootstrapped %d provider key(s) into encrypted gateway key store",
                imported,
            )
        return imported
