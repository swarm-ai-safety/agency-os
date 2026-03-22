"""SwarmWorkerAgent — wraps SWARM research primitives as autonomous service workers.

Each worker agent controls one or more SWARM services. When an ACP request
arrives, the worker agent:
1. Validates the request against the service input schema
2. Executes the appropriate SWARM module (with timeout)
3. Applies governance/safety checks
4. Formats and returns the result
5. Reports metering for billing settlement

Security:
    - Handler paths allowlisted to agency_os.marketplace.handlers.* only (C3)
    - Input params validated against service input_schema before dispatch (C2)
    - Execution timeout enforced per SLA (H1)
    - Thread-safe state management (L1)
"""

from __future__ import annotations

import concurrent.futures
import importlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from agency_os.marketplace.catalog import ServiceCatalog, SwarmService

logger = logging.getLogger(__name__)

# C3: Only allow handler imports from this module prefix
HANDLER_ALLOWLIST_PREFIX = "agency_os.marketplace.handlers"

# H1: Default execution timeout (seconds)
DEFAULT_EXECUTION_TIMEOUT = 300  # 5 minutes

# C2: Keys that should never be forwarded from input_params
_FORBIDDEN_PARAM_KEYS = {"__class__", "__module__", "__import__", "exec", "eval"}


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ServiceJob:
    """A single service invocation tracked by the worker agent."""

    job_id: str
    service_id: str
    client_agent_id: str
    input_params: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    cost_usd: float = 0.0

    @property
    def latency_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


