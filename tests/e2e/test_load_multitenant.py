"""E2E load tests: multi-tenant scenarios with concurrency."""

import threading
from typing import Any

import pytest

from agency_os.orchestration.organization import Organization
from agency_os.tenancy.tenant import Tenant, TenantRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry_with_tenants(
    n: int,
) -> tuple[TenantRegistry, list[Tenant], list[str]]:
    """Create a TenantRegistry populated with *n* tenants."""
    registry = TenantRegistry()
    pairs = [registry.register(name=f"Tenant {i}") for i in range(n)]
    tenants = [t for t, _ in pairs]
    keys = [k for _, k in pairs]
    return registry, tenants, keys


# ---------------------------------------------------------------------------
# TestConcurrentTenantIsolation
# ---------------------------------------------------------------------------


class TestConcurrentTenantIsolation:
    """Multiple tenants each launch their own org; no cross-contamination."""

    @pytest.mark.parametrize("num_tenants", [2, 4])
    def test_each_tenant_has_independent_org(self, num_tenants: int):
        """Every tenant's org is a separate object with its own agent list."""
        _, tenants, _ = _make_registry_with_tenants(num_tenants)

        orgs: list[Any] = [None] * num_tenants
        errors: list[Exception] = []

        def launch(index: int, tenant: Tenant) -> None:
            try:
                org = Organization.from_builtin("saas_dev_studio")
                org.start()
                orgs[index] = org
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=launch, args=(i, t)) for i, t in enumerate(tenants)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Errors during concurrent org launch: {errors}"

        # Each org must be a distinct object
        for i in range(num_tenants):
            assert orgs[i] is not None
            for j in range(i + 1, num_tenants):
                assert orgs[i] is not orgs[j], (
                    f"Orgs {i} and {j} are the same object — isolation violated"
                )

        # Agent lists must be independent (no shared references)
        for i in range(num_tenants):
            for j in range(i + 1, num_tenants):
                shared = {id(a) for a in orgs[i].agents} & {
                    id(a) for a in orgs[j].agents
                }
                assert not shared, (
                    f"Tenants {i} and {j} share agent objects — isolation violated"
                )

        # Cleanup
        for org in orgs:
            if org is not None:
                org.stop()

    def test_tenant_registry_lookup_isolation(self):
        """Tenants retrieved by ID or API key never return each other's data."""
        registry, tenants, keys = _make_registry_with_tenants(5)

        results: dict[str, Any] = {}
        errors: list[Exception] = []
        lock = threading.Lock()

        def lookup(tenant: Tenant, key: str) -> None:
            try:
                by_id = registry.get(tenant.tenant_id)
                by_key = registry.get_by_api_key(key)
                with lock:
                    results[tenant.tenant_id] = (by_id, by_key)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=lookup, args=(t, k))
            for t, k in zip(tenants, keys, strict=False)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors
        for tenant in tenants:
            by_id, by_key = results[tenant.tenant_id]
            assert by_id is not None
            assert by_id.tenant_id == tenant.tenant_id
            assert by_key is not None
            assert by_key.tenant_id == tenant.tenant_id


# ---------------------------------------------------------------------------
# TestConcurrentTaskSubmission
# ---------------------------------------------------------------------------


