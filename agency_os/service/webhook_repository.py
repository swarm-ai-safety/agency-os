"""Database-backed webhook subscription repository with encrypted secrets."""

from __future__ import annotations

import builtins
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, insert, select, update

from agency_os import models
from agency_os.service.webhooks import WebhookDispatcher
from agency_os.storage import Database
from agency_os.tenancy.secrets import SecretStore


class WebhookRepository:
    """Manages webhook subscriptions with database persistence and secret encryption.

    Responsibilities:
    - Persist webhook subscriptions to database
    - Encrypt/decrypt webhook signing secrets using SecretStore
    - Sync WebhookDispatcher state with database
    - Handle secret rotation
    """

    def __init__(
        self, db: Database, dispatcher: WebhookDispatcher, secret_store: SecretStore
    ):
        self._db = db
        self._dispatcher = dispatcher
        self._secrets = secret_store

    def create(
        self,
        tenant_id: str,
        url: str,
        events: list[str],
        secret: str | None = None,
    ) -> dict[str, Any]:
        """Create a new webhook subscription.

        Returns dict with webhook details including plaintext secret (only returned once).
        """
        webhook_id = str(uuid4())
        generated_secret = secret or secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).isoformat()

        # Encrypt secret for storage
        encrypted_secret = self._secrets._encrypt(generated_secret, tenant_id)

        # Insert into database
        with self._db._engine.begin() as conn:
            conn.execute(
                insert(models.webhooks).values(
                    id=webhook_id,
                    tenant_id=tenant_id,
                    url=url,
                    events=json.dumps(events),
                    secret_encrypted=encrypted_secret,
                    created_at=now,
                    rotated_at=None,
                )
            )

        # Sync to dispatcher
        self._dispatcher.subscribe(
            org_id=tenant_id,
            url=url,
            events=events,
            secret=generated_secret,
            webhook_id=webhook_id,
        )

        return {
            "id": webhook_id,
            "url": url,
            "events": events,
            "secret": generated_secret,  # Only returned on creation
            "created_at": now,
        }

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        """List all webhooks for a tenant (secrets not included)."""
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.webhooks.c.id,
                    models.webhooks.c.url,
                    models.webhooks.c.events,
                    models.webhooks.c.created_at,
                    models.webhooks.c.rotated_at,
                ).where(models.webhooks.c.tenant_id == tenant_id)
            ).fetchall()

        return [
            {
                "id": row.id,
                "url": row.url,
                "events": json.loads(row.events),
                "created_at": row.created_at,
                "rotated_at": row.rotated_at,
            }
            for row in rows
        ]

    def get(self, webhook_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Get webhook details by ID (secret not included)."""
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(
                    models.webhooks.c.id,
                    models.webhooks.c.url,
                    models.webhooks.c.events,
                    models.webhooks.c.created_at,
                    models.webhooks.c.rotated_at,
                ).where(
                    models.webhooks.c.id == webhook_id,
                    models.webhooks.c.tenant_id == tenant_id,
                )
            ).fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "url": row.url,
            "events": json.loads(row.events),
            "created_at": row.created_at,
            "rotated_at": row.rotated_at,
        }

    def delete(self, webhook_id: str, tenant_id: str) -> bool:
        """Delete a webhook subscription."""
        with self._db._engine.begin() as conn:
            row = conn.execute(
                select(models.webhooks.c.url).where(
                    models.webhooks.c.id == webhook_id,
                    models.webhooks.c.tenant_id == tenant_id,
                )
            ).fetchone()
            if not row:
                return False
            url = row.url
            result = conn.execute(
                delete(models.webhooks).where(
                    models.webhooks.c.id == webhook_id,
                    models.webhooks.c.tenant_id == tenant_id,
                )
            )

        # Sync to dispatcher
        if result.rowcount > 0:
            self._dispatcher.unsubscribe(org_id=tenant_id, url=url)
            return True

        return False

    def rotate_secret(self, webhook_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Rotate webhook signing secret. Returns new secret (only time it's returned)."""
        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(models.webhooks.c.url, models.webhooks.c.events).where(
                    models.webhooks.c.id == webhook_id,
                    models.webhooks.c.tenant_id == tenant_id,
                )
            ).fetchone()

        if not row:
            return None

        url, events_json = row.url, row.events
        events = json.loads(events_json)

        # Generate new secret
        new_secret = secrets.token_urlsafe(32)
        encrypted_secret = self._secrets._encrypt(new_secret, tenant_id)
        now = datetime.now(timezone.utc).isoformat()

        # Update database
        with self._db._engine.begin() as conn:
            conn.execute(
                update(models.webhooks)
                .where(
                    models.webhooks.c.id == webhook_id,
                    models.webhooks.c.tenant_id == tenant_id,
                )
                .values(secret_encrypted=encrypted_secret, rotated_at=now)
            )

        # Sync to dispatcher (replaces existing subscription for same URL)
        self._dispatcher.subscribe(
            org_id=tenant_id,
            url=url,
            events=events,
            secret=new_secret,
            webhook_id=webhook_id,
        )

        return {
            "id": webhook_id,
            "url": url,
            "secret": new_secret,  # Only returned on rotation
            "rotated_at": now,
        }

    def load_all(self) -> None:
        """Load all webhooks from database into dispatcher (called on startup)."""
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.webhooks.c.id,
                    models.webhooks.c.tenant_id,
                    models.webhooks.c.url,
                    models.webhooks.c.events,
                    models.webhooks.c.secret_encrypted,
                )
            ).fetchall()

        for row in rows:
            events = json.loads(row.events)

            # Decrypt secret
            plaintext_secret = self._secrets._decrypt(
                row.secret_encrypted, row.tenant_id
            )

            # Load into dispatcher
            self._dispatcher.subscribe(
                org_id=row.tenant_id,
                url=row.url,
                events=events,
                secret=plaintext_secret,
                webhook_id=row.id,
            )

    def create_delivery_record(
        self,
        *,
        webhook_id: str | None,
        tenant_id: str,
        url: str,
        event_type: str,
        org_id: str,
        payload_json: str,
        signature: str,
        event_timestamp: int,
        max_attempts: int,
    ) -> str:
        """Create delivery record and return delivery ID."""
        delivery_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._db._engine.begin() as conn:
            conn.execute(
                insert(models.webhook_deliveries).values(
                    id=delivery_id,
                    webhook_id=webhook_id,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    url=url,
                    event_type=event_type,
                    payload_json=payload_json,
                    signature=signature,
                    event_timestamp=event_timestamp,
                    attempt_count=0,
                    max_attempts=max_attempts,
                    retryable=False,
                    success=False,
                    status_code=None,
                    error=None,
                    next_retry_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return delivery_id

    def record_delivery_attempt(
        self,
        *,
        delivery_id: str,
        attempt_number: int,
        success: bool,
        status_code: int | None,
        error: str | None,
        retryable: bool,
        next_retry_at: str | None,
    ) -> None:
        """Persist result of a delivery attempt."""
        now = datetime.now(timezone.utc).isoformat()
        completed_at_value = now if (success or next_retry_at is None) else None
        update_values: dict[str, Any] = {
            "attempt_count": attempt_number,
            "success": success,
            "status_code": status_code,
            "error": error,
            "retryable": retryable,
            "next_retry_at": next_retry_at,
            "updated_at": now,
        }
        if completed_at_value is not None:
            update_values["completed_at"] = case(
                (
                    models.webhook_deliveries.c.completed_at.is_(None),
                    completed_at_value,
                ),
                else_=models.webhook_deliveries.c.completed_at,
            )
        with self._db._engine.begin() as conn:
            conn.execute(
                update(models.webhook_deliveries)
                .where(models.webhook_deliveries.c.id == delivery_id)
                .values(**update_values)
            )

    def list_due_retries(self, *, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """Return due retry records."""
        now = datetime.now(timezone.utc).isoformat()
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.webhook_deliveries.c.id,
                    models.webhook_deliveries.c.webhook_id,
                    models.webhook_deliveries.c.tenant_id,
                    models.webhook_deliveries.c.org_id,
                    models.webhook_deliveries.c.url,
                    models.webhook_deliveries.c.event_type,
                    models.webhook_deliveries.c.payload_json,
                    models.webhook_deliveries.c.signature,
                    models.webhook_deliveries.c.event_timestamp,
                    models.webhook_deliveries.c.attempt_count,
                    models.webhook_deliveries.c.max_attempts,
                    models.webhook_deliveries.c.next_retry_at,
                )
                .where(
                    models.webhook_deliveries.c.success.is_(False),
                    models.webhook_deliveries.c.retryable.is_(True),
                    models.webhook_deliveries.c.next_retry_at.is_not(None),
                    models.webhook_deliveries.c.next_retry_at <= now,
                    models.webhook_deliveries.c.attempt_count
                    < models.webhook_deliveries.c.max_attempts,
                )
                .order_by(models.webhook_deliveries.c.next_retry_at.asc())
                .limit(limit)
            ).fetchall()
        return [dict(row._mapping) for row in rows]

    def list_deliveries(
        self, *, tenant_id: str, webhook_id: str, limit: int = 100
    ) -> builtins.list[dict[str, Any]]:
        """List delivery status for a webhook."""
        with self._db._engine.connect() as conn:
            rows = conn.execute(
                select(
                    models.webhook_deliveries.c.id,
                    models.webhook_deliveries.c.webhook_id,
                    models.webhook_deliveries.c.tenant_id,
                    models.webhook_deliveries.c.org_id,
                    models.webhook_deliveries.c.url,
                    models.webhook_deliveries.c.event_type,
                    models.webhook_deliveries.c.event_timestamp,
                    models.webhook_deliveries.c.attempt_count,
                    models.webhook_deliveries.c.max_attempts,
                    models.webhook_deliveries.c.success,
                    models.webhook_deliveries.c.status_code,
                    models.webhook_deliveries.c.error,
                    models.webhook_deliveries.c.retryable,
                    models.webhook_deliveries.c.next_retry_at,
                    models.webhook_deliveries.c.created_at,
                    models.webhook_deliveries.c.updated_at,
                    models.webhook_deliveries.c.completed_at,
                )
                .where(
                    models.webhook_deliveries.c.tenant_id == tenant_id,
                    models.webhook_deliveries.c.webhook_id == webhook_id,
                )
                .order_by(models.webhook_deliveries.c.created_at.desc())
                .limit(limit)
            ).fetchall()
        return [dict(row._mapping) for row in rows]

    def delivery_stats(
        self, *, tenant_id: str, since: str | None = None
    ) -> dict[str, Any]:
        """Aggregate delivery metrics for a tenant.

        Returns total, succeeded, failed, and retry queue depth counts.
        """
        t = models.webhook_deliveries
        base = t.c.tenant_id == tenant_id
        if since is not None:
            base = base & (t.c.created_at >= since)

        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(
                    func.count().label("total"),
                    func.sum(func.iif(t.c.success.is_(True), 1, 0)).label("succeeded"),
                    func.sum(
                        func.iif(
                            t.c.success.is_(False) & t.c.retryable.is_(False), 1, 0
                        )
                    ).label("failed"),
                ).where(base)
            ).fetchone()

            retry_depth = conn.execute(
                select(func.count()).where(
                    t.c.tenant_id == tenant_id,
                    t.c.success.is_(False),
                    t.c.retryable.is_(True),
                    t.c.next_retry_at.is_not(None),
                    t.c.attempt_count < t.c.max_attempts,
                )
            ).scalar()

        total = int(row.total or 0) if row else 0
        succeeded = int(row.succeeded or 0) if row else 0
        failed = int(row.failed or 0) if row else 0
        success_rate = succeeded / total if total else 1.0

        return {
            "total_deliveries": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": round(success_rate, 4),
            "retry_queue_depth": int(retry_depth or 0),
        }

    def delivery_stats_global(self, *, since: str | None = None) -> dict[str, Any]:
        """System-wide delivery metrics (not tenant-scoped)."""
        t = models.webhook_deliveries
        where_clause = t.c.created_at >= since if since else True

        with self._db._engine.connect() as conn:
            row = conn.execute(
                select(
                    func.count().label("total"),
                    func.sum(func.iif(t.c.success.is_(True), 1, 0)).label("succeeded"),
                    func.sum(
                        func.iif(
                            t.c.success.is_(False) & t.c.retryable.is_(False), 1, 0
                        )
                    ).label("failed"),
                ).where(where_clause)
            ).fetchone()

            retry_depth = conn.execute(
                select(func.count()).where(
                    t.c.success.is_(False),
                    t.c.retryable.is_(True),
                    t.c.next_retry_at.is_not(None),
                    t.c.attempt_count < t.c.max_attempts,
                )
            ).scalar()

        total = int(row.total or 0) if row else 0
        succeeded = int(row.succeeded or 0) if row else 0
        failed = int(row.failed or 0) if row else 0
        success_rate = succeeded / total if total else 1.0

        return {
            "total_deliveries": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": round(success_rate, 4),
            "retry_queue_depth": int(retry_depth or 0),
        }
