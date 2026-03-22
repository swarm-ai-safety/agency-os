"""Persistent tenant registry backed by SQLite."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from agency_os.storage import Database
from agency_os.tenancy.tenant import Tenant, TenantPublic, TenantRegistry

logger = logging.getLogger(__name__)


class PersistentTenantRegistry:
    """Drop-in replacement for TenantRegistry that persists to SQLite.

    Falls back to in-memory-only operation if the database is unavailable.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get("DATABASE_PATH", "agency_os.db")
        self._fallback = TenantRegistry()
        self._db: Database | None = None
        try:
            self._db = Database(db_path)
        except Exception:
            logger.warning(
                "Could not open SQLite database at %s; running in-memory only.",
                db_path,
            )

    # -- public API (same shape as TenantRegistry) -------------------------

    def register(self, name: str, **kwargs: Any) -> tuple[Tenant, str]:
        tenant, plaintext_key = self._fallback.register(name, **kwargs)
        if self._db is not None:
            try:
                self._db.save_tenant(self._tenant_to_row(tenant))
            except Exception:
                logger.warning("Failed to persist tenant %s", tenant.tenant_id)
        return tenant, plaintext_key

    def get(self, tenant_id: str) -> Optional[Tenant]:
        # Try in-memory first (fast path)
        tenant = self._fallback.get(tenant_id)
        if tenant is not None:
            return tenant
        # Fall back to DB
        if self._db is not None:
            row = self._db.get_tenant(tenant_id)
            if row is not None:
                return self._row_to_tenant(row)
        return None

    def get_by_api_key(self, api_key: str) -> Optional[Tenant]:
        tenant = self._fallback.get_by_api_key(api_key)
        if tenant is not None:
            return tenant
        if self._db is not None:
            import hashlib

            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            row = self._db.get_tenant_by_key_hash(key_hash)
            if row is not None:
                return self._row_to_tenant(row)
        return None

    def list_all(self) -> list[TenantPublic]:
        if self._db is not None:
            try:
                rows = self._db.list_tenants()
                return [self._row_to_tenant_public(r) for r in rows]
            except Exception:
                logger.warning("DB read failed; returning in-memory tenants")
        return self._fallback.list_all()

    def deactivate(self, tenant_id: str) -> bool:
        result = self._fallback.deactivate(tenant_id)
        if self._db is not None:
            row = self._db.get_tenant(tenant_id)
            if row is not None:
                row["active"] = False
                self._db.save_tenant(row)
                return True
        return result

    # -- conversion helpers ------------------------------------------------

    @staticmethod
    def _tenant_to_row(tenant: Tenant) -> dict:
        import hashlib

        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "api_key_hash": hashlib.sha256(tenant.api_key.encode()).hexdigest(),
            "active": tenant.active,
            "metadata": tenant.metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _row_to_tenant(row: dict) -> Tenant:
        return Tenant(
            tenant_id=row["tenant_id"],
            name=row["name"],
            api_key=row.get("api_key_hash", ""),
            active=bool(row["active"]),
            metadata=row.get("metadata") or {},
        )

    @staticmethod
    def _row_to_tenant_public(row: dict) -> TenantPublic:
        return TenantPublic(
            tenant_id=row["tenant_id"],
            name=row["name"],
            active=bool(row["active"]),
            metadata=row.get("metadata") or {},
        )
