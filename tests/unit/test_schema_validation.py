"""Schema validation tests to prevent drift between models and Alembic schema."""

from pathlib import Path

from sqlalchemy import inspect

from agency_os import models, storage


def test_tasks_schema_matches_models(tmp_path):
    """Verify tasks table in migrated schema matches models.py definition."""
    model_columns = {col.name: col for col in models.tasks.columns}

    db_path = str(tmp_path / "schema.db")
    with storage.Database(db_path) as db:
        schema_columns = {
            column["name"] for column in inspect(db._engine).get_columns("tasks")
        }

        for col_name in model_columns:
            assert col_name in schema_columns, (
                f"Column '{col_name}' exists in models.py but missing in database schema"
            )

        assert "governance_preset" in schema_columns
        assert "task_id" in schema_columns
        assert "tenant_id" in schema_columns


def test_waitlist_schema_uses_ip_hash(tmp_path):
    """Verify waitlist table uses ip_hash (not ip)."""
    db_path = str(tmp_path / "waitlist.db")
    with storage.Database(db_path) as db:
        column_names = {
            column["name"] for column in inspect(db._engine).get_columns("waitlist")
        }

        assert "ip_hash" in column_names
        assert "ip" not in column_names


def test_schema_has_foreign_keys(tmp_path):
    """Verify foreign key constraints are active for the configured backend."""
    db_path = str(tmp_path / "fk.db")
    with storage.Database(db_path) as db:
        with db._engine.connect() as conn:
            foreign_keys = inspect(conn).get_foreign_keys("tasks")
            constrained = {
                col for fk in foreign_keys for col in fk.get("constrained_columns", [])
            }
            assert "tenant_id" in constrained
            assert "org_id" in constrained


def test_runtime_ddl_is_removed():
    """Storage should rely on Alembic, not hardcoded CREATE TABLE scripts."""
    source = Path("agency_os/storage.py").read_text()
    assert "_init_tables(" not in source
    assert "CREATE TABLE IF NOT EXISTS" not in source


def test_critical_tables_exist_in_both_sources(tmp_path):
    """Verify critical tables exist in both models.py and migrated database."""
    critical_tables = {
        "tenants",
        "organizations",
        "tasks",
        "metering_events",
        "trust_scores",
        "waitlist",
        "gateway_requests",
    }

    model_tables = {table.name for table in models.metadata.tables.values()}

    db_path = str(tmp_path / "tables.db")
    with storage.Database(db_path) as db:
        schema_tables = set(inspect(db._engine).get_table_names())

        for table_name in critical_tables:
            assert table_name in model_tables, (
                f"Critical table '{table_name}' missing in models.py"
            )
            assert table_name in schema_tables, (
                f"Critical table '{table_name}' missing in database schema"
            )