class TestConcurrentTaskSubmission:
    """Multiple tasks submitted to the same org concurrently all get assigned."""

    @pytest.mark.parametrize("num_tasks", [5, 10, 20])
    def test_all_tasks_assigned(self, num_tasks: int):
        """Each of *num_tasks* concurrent submissions returns status='assigned'."""
        org = Organization.from_builtin("saas_dev_studio")
        org.start()

        results: list[Any] = [None] * num_tasks
        errors: list[Exception] = []
        lock = threading.Lock()

        def submit(index: int) -> None:
            try:
                result = org.submit_task(f"Concurrent task {index}")
                with lock:
                    results[index] = result
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(num_tasks)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Errors during concurrent task submission: {errors}"

        for i, result in enumerate(results):
            assert result is not None, f"Task {i} produced no result"
            assert result["status"] == "assigned", (
                f"Task {i} expected status='assigned', got {result['status']!r}"
            )
            assert result["assigned_to"] is not None, (
                f"Task {i} has no assigned_to value"
            )

        org.stop()

    def test_assigned_agents_belong_to_org(self):
        """Every assigned_to value references an agent that exists in the org."""
        org = Organization.from_builtin("saas_dev_studio")
        org.start()

        agent_ids = {a.agent_id for a in org.agents}
        num_tasks = 8
        assigned_ids: list[str] = []
        lock = threading.Lock()

        def submit(i: int) -> None:
            result = org.submit_task(f"Validation task {i}")
            with lock:
                assigned_ids.append(result["assigned_to"])

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(num_tasks)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        for assigned in assigned_ids:
            assert assigned in agent_ids, (
                f"Assigned agent {assigned!r} is not a member of the org"
            )

        org.stop()


# ---------------------------------------------------------------------------
# TestOrgLifecycleStress
# ---------------------------------------------------------------------------


class TestOrgLifecycleStress:
    """Rapidly start and stop multiple orgs to surface lifecycle bugs."""

    @pytest.mark.parametrize("num_orgs", [3, 5, 8])
    def test_rapid_start_stop(self, num_orgs: int):
        """All orgs reach 'running' then 'stopped' without errors."""
        statuses_after_start: list[str] = [None] * num_orgs  # type: ignore[list-item]
        statuses_after_stop: list[str] = [None] * num_orgs  # type: ignore[list-item]
        errors: list[Exception] = []
        lock = threading.Lock()

        def lifecycle(index: int) -> None:
            try:
                org = Organization.from_builtin("saas_dev_studio")
                org.start()
                with lock:
                    statuses_after_start[index] = org.status.value
                org.stop()
                with lock:
                    statuses_after_stop[index] = org.status.value
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=lifecycle, args=(i,)) for i in range(num_orgs)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Errors during rapid lifecycle: {errors}"

        for i in range(num_orgs):
            assert statuses_after_start[i] == "running", (
                f"Org {i} expected 'running' after start, got {statuses_after_start[i]!r}"
            )
            assert statuses_after_stop[i] == "stopped", (
                f"Org {i} expected 'stopped' after stop, got {statuses_after_stop[i]!r}"
            )

    def test_restart_org_is_clean(self):
        """An org that is stopped and restarted behaves like a fresh instance."""
        org = Organization.from_builtin("saas_dev_studio")

        org.start()
        assert org.status.value == "running"
        result_first = org.submit_task("First run task")
        assert result_first["status"] == "assigned"
        org.stop()
        assert org.status.value == "stopped"

        # Restart
        org.start()
        assert org.status.value == "running"
        result_second = org.submit_task("Second run task")
        assert result_second["status"] == "assigned"
        assert result_second["assigned_to"] is not None

        org.stop()

    @pytest.mark.parametrize(
        "package_name",
        [
            "saas_dev_studio",
            "marketing_agency",
            "devops_team",
            "product_squad",
        ],
    )
    def test_concurrent_start_different_packages(self, package_name: str):
        """Each package can be started concurrently without interfering."""
        num_instances = 3
        orgs: list[Any] = [None] * num_instances
        errors: list[Exception] = []
        lock = threading.Lock()

        def launch(index: int) -> None:
            try:
                org = Organization.from_builtin(package_name)
                org.start()
                with lock:
                    orgs[index] = org
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=launch, args=(i,)) for i in range(num_instances)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, (
            f"Errors launching {num_instances}x '{package_name}': {errors}"
        )
        for i, org in enumerate(orgs):
            assert org is not None
            assert org.status.value == "running", (
                f"Instance {i} of '{package_name}' not running"
            )
            assert len(org.agents) > 0

        for org in orgs:
            if org is not None:
                org.stop()