def _validate_input_params(
    params: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Validate and sanitize input parameters against the service schema (C2).

    - Strips keys not declared in the schema properties
    - Rejects forbidden parameter names
    - Enforces basic type constraints from the schema
    """
    # Reject forbidden keys
    for key in _FORBIDDEN_PARAM_KEYS:
        if key in params:
            raise ValueError(f"Forbidden parameter: {key}")

    # If no schema properties defined, allow known safe params only
    properties = schema.get("properties", {})
    if not properties:
        # No schema — strip internal keys, pass through
        return {k: v for k, v in params.items() if not k.startswith("_")}

    # Filter to only declared properties
    validated: dict[str, Any] = {}
    for key, prop_schema in properties.items():
        if key in params:
            value = params[key]
            expected_type = prop_schema.get("type")
            # Basic type coercion / validation
            if expected_type == "integer" and isinstance(value, (int, float)):
                validated[key] = int(value)
            elif expected_type == "number" and isinstance(value, (int, float)):
                validated[key] = float(value)
            elif expected_type == "string" and isinstance(value, str):
                # Enforce enum constraints if present
                allowed = prop_schema.get("enum")
                if allowed and value not in allowed:
                    validated[key] = prop_schema.get("default", allowed[0])
                else:
                    validated[key] = value
            elif expected_type == "array" and isinstance(value, list):
                validated[key] = value
            elif expected_type == "object" and isinstance(value, dict):
                validated[key] = value
            elif expected_type == "boolean" and isinstance(value, bool):
                validated[key] = value
            else:
                # Type mismatch — use default or skip
                if "default" in prop_schema:
                    validated[key] = prop_schema["default"]
        elif "default" in prop_schema:
            validated[key] = prop_schema["default"]

    return validated


class SwarmWorkerAgent:
    """Autonomous worker agent that executes SWARM services for paying clients.

    Each worker manages a set of SWARM services and handles the full lifecycle:
    request validation -> execution -> governance -> result formatting -> billing.
    """

    def __init__(
        self,
        agent_id: str,
        catalog: ServiceCatalog,
        service_ids: list[str] | None = None,
        execution_timeout: float = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        self.agent_id = agent_id
        self._catalog = catalog
        self._service_ids = set(service_ids or [])
        self._jobs: dict[str, ServiceJob] = {}
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {}
        self._execution_timeout = execution_timeout
        # L1: Thread-safe counters
        self._lock = threading.Lock()
        self._total_revenue_usd: float = 0.0
        self._total_jobs: int = 0
        self._failed_jobs: int = 0
        # M3: Limit in-memory job history
        self._max_job_history = 10000

        # Resolve handlers for assigned services
        for sid in self._service_ids:
            service = catalog.get(sid)
            if service:
                self._resolve_handler(service)

    def _resolve_handler(self, service: SwarmService) -> None:
        """Dynamically resolve the handler function for a service.

        C3: Only allows imports from the allowlisted module prefix.
        """
        handler_path = service.handler
        # C3: Validate handler path against allowlist
        if not handler_path.startswith(HANDLER_ALLOWLIST_PREFIX):
            logger.error(
                "SECURITY: Rejected handler path '%s' for service '%s' — "
                "not in allowlist prefix '%s'",
                handler_path,
                service.service_id,
                HANDLER_ALLOWLIST_PREFIX,
            )
            return

        try:
            module_path, func_name = handler_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler = getattr(module, func_name)
            if not callable(handler):
                raise TypeError(f"{handler_path} is not callable")
            self._handlers[service.service_id] = handler
            logger.info("Resolved handler for %s: %s", service.service_id, handler_path)
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning(
                "Could not resolve handler for %s: %s. Service will not be available.",
                service.service_id,
                e,
            )

    def register_handler(
        self, service_id: str, handler: Callable[..., dict[str, Any]]
    ) -> None:
        """Manually register a handler function for a service."""
        self._handlers[service_id] = handler
        self._service_ids.add(service_id)

    @property
    def services(self) -> list[SwarmService]:
        """List services this worker can execute."""
        return [
            s for sid in self._service_ids if (s := self._catalog.get(sid)) is not None
        ]

    def can_handle(self, service_id: str) -> bool:
        """Check if this worker can handle a given service."""
        return service_id in self._service_ids and service_id in self._handlers

    def submit_job(
        self,
        service_id: str,
        client_agent_id: str,
        input_params: dict[str, Any],
    ) -> ServiceJob:
        """Submit a new job for execution.

        Args:
            service_id: Which SWARM service to invoke.
            client_agent_id: The requesting agent's ID.
            input_params: Parameters for the service invocation.

        Returns:
            ServiceJob with status and results after execution.

        Raises:
            ValueError: If the service is unknown or the worker can't handle it.
        """
        service = self._catalog.get(service_id)
        if service is None:
            raise ValueError(f"Unknown service: {service_id}")
        if not self.can_handle(service_id):
            raise ValueError(
                f"Worker {self.agent_id} cannot handle service: {service_id}"
            )

        # C2: Validate input_params against service schema
        validated_params = _validate_input_params(input_params, service.input_schema)

        job = ServiceJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            service_id=service_id,
            client_agent_id=client_agent_id,
            input_params=validated_params,
        )
        with self._lock:
            # M3: Evict oldest jobs if at capacity
            if len(self._jobs) >= self._max_job_history:
                oldest_key = next(iter(self._jobs))
                del self._jobs[oldest_key]
            self._jobs[job.job_id] = job
            self._total_jobs += 1

        # Execute synchronously (with timeout)
        self._execute_job(job, service)
        return job

    def _execute_job(self, job: ServiceJob, service: SwarmService) -> None:
        """Execute a service job using the resolved handler with timeout (H1)."""
        job.status = JobStatus.RUNNING
        job.started_at = time.time()

        handler = self._handlers.get(service.service_id)
        if handler is None:
            job.status = JobStatus.FAILED
            job.error = f"No handler registered for {service.service_id}"
            job.completed_at = time.time()
            with self._lock:
                self._failed_jobs += 1
            return

        # H1: Execute with timeout using ThreadPoolExecutor
        timeout = min(self._execution_timeout, service.sla.max_latency_seconds)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(handler, **job.input_params)
                result = future.result(timeout=timeout)

            job.result = result
            job.status = JobStatus.COMPLETED

            # Compute cost based on pricing model
            units = result.get("_units", 1)
            job.cost_usd = service.pricing.compute_cost(units)

            latency = time.time() - job.started_at
            self._catalog.record_invocation(service.service_id, latency, job.cost_usd)
            with self._lock:
                self._total_revenue_usd += job.cost_usd

            logger.info(
                "Job %s completed: service=%s, client=%s, cost=$%.2f, latency=%.1fs",
                job.job_id,
                service.service_id,
                job.client_agent_id,
                job.cost_usd,
                latency,
            )
        except concurrent.futures.TimeoutError:
            job.status = JobStatus.FAILED
            job.error = f"Execution timed out after {timeout:.0f}s"
            with self._lock:
                self._failed_jobs += 1
            logger.error(
                "Job %s timed out: service=%s, timeout=%.0fs",
                job.job_id,
                service.service_id,
                timeout,
            )
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            with self._lock:
                self._failed_jobs += 1
            logger.error(
                "Job %s failed: service=%s, error=%s",
                job.job_id,
                service.service_id,
                e,
            )
        finally:
            job.completed_at = time.time()

    def get_job(self, job_id: str) -> ServiceJob | None:
        """Look up a job by ID."""
        return self._jobs.get(job_id)

    def stats(self) -> dict[str, Any]:
        """Return worker agent statistics."""
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "services": list(self._service_ids),
                "total_jobs": self._total_jobs,
                "failed_jobs": self._failed_jobs,
                "success_rate": (
                    (self._total_jobs - self._failed_jobs) / self._total_jobs
                    if self._total_jobs > 0
                    else 1.0
                ),
                "total_revenue_usd": self._total_revenue_usd,
            }
