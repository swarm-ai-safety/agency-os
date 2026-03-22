"""Tests for the SQLite storage layer and persistent tenant registry."""

from __future__ import annotations

import sqlite3
import time

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

from agency_os.storage import Database
from agency_os.storage_backed_registry import PersistentTenantRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Provide a Database instance backed by a temp SQLite file."""
    path = str(tmp_path / "test.db")
    with Database(path) as database:
        # Seed tenants and orgs required by FK constraints
        for tid in ("t-1", "t-2"):
            database.save_tenant(
                {
                    "tenant_id": tid,
                    "name": f"Test Tenant {tid}",
                    "api_key_hash": f"hash-{tid}",
                    "active": True,
                    "metadata": None,
                    "created_at": "2025-01-01T00:00:00Z",
                }
            )
        for oid, tid in (("org-1", "t-1"), ("org-2", "t-1"), ("org-3", "t-2")):
            database.save_org(
                {
                    "org_id": oid,
                    "tenant_id": tid,
                    "package_name": "starter",
                    "status": "active",
                    "created_at": "2025-01-01T00:00:00Z",
                }
            )
        yield database


@pytest.fixture
def registry(tmp_path):
    """Provide a PersistentTenantRegistry backed by a temp SQLite file."""
    path = str(tmp_path / "registry.db")
    return PersistentTenantRegistry(db_path=path)


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


class TestTableCreation:
    def test_tables_exist(self, db):
        tables = sorted(inspect(db._engine).get_table_names())
        assert "metering_events" in tables
        assert "organizations" in tables
        assert "tasks" in tables
        assert "tenants" in tables
        assert "wallet_snapshots" in tables
        assert "trust_scores" in tables
        assert "audit_log" in tables


class TestEngineConfiguration:
    def test_postgres_pool_config_from_env(self, monkeypatch, tmp_path):
        captured: dict[str, object] = {}

        class DummyConn:
            def exec_driver_sql(self, _sql: str):
                return None

        class DummyBegin:
            def __enter__(self):
                return DummyConn()

            def __exit__(self, exc_type, exc, tb):
                return False

        class DummyEngine:
            def begin(self):
                return DummyBegin()

            def dispose(self):
                return None

        def fake_create_engine(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return DummyEngine()

        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/agency_os"
        )
        monkeypatch.setenv("SQLALCHEMY_POOL_SIZE", "20")
        monkeypatch.setenv("SQLALCHEMY_MAX_OVERFLOW", "30")
        monkeypatch.setattr("agency_os.storage.create_engine", fake_create_engine)
        monkeypatch.setattr(
            "agency_os.storage.Database._run_migrations", lambda _: None
        )

        db = Database(str(tmp_path / "test.db"))
        assert str(captured["url"]).startswith(
            "postgresql+psycopg://user:pass@localhost:5432/agency_os"
        )
        assert "search_path" in str(captured["url"])
        kwargs = captured["kwargs"]
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_size"] == 20
        assert kwargs["max_overflow"] == 30
        assert "poolclass" not in kwargs
        db.close()

    def test_sqlite_engine_uses_static_pool(self, monkeypatch, tmp_path):
        captured: dict[str, object] = {}

        class DummyEngine:
            def dispose(self):
                return None

        def fake_create_engine(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return DummyEngine()

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("SQLALCHEMY_POOL_SIZE", "20")
        monkeypatch.setenv("SQLALCHEMY_MAX_OVERFLOW", "30")
        monkeypatch.setattr("agency_os.storage.create_engine", fake_create_engine)
        monkeypatch.setattr(
            "agency_os.storage.Database._run_migrations", lambda _: None
        )

        db = Database(str(tmp_path / "test.db"))
        kwargs = captured["kwargs"]
        assert kwargs["connect_args"] == {"check_same_thread": False}
        assert kwargs["poolclass"] is StaticPool
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs
        db.close()

    def test_database_url_precedence_and_db_path_schema_isolation(
        self, monkeypatch, tmp_path
    ):
        captured_urls: list[str] = []

        class DummyConn:
            def exec_driver_sql(self, _sql: str):
                return None

        class DummyBegin:
            def __enter__(self):
                return DummyConn()

            def __exit__(self, exc_type, exc, tb):
                return False

        class DummyEngine:
            def __init__(self, url: str):
                self.url = make_url(url)

            def begin(self):
                return DummyBegin()

            def dispose(self):
                return None

        def fake_create_engine(url, **_kwargs):
            captured_urls.append(str(url))
            return DummyEngine(url)

        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://user:pass@localhost:5432/agency_os?sslmode=disable",
        )
        monkeypatch.setattr("agency_os.storage.create_engine", fake_create_engine)
        monkeypatch.setattr(
            "agency_os.storage.Database._run_migrations", lambda _: None
        )

        db1 = Database(str(tmp_path / "one.db"))
        db2 = Database(str(tmp_path / "two.db"))
        db1.close()
        db2.close()

        assert len(captured_urls) == 2
        for url in captured_urls:
            assert url.startswith(
                "postgresql+psycopg://user:pass@localhost:5432/agency_os"
            )
            options = make_url(url).query.get("options", "")
            assert "search_path=" in options
        assert captured_urls[0] != captured_urls[1]

    def test_default_db_path_schema_includes_pytest_test_id(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/test_a.py::test_alpha")
        schema_a = Database._schema_name_for_path("agency_os.db")
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/test_b.py::test_bravo")
        schema_b = Database._schema_name_for_path("agency_os.db")
        assert schema_a != schema_b


# ---------------------------------------------------------------------------
# Trust Scores
# ---------------------------------------------------------------------------


class TestTrustScores:
    def test_save_and_get_history(self, db):
        import time

        for i in range(3):
            db.save_trust_score(
                {
                    "tenant_id": "t-1",
                    "org_id": "org-1",
                    "agent_id": "agent-a",
                    "score": 0.5 + i * 0.1,
                    "tier": "medium",
                    "total_tasks": 10 + i,
                    "successes": 5 + i,
                    "failures": 5,
                    "partials": 0,
                    "computed_at": time.time() + i,
                }
            )
        history = db.get_trust_score_history("agent-a")
        assert len(history) == 3
        # Most recent first
        assert history[0]["score"] > history[-1]["score"]

    def test_get_latest(self, db):
        import time

        db.save_trust_score(
            {
                "tenant_id": "t-1",
                "org_id": "org-1",
                "agent_id": "agent-b",
                "score": 0.9,
                "tier": "high",
                "total_tasks": 20,
                "successes": 18,
                "failures": 2,
                "partials": 0,
                "computed_at": time.time(),
            }
        )
        latest = db.get_latest_trust_score("agent-b")
        assert latest is not None
        assert latest["score"] == 0.9
        assert latest["tier"] == "high"

    def test_no_scores_returns_none(self, db):
        assert db.get_latest_trust_score("nonexistent") is None

    def test_history_limit(self, db):
        import time

        for i in range(10):
            db.save_trust_score(
                {
                    "tenant_id": "t-1",
                    "org_id": "org-1",
                    "agent_id": "agent-c",
                    "score": 0.5,
                    "tier": "medium",
                    "total_tasks": 10,
                    "successes": 5,
                    "failures": 5,
                    "partials": 0,
                    "computed_at": time.time() + i,
                }
            )
        history = db.get_trust_score_history("agent-c", limit=3)
        assert len(history) == 3


class TestAgentWalletSnapshots:
    def test_get_by_agent(self, db):
        db.save_wallet_snapshot(
            {
                "org_id": "org-1",
                "agent_id": "agent-x",
                "balance": 100.0,
                "reputation": 1.0,
                "snapshot_at": "2025-01-01T00:00:00Z",
            }
        )
        db.save_wallet_snapshot(
            {
                "org_id": "org-1",
                "agent_id": "agent-y",
                "balance": 200.0,
                "reputation": 0.8,
                "snapshot_at": "2025-01-01T00:00:01Z",
            }
        )
        snaps = db.get_agent_wallet_snapshots("agent-x")
        assert len(snaps) == 1
        assert snaps[0]["balance"] == 100.0


# ---------------------------------------------------------------------------
# Tenant CRUD
# ---------------------------------------------------------------------------


class TestTenantCRUD:
    def _make_tenant(self, **overrides):
        base = {
            "tenant_id": "t-1",
            "name": "Acme",
            "api_key_hash": "hash-abc",
            "active": True,
            "metadata": {"plan": "pro"},
            "created_at": "2025-01-01T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_save_and_get(self, db):
        db.save_tenant(self._make_tenant())
        t = db.get_tenant("t-1")
        assert t is not None
        assert t["name"] == "Acme"
        assert t["metadata"] == {"plan": "pro"}

    def test_get_by_key_hash(self, db):
        db.save_tenant(self._make_tenant())
        t = db.get_tenant_by_key_hash("hash-abc")
        assert t is not None
        assert t["tenant_id"] == "t-1"

    def test_get_missing(self, db):
        assert db.get_tenant("nonexistent") is None

    def test_list_tenants(self, db):
        db.save_tenant(self._make_tenant(tenant_id="t-1", api_key_hash="hash-1"))
        db.save_tenant(
            self._make_tenant(tenant_id="t-2", api_key_hash="hash-2", name="Beta")
        )
        tenants = db.list_tenants()
        assert len(tenants) == 2

    def test_deactivate_via_save(self, db):
        db.save_tenant(self._make_tenant())
        t = db.get_tenant("t-1")
        t["active"] = False
        # re-serialize metadata (already a dict from get_tenant)
        db.save_tenant(t)
        t2 = db.get_tenant("t-1")
        assert t2["active"] == 0 or t2["active"] is False


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


class TestOrgCRUD:
    def _make_org(self, **overrides):
        base = {
            "org_id": "org-1",
            "tenant_id": "t-1",
            "package_name": "starter",
            "status": "active",
            "created_at": "2025-01-01T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_save_and_get(self, db):
        db.save_org(self._make_org())
        o = db.get_org("org-1")
        assert o is not None
        assert o["package_name"] == "starter"

    def test_list_by_tenant(self, db):
        db.save_org(self._make_org(org_id="org-1", tenant_id="t-1"))
        db.save_org(self._make_org(org_id="org-2", tenant_id="t-1"))
        db.save_org(self._make_org(org_id="org-3", tenant_id="t-2"))
        orgs = db.list_orgs("t-1")
        assert len(orgs) == 2

    def test_update_status(self, db):
        db.save_org(self._make_org())
        db.update_org_status("org-1", "suspended", tenant_id="t-1")
        o = db.get_org("org-1")
        assert o["status"] == "suspended"

    def test_get_org_respects_tenant_scope(self, db):
        db.save_org(self._make_org(org_id="org-1", tenant_id="t-1"))
        assert db.get_org("org-1", tenant_id="t-2") is None
        scoped = db.get_org("org-1", tenant_id="t-1")
        assert scoped is not None
        assert scoped["tenant_id"] == "t-1"


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


class TestTaskCRUD:
    def _make_task(self, **overrides):
        base = {
            "task_id": "task-1",
            "tenant_id": "t-1",
            "org_id": "org-1",
            "description": "Do something",
            "assigned_to": "agent-a",
            "status": "pending",
            "result": {"output": "done"},
            "created_at": "2025-01-01T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_save_and_get(self, db):
        db.save_task(self._make_task())
        t = db.get_task("task-1")
        assert t is not None
        assert t["result"] == {"output": "done"}

    def test_list_by_org(self, db):
        db.save_task(self._make_task(task_id="task-1", org_id="org-1"))
        db.save_task(self._make_task(task_id="task-2", org_id="org-1"))
        db.save_task(self._make_task(task_id="task-3", org_id="org-2"))
        tasks = db.list_tasks("org-1", tenant_id="t-1")
        assert len(tasks) == 2

    def test_get_missing(self, db):
        assert db.get_task("nonexistent") is None

    def test_update_status_respects_tenant_scope(self, db):
        db.save_task(self._make_task(task_id="task-1", tenant_id="t-1", org_id="org-1"))
        db.update_task_status("task-1", "completed", {"ok": True}, tenant_id="t-2")
        unchanged = db.get_task("task-1", tenant_id="t-1")
        assert unchanged is not None
        assert unchanged["status"] == "pending"
        assert unchanged["result"] == {"output": "done"}

        db.update_task_status("task-1", "completed", {"ok": True}, tenant_id="t-1")
        updated = db.get_task("task-1", tenant_id="t-1")
        assert updated is not None
        assert updated["status"] == "completed"
        assert updated["result"] == {"ok": True}


class _CompileOnlyResult:
    def __init__(self, scalar: str | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> str | None:
        return self._scalar


class _CompileOnlyPGConnection:
    def __init__(self) -> None:
        self.dialect = postgresql.dialect()
        self.compiled_sql: list[str] = []

    def execute(self, stmt):
        compiled = str(
            stmt.compile(dialect=self.dialect, compile_kwargs={"literal_binds": True})
        )
        self.compiled_sql.append(compiled)
        if "RETURNING" in compiled.upper():
            return _CompileOnlyResult("claimed")
        return _CompileOnlyResult()


class _CompileOnlyPGBegin:
    def __init__(self, conn: _CompileOnlyPGConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _CompileOnlyPGConnection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _CompileOnlyPGEngine:
    def __init__(self) -> None:
        self.conn = _CompileOnlyPGConnection()

    def begin(self) -> _CompileOnlyPGBegin:
        return _CompileOnlyPGBegin(self.conn)

    def dispose(self) -> None:
        return None


class TestPostgresUpsertCompilation:
    def test_upsert_paths_compile_against_postgresql_dialect(self, db, monkeypatch):
        compile_only_engine = _CompileOnlyPGEngine()
        monkeypatch.setattr(db, "_engine", compile_only_engine)

        db.save_tenant(
            {
                "tenant_id": "tenant-pg",
                "name": "Tenant PG",
                "api_key_hash": "hash-tenant-pg",
                "active": True,
                "metadata": {"plan": "pro"},
                "created_at": "2026-01-01T00:00:00Z",
            }
        )
        db.save_org(
            {
                "org_id": "org-pg",
                "tenant_id": "tenant-pg",
                "package_name": "starter",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
            }
        )
        db.save_task(
            {
                "task_id": "task-pg",
                "tenant_id": "tenant-pg",
                "org_id": "org-pg",
                "description": "compile test",
                "assigned_to": "agent-1",
                "status": "pending",
                "result": {"ok": True},
                "created_at": "2026-01-01T00:00:00Z",
            }
        )
        assert db.try_claim_webhook_event("event-pg", "task.completed") is True
        db.save_gateway_request(
            {
                "request_id": "req-pg",
                "tenant_id": "tenant-pg",
                "provider": "openai",
                "model_id": "gpt-4o-mini",
                "tokens_in": 1,
                "tokens_out": 2,
                "provider_cost": 0.0001,
                "customer_cost": 0.0002,
                "margin": 0.0001,
                "latency_ms": 25,
                "cached": False,
                "routed_by": "explicit",
                "timestamp": 1.0,
            }
        )
        db.save_waitlist_signup("pg@example.com", "hash-pg")

        sql = compile_only_engine.conn.compiled_sql
        assert len(sql) == 6
        assert all("ON CONFLICT" in statement.upper() for statement in sql)


# ---------------------------------------------------------------------------
# Webhook idempotency
# ---------------------------------------------------------------------------


class TestWebhookIdempotencyClaims:
    def test_claim_release_and_reclaim(self, db):
        event_id = "evt-claim-release"
        assert (
            db.try_claim_webhook_event(event_id, "checkout.session.completed") is True
        )
        assert (
            db.try_claim_webhook_event(event_id, "checkout.session.completed") is False
        )
        db.release_webhook_event_claim(event_id)
        assert (
            db.try_claim_webhook_event(event_id, "checkout.session.completed") is True
        )


# ---------------------------------------------------------------------------
# Metering events
# ---------------------------------------------------------------------------


class TestMeteringEvents:
    def _make_event(self, **overrides):
        base = {
            "tenant_id": "t-1",
            "org_id": "org-1",
            "agent_id": "agent-a",
            "event_type": "llm_call",
            "tokens_in": 100,
            "tokens_out": 50,
            "timestamp": time.time(),
            "metadata": {"model": "gpt-4"},
        }
        base.update(overrides)
        return base

    def test_save_and_get(self, db):
        db.save_metering_event(self._make_event())
        events = db.get_metering_events("t-1")
        assert len(events) == 1
        assert events[0]["tokens_in"] == 100
        assert events[0]["metadata"] == {"model": "gpt-4"}

    def test_since_filter(self, db):
        now = time.time()
        db.save_metering_event(self._make_event(timestamp=now - 100))
        db.save_metering_event(self._make_event(timestamp=now - 10))
        db.save_metering_event(self._make_event(timestamp=now))

        events = db.get_metering_events("t-1", since=now - 50)
        assert len(events) == 2

    def test_empty(self, db):
        assert db.get_metering_events("t-1") == []


# ---------------------------------------------------------------------------
# Wallet snapshots
# ---------------------------------------------------------------------------


class TestWalletSnapshots:
    def _make_snapshot(self, **overrides):
        base = {
            "org_id": "org-1",
            "agent_id": "agent-a",
            "balance": 100.0,
            "reputation": 0.95,
            "snapshot_at": "2025-01-01T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_save_and_get(self, db):
        db.save_wallet_snapshot(self._make_snapshot())
        snaps = db.get_wallet_snapshots("org-1")
        assert len(snaps) == 1
        assert snaps[0]["balance"] == 100.0

    def test_multiple_snapshots(self, db):
        db.save_wallet_snapshot(self._make_snapshot(agent_id="a1"))
        db.save_wallet_snapshot(self._make_snapshot(agent_id="a2"))
        snaps = db.get_wallet_snapshots("org-1")
        assert len(snaps) == 2

    def test_filter_by_org(self, db):
        db.save_wallet_snapshot(self._make_snapshot(org_id="org-1"))
        db.save_wallet_snapshot(self._make_snapshot(org_id="org-2"))
        assert len(db.get_wallet_snapshots("org-1")) == 1


# ---------------------------------------------------------------------------
# PersistentTenantRegistry
# ---------------------------------------------------------------------------


class TestPersistentTenantRegistry:
    def test_register_and_get(self, registry):
        t, _ = registry.register("Acme")
        assert registry.get(t.tenant_id) is not None
        assert registry.get(t.tenant_id).name == "Acme"

    def test_get_by_api_key(self, registry):
        t, api_key = registry.register("Acme")
        found = registry.get_by_api_key(api_key)
        assert found is not None
        assert found.tenant_id == t.tenant_id

    def test_deactivate(self, registry):
        t, _ = registry.register("Acme")
        assert registry.deactivate(t.tenant_id) is True
        tenant = registry.get(t.tenant_id)
        assert tenant.active is False

    def test_list_all(self, registry):
        registry.register("A")
        registry.register("B")
        assert len(registry.list_all()) == 2

    def test_get_missing(self, registry):
        assert registry.get("nope") is None

    def test_deactivate_missing(self, registry):
        assert registry.deactivate("nope") is False


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_save_and_query(self, db):
        db.save_audit_event(
            actor="agent-a",
            action="task.created",
            resource="task",
            resource_id="task-1",
            tenant_id="t-1",
        )
        logs = db.get_audit_log(tenant_id="t-1")
        assert len(logs) == 1
        assert logs[0]["actor"] == "agent-a"
        assert logs[0]["action"] == "task.created"

    def test_append_only_multiple(self, db):
        for i in range(5):
            db.save_audit_event(
                actor=f"agent-{i}",
                action="org.updated",
                tenant_id="t-1",
            )
        logs = db.get_audit_log(tenant_id="t-1")
        assert len(logs) == 5

    def test_since_filter(self, db):
        import time as _time

        # Use timestamps with clear separation to avoid flakiness
        db.save_audit_event(actor="old", action="login", tenant_id="t-1")
        # Query the actual stored timestamp so cutoff is deterministic
        logs_all = db.get_audit_log(tenant_id="t-1")
        old_ts = logs_all[0]["timestamp"]
        cutoff = old_ts + 0.001  # 1ms after the old event
        # Ensure wall clock is past cutoff before inserting new event
        while _time.time() <= cutoff:
            _time.sleep(0.01)
        db.save_audit_event(actor="new", action="login", tenant_id="t-1")
        logs = db.get_audit_log(tenant_id="t-1", since=cutoff)
        assert len(logs) == 1
        assert logs[0]["actor"] == "new"

    def test_limit(self, db):
        for _i in range(10):
            db.save_audit_event(actor="a", action="x", tenant_id="t-1")
        logs = db.get_audit_log(tenant_id="t-1", limit=3)
        assert len(logs) == 3

    def test_no_tenant_filter(self, db):
        db.save_audit_event(actor="sys", action="boot")
        db.save_audit_event(actor="sys", action="boot", tenant_id="t-1")
        logs = db.get_audit_log()
        assert len(logs) == 2

    def test_table_exists(self, db):
        assert "audit_log" in inspect(db._engine).get_table_names()


class TestContextManager:
    def test_context_manager_closes_connection(self, tmp_path):
        path = str(tmp_path / "ctx.db")
        with Database(path) as db:
            db.save_tenant(
                {
                    "tenant_id": "t-1",
                    "name": "Acme",
                    "api_key_hash": "hash-1",
                    "active": True,
                    "metadata": {},
                    "created_at": "2025-01-01T00:00:00Z",
                }
            )
        # After exiting, connection is closed — operations should fail
        with pytest.raises(sqlite3.ProgrammingError):
            db._conn.execute("SELECT 1")
