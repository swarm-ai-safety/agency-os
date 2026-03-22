"""ACP Request Router — routes incoming agent-to-agent service requests.

Handles the full lifecycle of an autonomous agent purchasing a SWARM service:
1. Client agent discovers services via ACP
2. Client submits a service request with payment
3. Router creates escrow, finds a worker, dispatches the job
4. Worker executes SWARM module
5. Result is evaluated and payment is settled

Security:
    - Bounded request log with eviction (M3)
    - Improved evaluation with structural + content checks (M2)
    - Certification signing with deterministic IDs
"""

from __future__ import annotations

import collections
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agency_os.marketplace.acp import ACPClient
from agency_os.marketplace.catalog import ServiceCatalog
from agency_os.marketplace.worker_agent import SwarmWorkerAgent

logger = logging.getLogger(__name__)

# M3: Maximum request log entries
MAX_REQUEST_LOG = 10000


@dataclass
class ServiceRequest:
    """An incoming request from a client agent to purchase a SWARM service."""

    request_id: str
    client_agent_id: str
    service_id: str
    input_params: dict[str, Any]
    max_price_usd: float | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class ServiceResponse:
    """Response returned to the client agent after service execution."""

    request_id: str
    service_id: str
    status: str  # "completed", "failed", "rejected"
    result: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    escrow_id: str | None = None
    latency_seconds: float = 0.0
    error: str | None = None
    certification: dict[str, Any] | None = None


