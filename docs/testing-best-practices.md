# Testing Best Practices

## Database Connection Lifecycle

The `Database` class implements the context manager protocol (`__enter__` and `__exit__`). Always use context managers to ensure connections are properly closed, even if exceptions occur.

### ✅ Correct Pattern

```python
from agency_os.storage import Database

def test_something():
    with Database(":memory:") as db:
        # Use the database
        db.save_tenant({"tenant_id": "test", ...})
        result = db.get_tenant("test")
        assert result is not None
    # Connection automatically closed here
```

### ✅ Correct Fixture Pattern

```python
import pytest
import tempfile
import os
from agency_os.storage import Database

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    db.close()  # Explicit cleanup after all tests using this fixture
    os.remove(path)
```

### ❌ Incorrect Pattern (Resource Leak)

```python
def test_something():
    db = Database(":memory:")
    db.save_tenant({"tenant_id": "test", ...})
    result = db.get_tenant("test")
    assert result is not None
    db.close()  # ⚠️ Won't run if assertion fails or exception occurs
```

### ❌ Incorrect Fixture Pattern (Resource Leak)

```python
@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Database(path)  # ⚠️ Connection never closed
    os.remove(path)
```

## Resource Leak Prevention

### CI Enforcement

The CI pipeline runs tests with `-W error::ResourceWarning`, which treats unclosed database connections as test failures:

```bash
pytest tests/ -W error::ResourceWarning
```

This prevents resource leaks from being merged.

### Local Development

Enable resource warnings during local testing:

```bash
# Fail on resource warnings
pytest -W error::ResourceWarning

# Show resource warnings without failing
pytest -W default::ResourceWarning

# Enable tracemalloc for allocation tracebacks
python -X tracemalloc=5 -m pytest
```

## Why Context Managers Matter

1. **Exception Safety**: If an exception occurs before `db.close()`, the connection leaks
2. **File Descriptor Exhaustion**: Unclosed connections can exhaust file descriptors in CI/CD
3. **Test Isolation**: Leaked connections can cause "database is locked" errors in subsequent tests
4. **Production Risk**: Patterns in tests often mirror production code — if tests leak, production might too

## Common Scenarios

### In-Memory Database (Tests)

```python
with Database(":memory:") as db:
    # Ideal for unit tests — fast, isolated, auto-cleanup
    pass
```

### Temporary File Database (Integration Tests)

```python
import tempfile
import os

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name

try:
    with Database(db_path) as db:
        # Integration test logic
        pass
finally:
    os.unlink(db_path)
```

### Long-Lived Database (Production)

```python
# FastAPI app startup
db = Database()  # OK to keep open for app lifetime

# No need for context manager — connection lives as long as the process
```

## Migration from Old Pattern

If you see this pattern in existing tests:

```python
db = Database(path)
# ... test code ...
db.close()
```

Refactor to:

```python
with Database(path) as db:
    # ... test code ...
```

## Related

- Database schema: `agency_os/storage.py`
- Database migrations: `docs/database-migrations.md`
- CI configuration: `.github/workflows/ci.yml`

## Backend-Specific Notes

- `tests/unit/test_storage.py` intentionally validates SQLite-specific fallback behavior and should remain SQLite-focused.
- Cross-backend compatibility checks run in CI via `backend-compat` matrix (`sqlite`, `postgres`) against:
  - `tests/unit/test_schema_validation.py`
  - `tests/integration/test_sqlite_to_postgres_migration.py`
- Database selection contract:
  - If `DATABASE_URL` is set, `Database(db_path=...)` uses that URL for the SQLAlchemy engine.
  - Under non-SQLite backends (for example PostgreSQL), `db_path` is still used to derive an isolated schema name (`search_path`) so tempfile-backed tests do not bleed state across cases.
  - If `DATABASE_URL` is unset, `db_path` selects the SQLite file path directly.
