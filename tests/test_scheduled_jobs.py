"""Tests for scheduled background jobs."""

from __future__ import annotations

import types

from agency_os.service.scheduled_jobs import (
    ScheduledJobsManager,
    get_orphaned_lock_reconciliation_metrics,
    get_queued_run_timeout_metrics,
    get_workspace_drift_metrics,
    reset_orphaned_lock_reconciliation_metrics,
    reset_queued_run_timeout_metrics,
    reset_workspace_drift_metrics,
    start_scheduled_jobs,
    stop_scheduled_jobs,
)


class _DummyRunFailureTracker:
    def record(self, *, failure: bool) -> None:
        pass

    def record_api_error(self, error: str) -> None:
        pass


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeErrorResponse(_FakeResponse):
    def raise_for_status(self) -> None:
        raise RuntimeError("500 Internal Server Error")


class _TrackingRunFailureTracker:
    def __init__(self) -> None:
        self.events: list[bool] = []
        self.api_errors: list[str] = []

    def record(self, *, failure: bool) -> None:
        self.events.append(failure)

    def record_api_error(self, error: str) -> None:
        self.api_errors.append(error)


def test_cleanup_stale_locks_releases_execution_and_checkout(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-1",
                "identifier": "ZERA-1",
                "executionLockedAt": "2000-01-01T00:00:00Z",
            },
            {
                "id": "i-2",
                "identifier": "ZERA-2",
                "checkoutLockedAt": "2000-01-01T00:00:00Z",
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_stale_locks()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-1/release",
        "http://paperclip.local/api/issues/i-2/release",
    ]


def test_cleanup_stale_locks_uses_standard_release_endpoint_only(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-9",
                "identifier": "ZERA-9",
                "executionLockedAt": "2000-01-01T00:00:00Z",
            }
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_stale_locks()

    assert released_urls == ["http://paperclip.local/api/issues/i-9/release"]
    assert all("/force-release" not in url for url in released_urls)


def test_cleanup_stale_locks_continues_when_release_fails(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-1",
                "identifier": "ZERA-1",
                "executionLockedAt": "2000-01-01T00:00:00Z",
            },
            {
                "id": "i-2",
                "identifier": "ZERA-2",
                "checkoutLockedAt": "2000-01-01T00:00:00Z",
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        if url.endswith("/i-1/release"):
            return _FakeErrorResponse({})
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_stale_locks()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-1/release",
        "http://paperclip.local/api/issues/i-2/release",
    ]


