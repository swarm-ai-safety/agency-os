from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from agency_os import models
from agency_os.sqlite_to_postgres_migration import migrate_sqlite_to_postgres


@pytest.fixture
def source_sqlite_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "source.db"
    conn = sqlite3.connect(db_path)
    fixture_sql = Path("tests/fixtures/sqlite_migration_sample.sql").read_text(
        encoding="utf-8"
    )
    conn.executescript(fixture_sql)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def target_database_url(tmp_path: Path) -> str:
    target_path = tmp_path / "target.db"
    engine = create_engine(f"sqlite:///{target_path}")
    models.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite:///{target_path}"


def _count_rows(database_url: str, table_name: str) -> int:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return int(
                conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
            )
    finally:
        engine.dispose()


def test_migrates_sample_fixture_with_row_reconciliation(
    source_sqlite_db: Path,
    target_database_url: str,
) -> None:
    report = migrate_sqlite_to_postgres(
        sqlite_path=str(source_sqlite_db),
        target_database_url=target_database_url,
        batch_size=2,
    )

    assert report["ok"] is True
    assert report["mismatches"] == []

    per_table = {row["table"]: row for row in report["tables"]}
    assert per_table["tenants"]["source_rows"] == 2
    assert per_table["organizations"]["source_rows"] == 2
    assert per_table["tasks"]["source_rows"] == 3
    assert per_table["metering_events"]["source_rows"] == 3

    assert _count_rows(target_database_url, "tenants") == 2
    assert _count_rows(target_database_url, "organizations") == 2
    assert _count_rows(target_database_url, "tasks") == 3
    assert _count_rows(target_database_url, "metering_events") == 3


def test_rerun_requires_truncate_target(
    source_sqlite_db: Path,
    target_database_url: str,
) -> None:
    migrate_sqlite_to_postgres(
        sqlite_path=str(source_sqlite_db),
        target_database_url=target_database_url,
    )

    with pytest.raises(ValueError, match="not empty"):
        migrate_sqlite_to_postgres(
            sqlite_path=str(source_sqlite_db),
            target_database_url=target_database_url,
        )

    rerun_report = migrate_sqlite_to_postgres(
        sqlite_path=str(source_sqlite_db),
        target_database_url=target_database_url,
        truncate_target=True,
    )
    assert rerun_report["ok"] is True


def test_dry_run_does_not_write_target_rows(
    source_sqlite_db: Path,
    target_database_url: str,
) -> None:
    report = migrate_sqlite_to_postgres(
        sqlite_path=str(source_sqlite_db),
        target_database_url=target_database_url,
        dry_run=True,
    )

    assert report["ok"] is True
    assert all(row["status"] == "dry-run" for row in report["tables"])
    assert _count_rows(target_database_url, "tenants") == 0
    assert _count_rows(target_database_url, "tasks") == 0
