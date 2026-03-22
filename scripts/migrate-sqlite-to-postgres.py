#!/usr/bin/env python3
"""CLI wrapper for SQLite-to-PostgreSQL migration pipeline."""

from agency_os.sqlite_to_postgres_migration import main

if __name__ == "__main__":
    raise SystemExit(main())
