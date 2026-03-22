"""Middleware to add rate limit headers to all responses."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Add X-RateLimit-* headers to responses when rate limit info is available."""

    async def dispatch(self, request: Request, call_next):
        """Process request and add rate limit headers to response."""
        response: Response = await call_next(request)

        # Check if rate limit info was set by auth dependency
        if hasattr(request.state, "rate_limit_info"):
            info = request.state.rate_limit_info
            response.headers["X-RateLimit-Limit"] = str(info.limit)
            response.headers["X-RateLimit-Remaining"] = str(info.remaining)
            response.headers["X-RateLimit-Reset"] = str(info.reset)

        return response
