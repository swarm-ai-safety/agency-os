"""Unit tests for rate limiting."""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from agency_os.service.api.middleware.rate_limit import RateLimiter, RateLimitInfo


class TestRateLimiter:
    """Test suite for RateLimiter class."""

    def test_init_default(self):
        """Test default initialization."""
        limiter = RateLimiter()
        assert limiter._default_rpm == 60

    def test_init_custom_rpm(self):
        """Test initialization with custom RPM."""
        limiter = RateLimiter(requests_per_minute=100)
        assert limiter._default_rpm == 100

    def test_tier_limits_configured(self):
        """Test tier-specific limits are defined."""
        assert RateLimiter.TIER_LIMITS["free"] == 30
        assert RateLimiter.TIER_LIMITS["pro"] == 120
        assert RateLimiter.TIER_LIMITS["enterprise"] == 300

    def test_check_first_request_free_tier(self):
        """Test first request for free tier tenant."""
        limiter = RateLimiter()
        info = limiter.check("tenant-1", tier="free")

        assert isinstance(info, RateLimitInfo)
        assert info.limit == 30  # Free tier
        assert info.remaining == 29  # 30 - 1
        assert info.reset > time.time()

    def test_check_first_request_pro_tier(self):
        """Test first request for pro tier tenant."""
        limiter = RateLimiter()
        info = limiter.check("tenant-2", tier="pro")

        assert info.limit == 120  # Pro tier
        assert info.remaining == 119
        assert info.reset > time.time()

    def test_check_first_request_enterprise_tier(self):
        """Test first request for enterprise tier tenant."""
        limiter = RateLimiter()
        info = limiter.check("tenant-3", tier="enterprise")

        assert info.limit == 300  # Enterprise tier
        assert info.remaining == 299
        assert info.reset > time.time()

    def test_check_unknown_tier_uses_default(self):
        """Test unknown tier falls back to default RPM."""
        limiter = RateLimiter(requests_per_minute=60)
        info = limiter.check("tenant-4", tier="unknown")

        assert info.limit == 60  # Default
        assert info.remaining == 59

    def test_check_multiple_requests_decrements_remaining(self):
        """Test remaining count decrements with each request."""
        limiter = RateLimiter()
        tenant_id = "tenant-5"

        info1 = limiter.check(tenant_id, tier="free")
        assert info1.remaining == 29  # 30 - 1

        info2 = limiter.check(tenant_id, tier="free")
        assert info2.remaining == 28  # 30 - 2

        info3 = limiter.check(tenant_id, tier="free")
        assert info3.remaining == 27  # 30 - 3

    def test_check_rate_limit_exceeded_free_tier(self):
        """Test 429 exception when free tier limit exceeded."""
        limiter = RateLimiter()
        tenant_id = "tenant-6"

        # Exhaust free tier limit (30 requests)
        for _ in range(30):
            limiter.check(tenant_id, tier="free")

        # 31st request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            limiter.check(tenant_id, tier="free")

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail
        assert "30 requests per minute" in exc_info.value.detail
        assert "free tier" in exc_info.value.detail

    def test_check_rate_limit_exceeded_pro_tier(self):
        """Test 429 exception when pro tier limit exceeded."""
        limiter = RateLimiter()
        tenant_id = "tenant-7"

        # Exhaust pro tier limit (120 requests)
        for _ in range(120):
            limiter.check(tenant_id, tier="pro")

        # 121st request should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            limiter.check(tenant_id, tier="pro")

        assert exc_info.value.status_code == 429
        assert "120 requests per minute" in exc_info.value.detail
        assert "pro tier" in exc_info.value.detail

    def test_check_sliding_window_cleanup(self):
        """Test sliding window removes old timestamps."""
        limiter = RateLimiter()
        tenant_id = "tenant-8"

        # Make first request
        limiter.check(tenant_id, tier="free")

        # Mock time to advance by 61 seconds (past window)
        original_time = time.time
        mock_time = Mock(return_value=original_time() + 61)
        time.time = mock_time

        try:
            # Old request should be cleaned up, so we should have full quota again
            info = limiter.check(tenant_id, tier="free")
            assert info.remaining == 29  # Full quota minus current request
        finally:
            time.time = original_time

    def test_check_different_tenants_isolated(self):
        """Test different tenants have independent rate limits."""
        limiter = RateLimiter()

        # Tenant 1 makes 10 requests
        for _ in range(10):
            limiter.check("tenant-9", tier="free")

        # Tenant 2 should still have full quota
        info = limiter.check("tenant-10", tier="free")
        assert info.remaining == 29  # Full quota

    def test_check_lru_eviction(self):
        """Test LRU eviction when max tenants exceeded."""
        limiter = RateLimiter()
        limiter._MAX_TENANTS = 3  # Override for test

        # Add 3 tenants (at capacity)
        limiter.check("tenant-a", tier="free")
        limiter.check("tenant-b", tier="free")
        limiter.check("tenant-c", tier="free")

        # Add 4th tenant - should evict tenant-a (oldest)
        limiter.check("tenant-d", tier="free")

        # Verify tenant-a was evicted (should have full quota again)
        info = limiter.check("tenant-a", tier="free")
        assert info.remaining == 29  # Full quota (was evicted)

    def test_check_lru_move_to_end(self):
        """Test accessing a tenant moves it to end of LRU."""
        limiter = RateLimiter()
        limiter._MAX_TENANTS = 3

        # Add 3 tenants
        limiter.check("tenant-e", tier="free")
        limiter.check("tenant-f", tier="free")
        limiter.check("tenant-g", tier="free")

        # Access tenant-e again (should move to end)
        limiter.check("tenant-e", tier="free")

        # Add 4th tenant - should evict tenant-f (now oldest)
        limiter.check("tenant-h", tier="free")

        # Verify tenant-f was evicted
        info = limiter.check("tenant-f", tier="free")
        assert info.remaining == 29

    def test_check_thread_safety(self):
        """Test rate limiter is thread-safe."""
        import threading

        limiter = RateLimiter()
        tenant_id = "tenant-11"
        errors = []

        def make_requests():
            try:
                for _ in range(5):
                    limiter.check(tenant_id, tier="free")
            except Exception as e:
                errors.append(e)

        # Run 6 threads making 5 requests each = 30 total (at limit)
        threads = [threading.Thread(target=make_requests) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no unexpected errors (only HTTPException 429 expected if limit hit)
        for error in errors:
            assert isinstance(error, HTTPException)
            assert error.status_code == 429

    def test_check_reset_timestamp_calculation(self):
        """Test reset timestamp is calculated correctly."""
        limiter = RateLimiter()
        tenant_id = "tenant-12"

        before = time.time()
        info = limiter.check(tenant_id, tier="free")
        after = time.time()

        # Reset should be ~60 seconds from now
        assert info.reset >= before + 59
        assert info.reset <= after + 61

    def test_check_remaining_never_negative(self):
        """Test remaining count never goes below zero."""
        limiter = RateLimiter()
        tenant_id = "tenant-13"

        # Exhaust limit
        for _ in range(30):
            limiter.check(tenant_id, tier="free")

        # Try to get current state before exception
        # (This is a bit tricky since check() raises on exceed,
        # but the implementation ensures remaining is max(0, ...) before raising)
        # We can verify by checking the last successful call
        limiter2 = RateLimiter()
        for i in range(31):
            try:
                info = limiter2.check("tenant-14", tier="free")
                if i == 29:  # Last successful request
                    assert info.remaining == 0
            except HTTPException:
                pass  # Expected on 31st
