from __future__ import annotations

import os
import tempfile

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from agency_os import models
from agency_os.gateway.provider_key_store import GatewayProviderKeyStore
from agency_os.gateway.providers.openai_provider import OpenAIProvider
from agency_os.gateway.providers.registry import ProviderRegistry
from agency_os.storage import Database
from agency_os.tenancy.secrets import SecretStore


def _make_db() -> tuple[Database, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(tmp.name)
    return db, tmp.name


class _CompileOnlyResult:
    def scalar_one_or_none(self) -> None:
        return None


class _CompileOnlyPGConnection:
    def __init__(self) -> None:
        self.dialect = postgresql.dialect()
        self.compiled_sql: list[str] = []

    def execute(self, stmt):
        compiled = str(
            stmt.compile(dialect=self.dialect, compile_kwargs={"literal_binds": True})
        )
        self.compiled_sql.append(compiled)
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


def test_set_key_encrypts_and_get_key_decrypts() -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        store.set_key("openai", "sk-live-test")

        with db._engine.connect() as conn:
            row = conn.execute(
                select(models.gateway_provider_keys.c.secret_encrypted).where(
                    models.gateway_provider_keys.c.provider == "openai"
                )
            ).fetchone()

        assert row is not None
        assert row.secret_encrypted != "sk-live-test"
        assert row.secret_encrypted.startswith("gAAAAA")
        assert store.get_key("openai") == "sk-live-test"
    finally:
        db.close()
        os.unlink(path)


def test_bootstrap_from_env_imports_missing_only(monkeypatch) -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        store.set_key("openai", "sk-existing")

        for env_var in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "TOGETHER_API_KEY",
            "FIREWORKS_API_KEY",
            "GROQ_API_KEY",
            "CUSTOM_OPENAI_API_KEY",
            "OLLAMA_API_KEY",
        ):
            monkeypatch.delenv(env_var, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-ignored")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-imported")

        imported = store.bootstrap_from_env()

        assert imported == 1
        assert store.get_key("openai") == "sk-existing"
        assert store.get_key("anthropic") == "ak-imported"
    finally:
        db.close()
        os.unlink(path)


def test_provider_registry_reads_secret_store_before_env(monkeypatch) -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        store.set_key("openai", "sk-from-store")

        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

        registry = ProviderRegistry(key_store=store)
        provider = registry.get("openai")

        assert provider is not None
        assert provider._api_key == "sk-from-store"
    finally:
        db.close()
        os.unlink(path)


def test_list_key_metadata_and_has_key() -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        assert store.has_key("openai") is False
        store.set_key("openai", "sk-live-test")
        assert store.has_key("openai") is True

        rows = store.list_key_metadata()
        assert len(rows) == 1
        assert rows[0]["provider"] == "openai"
        assert rows[0]["created_at"]
        assert rows[0]["updated_at"]
    finally:
        db.close()
        os.unlink(path)


def test_provider_registry_invalidate_reloads_rotated_key(monkeypatch) -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        store.set_key("openai", "sk-v1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-fallback")

        registry = ProviderRegistry(key_store=store)
        first = registry.get("openai")
        assert first is not None
        assert first._api_key == "sk-v1"

        store.set_key("openai", "sk-v2")
        same_before_invalidate = registry.get("openai")
        assert same_before_invalidate is first
        assert same_before_invalidate._api_key == "sk-v1"

        registry.invalidate("openai")
        second = registry.get("openai")
        assert second is not None
        assert second is not first
        assert second._api_key == "sk-v2"
    finally:
        db.close()
        os.unlink(path)


def test_provider_registry_allows_ollama_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    registry = ProviderRegistry()
    provider = registry.get("ollama")

    assert provider is not None
    assert isinstance(provider, OpenAIProvider)
    assert provider._api_key == ""
    assert provider._headers() == {"Content-Type": "application/json"}


def test_provider_registry_uses_auth_header_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    registry = ProviderRegistry()
    provider = registry.get("openai")

    assert provider is not None
    assert isinstance(provider, OpenAIProvider)
    assert provider._headers()["Authorization"] == "Bearer sk-test"


def test_set_key_upsert_compiles_for_postgres(monkeypatch) -> None:
    db, path = _make_db()
    try:
        store = GatewayProviderKeyStore(
            db=db,
            secret_store=SecretStore(master_key="test-master-key-32-bytes-long!!"),
        )
        compile_only_engine = _CompileOnlyPGEngine()
        monkeypatch.setattr(db, "_engine", compile_only_engine)

        store.set_key("openai", "sk-live-test")

        sql = compile_only_engine.conn.compiled_sql
        assert len(sql) == 1
        assert "ON CONFLICT" in sql[0].upper()
        assert "DO UPDATE" in sql[0].upper()
    finally:
        db.close()
        os.unlink(path)
