"""Storage layer for Agency OS."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, cast

from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import create_engine, delete, insert, select, update
from sqlalchemy import event as sa_event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import StaticPool

from agency_os import models

logger = logging.getLogger(__name__)


class Database:
    """Thin wrapper around SQLAlchemy/sqlite3 for persistent storage.

    All write operations are serialized through a threading lock to
    prevent 'database is locked' errors when background threads
    (e.g. task executor) and the async event loop both write.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get("DATABASE_PATH", "agency_os.db")
        self.db_path = db_path

        # SQLAlchemy engine
        database_url = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
        is_sqlite = database_url.startswith("sqlite")
        self._is_sqlite = is_sqlite
        self._schema_name: str | None = None
        echo = os.environ.get("SQLALCHEMY_ECHO", "").lower() in ("1", "true", "yes")
        engine_kwargs: dict[str, Any] = {"echo": echo}
        if is_sqlite:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = StaticPool
        else:
            self._schema_name = self._schema_name_for_path(db_path)
            database_url = self._with_search_path(database_url, self._schema_name)
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_size"] = self._get_env_int(
                "SQLALCHEMY_POOL_SIZE", default=20, minimum=1
            )
            engine_kwargs["max_overflow"] = self._get_env_int(
                "SQLALCHEMY_MAX_OVERFLOW", default=10, minimum=0
            )
            engine_kwargs["pool_timeout"] = self._get_env_int(
                "SQLALCHEMY_POOL_TIMEOUT", default=30, minimum=1
            )
            engine_kwargs["pool_recycle"] = self._get_env_int(
                "SQLALCHEMY_POOL_RECYCLE", default=1800, minimum=-1
            )
        self._engine = create_engine(
            database_url,
            **engine_kwargs,
        )
        self._base_engine = self._engine
        self._closed = False

        # Set SQLite PRAGMAs via event listener instead of raw sqlite3 connection
        if is_sqlite:

            @sa_event.listens_for(self._engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.close()

        self._lock = threading.Lock()
        self._ensure_non_sqlite_schema()
        self._run_migrations()

    @staticmethod
    def _get_env_int(name: str, default: int, minimum: int) -> int:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        if value < minimum:
            return default
        return value

    @staticmethod
    def _schema_name_for_path(db_path: str) -> str:
        base = Path(db_path).stem.lower()
        base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_") or "db"
        pytest_test_id = os.environ.get("PYTEST_CURRENT_TEST", "")
        seed = str(Path(db_path).resolve())
        if base == "agency_os" and pytest_test_id:
            seed = f"{seed}|{pytest_test_id}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
        return f"isol_{base[:24]}_{digest}"

    @staticmethod
    def _with_search_path(database_url: str, schema_name: str) -> str:
        url: URL = make_url(database_url)
        query = dict(url.query)
        existing_options = str(query.get("options", "")).strip()
        if f"search_path={schema_name}" not in existing_options:
            search_path_option = f"-csearch_path={schema_name}"
            query["options"] = (
                f"{existing_options} {search_path_option}".strip()
                if existing_options
                else search_path_option
            )
        return cast(str, url.set(query=query).render_as_string(hide_password=False))

    def _ensure_non_sqlite_schema(self) -> None:
        if self._is_sqlite or not self._schema_name:
            return
        # Keep per-Database schema isolated so tempfile-backed tests don't share rows.
        with self._engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{self._schema_name}"')

    # -- context manager --------------------------------------------------

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        # Best-effort fallback for tests/callers that drop DB objects without closing.
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._engine.dispose()
        if self._engine is not self._base_engine:
            self._base_engine.dispose()

    # -- pool metrics -----------------------------------------------------

    def get_pool_status(self) -> dict[str, Any]:
        """Return connection pool metrics (active/idle/overflow).

        For SQLite (StaticPool), returns minimal info since pooling is not applicable.
        """
        pool = self._engine.pool
        if self._is_sqlite:
            return {
                "pool_size": 1,
                "checked_in": 1 if not self._closed else 0,
                "checked_out": 0,
                "overflow": 0,
            }
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }

    # -- schema -----------------------------------------------------------

    def _run_migrations(self) -> None:
        """Apply Alembic migrations on startup."""
        repo_root = Path(__file__).resolve().parents[1]
        alembic_ini = repo_root / "alembic.ini"
        if not alembic_ini.exists():
            raise RuntimeError(f"Alembic config not found: {alembic_ini}")

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(repo_root / "alembic"))
        engine_url_raw = self._engine.url.render_as_string(hide_password=False)
        if self._schema_name:
            cfg.set_main_option("version_table_schema", self._schema_name)
        engine_url = engine_url_raw.replace("%", "%%")
        cfg.set_main_option(
            "sqlalchemy.url",
            engine_url,
        )
        previous_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = engine_url_raw
        try:
            upgrade(cfg, "head")
        finally:
            if previous_db_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_db_url

    def get_migration_version(self) -> str | None:
        """Return current Alembic migration revision for the active database."""
        with self._engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _dialect_insert(conn: Any, table: Any) -> Any:
        """Return INSERT construct compatible with current DB dialect."""
        if conn.dialect.name == "postgresql":
            return postgresql.insert(table)
        return sqlite.insert(table)

    # -- tenants ----------------------------------------------------------

    def save_tenant(self, tenant: dict) -> None:
        t = dict(tenant)
        if "metadata" in t and not isinstance(t["metadata"], str):
            t["metadata"] = json.dumps(t["metadata"])

        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.tenants).values(**t)
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id"],
                set_={
                    "name": stmt.excluded.name,
                    "api_key_hash": stmt.excluded.api_key_hash,
                    "active": stmt.excluded.active,
                    "metadata": stmt.excluded.metadata,
                    "created_at": stmt.excluded.created_at,
                },
            )
            conn.execute(stmt)

    def get_tenant(self, tenant_id: str) -> dict | None:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.tenants).where(models.tenants.c.tenant_id == tenant_id)
            result = conn.execute(stmt).fetchone()
            if result is None:
                return None
            d = dict(result._mapping)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            return d

    def get_tenant_by_key_hash(self, api_key_hash: str) -> dict | None:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.tenants).where(
                models.tenants.c.api_key_hash == api_key_hash
            )
            result = conn.execute(stmt).fetchone()
            if result is None:
                return None
            d = dict(result._mapping)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            return d

    def list_tenants(self) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.tenants)
            results = conn.execute(stmt).fetchall()
            result = [dict(r._mapping) for r in results]
            for d in result:
                if d.get("metadata"):
                    d["metadata"] = json.loads(d["metadata"])
            return result

    def create_tenant_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        token_hash: str,
        created_at: float,
        expires_at: float,
    ) -> None:
        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.tenant_sessions).values(
                session_id=session_id,
                tenant_id=tenant_id,
                token_hash=token_hash,
                created_at=created_at,
                expires_at=expires_at,
                revoked_at=None,
            )
            # On collision, replace with a fresh active session row.
            stmt = stmt.on_conflict_do_update(
                index_elements=["token_hash"],
                set_={
                    "session_id": stmt.excluded.session_id,
                    "tenant_id": stmt.excluded.tenant_id,
                    "created_at": stmt.excluded.created_at,
                    "expires_at": stmt.excluded.expires_at,
                    "revoked_at": None,
                },
            )
            conn.execute(stmt)

    def get_active_tenant_session(self, token_hash: str, now_ts: float) -> dict | None:
        with self._engine.connect() as conn:
            stmt = (
                select(models.tenant_sessions)
                .where(models.tenant_sessions.c.token_hash == token_hash)
                .where(models.tenant_sessions.c.revoked_at.is_(None))
                .where(models.tenant_sessions.c.expires_at > now_ts)
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if row is None:
                return None
            return dict(row._mapping)

    def revoke_tenant_session(self, token_hash: str, revoked_at: float) -> bool:
        with self._engine.begin() as conn:
            stmt = (
                update(models.tenant_sessions)
                .where(models.tenant_sessions.c.token_hash == token_hash)
                .where(models.tenant_sessions.c.revoked_at.is_(None))
                .values(revoked_at=revoked_at)
            )
            result = conn.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)

    # -- organizations ----------------------------------------------------

    def save_org(self, org: dict) -> None:
        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.organizations).values(**org)
            stmt = stmt.on_conflict_do_update(
                index_elements=["org_id"],
                set_={
                    "tenant_id": stmt.excluded.tenant_id,
                    "package_name": stmt.excluded.package_name,
                    "status": stmt.excluded.status,
                    "created_at": stmt.excluded.created_at,
                },
            )
            conn.execute(stmt)

    def get_org(self, org_id: str, tenant_id: str | None = None) -> dict | None:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.organizations).where(
                models.organizations.c.org_id == org_id
            )
            if tenant_id is not None:
                stmt = stmt.where(models.organizations.c.tenant_id == tenant_id)
            result = conn.execute(stmt).fetchone()
            return dict(result._mapping) if result else None

    def list_orgs(self, tenant_id: str) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.organizations).where(
                models.organizations.c.tenant_id == tenant_id
            )
            results = conn.execute(stmt).fetchall()
            return [dict(r._mapping) for r in results]

    def update_org_status(self, org_id: str, status: str, tenant_id: str) -> None:
        # SQLAlchemy version (new)
        from sqlalchemy import update

        with self._engine.begin() as conn:
            stmt = (
                update(models.organizations)
                .where(
                    (models.organizations.c.org_id == org_id)
                    & (models.organizations.c.tenant_id == tenant_id)
                )
                .values(status=status)
            )
            conn.execute(stmt)

    # -- tasks ------------------------------------------------------------

    def save_task(self, task: dict) -> None:
        t = dict(task)
        if "result" in t and not isinstance(t["result"], str):
            t["result"] = json.dumps(t["result"])
        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.tasks).values(**t)
            # INSERT OR IGNORE behavior - only insert if not exists
            stmt = stmt.on_conflict_do_nothing(index_elements=["task_id"])
            conn.execute(stmt)

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        tenant_id: str | None = None,
    ) -> None:
        """Update only the status and result of an existing task (no race with INSERT)."""
        # SQLAlchemy version (new)
        result_json = json.dumps(result) if result is not None else None
        with self._engine.begin() as conn:
            stmt = update(models.tasks).where(models.tasks.c.task_id == task_id)
            if tenant_id is not None:
                stmt = stmt.where(models.tasks.c.tenant_id == tenant_id)
            stmt = stmt.values(status=status, result=result_json)
            conn.execute(stmt)

    def save_trajectory(
        self,
        task_id: str,
        trajectory_json: str,
        tenant_id: str | None = None,
    ) -> None:
        """Persist an ATIF trajectory JSON string on an existing task row."""
        with self._engine.begin() as conn:
            stmt = update(models.tasks).where(models.tasks.c.task_id == task_id)
            if tenant_id is not None:
                stmt = stmt.where(models.tasks.c.tenant_id == tenant_id)
            stmt = stmt.values(trajectory=trajectory_json)
            conn.execute(stmt)

    def get_trajectory(self, task_id: str, tenant_id: str | None = None) -> dict | None:
        """Return the parsed ATIF trajectory for a task, or None."""
        with self._engine.connect() as conn:
            stmt = select(models.tasks.c.trajectory).where(
                models.tasks.c.task_id == task_id
            )
            if tenant_id is not None:
                stmt = stmt.where(models.tasks.c.tenant_id == tenant_id)
            row = conn.execute(stmt).fetchone()
            if row is None or row[0] is None:
                return None
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return None

    def get_task(self, task_id: str, tenant_id: str | None = None) -> dict | None:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.tasks).where(models.tasks.c.task_id == task_id)
            if tenant_id is not None:
                stmt = stmt.where(models.tasks.c.tenant_id == tenant_id)
            result = conn.execute(stmt).fetchone()
            if result is None:
                return None
            d = dict(result._mapping)
            if d.get("result"):
                try:
                    d["result"] = json.loads(d["result"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return d

    def list_tasks(self, org_id: str, tenant_id: str) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.tasks).where(
                models.tasks.c.org_id == org_id,
                models.tasks.c.tenant_id == tenant_id,
            )
            results = conn.execute(stmt).fetchall()
            result = [dict(r._mapping) for r in results]
            for d in result:
                if d.get("result"):
                    try:
                        d["result"] = json.loads(d["result"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return result

    def poll_pending_tasks(self, limit: int = 10) -> list[dict]:
        """Poll for tasks with status='assigned' that need to be executed.

        Returns tasks ordered by created_at (oldest first), limited by limit parameter.
        """
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.tasks)
                .where(models.tasks.c.status == "assigned")
                .order_by(models.tasks.c.created_at.asc())
                .limit(limit)
            )
            results = conn.execute(stmt).fetchall()
            result = [dict(r._mapping) for r in results]
            for d in result:
                if d.get("result"):
                    try:
                        d["result"] = json.loads(d["result"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return result

    def claim_task(self, task_id: str, worker_id: str) -> bool:
        """Atomically claim a task for execution by a worker.

        Updates status from 'assigned' to 'executing' only if still assigned.
        Returns True if claim succeeded, False if another worker got it first.
        """
        # SQLAlchemy version (new)
        with self._engine.begin() as conn:
            stmt = (
                update(models.tasks)
                .where(
                    models.tasks.c.task_id == task_id,
                    models.tasks.c.status == "assigned",
                )
                .values(status="executing")
            )
            result = conn.execute(stmt)
            return cast(int, result.rowcount or 0) > 0

    # -- metering events --------------------------------------------------

    def save_metering_event(self, event: dict) -> None:
        # SQLAlchemy version (new)
        e = dict(event)
        if "metadata" in e and not isinstance(e["metadata"], str):
            e["metadata"] = json.dumps(e["metadata"])
        with self._engine.begin() as conn:
            stmt = insert(models.metering_events).values(**e)
            conn.execute(stmt)

    def get_metering_events(
        self, tenant_id: str, since: float | None = None
    ) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.metering_events).where(
                models.metering_events.c.tenant_id == tenant_id
            )
            if since is not None:
                stmt = stmt.where(models.metering_events.c.timestamp >= since)
            rows = conn.execute(stmt).fetchall()
        result = [dict(r._mapping) for r in rows]
        for d in result:
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    def query_metering_events(
        self,
        *,
        tenant_id: str,
        start_time: float | None = None,
        end_time: float | None = None,
        agent_id: str | None = None,
        org_id: str | None = None,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query metering events with filtering and pagination.

        Notes:
        - Tenant scoping is mandatory.
        - ``task_id`` currently lives in metadata, so that filter is applied in Python.
        """
        with self._engine.connect() as conn:
            stmt = select(models.metering_events).where(
                models.metering_events.c.tenant_id == tenant_id
            )
            if start_time is not None:
                stmt = stmt.where(models.metering_events.c.timestamp >= start_time)
            if end_time is not None:
                stmt = stmt.where(models.metering_events.c.timestamp <= end_time)
            if agent_id is not None:
                stmt = stmt.where(models.metering_events.c.agent_id == agent_id)
            if org_id is not None:
                stmt = stmt.where(models.metering_events.c.org_id == org_id)
            if event_type is not None:
                stmt = stmt.where(models.metering_events.c.event_type == event_type)

            stmt = stmt.order_by(
                models.metering_events.c.timestamp.desc(),
                models.metering_events.c.id.desc(),
            )
            rows = conn.execute(stmt).fetchall()

        events: list[dict[str, Any]] = [dict(row._mapping) for row in rows]
        for event in events:
            metadata_raw = event.get("metadata")
            if not metadata_raw:
                event["metadata"] = {}
                continue
            try:
                event["metadata"] = (
                    json.loads(metadata_raw)
                    if isinstance(metadata_raw, str)
                    else dict(metadata_raw)
                )
            except Exception:
                event["metadata"] = {}

        if task_id is not None:
            events = [
                event
                for event in events
                if event.get("metadata", {}).get("task_id") == task_id
            ]

        total = len(events)
        page = events[offset : offset + limit]
        return page, total

    def get_worker_task_metrics(self, since: float | None = None) -> dict[str, Any]:
        """Aggregate worker task-outcome and circuit-breaker metrics.

        Metrics are derived from ``metering_events`` where:
        - ``event_type = task_outcome`` carries ``metadata.outcome`` and optional
          ``metadata.duration_sec``.
        - ``event_type = circuit_breaker.tripped`` represents an actual trip event.
        """
        with self._engine.connect() as conn:
            stmt = select(
                models.metering_events.c.event_type,
                models.metering_events.c.metadata,
            )
            if since is not None:
                stmt = stmt.where(models.metering_events.c.timestamp >= since)
            rows = conn.execute(stmt).fetchall()

        metrics: dict[str, Any] = {
            "task_outcomes_total": 0,
            "task_outcomes_success_total": 0,
            "task_outcomes_failure_total": 0,
            "task_completion_duration_count": 0,
            "task_completion_duration_sum_sec": 0.0,
            "circuit_breaker_tripped_total": 0,
        }
        for row in rows:
            event_type = row._mapping["event_type"]
            if event_type == "circuit_breaker.tripped":
                metrics["circuit_breaker_tripped_total"] += 1
                continue
            if event_type != "task_outcome":
                continue
            metrics["task_outcomes_total"] += 1
            metadata_raw = row._mapping.get("metadata")
            metadata: dict[str, Any] = {}
            if metadata_raw:
                try:
                    metadata = (
                        json.loads(metadata_raw)
                        if isinstance(metadata_raw, str)
                        else dict(metadata_raw)
                    )
                except Exception:
                    metadata = {}
            outcome = metadata.get("outcome")
            if outcome == "success":
                metrics["task_outcomes_success_total"] += 1
            elif outcome == "failure":
                metrics["task_outcomes_failure_total"] += 1
            duration = metadata.get("duration_sec")
            if isinstance(duration, (int, float)):
                metrics["task_completion_duration_count"] += 1
                metrics["task_completion_duration_sum_sec"] += float(duration)

        duration_count = int(metrics.get("task_completion_duration_count") or 0)
        duration_sum = float(metrics.get("task_completion_duration_sum_sec") or 0.0)
        metrics["task_completion_duration_avg_sec"] = (
            duration_sum / duration_count if duration_count else 0.0
        )
        return metrics

    def get_run_failure_metrics(
        self,
        tenant_id: str,
        org_id: str,
        since: str | None = None,
        until: str | None = None,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Aggregate task failure metrics for an org.

        Queries the tasks table for tasks scoped to tenant+org.
        Returns failure count, rate, common error causes, and recent failures.

        ``since`` and ``until`` are ISO8601 strings compared against ``created_at``.
        """
        with self._engine.connect() as conn:
            stmt = select(models.tasks).where(
                models.tasks.c.tenant_id == tenant_id,
                models.tasks.c.org_id == org_id,
            )
            if agent_id is not None:
                stmt = stmt.where(models.tasks.c.assigned_to == agent_id)
            if since is not None:
                stmt = stmt.where(models.tasks.c.created_at >= since)
            if until is not None:
                stmt = stmt.where(models.tasks.c.created_at <= until)
            all_rows = conn.execute(stmt).fetchall()

        all_tasks = [dict(r._mapping) for r in all_rows]
        total = len(all_tasks)
        failed_tasks = [t for t in all_tasks if t.get("status") == "failed"]
        failure_count = len(failed_tasks)
        failure_rate = failure_count / total if total > 0 else 0.0

        sorted_failures = sorted(
            failed_tasks,
            key=lambda x: x.get("created_at") or "",
            reverse=True,
        )

        recent_failures: list[dict[str, Any]] = []
        causes: dict[str, int] = {}

        for t in sorted_failures:
            result = t.get("result")
            if result and isinstance(result, str):
                try:
                    result = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    result = {}
            error_msg: str | None = None
            if isinstance(result, dict):
                error_msg = result.get("error") or result.get("message")
            if error_msg:
                cause_key = str(error_msg)[:100]
                causes[cause_key] = causes.get(cause_key, 0) + 1
            if len(recent_failures) < limit:
                recent_failures.append(
                    {
                        "task_id": t["task_id"],
                        "description": t.get("description"),
                        "assigned_to": t.get("assigned_to"),
                        "governance_preset": t.get("governance_preset"),
                        "created_at": t.get("created_at"),
                        "error": error_msg,
                    }
                )

        cause_list: list[dict[str, Any]] = [
            {"cause": k, "count": v} for k, v in causes.items()
        ]
        common_causes = sorted(
            cause_list,
            key=lambda x: x.get("count", 0),
            reverse=True,
        )[:10]

        return {
            "total_tasks": total,
            "failure_count": failure_count,
            "failure_rate": round(failure_rate, 4),
            "recent_failures": recent_failures,
            "common_causes": common_causes,
        }

    # -- wallet snapshots -------------------------------------------------

    def save_wallet_snapshot(self, snapshot: dict) -> None:
        # SQLAlchemy version (new)
        with self._engine.begin() as conn:
            stmt = insert(models.wallet_snapshots).values(**snapshot)
            conn.execute(stmt)

    def get_wallet_snapshots(self, org_id: str) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = select(models.wallet_snapshots).where(
                models.wallet_snapshots.c.org_id == org_id
            )
            rows = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_agent_wallet_snapshots(self, agent_id: str, limit: int = 100) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.wallet_snapshots)
                .where(models.wallet_snapshots.c.agent_id == agent_id)
                .order_by(models.wallet_snapshots.c.snapshot_at.desc())
                .limit(limit)
            )
            rows = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in rows]

    # -- trust scores -----------------------------------------------------

    def save_trust_score(self, score: dict) -> None:
        # SQLAlchemy version (new)
        with self._engine.begin() as conn:
            stmt = insert(models.trust_scores).values(**score)
            conn.execute(stmt)

    def get_trust_score_history(self, agent_id: str, limit: int = 100) -> list[dict]:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.trust_scores)
                .where(models.trust_scores.c.agent_id == agent_id)
                .order_by(models.trust_scores.c.computed_at.desc())
                .limit(limit)
            )
            rows = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_latest_trust_score(self, agent_id: str) -> dict | None:
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.trust_scores)
                .where(models.trust_scores.c.agent_id == agent_id)
                .order_by(models.trust_scores.c.computed_at.desc())
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
        return dict(row._mapping) if row is not None else None

    # -- webhook idempotency ----------------------------------------------

    def try_claim_webhook_event(self, event_id: str, event_type: str) -> bool:
        """Atomically claim a webhook event for processing.

        Returns True if this caller claimed it (should process).
        Returns False if already claimed by another request (skip).
        """
        from datetime import datetime, timezone

        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.processed_webhook_events).values(
                event_id=event_id,
                event_type=event_type,
                processed_at=datetime.now(timezone.utc).isoformat(),
            )
            # INSERT OR IGNORE behavior
            stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"]).returning(
                models.processed_webhook_events.c.event_id
            )
            result = conn.execute(stmt)
            return result.scalar_one_or_none() is not None

    def release_webhook_event_claim(self, event_id: str) -> None:
        """Release a previously-claimed webhook event.

        Used when processing fails after a claim so a retry can reprocess it.
        """
        with self._engine.begin() as conn:
            stmt = delete(models.processed_webhook_events).where(
                models.processed_webhook_events.c.event_id == event_id
            )
            conn.execute(stmt)

    # -- gateway requests -------------------------------------------------

    def save_gateway_request(self, req: dict) -> None:
        """Log a gateway request with cost tracking."""
        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.gateway_requests).values(**req)
            # INSERT OR IGNORE behavior
            stmt = stmt.on_conflict_do_nothing(index_elements=["request_id"])
            conn.execute(stmt)

    def get_gateway_stats(self, tenant_id: str, since: float | None = None) -> dict:
        """Get aggregated gateway stats for a tenant."""
        # SQLAlchemy version (new)
        from sqlalchemy import case, func

        with self._engine.connect() as conn:
            stmt = select(
                func.count().label("total_requests"),
                func.coalesce(func.sum(models.gateway_requests.c.tokens_in), 0).label(
                    "total_tokens_in"
                ),
                func.coalesce(func.sum(models.gateway_requests.c.tokens_out), 0).label(
                    "total_tokens_out"
                ),
                func.coalesce(
                    func.sum(models.gateway_requests.c.provider_cost), 0
                ).label("total_provider_cost"),
                func.coalesce(
                    func.sum(models.gateway_requests.c.customer_cost), 0
                ).label("total_customer_cost"),
                func.coalesce(func.sum(models.gateway_requests.c.margin), 0).label(
                    "total_margin"
                ),
                func.coalesce(func.avg(models.gateway_requests.c.latency_ms), 0).label(
                    "avg_latency_ms"
                ),
                func.coalesce(
                    func.sum(case((models.gateway_requests.c.cached, 1), else_=0)), 0
                ).label("cache_hits"),
            ).where(models.gateway_requests.c.tenant_id == tenant_id)
            if since is not None:
                stmt = stmt.where(models.gateway_requests.c.timestamp >= since)
            row = conn.execute(stmt).fetchone()
        return dict(row._mapping) if row else {}

    def get_gateway_requests(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """Get recent gateway requests for a tenant."""
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.gateway_requests)
                .where(models.gateway_requests.c.tenant_id == tenant_id)
                .order_by(models.gateway_requests.c.timestamp.desc())
                .limit(limit)
            )
            results = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in results]

    def get_gateway_savings(self, tenant_id: str, since: float | None = None) -> dict:
        """Calculate cost savings from caching and smart routing for a tenant.

        Returns:
            - total_requests: total number of requests
            - cache_hits: number of cached requests (zero provider cost)
            - cache_savings_usd: total customer_cost saved from cache hits
            - smart_routed: number of requests that used auto routing
            - total_cost_usd: actual total customer cost
        """
        # SQLAlchemy version (new)
        from sqlalchemy import and_, case, func

        with self._engine.connect() as conn:
            stmt = select(
                func.count().label("total_requests"),
                func.coalesce(
                    func.sum(case((models.gateway_requests.c.cached, 1), else_=0)), 0
                ).label("cache_hits"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                models.gateway_requests.c.cached,
                                models.gateway_requests.c.customer_cost,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("cache_savings_usd"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    models.gateway_requests.c.routed_by != "explicit",
                                    models.gateway_requests.c.routed_by.isnot(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("smart_routed"),
                func.coalesce(
                    func.sum(models.gateway_requests.c.customer_cost), 0
                ).label("total_cost_usd"),
            ).where(models.gateway_requests.c.tenant_id == tenant_id)
            if since is not None:
                stmt = stmt.where(models.gateway_requests.c.timestamp >= since)
            row = conn.execute(stmt).fetchone()
        return dict(row._mapping) if row else {}

    def get_gateway_top_models(
        self, tenant_id: str, limit: int = 5, since: float | None = None
    ) -> list[dict]:
        """Get top N models by request count for a tenant.

        Returns list of dicts with: model_id, request_count
        """
        # SQLAlchemy version (new)
        from sqlalchemy import func

        with self._engine.connect() as conn:
            stmt = (
                select(
                    models.gateway_requests.c.model_id,
                    func.count().label("request_count"),
                )
                .where(models.gateway_requests.c.tenant_id == tenant_id)
                .group_by(models.gateway_requests.c.model_id)
                .order_by(func.count().desc())
                .limit(limit)
            )
            if since is not None:
                stmt = stmt.where(models.gateway_requests.c.timestamp >= since)
            results = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in results]

    def get_task_outcome_latency_stats(
        self, since: float | None = None
    ) -> dict[str, float]:
        """Aggregate worker task_outcome latency from metering metadata."""
        with self._engine.connect() as conn:
            stmt = select(models.metering_events.c.metadata).where(
                models.metering_events.c.event_type == "task_outcome"
            )
            if since is not None:
                stmt = stmt.where(models.metering_events.c.timestamp >= since)
            rows = conn.execute(stmt).fetchall()

        durations: list[float] = []
        for row in rows:
            raw = row._mapping.get("metadata")
            if not raw:
                continue
            try:
                payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except Exception:
                continue
            duration = payload.get("duration_sec")
            if isinstance(duration, (int, float)) and duration >= 0:
                durations.append(float(duration))

        if not durations:
            return {"count": 0, "avg_duration_sec": 0.0, "p95_duration_sec": 0.0}

        durations.sort()
        count = len(durations)
        avg = sum(durations) / count
        p95_index = max(0, min(count - 1, math.ceil(count * 0.95) - 1))
        p95 = durations[p95_index]
        return {"count": count, "avg_duration_sec": avg, "p95_duration_sec": p95}

    # -- audit log --------------------------------------------------------

    def save_audit_event(
        self,
        *,
        actor: str,
        action: str,
        resource: str | None = None,
        resource_id: str | None = None,
        detail: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Append an immutable audit event. No UPDATE/DELETE methods exist by design."""
        # SQLAlchemy version (new)
        import time as _time

        with self._engine.begin() as conn:
            stmt = insert(models.audit_log).values(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                resource=resource,
                resource_id=resource_id,
                detail=detail,
                timestamp=_time.time(),
            )
            conn.execute(stmt)

    def get_audit_log(
        self,
        tenant_id: str | None = None,
        since: float | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Query the append-only audit log. Supports tenant and time filters."""
        # SQLAlchemy version (new)
        with self._engine.connect() as conn:
            stmt = (
                select(models.audit_log)
                .order_by(models.audit_log.c.id.desc())
                .limit(limit)
            )
            if tenant_id is not None:
                stmt = stmt.where(models.audit_log.c.tenant_id == tenant_id)
            if since is not None:
                stmt = stmt.where(models.audit_log.c.timestamp >= since)
            results = conn.execute(stmt).fetchall()
        return [dict(r._mapping) for r in results]

    # -- timeline events --------------------------------------------------

    def save_timeline_event(self, event: dict) -> None:
        """Persist a timeline event for the time-lapse feature."""
        with self._engine.begin() as conn:
            stmt = insert(models.timeline_events).values(**event)
            conn.execute(stmt)

    def get_timeline_events(
        self,
        org_id: str,
        tenant_id: str,
        since: float | None = None,
        until: float | None = None,
        event_types: list[str] | None = None,
        agent_id: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Query persisted timeline events for replay."""
        with self._engine.connect() as conn:
            stmt = (
                select(models.timeline_events)
                .where(
                    models.timeline_events.c.org_id == org_id,
                    models.timeline_events.c.tenant_id == tenant_id,
                )
                .order_by(models.timeline_events.c.timestamp.desc())
                .limit(limit)
            )
            if since is not None:
                stmt = stmt.where(models.timeline_events.c.timestamp >= since)
            if until is not None:
                stmt = stmt.where(models.timeline_events.c.timestamp <= until)
            if event_types:
                stmt = stmt.where(models.timeline_events.c.event_type.in_(event_types))
            if agent_id:
                stmt = stmt.where(models.timeline_events.c.agent_id == agent_id)
            rows = conn.execute(stmt).fetchall()

        results = []
        for r in rows:
            d = dict(r._mapping)
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d["metadata_json"])
                except (json.JSONDecodeError, TypeError):
                    d["metadata"] = {}
            else:
                d["metadata"] = {}
            d.pop("metadata_json", None)
            results.append(d)
        return results

    # -- waitlist ---------------------------------------------------------

    def save_waitlist_signup(self, email: str, ip_hash: str) -> None:
        """Record a waitlist signup.

        Args:
            email: Signup email address.
            ip_hash: SHA-256 hash of client IP (not plaintext IP).
        """
        # SQLAlchemy version (new)
        import time as _time

        with self._engine.begin() as conn:
            stmt = self._dialect_insert(conn, models.waitlist).values(
                email=email, signed_up_at=_time.time(), ip_hash=ip_hash
            )
            # INSERT OR IGNORE behavior
            stmt = stmt.on_conflict_do_nothing(index_elements=["email"])
            conn.execute(stmt)

    def get_waitlist_signups(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Retrieve waitlist signups, most recent first."""
        import sqlalchemy as sa

        with self._engine.connect() as conn:
            stmt = (
                sa.select(models.waitlist)
                .order_by(models.waitlist.c.signed_up_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = conn.execute(stmt).mappings().all()
            return [dict(r) for r in rows]

    def get_waitlist_stats(self) -> dict[str, int]:
        """Return waitlist signup counts: total, last_24h, last_7d, last_30d."""
        import time as _time

        import sqlalchemy as sa

        now = _time.time()
        cutoffs = {
            "last_24h": now - 86400,
            "last_7d": now - 86400 * 7,
            "last_30d": now - 86400 * 30,
        }
        with self._engine.connect() as conn:
            total = (
                conn.execute(
                    sa.select(sa.func.count()).select_from(models.waitlist)
                ).scalar()
                or 0
            )
            stats: dict[str, int] = {"total": total}
            for key, cutoff in cutoffs.items():
                count = (
                    conn.execute(
                        sa.select(sa.func.count())
                        .select_from(models.waitlist)
                        .where(models.waitlist.c.signed_up_at >= cutoff)
                    ).scalar()
                    or 0
                )
                stats[key] = count
            return stats
