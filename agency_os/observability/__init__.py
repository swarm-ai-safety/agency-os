"""Observability package — trajectory capture and structured logging."""

# Re-export everything from the original observability module so that
# existing ``from agency_os.observability import ...`` statements continue
# to work after the module→package conversion.
from agency_os.observability._logging import (  # noqa: F401
    METRIC_BID_PLACED,
    METRIC_BUDGET_DEPLETED,
    METRIC_CIRCUIT_BREAKER_TRIPPED,
    METRIC_PAYMENT_FAILED,
    METRIC_REQUEST_COMPLETED,
    METRIC_TASK_COMPLETED,
    METRIC_TASK_SUBMITTED,
    EventTracker,
    HealthCheck,
    bind_request_id,
    configure_logging,
    get_logger,
    reset_request_id,
)
