"""
API Rate Limiting

Provides per-endpoint rate limiting with configurable limits.
Uses sliding window algorithm for accurate rate control.

Features:
- Per-user rate limiting
- Per-endpoint customizable limits
- Sliding window algorithm
- Rate limit headers in responses
- Graceful degradation
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an endpoint pattern."""
    requests_per_minute: int = 60
    requests_per_second: int = 10
    burst_size: int = 20  # Allow burst up to this size


# Default rate limits by endpoint pattern
DEFAULT_RATE_LIMITS: dict[str, RateLimitConfig] = {
    # SECURITY: Auth endpoints - strict limits to prevent brute force attacks
    "/api/v1/auth/login": RateLimitConfig(requests_per_minute=5, requests_per_second=1, burst_size=3),
    "/api/v1/auth/token": RateLimitConfig(requests_per_minute=5, requests_per_second=1, burst_size=3),
    "/api/v1/auth/register": RateLimitConfig(requests_per_minute=3, requests_per_second=1, burst_size=2),
    "/api/v1/auth/password-reset": RateLimitConfig(requests_per_minute=3, requests_per_second=1, burst_size=2),
    
    # Order endpoints - strict limits to prevent abuse
    "/api/v1/orders": RateLimitConfig(requests_per_minute=30, requests_per_second=2, burst_size=5),

    # Portfolio/positions - moderate limits (hot path)
    "/api/v1/portfolio": RateLimitConfig(requests_per_minute=120, requests_per_second=5, burst_size=10),
    "/api/v1/positions": RateLimitConfig(requests_per_minute=120, requests_per_second=5, burst_size=10),

    # Trades - moderate limits
    "/api/v1/trades": RateLimitConfig(requests_per_minute=60, requests_per_second=3, burst_size=10),

    # Models/ML - lower limits (expensive operations)
    "/api/v1/models": RateLimitConfig(requests_per_minute=30, requests_per_second=2, burst_size=5),

    # Strategies - moderate limits
    "/api/v1/strategies": RateLimitConfig(requests_per_minute=60, requests_per_second=3, burst_size=10),

    # Health/system - high limits
    "/api/v1/health": RateLimitConfig(requests_per_minute=300, requests_per_second=20, burst_size=50),
    "/api/v1/system": RateLimitConfig(requests_per_minute=120, requests_per_second=5, burst_size=20),

    # Default for unspecified endpoints
    "default": RateLimitConfig(requests_per_minute=60, requests_per_second=5, burst_size=15),
}


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter with sub-second precision.

    Uses a combination of fixed window counters and sliding window
    for accurate rate limiting with minimal memory overhead.
    """

    def __init__(self, window_size: float = 60.0):
        """
        Initialize rate limiter.

        Args:
            window_size: Size of sliding window in seconds
        """
        self.window_size = window_size
        self._windows: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = asyncio.Lock()

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_size: float | None = None,
    ) -> tuple[bool, int, float]:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (e.g., "user:123:/api/orders")
            limit: Maximum requests allowed in window
            window_size: Override window size (uses default if None)

        Returns:
            Tuple of (allowed, remaining, reset_time)
        """
        window = window_size or self.window_size
        now = time.time()
        current_window = int(now / window)
        window_start = current_window * window

        async with self._lock:
            windows = self._windows[key]

            # Clean old windows
            old_windows = [w for w in windows.keys() if w < current_window - 1]
            for w in old_windows:
                del windows[w]

            # Calculate current count using sliding window
            current_count = windows.get(current_window, 0)
            previous_count = windows.get(current_window - 1, 0)

            # Weight previous window by remaining time
            elapsed = now - window_start
            weight = 1 - (elapsed / window)
            total_count = current_count + int(previous_count * weight)

            remaining = max(0, limit - total_count - 1)
            reset_time = window_start + window

            if total_count >= limit:
                return False, 0, reset_time

            # Increment current window
            windows[current_window] += 1
            return True, remaining, reset_time

    async def get_usage(self, key: str, window_size: float | None = None) -> int:
        """Get current usage count for a key."""
        window = window_size or self.window_size
        now = time.time()
        current_window = int(now / window)
        window_start = current_window * window

        async with self._lock:
            windows = self._windows.get(key, {})
            current_count = windows.get(current_window, 0)
            previous_count = windows.get(current_window - 1, 0)

            elapsed = now - window_start
            weight = 1 - (elapsed / window)
            return current_count + int(previous_count * weight)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with per-endpoint configuration.

    Adds rate limit headers to responses:
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    """

    def __init__(
        self,
        app,
        rate_limits: dict[str, RateLimitConfig] | None = None,
        enabled: bool = True,
        exempt_paths: set | None = None,
    ):
        super().__init__(app)
        self.rate_limits = rate_limits or DEFAULT_RATE_LIMITS
        self.enabled = enabled
        self.exempt_paths = exempt_paths or {"/health", "/metrics", "/docs", "/openapi.json"}
        self._limiter = SlidingWindowRateLimiter()
        self._stats = {"allowed": 0, "rejected": 0}
        logger.info(f"RateLimitMiddleware initialized: enabled={enabled}")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        if path in self.exempt_paths:
            return await call_next(request)

        # Get rate limit config for this endpoint
        config = self._get_config_for_path(path)

        # Build rate limit key
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            key = f"user:{user_id}:{path}"
        else:
            # Fall back to IP for unauthenticated requests
            client_ip = request.client.host if request.client else "unknown"
            key = f"ip:{client_ip}:{path}"

        # Check rate limit (per minute)
        allowed, remaining, reset_time = await self._limiter.is_allowed(
            key=key,
            limit=config.requests_per_minute,
            window_size=60.0,
        )

        if not allowed:
            self._stats["rejected"] += 1
            retry_after = max(1, int(reset_time - time.time()))
            logger.warning(f"Rate limit exceeded for {key}, retry_after={retry_after}s")

            response = Response(
                content=f'{{"detail": "Rate limit exceeded. Please wait {retry_after} seconds before retrying.", "code": "RATE_LIMIT_EXCEEDED", "retry_after": {retry_after}}}',
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )
            self._add_rate_limit_headers(response, config, 0, reset_time, retry_after)
            return response

        self._stats["allowed"] += 1

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        self._add_rate_limit_headers(response, config, remaining, reset_time)

        return response

    def _get_config_for_path(self, path: str) -> RateLimitConfig:
        """Get rate limit config for a path."""
        # Try exact match first
        if path in self.rate_limits:
            return self.rate_limits[path]

        # Try prefix match
        for pattern, config in self.rate_limits.items():
            if pattern != "default" and path.startswith(pattern):
                return config

        # Fall back to default
        return self.rate_limits.get("default", RateLimitConfig())

    def _add_rate_limit_headers(
        self,
        response: Response,
        config: RateLimitConfig,
        remaining: int,
        reset_time: float,
        retry_after: int | None = None,
    ) -> None:
        """
        Add rate limit headers to response.
        
        Headers added:
        - X-RateLimit-Limit: Maximum requests per window
        - X-RateLimit-Remaining: Requests remaining in current window
        - X-RateLimit-Reset: Unix timestamp when window resets
        - Retry-After: Seconds to wait (only when rate limited)
        """
        response.headers["X-RateLimit-Limit"] = str(config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))

        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        total = self._stats["allowed"] + self._stats["rejected"]
        return {
            **self._stats,
            "rejection_rate": self._stats["rejected"] / total if total > 0 else 0,
        }