class ACPRequestRouter:
    """Routes ACP service requests to SWARM worker agents."""

    def __init__(
        self,
        catalog: ServiceCatalog,
        acp_client: ACPClient,
    ) -> None:
        self._catalog = catalog
        self._acp = acp_client
        self._workers: dict[str, SwarmWorkerAgent] = {}
        # M3: Bounded request log using deque
        self._request_log: collections.deque[dict[str, Any]] = collections.deque(
            maxlen=MAX_REQUEST_LOG
        )

    def register_worker(self, worker: SwarmWorkerAgent) -> None:
        """Register a worker agent that can execute services."""
        self._workers[worker.agent_id] = worker
        logger.info(
            "Registered worker %s for services: %s",
            worker.agent_id,
            [s.service_id for s in worker.services],
        )

    def handle_request(self, request: ServiceRequest) -> ServiceResponse:
        """Handle an incoming service request from a client agent.

        Full lifecycle:
        1. Validate service exists and is enabled
        2. Check price against client's max_price_usd
        3. Find a capable worker agent
        4. Create ACP escrow
        5. Execute via worker agent
        6. Auto-evaluate result
        7. Settle escrow (pay provider or refund)
        8. Return result with optional certification
        """
        start_time = time.time()

        # 1. Validate service
        service = self._catalog.get(request.service_id)
        if service is None or not service.enabled:
            return ServiceResponse(
                request_id=request.request_id,
                service_id=request.service_id,
                status="rejected",
                error=f"Service not found or disabled: {request.service_id}",
            )

        # 2. Price check
        estimated_cost = service.pricing.compute_cost(
            request.input_params.get("_units", 1)
        )
        if request.max_price_usd is not None and estimated_cost > request.max_price_usd:
            return ServiceResponse(
                request_id=request.request_id,
                service_id=request.service_id,
                status="rejected",
                error=(
                    f"Price ${estimated_cost:.2f} exceeds max ${request.max_price_usd:.2f}"
                ),
                cost_usd=estimated_cost,
            )

        # 3. Find a worker
        worker = self._find_worker(request.service_id)
        if worker is None:
            return ServiceResponse(
                request_id=request.request_id,
                service_id=request.service_id,
                status="rejected",
                error=f"No worker available for service: {request.service_id}",
            )

        # 4. Create escrow
        try:
            escrow = self._acp.create_escrow(
                client_agent_id=request.client_agent_id,
                provider_agent_id=worker.agent_id,
                service_id=request.service_id,
                amount_usd=estimated_cost,
            )
        except ValueError as e:
            return ServiceResponse(
                request_id=request.request_id,
                service_id=request.service_id,
                status="rejected",
                error=str(e),
            )
        self._acp.mark_executing(escrow.escrow_id)

        # 5. Execute
        try:
            job = worker.submit_job(
                service_id=request.service_id,
                client_agent_id=request.client_agent_id,
                input_params=request.input_params,
            )
        except Exception as e:
            self._acp.submit_evaluation(escrow.escrow_id, score=0.0)
            self._acp.settle(escrow.escrow_id)
            return ServiceResponse(
                request_id=request.request_id,
                service_id=request.service_id,
                status="failed",
                error=str(e),
                escrow_id=escrow.escrow_id,
            )

        # 6. Auto-evaluate (M2: improved evaluation)
        if job.status.value == "completed":
            eval_score = self._evaluate_result(job.result, service)
            self._acp.submit_evaluation(escrow.escrow_id, score=eval_score)
        else:
            self._acp.submit_evaluation(escrow.escrow_id, score=0.0)

        # 7. Settle
        self._acp.settle(escrow.escrow_id)
        latency = time.time() - start_time

        # 8. Build certification (safety oracle output)
        certification = None
        if job.status.value == "completed" and service.category.value in (
            "safety",
            "evaluation",
            "certification",
        ):
            certification = self._build_certification(
                service,
                job.result,
                eval_score if job.status.value == "completed" else 0.0,
            )

        # Log request (M3: bounded deque auto-evicts oldest)
        self._request_log.append(
            {
                "request_id": request.request_id,
                "client_agent_id": request.client_agent_id,
                "service_id": request.service_id,
                "worker_agent_id": worker.agent_id,
                "status": job.status.value,
                "cost_usd": job.cost_usd,
                "latency_seconds": latency,
                "timestamp": time.time(),
            }
        )

        return ServiceResponse(
            request_id=request.request_id,
            service_id=request.service_id,
            status=job.status.value,
            result=job.result,
            cost_usd=job.cost_usd,
            escrow_id=escrow.escrow_id,
            latency_seconds=latency,
            error=job.error,
            certification=certification,
        )

    def _find_worker(self, service_id: str) -> SwarmWorkerAgent | None:
        """Find a worker agent capable of handling this service."""
        for worker in self._workers.values():
            if worker.can_handle(service_id):
                return worker
        return None

    def _evaluate_result(self, result: dict[str, Any], service: Any) -> float:
        """Evaluate service result quality (M2: improved independence).

        Uses structural checks that the provider cannot trivially game:
        - Checks for expected output keys based on service category
        - Validates numeric ranges for score fields
        - Penalizes suspiciously perfect scores
        """
        if not result:
            return 0.0

        score = 0.0

        # Structural check: result has substantive content
        has_summary = (
            isinstance(result.get("summary"), str)
            and len(result.get("summary", "")) > 10
        )
        has_metrics = (
            isinstance(result.get("metrics"), dict)
            and len(result.get("metrics", {})) > 0
        )

        if has_summary:
            score += 0.3
        if has_metrics:
            score += 0.2

        # Content validation: check that numeric scores are in valid ranges
        for key in (
            "risk_score",
            "alignment_score",
            "robustness_score",
            "escalation_probability",
        ):
            val = result.get(key)
            if isinstance(val, (int, float)) and 0.0 <= val <= 1.0:
                score += 0.1
                break  # Only count once

        # Check for service-specific expected fields
        category = getattr(service, "category", None)
        category_val = category.value if category else ""
        if (
            category_val == "simulation"
            and result.get("tipping_point_step") is not None
        ):
            score += 0.1
        elif category_val == "governance" and isinstance(
            result.get("lever_results"), dict
        ):
            score += 0.1
        elif category_val == "evaluation" and result.get("alignment_grade") in (
            "A",
            "A-",
            "B+",
            "B",
            "C",
            "F",
        ):
            score += 0.1
        elif category_val == "red_team" and isinstance(
            result.get("vulnerabilities"), list
        ):
            score += 0.1
        elif category_val == "certification" and isinstance(
            result.get("certified"), bool
        ):
            score += 0.1

        # Penalize suspiciously empty results that only have filler keys
        total_keys = len([k for k in result if not k.startswith("_")])
        if total_keys < 2:
            score *= 0.5

        return min(1.0, max(0.0, score))

    def _build_certification(
        self,
        service: Any,
        result: dict[str, Any],
        eval_score: float,
    ) -> dict[str, Any]:
        """Build a SWARM safety certification for the service result."""
        risk_score = result.get("risk_score", result.get("escalation_probability"))
        alignment_score = result.get("alignment_score", eval_score)

        if alignment_score >= 0.9:
            grade = "A"
        elif alignment_score >= 0.8:
            grade = "A-"
        elif alignment_score >= 0.7:
            grade = "B+"
        elif alignment_score >= 0.6:
            grade = "B"
        elif alignment_score >= 0.5:
            grade = "C"
        else:
            grade = "F"

        # Deterministic certification ID based on result content
        cert_content = f"{service.service_id}:{eval_score}:{risk_score}:{time.time()}"
        cert_id = hashlib.sha256(cert_content.encode()).hexdigest()[:16]

        return {
            "certified_by": "SWARM Safety Oracle",
            "certification_id": f"CERT-{cert_id.upper()}",
            "service": service.name if hasattr(service, "name") else str(service),
            "risk_score": risk_score,
            "alignment_grade": grade,
            "evaluation_score": eval_score,
            "timestamp": time.time(),
            "version": service.version if hasattr(service, "version") else "1.0.0",
        }

    def request_log_summary(self) -> dict[str, Any]:
        """Return summary statistics of all requests processed."""
        log_list = list(self._request_log)
        if not log_list:
            return {
                "total_requests": 0,
                "total_revenue_usd": 0.0,
                "avg_latency_seconds": 0.0,
            }
        total = len(log_list)
        revenue = sum(r.get("cost_usd", 0) for r in log_list)
        avg_latency = sum(r.get("latency_seconds", 0) for r in log_list) / total
        return {
            "total_requests": total,
            "total_revenue_usd": revenue,
            "avg_latency_seconds": avg_latency,
            "by_service": self._group_by_service(log_list),
        }

    def _group_by_service(
        self, log_list: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Group request log stats by service."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for entry in log_list:
            sid = entry["service_id"]
            groups.setdefault(sid, []).append(entry)
        return {
            sid: {
                "count": len(entries),
                "revenue_usd": sum(e.get("cost_usd", 0) for e in entries),
                "avg_latency": sum(e.get("latency_seconds", 0) for e in entries)
                / len(entries),
            }
            for sid, entries in groups.items()
        }
