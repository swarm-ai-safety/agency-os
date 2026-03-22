"""Per-tenant rate limiting middleware."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import HTTPException

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """Rate limit quota information for a tenant."""

    limit: int  # Requests per minute allowed
    remaining: int  # Requests remaining in current window
    reset: int  # Unix timestamp when the window resets


class RateLimiter:
    """Simple in-memory rate limiter per tenant with bounded storage.

    Thread-safe: all access is protected by a lock.
    Supports tier-specific rate limits.
    """

    # Maximum number of distinct tenant IDs tracked (LRU eviction)
    _MAX_TENANTS = 10_000

    # Default rate limits per tier (requests per minute)
    TIER_LIMITS = {
        "free": 30,
        "pro": 120,
        "enterprise": 300,
    }

    def __init__(self, requests_per_minute: int = 60):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Default RPM for tenants without tier-specific limit
        """
        self._default_rpm = requests_per_minute
        self._requests: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, tenant_id: str, tier: str = "free") -> RateLimitInfo:
        """Check rate limit and return quota info.

        Args:
            tenant_id: Unique tenant identifier
            tier: Billing tier (free, pro, enterprise)

        Returns:
            RateLimitInfo with limit, remaining, and reset timestamp

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        rpm = self.TIER_LIMITS.get(tier, self._default_rpm)

        with self._lock:
            now = time.time()
            window = now - 60.0

            # Evict oldest tenants if over capacity
            while len(self._requests) > self._MAX_TENANTS:
                evicted_id, _ = self._requests.popitem(last=False)
                logger.warning(
                    "Rate limiter evicted tenant %s (capacity %d)",
                    evicted_id,
                    self._MAX_TENANTS,
                )

            # Clean old entries for this tenant
            timestamps = self._requests.get(tenant_id, [])
            timestamps = [t for t in timestamps if t > window]

            current_count = len(timestamps)
            remaining = max(0, rpm - current_count)

            # Calculate reset time (start of next minute window)
            oldest_request = timestamps[0] if timestamps else now
            reset = int(oldest_request + 60.0)

            if current_count >= rpm:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {rpm} requests per minute for {tier} tier",
                )

            timestamps.append(now)
            self._requests[tenant_id] = timestamps
            # Move to end (most recently used)
            self._requests.move_to_end(tenant_id)

            return RateLimitInfo(limit=rpm, remaining=remaining - 1, reset=reset)