def test_cleanup_stale_queued_runs_releases_timed_out_queue(monkeypatch):
    reset_queued_run_timeout_metrics()
    issue_payload = {
        "items": [
            {
                "id": "i-3",
                "identifier": "ZERA-3",
                "executionRunId": "r-3",
                "activeRun": {
                    "id": "r-3",
                    "status": "queued",
                    "createdAt": "2000-01-01T00:00:00Z",
                },
            },
            {
                "id": "i-4",
                "identifier": "ZERA-4",
                "executionRunId": "r-4",
                "activeRun": {
                    "id": "r-4",
                    "status": "running",
                    "createdAt": "2000-01-01T00:00:00Z",
                },
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")
    monkeypatch.setenv("PAPERCLIP_QUEUED_RUN_TIMEOUT_MINUTES", "5")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_stale_queued_runs()

    assert released_urls == ["http://paperclip.local/api/issues/i-3/release"]
    metrics = get_queued_run_timeout_metrics()
    assert metrics["timed_out_runs_total"] == 1
    assert metrics["timed_out_issues_total"] == 1
    assert metrics["last_timeout_timestamp"] is not None


def test_cleanup_stale_queued_runs_continues_when_release_fails(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-3",
                "identifier": "ZERA-3",
                "executionRunId": "r-3",
                "activeRun": {
                    "id": "r-3",
                    "status": "queued",
                    "createdAt": "2000-01-01T00:00:00Z",
                },
            },
            {
                "id": "i-4",
                "identifier": "ZERA-4",
                "executionRunId": "r-4",
                "activeRun": {
                    "id": "r-4",
                    "status": "queued",
                    "createdAt": "2000-01-01T00:00:00Z",
                },
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        if url.endswith("/i-3/release"):
            return _FakeErrorResponse({})
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")
    monkeypatch.setenv("PAPERCLIP_QUEUED_RUN_TIMEOUT_MINUTES", "5")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_stale_queued_runs()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-3/release",
        "http://paperclip.local/api/issues/i-4/release",
    ]


def test_clear_startup_execution_locks_releases_all_run_locks(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-1",
                "identifier": "ZERA-1",
                "executionRunId": "run-1",
            },
            {
                "id": "i-2",
                "identifier": "ZERA-2",
                "checkoutRunId": "run-2",
            },
            {
                "id": "i-3",
                "identifier": "ZERA-3",
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(issue_payload)

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.clear_startup_execution_locks()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-1/release",
        "http://paperclip.local/api/issues/i-2/release",
    ]


def test_cleanup_orphaned_run_locks_releases_only_orphans(monkeypatch):
    reset_orphaned_lock_reconciliation_metrics()
    issue_payload = {
        "items": [
            {
                "id": "i-1",
                "identifier": "ZERA-1",
                "executionRunId": "run-missing",
                "executionLockedAt": "2026-03-08T00:00:00Z",
            },
            {
                "id": "i-2",
                "identifier": "ZERA-2",
                "executionRunId": "run-present",
                "executionLockedAt": "2026-03-08T00:00:00Z",
            },
            {
                "id": "i-3",
                "identifier": "ZERA-3",
                "checkoutRunId": "checkout-missing",
                "checkoutLockedAt": "2026-03-08T00:00:00Z",
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse(issue_payload)
        if url.endswith("/api/issues/i-1/runs"):
            return _FakeResponse([{"runId": "some-other-run"}])
        if url.endswith("/api/issues/i-2/runs"):
            return _FakeResponse([{"runId": "run-present"}])
        if url.endswith("/api/issues/i-3/runs"):
            return _FakeResponse([])
        raise AssertionError(f"Unexpected GET URL: {url}")

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-1/release",
        "http://paperclip.local/api/issues/i-3/release",
    ]
    metrics = get_orphaned_lock_reconciliation_metrics()
    assert metrics["reconciled_locks_total"] == 2
    assert metrics["reconciled_issues_total"] == 2
    assert metrics["last_reconciliation_timestamp"] is not None


def test_cleanup_orphaned_run_locks_continues_when_release_fails(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-1",
                "identifier": "ZERA-1",
                "executionRunId": "run-missing",
            },
            {
                "id": "i-2",
                "identifier": "ZERA-2",
                "executionRunId": "run-missing-2",
            },
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse(issue_payload)
        if url.endswith("/api/issues/i-1/runs"):
            return _FakeResponse([])
        if url.endswith("/api/issues/i-2/runs"):
            return _FakeResponse([])
        raise AssertionError(f"Unexpected GET URL: {url}")

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        if url.endswith("/i-1/release"):
            return _FakeErrorResponse({})
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert released_urls == [
        "http://paperclip.local/api/issues/i-1/release",
        "http://paperclip.local/api/issues/i-2/release",
    ]


def test_cleanup_orphaned_run_locks_releases_detached_terminal_execution_lock(
    monkeypatch,
):
    issue_payload = {
        "items": [
            {
                "id": "i-10",
                "identifier": "ZERA-10",
                "executionRunId": "run-finished",
                "activeRun": None,
            }
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse(issue_payload)
        if url.endswith("/api/issues/i-10/runs"):
            return _FakeResponse([{"runId": "run-finished", "status": "completed"}])
        raise AssertionError(f"Unexpected GET URL: {url}")

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert released_urls == ["http://paperclip.local/api/issues/i-10/release"]


def test_cleanup_orphaned_run_locks_skips_detached_non_terminal_execution_lock(
    monkeypatch,
):
    issue_payload = {
        "items": [
            {
                "id": "i-11",
                "identifier": "ZERA-11",
                "executionRunId": "run-queued",
                "activeRun": None,
            }
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse(issue_payload)
        if url.endswith("/api/issues/i-11/runs"):
            return _FakeResponse([{"runId": "run-queued", "status": "queued"}])
        raise AssertionError(f"Unexpected GET URL: {url}")

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert released_urls == []


def test_cleanup_orphaned_run_locks_releases_orphan_without_locked_at(monkeypatch):
    issue_payload = {
        "items": [
            {
                "id": "i-12",
                "identifier": "ZERA-12",
                "executionRunId": "run-missing",
            }
        ]
    }
    released_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse(issue_payload)
        if url.endswith("/api/issues/i-12/runs"):
            return _FakeResponse([{"runId": "different-run", "status": "completed"}])
        raise AssertionError(f"Unexpected GET URL: {url}")

    def fake_post(url, headers=None, timeout=None):
        released_urls.append(url)
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert released_urls == ["http://paperclip.local/api/issues/i-12/release"]


def test_cleanup_orphaned_run_locks_respects_toggle(monkeypatch):
    calls = {"get": 0, "post": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["get"] += 1
        return _FakeResponse({"items": []})

    def fake_post(url, headers=None, timeout=None):
        calls["post"] += 1
        return _FakeResponse({})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(get=fake_get, post=fake_post),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_ENABLED", "false")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.cleanup_orphaned_run_locks()

    assert calls == {"get": 0, "post": 0}


def test_audit_workspace_configuration_drift_detects_mismatch(monkeypatch):
    reset_workspace_drift_metrics()
    issue_payload = {
        "items": [
            {
                "id": "project-1",
                "name": "agency-os",
                "workspaces": [
                    {
                        "id": "w-1",
                        "name": "agency-os",
                        "cwd": "/tmp/repo",
                        "repoUrl": "https://github.com/raelisavitt/agency-os.git",
                    }
                ],
            }
        ]
    }

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/projects"):
            return _FakeResponse(issue_payload)
        raise AssertionError(f"Unexpected GET URL: {url}")

    class _Result:
        returncode = 0
        stdout = "git@github.com:rsavitt/agency-os.git\n"

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(
            get=fake_get, post=lambda *args, **kwargs: _FakeResponse({})
        ),
    )
    monkeypatch.setattr(
        "agency_os.service.scheduled_jobs.os.path.isdir", lambda _path: True
    )
    monkeypatch.setattr(
        "agency_os.service.scheduled_jobs.os.path.exists", lambda _path: True
    )
    monkeypatch.setattr(
        "agency_os.service.scheduled_jobs.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.audit_workspace_configuration_drift()

    metrics = get_workspace_drift_metrics()
    assert metrics["scanned_workspaces_total"] == 1
    assert metrics["drifted_workspaces_total"] == 1
    assert metrics["last_scan_timestamp"] is not None


def test_audit_workspace_configuration_drift_respects_toggle(monkeypatch):
    calls = {"get": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["get"] += 1
        return _FakeResponse({"items": []})

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(
            get=fake_get, post=lambda *args, **kwargs: _FakeResponse({})
        ),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("PAPERCLIP_WORKSPACE_DRIFT_DETECTION_ENABLED", "false")

    manager = ScheduledJobsManager(_DummyRunFailureTracker(), db=None)
    manager.audit_workspace_configuration_drift()
    assert calls["get"] == 0


def test_start_scheduled_jobs_orphaned_reconciliation_interval_and_toggle(monkeypatch):
    jobs: list[dict] = []
    calls: list[str] = []

    class _FakeScheduler:
        def add_job(self, func, trigger, minutes, id, name):
            jobs.append(
                {
                    "func": func.__name__,
                    "trigger": trigger,
                    "minutes": minutes,
                    "id": id,
                    "name": name,
                }
            )

        def start(self):
            calls.append("scheduler.start")

        def shutdown(self, wait=False):
            calls.append(f"scheduler.shutdown(wait={wait})")

    sys_modules = __import__("sys").modules
    monkeypatch.setitem(sys_modules, "apscheduler", types.SimpleNamespace())
    monkeypatch.setitem(sys_modules, "apscheduler.schedulers", types.SimpleNamespace())
    monkeypatch.setitem(
        sys_modules,
        "apscheduler.schedulers.background",
        types.SimpleNamespace(BackgroundScheduler=_FakeScheduler),
    )
    monkeypatch.setenv("PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_MINUTES", "10")
    monkeypatch.setenv("PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_ENABLED", "true")
    monkeypatch.setenv("PAPERCLIP_WORKSPACE_DRIFT_DETECTION_MINUTES", "30")
    monkeypatch.setenv("PAPERCLIP_WORKSPACE_DRIFT_DETECTION_ENABLED", "true")

    monkeypatch.setattr(
        ScheduledJobsManager,
        "clear_startup_execution_locks",
        lambda self: calls.append("clear_startup_execution_locks"),
    )
    monkeypatch.setattr(
        ScheduledJobsManager,
        "cleanup_orphaned_run_locks",
        lambda self: calls.append("cleanup_orphaned_run_locks"),
    )
    monkeypatch.setattr(
        ScheduledJobsManager,
        "cleanup_stale_queued_runs",
        lambda self: calls.append("cleanup_stale_queued_runs"),
    )
    monkeypatch.setattr(
        ScheduledJobsManager,
        "cleanup_stale_locks",
        lambda self: calls.append("cleanup_stale_locks"),
    )
    monkeypatch.setattr(
        ScheduledJobsManager,
        "audit_workspace_configuration_drift",
        lambda self: calls.append("audit_workspace_configuration_drift"),
    )

    scheduler = start_scheduled_jobs(_DummyRunFailureTracker(), db=None)
    orphan_jobs = [job for job in jobs if job["id"] == "cleanup_orphaned_run_locks"]
    drift_jobs = [
        job for job in jobs if job["id"] == "audit_workspace_configuration_drift"
    ]
    assert scheduler is not None
    assert len(orphan_jobs) == 1
    assert orphan_jobs[0]["minutes"] == 10
    assert len(drift_jobs) == 1
    assert drift_jobs[0]["minutes"] == 30

    jobs.clear()
    monkeypatch.setenv("PAPERCLIP_ORPHANED_LOCK_RECONCILIATION_ENABLED", "false")
    monkeypatch.setenv("PAPERCLIP_WORKSPACE_DRIFT_DETECTION_ENABLED", "false")
    scheduler = start_scheduled_jobs(_DummyRunFailureTracker(), db=None)
    orphan_jobs = [job for job in jobs if job["id"] == "cleanup_orphaned_run_locks"]
    drift_jobs = [
        job for job in jobs if job["id"] == "audit_workspace_configuration_drift"
    ]
    assert scheduler is not None
    assert orphan_jobs == []
    assert drift_jobs == []


def test_stop_scheduled_jobs_calls_shutdown_wait_false():
    calls: list[bool] = []

    class _FakeScheduler:
        def shutdown(self, wait=False):
            calls.append(wait)

    stop_scheduled_jobs(_FakeScheduler())
    assert calls == [False]


def test_poll_run_statistics_falls_back_when_company_runs_500(monkeypatch):
    tracker = _TrackingRunFailureTracker()

    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/dashboard"):
            return _FakeResponse({"tasks": {"total": 12}, "agents": {"total": 4}})
        if url.endswith("/api/companies/c/runs"):
            return _FakeErrorResponse({})
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse({"items": [{"id": "i-1"}, {"id": "i-2"}]})
        if url.endswith("/api/issues/i-1/runs"):
            return _FakeResponse([{"status": "succeeded"}, {"status": "failed"}])
        if url.endswith("/api/issues/i-2/runs"):
            return _FakeResponse([{"status": "completed"}, {"status": "error"}])
        raise AssertionError(f"Unexpected GET URL: {url}")

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(
            get=fake_get, post=lambda *args, **kwargs: _FakeResponse({})
        ),
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://paperclip.local")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")

    manager = ScheduledJobsManager(tracker, db=None)
    manager.poll_run_statistics()  # Establish baseline from issue run fallback (2 success / 2 fail)
    assert tracker.events == []
    assert tracker.api_errors == []

    def fake_get_second_poll(url, headers=None, params=None, timeout=None):
        if url.endswith("/api/companies/c/dashboard"):
            return _FakeResponse({"tasks": {"total": 12}, "agents": {"total": 4}})
        if url.endswith("/api/companies/c/runs"):
            return _FakeErrorResponse({})
        if url.endswith("/api/companies/c/issues"):
            return _FakeResponse({"items": [{"id": "i-1"}, {"id": "i-2"}]})
        if url.endswith("/api/issues/i-1/runs"):
            return _FakeResponse(
                [
                    {"status": "succeeded"},
                    {"status": "failed"},
                    {"status": "succeeded"},
                ]
            )
        if url.endswith("/api/issues/i-2/runs"):
            return _FakeResponse([{"status": "completed"}, {"status": "error"}])
        raise AssertionError(f"Unexpected GET URL: {url}")

    monkeypatch.setitem(
        __import__("sys").modules,
        "httpx",
        types.SimpleNamespace(
            get=fake_get_second_poll,
            post=lambda *args, **kwargs: _FakeResponse({}),
        ),
    )

    manager.poll_run_statistics()
    assert tracker.events == [False]
    assert tracker.api_errors == []
