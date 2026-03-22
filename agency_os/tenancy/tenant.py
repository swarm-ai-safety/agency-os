"""Tenant model and registry for multi-tenant isolation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Tenant(BaseModel):
    """A tenant (customer) in the system."""

    tenant_id: str = Field(default_factory=lambda: f"tenant-{uuid.uuid4().hex}")
    name: str
    api_key: str = Field(default_factory=lambda: f"ak-{secrets.token_urlsafe(32)}")
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenantPublic(BaseModel):
    """Public-facing tenant view (excludes secrets)."""

    tenant_id: str
    name: str
    active: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenantRegistry:
    """Tenant registry backed by SQLite via Database.

    Keeps an in-memory index for fast API key lookups while
    persisting all mutations to the database.
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._tenants: dict[str, Tenant] = {}
        self._by_key_hash: dict[str, Tenant] = {}  # hash(api_key) -> tenant
        if db is not None:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Load all tenants from the database into the in-memory index.

        DB stores only the key hash — tenants loaded from DB cannot be
        looked up by API key until they authenticate (the plaintext key
        is only known to the tenant). We index by stored hash so that
        get_by_api_key() can hash the incoming key and match it.
        """
        if self._db is None:
            return
        rows = self._db.list_tenants()
        for row in rows:
            stored_hash = row.get("api_key_hash", "")
            tenant = Tenant(
                tenant_id=row["tenant_id"],
                name=row["name"],
                api_key=stored_hash,  # placeholder — not the real key
                active=bool(row["active"]),
                metadata=row.get("metadata") or {},
            )
            # Mark that this tenant was loaded from DB (no plaintext key)
            tenant._from_db = True  # type: ignore[attr-defined]
            self._tenants[tenant.tenant_id] = tenant
            if tenant.active and stored_hash:
                self._by_key_hash[stored_hash] = tenant
        logger.info("Loaded %d tenants from database", len(self._tenants))

    def _persist(self, tenant: Tenant) -> None:
        """Write tenant state to the database.

        Only the SHA-256 hash of the API key is stored — never the
        plaintext key.
        """
        if self._db is None:
            return
        # If tenant was loaded from DB or already has hash in memory,
        # api_key already contains the hash — don't hash again
        if getattr(tenant, "_from_db", False):
            key_hash = tenant.api_key
        else:
            key_hash = self._hash_key(tenant.api_key)
        self._db.save_tenant(
            {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "api_key_hash": key_hash,
                "active": tenant.active,
                "metadata": tenant.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def register(self, name: str, **kwargs: Any) -> tuple[Tenant, str]:
        """Create and register a new tenant.

        Returns (tenant, plaintext_api_key). The plaintext key is NOT
        retained on the tenant object — only the hash is kept in memory.
        """
        tenant = Tenant(name=name, **kwargs)
        plaintext_key = tenant.api_key
        key_hash = self._hash_key(plaintext_key)
        self._tenants[tenant.tenant_id] = tenant
        self._by_key_hash[key_hash] = tenant
        self._persist(tenant)
        # Replace plaintext with hash in memory
        tenant.api_key = key_hash
        tenant._from_db = True  # type: ignore[attr-defined]
        return tenant, plaintext_key

    def get(self, tenant_id: str) -> Optional[Tenant]:
        return self._tenants.get(tenant_id)

    def get_by_api_key(self, api_key: str) -> Optional[Tenant]:
        """Constant-time API key lookup using hash comparison.

        Hashes the incoming key and looks it up in the index.
        Uses hmac.compare_digest on the hashes to prevent timing attacks.
        """
        key_hash = self._hash_key(api_key)
        tenant = self._by_key_hash.get(key_hash)
        if tenant is None:
            return None
        # For DB-loaded tenants, api_key holds the hash; compare hashes.
        # For freshly-registered tenants, api_key is plaintext; hash and compare.
        stored = tenant.api_key
        if getattr(tenant, "_from_db", False):
            # tenant.api_key is already the hash
            if hmac.compare_digest(key_hash, stored):
                return tenant
        else:
            # tenant.api_key is plaintext — compare hashes
            if hmac.compare_digest(key_hash, self._hash_key(stored)):
                return tenant
        return None

    def list_all(self) -> list[TenantPublic]:
        """List all tenants (public view, no API keys)."""
        return [
            TenantPublic(
                tenant_id=t.tenant_id,
                name=t.name,
                active=t.active,
                metadata=t.metadata,
            )
            for t in self._tenants.values()
        ]

    def deactivate(self, tenant_id: str) -> bool:
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.active = False
            # Remove from key index — handle both hash and plaintext forms
            if getattr(tenant, "_from_db", False):
                self._by_key_hash.pop(tenant.api_key, None)
            else:
                self._by_key_hash.pop(self._hash_key(tenant.api_key), None)
            self._persist(tenant)
            return True
        return False

    def save_metadata(self, tenant: Tenant) -> None:
        """Persist tenant metadata changes to the database."""
        self._persist(tenant)

    def find_by_metadata(self, key: str, value: Any) -> Optional["Tenant"]:
        """Find a tenant by a metadata key-value pair.

        When multiple tenants match (e.g. duplicate emails from before
        uniqueness enforcement), returns the most recently created one
        since it has the most current password hash.
        """
        matches: list[Tenant] = []
        for tenant in self._tenants.values():
            if tenant.metadata.get(key) == value:
                matches.append(tenant)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        # Most recently created tenant (highest tenant_id hex suffix)
        return max(matches, key=lambda t: t.tenant_id)

    def email_exists(self, email: str) -> bool:
        """Check if any active tenant already uses this email."""
        email = email.lower().strip()
        for tenant in self._tenants.values():
            if tenant.active and tenant.metadata.get("email") == email:
                return True
        return False

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Hash an API key for index lookup."""
        return hashlib.sha256(api_key.encode()).hexdigest()
