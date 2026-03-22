"""Service catalog — maps SWARM research primitives to sellable micro-services.

Each SWARM module (governance audit, escalation simulation, alignment test, etc.)
is registered as a SwarmService with pricing, capabilities, and SLA metadata.
Autonomous agents discover and purchase these services via ACP.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

CATALOG_DIR = Path(__file__).parent / "services"


class PricingModel(str, Enum):
    """How a service is billed."""

    FLAT = "flat"  # Fixed price per invocation
    PER_ITERATION = "per_iteration"  # Base + per-iteration cost
    PER_AGENT = "per_agent"  # Base + per-agent cost
    METERED = "metered"  # Pay for actual compute consumed


class ServiceCategory(str, Enum):
    """High-level category for marketplace discovery."""

    SAFETY = "safety"
    GOVERNANCE = "governance"
    EVALUATION = "evaluation"
    SIMULATION = "simulation"
    RED_TEAM = "red_team"
    CERTIFICATION = "certification"


@dataclass
class ServicePricing:
    """Pricing configuration for a SWARM service."""

    model: PricingModel = PricingModel.FLAT
    base_price_usd: float = 10.0
    per_unit_usd: float = 0.0
    unit_name: str = "invocation"
    currency: str = "USDC"
    min_price_usd: float = 1.0
    max_price_usd: float = 500.0

    def compute_cost(self, units: int = 1) -> float:
        """Compute total cost for a service invocation."""
        if self.model == PricingModel.FLAT:
            return self.base_price_usd
        cost = self.base_price_usd + (self.per_unit_usd * units)
        return max(self.min_price_usd, min(self.max_price_usd, cost))


@dataclass
class ServiceSLA:
    """Service-level agreement metadata."""

    max_latency_seconds: float = 120.0
    availability_target: float = 0.99
    max_concurrent_requests: int = 10


@dataclass
class SwarmService:
    """A SWARM research primitive packaged as a purchasable API service.

    This is the core unit of the marketplace — each service wraps one or more
    SWARM modules and exposes them as a callable capability that autonomous
    agents can discover, request, and pay for.
    """

    service_id: str
    name: str
    description: str
    category: ServiceCategory
    capabilities: list[str]
    swarm_module: str  # Dotted path to the SWARM module (e.g. "swarm.redteam")
    handler: str  # Dotted path to the handler function
    pricing: ServicePricing = field(default_factory=ServicePricing)
    sla: ServiceSLA = field(default_factory=ServiceSLA)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    enabled: bool = True

    def to_acp_manifest(self) -> dict[str, Any]:
        """Serialize to ACP-compatible agent manifest for marketplace registration."""
        return {
            "agent_id": f"swarm_{self.service_id}",
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "category": self.category.value,
            "pricing": {
                "model": self.pricing.model.value,
                "base": self.pricing.base_price_usd,
                "per_unit": self.pricing.per_unit_usd,
                "unit": self.pricing.unit_name,
                "currency": self.pricing.currency,
            },
            "sla": {
                "max_latency_seconds": self.sla.max_latency_seconds,
                "availability": self.sla.availability_target,
            },
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "version": self.version,
            "tags": self.tags,
        }


class ServiceCatalog:
    """Registry of all SWARM services available for purchase.

    Agents query the catalog for discovery (by category, capability, or tag),
    then invoke services through the ACP request router.
    """

    def __init__(self) -> None:
        self._services: dict[str, SwarmService] = {}
        self._stats: dict[str, dict[str, Any]] = {}

    def register(self, service: SwarmService) -> None:
        """Register a SWARM service in the catalog."""
        self._services[service.service_id] = service
        self._stats[service.service_id] = {
            "total_invocations": 0,
            "total_revenue_usd": 0.0,
            "avg_latency_seconds": 0.0,
            "last_invoked": None,
        }
        logger.info(
            "Registered service: %s (%s) @ $%.2f base",
            service.service_id,
            service.name,
            service.pricing.base_price_usd,
        )

    def get(self, service_id: str) -> SwarmService | None:
        """Look up a service by ID."""
        return self._services.get(service_id)

    def list_services(
        self,
        category: ServiceCategory | None = None,
        capability: str | None = None,
        tag: str | None = None,
        enabled_only: bool = True,
    ) -> list[SwarmService]:
        """Query services by filter criteria."""
        results = list(self._services.values())
        if enabled_only:
            results = [s for s in results if s.enabled]
        if category:
            results = [s for s in results if s.category == category]
        if capability:
            cap_lower = capability.lower()
            results = [
                s
                for s in results
                if any(cap_lower in c.lower() for c in s.capabilities)
            ]
        if tag:
            tag_lower = tag.lower()
            results = [
                s for s in results if any(tag_lower in t.lower() for t in s.tags)
            ]
        return results

    def record_invocation(
        self, service_id: str, latency_seconds: float, revenue_usd: float
    ) -> None:
        """Record a service invocation for analytics."""
        stats = self._stats.get(service_id)
        if stats is None:
            return
        n = stats["total_invocations"]
        stats["total_invocations"] = n + 1
        stats["total_revenue_usd"] += revenue_usd
        # Running average of latency
        if n == 0:
            stats["avg_latency_seconds"] = latency_seconds
        else:
            stats["avg_latency_seconds"] = (
                stats["avg_latency_seconds"] * n + latency_seconds
            ) / (n + 1)
        stats["last_invoked"] = time.time()

    def get_stats(self, service_id: str) -> dict[str, Any]:
        """Get invocation stats for a service."""
        return dict(self._stats.get(service_id, {}))

    def catalog_summary(self) -> list[dict[str, Any]]:
        """Return summary of all services for API responses."""
        return [
            {
                "service_id": s.service_id,
                "name": s.name,
                "description": s.description,
                "category": s.category.value,
                "capabilities": s.capabilities,
                "pricing": {
                    "model": s.pricing.model.value,
                    "base_usd": s.pricing.base_price_usd,
                    "per_unit_usd": s.pricing.per_unit_usd,
                    "unit": s.pricing.unit_name,
                    "currency": s.pricing.currency,
                },
                "sla": {
                    "max_latency_seconds": s.sla.max_latency_seconds,
                    "availability": s.sla.availability_target,
                },
                "tags": s.tags,
                "version": s.version,
                "enabled": s.enabled,
                "stats": self.get_stats(s.service_id),
            }
            for s in self._services.values()
        ]

    def load_builtin_services(self) -> int:
        """Load service definitions from YAML files in the services/ directory."""
        if not CATALOG_DIR.exists():
            logger.warning("Service catalog directory not found: %s", CATALOG_DIR)
            return 0
        count = 0
        for path in sorted(CATALOG_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text())
                service = _parse_service_yaml(data)
                self.register(service)
                count += 1
            except Exception as e:
                logger.error("Failed to load service %s: %s", path.name, e)
        return count


def _parse_service_yaml(data: dict[str, Any]) -> SwarmService:
    """Parse a service YAML definition into a SwarmService."""
    pricing_data = data.get("pricing", {})
    sla_data = data.get("sla", {})
    return SwarmService(
        service_id=data["service_id"],
        name=data["name"],
        description=data["description"],
        category=ServiceCategory(data["category"]),
        capabilities=data.get("capabilities", []),
        swarm_module=data["swarm_module"],
        handler=data["handler"],
        pricing=ServicePricing(
            model=PricingModel(pricing_data.get("model", "flat")),
            base_price_usd=pricing_data.get("base_price_usd", 10.0),
            per_unit_usd=pricing_data.get("per_unit_usd", 0.0),
            unit_name=pricing_data.get("unit_name", "invocation"),
            currency=pricing_data.get("currency", "USDC"),
        ),
        sla=ServiceSLA(
            max_latency_seconds=sla_data.get("max_latency_seconds", 120.0),
            availability_target=sla_data.get("availability_target", 0.99),
            max_concurrent_requests=sla_data.get("max_concurrent_requests", 10),
        ),
        input_schema=data.get("input_schema", {}),
        output_schema=data.get("output_schema", {}),
        tags=data.get("tags", []),
        version=data.get("version", "1.0.0"),
        enabled=data.get("enabled", True),
    )
