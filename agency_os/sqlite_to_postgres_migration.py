"""SQLite-to-PostgreSQL data migration utility.

This module provides a deterministic data copy pipeline from a SQLite source
file into an already-migrated target database (typically PostgreSQL).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, func, select, table
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql import sqltypes

SQLITE_INTERNAL_TABLE_PREFIX = "sqlite_"


@dataclass
class TableReport:
    """Per-table migration summary."""

    table: str
    source_rows: int
    target_rows_before: int
    target_rows_after: int
    inserted_rows: int
    status: str


def _chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _fetch_source_tables(
    conn: sqlite3.Connection, requested: list[str] | None
) -> list[str]:
    if requested:
        return requested

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    tables = [str(row[0]) for row in rows]
    return [t for t in tables if not t.startswith(SQLITE_INTERNAL_TABLE_PREFIX)]


def _fk_dependencies(
    conn: sqlite3.Connection, tables: list[str]
) -> dict[str, set[str]]:
    deps: dict[str, set[str]] = {name: set() for name in tables}
    table_set = set(tables)
    for name in tables:
        rows = conn.execute(f"PRAGMA foreign_key_list({name})").fetchall()
        for row in rows:
            parent = str(row[2])
            if parent in table_set and parent != name:
                deps[name].add(parent)
    return deps


def _topological_order(deps: dict[str, set[str]]) -> list[str]:
    indegree: dict[str, int] = {name: len(parents) for name, parents in deps.items()}
    dependents: dict[str, list[str]] = defaultdict(list)
    for child, parents in deps.items():
        for parent in parents:
            dependents[parent].append(child)

    queue = deque(sorted([name for name, degree in indegree.items() if degree == 0]))
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for dependent in dependents[node]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(deps):
        # If there is a cycle (rare in this schema), preserve deterministic order.
        return sorted(deps.keys())
    return ordered


def _source_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _source_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0]) if row else 0


def _target_count(conn: Connection, table_name: str) -> int:
    tbl = table(table_name)
    stmt = select(func.count()).select_from(tbl)
    return int(conn.execute(stmt).scalar_one())


def _normalize_row(
    row: dict[str, Any],
    target_columns: dict[str, sqltypes.TypeEngine[Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        col_type = target_columns.get(key)
        if col_type is None:
            continue
        if isinstance(col_type, sqltypes.Boolean) and value in (0, 1):
            out[key] = bool(value)
        else:
            out[key] = value
    return out


def _truncate_target(
    conn: Connection,
    table_names: list[str],
    metadata: MetaData,
) -> None:
    if conn.dialect.name == "postgresql":
        quoted = [
            postgresql.dialect().identifier_preparer.quote(name) for name in table_names
        ]
        sql = f"TRUNCATE TABLE {', '.join(quoted)} RESTART IDENTITY CASCADE"
        conn.exec_driver_sql(sql)
        return

    # Fallback for non-PostgreSQL targets (used by local tests).
    for table_name in reversed(table_names):
        conn.execute(metadata.tables[table_name].delete())


def migrate_sqlite_to_postgres(
    sqlite_path: str,
    target_database_url: str,
    *,
    batch_size: int = 1000,
    dry_run: bool = False,
    truncate_target: bool = False,
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """Migrate SQLite rows into the target database and return reconciliation report."""

    source_path = Path(sqlite_path)
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    source = sqlite3.connect(str(source_path))
    source.row_factory = sqlite3.Row
    engine: Engine | None = None
    report: list[TableReport] = []
    try:
        table_names = _fetch_source_tables(source, tables)
        dependencies = _fk_dependencies(source, table_names)
        ordered_tables = _topological_order(dependencies)

        engine = create_engine(target_database_url)
        metadata = MetaData()
        metadata.reflect(bind=engine, only=ordered_tables)

        missing = [name for name in ordered_tables if name not in metadata.tables]
        if missing:
            raise RuntimeError(
                "Target DB is missing required tables. Run alembic upgrade head first. "
                f"Missing: {', '.join(missing)}"
            )

        with engine.begin() as target_conn:
            if truncate_target and not dry_run:
                _truncate_target(target_conn, ordered_tables, metadata)

            for table_name in ordered_tables:
                source_cols = _source_columns(source, table_name)
                source_row_count = _source_count(source, table_name)
                target_before = _target_count(target_conn, table_name)

                if not dry_run and not truncate_target and target_before > 0:
                    raise ValueError(
                        f"Target table '{table_name}' is not empty ({target_before} rows). "
                        "Use --truncate-target for reruns."
                    )

                target_table = metadata.tables[table_name]
                target_col_types = {
                    col.name: col.type
                    for col in target_table.columns
                    if col.name in source_cols
                }

                inserted = 0
                if not dry_run and source_row_count > 0:
                    rows = source.execute(f"SELECT * FROM {table_name}").fetchall()
                    payload = [
                        _normalize_row(dict(row), target_col_types)
                        for row in rows
                        if dict(row)
                    ]
                    for chunk in _chunked(payload, batch_size):
                        if chunk:
                            target_conn.execute(target_table.insert(), chunk)
                            inserted += len(chunk)

                target_after = _target_count(target_conn, table_name)
                status = "dry-run"
                if not dry_run:
                    status = "ok" if target_after == source_row_count else "mismatch"

                report.append(
                    TableReport(
                        table=table_name,
                        source_rows=source_row_count,
                        target_rows_before=target_before,
                        target_rows_after=target_after,
                        inserted_rows=inserted,
                        status=status,
                    )
                )
    finally:
        source.close()
        if engine is not None:
            engine.dispose()

    mismatches = [item.table for item in report if item.status == "mismatch"]
    return {
        "sqlite_path": str(source_path),
        "target_database_url": target_database_url,
        "dry_run": dry_run,
        "truncate_target": truncate_target,
        "tables": [item.__dict__ for item in report],
        "mismatches": mismatches,
        "ok": len(mismatches) == 0,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite into PostgreSQL with reconciliation."
    )
    parser.add_argument(
        "--sqlite-path",
        required=True,
        help="Path to SQLite source DB file",
    )
    parser.add_argument(
        "--postgres-url",
        required=True,
        help="Target PostgreSQL URL (e.g. postgresql+psycopg://...)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows per insert batch (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + report only; do not write target rows",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Truncate target tables before import for deterministic reruns",
    )
    parser.add_argument(
        "--tables",
        help="Optional comma-separated table subset",
    )
    parser.add_argument(
        "--report-path",
        help="Optional path to write JSON migration report",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    table_subset = None
    if args.tables:
        table_subset = [t.strip() for t in args.tables.split(",") if t.strip()]

    report = migrate_sqlite_to_postgres(
        sqlite_path=args.sqlite_path,
        target_database_url=args.postgres_url,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        truncate_target=args.truncate_target,
        tables=table_subset,
    )

    report_json = json.dumps(report, indent=2)
    if args.report_path:
        Path(args.report_path).write_text(report_json + "\n", encoding="utf-8")
    print(report_json)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
