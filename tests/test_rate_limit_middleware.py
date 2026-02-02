"""
Tests for API Rate Limiting middleware.

Tests cover:
- Rate limit configuration per endpoint
- Sliding window rate limiter algorithm
- Rate limit headers in responses
- Retry-After header for 429 responses
- Exempt paths bypass
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import Request, Response
from starlette.datastructures import URL

from backend.api.middleware.rate_limit import (
    RateLimitConfig,
    SlidingWindowRateLimiter,
    RateLimitMiddleware,
    DEFAULT_RATE_LIMITS,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_values(self):
        """Default values are sensible."""
        config = RateLimitConfig()
        
        assert config.requests_per_minute == 60
        assert config.requests_per_second == 10
        assert config.burst_size == 20

    def test_custom_values(self):
        """Custom values are applied."""
        config = RateLimitConfig(
            requests_per_minute=30,
            requests_per_second=2,
            burst_size=5,
        )
        
        assert config.requests_per_minute == 30
        assert config.requests_per_second == 2
        assert config.burst_size == 5


class TestDefaultRateLimits:
    """Tests for DEFAULT_RATE_LIMITS configuration."""

    def test_orders_endpoint_has_strict_limits(self):
        """Orders endpoint has strict limits."""
        config = DEFAULT_RATE_LIMITS["/api/v1/orders"]
        
        assert config.requests_per_minute == 30
        assert config.requests_per_second == 2
        assert config.burst_size == 5

    def test_portfolio_endpoint_has_moderate_limits(self):
        """Portfolio endpoint has moderate limits."""
        config = DEFAULT_RATE_LIMITS["/api/v1/portfolio"]
        
        assert config.requests_per_minute == 120
        assert config.requests_per_second == 5
        assert config.burst_size == 10

    def test_health_endpoint_has_high_limits(self):
        """Health endpoint has high limits."""
        config = DEFAULT_RATE_LIMITS["/api/v1/health"]
        
        assert config.requests_per_minute == 300
        assert config.requests_per_second == 20
        assert config.burst_size == 50

    def test_default_fallback_exists(self):
        """Default fallback config exists."""
        assert "default" in DEFAULT_RATE_LIMITS
        config = DEFAULT_RATE_LIMITS["default"]
        
        assert config.requests_per_minute == 60


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        """Allows requests when under limit."""
        limiter = SlidingWindowRateLimiter(window_size=60.0)
        
        allowed, remaining, reset_time = await limiter.is_allowed(
            key="test",
            limit=10,
        )
        
        assert allowed is True
        assert remaining >= 0
        assert reset_time > time.time()

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self):
        """Blocks requests when limit is exceeded."""
        limiter = SlidingWindowRateLimiter(window_size=1.0)  # 1 second window
        
        # Make limit + 1 requests
        for _ in range(5):
            await limiter.is_allowed(key="test", limit=5)
        
        # Next request should be blocked
        allowed, remaining, reset_time = await limiter.is_allowed(
            key="test",
            limit=5,
        )
        
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_separate_keys_have_separate_limits(self):
        """Different keys have independent limits."""
        limiter = SlidingWindowRateLimiter(window_size=1.0)
        
        # Exhaust limit for key1
        for _ in range(5):
            await limiter.is_allowed(key="key1", limit=5)
        
        # key2 should still be allowed
        allowed, _, _ = await limiter.is_allowed(key="key2", limit=5)
        
        assert allowed is True

    @pytest.mark.asyncio
    async def test_get_usage_returns_current_count(self):
        """get_usage returns accurate count."""
        limiter = SlidingWindowRateLimiter(window_size=60.0)
        
        # Initial usage should be 0
        usage = await limiter.get_usage("test")
        assert usage == 0
        
        # Make 3 requests
        for _ in range(3):
            await limiter.is_allowed(key="test", limit=10)
        
        # Usage should be 3
        usage = await limiter.get_usage("test")
        assert usage == 3


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def create_mock_request(
        self,
        path: str = "/api/v1/orders",
        user_id: str | None = "user_123",
        client_ip: str = "127.0.0.1",
    ):
        """Create a mock request for testing."""
        request = MagicMock(spec=Request)
        request.url = URL(f"http://localhost{path}")
        request.client = MagicMock()
        request.client.host = client_ip
        request.state = MagicMock()
        
        if user_id:
            request.state.user_id = user_id
        else:
            delattr(request.state, 'user_id')
        
        return request

    def test_middleware_initializes_with_defaults(self):
        """Middleware initializes with default config."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        assert middleware.enabled is True
        assert middleware.rate_limits is not None
        assert "/health" in middleware.exempt_paths

    def test_middleware_can_be_disabled(self):
        """Middleware can be disabled."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app, enabled=False)
        
        assert middleware.enabled is False

    @pytest.mark.asyncio
    async def test_exempt_paths_bypass_rate_limiting(self):
        """Exempt paths bypass rate limiting."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(app, exempt_paths={"/health"})
        
        request = self.create_mock_request(path="/health")
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response.status_code == 200
        # No rate limit headers on exempt paths (headers are only added when rate limiting is checked)

    @pytest.mark.asyncio
    async def test_adds_rate_limit_headers(self):
        """Rate limit headers are added to responses."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        request = self.create_mock_request(path="/api/v1/orders")
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    @pytest.mark.asyncio
    async def test_returns_429_when_rate_limited(self):
        """Returns 429 when rate limit exceeded."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(
            app,
            rate_limits={"/api/v1/orders": RateLimitConfig(requests_per_minute=2)}
        )
        
        request = self.create_mock_request(path="/api/v1/orders")
        
        # Exhaust the limit
        await middleware.dispatch(request, mock_call_next)
        await middleware.dispatch(request, mock_call_next)
        
        # Next request should be rate limited
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limited_response_includes_retry_after(self):
        """429 response includes Retry-After header."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(
            app,
            rate_limits={"/api/v1/test": RateLimitConfig(requests_per_minute=1)}
        )
        
        request = self.create_mock_request(path="/api/v1/test")
        
        # Exhaust the limit
        await middleware.dispatch(request, mock_call_next)
        
        # Get rate limited response
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after >= 1  # At least 1 second

    @pytest.mark.asyncio
    async def test_rate_limited_response_body_format(self):
        """429 response body has correct format."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(
            app,
            rate_limits={"/api/v1/test": RateLimitConfig(requests_per_minute=1)}
        )
        
        request = self.create_mock_request(path="/api/v1/test")
        
        # Exhaust and get rate limited
        await middleware.dispatch(request, mock_call_next)
        response = await middleware.dispatch(request, mock_call_next)
        
        import json
        body = json.loads(response.body.decode())
        
        assert "detail" in body
        assert "code" in body
        assert body["code"] == "RATE_LIMIT_EXCEEDED"
        assert "retry_after" in body

    @pytest.mark.asyncio
    async def test_uses_user_id_when_authenticated(self):
        """Uses user_id in rate limit key when authenticated."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        # Two different users
        request1 = self.create_mock_request(path="/api/v1/orders", user_id="user_1")
        request2 = self.create_mock_request(path="/api/v1/orders", user_id="user_2")
        
        # Both should be allowed (separate limits)
        response1 = await middleware.dispatch(request1, mock_call_next)
        response2 = await middleware.dispatch(request2, mock_call_next)
        
        assert response1.status_code == 200
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_uses_ip_when_unauthenticated(self):
        """Uses IP address in rate limit key when unauthenticated."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        # Mock request without user_id
        request = MagicMock(spec=Request)
        request.url = URL("http://localhost/api/v1/orders")
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = MagicMock(spec=[])  # No user_id attribute
        
        response = await middleware.dispatch(request, mock_call_next)
        
        # Should use IP-based key
        assert response.status_code == 200

    def test_get_config_for_path_exact_match(self):
        """_get_config_for_path finds exact matches."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        config = middleware._get_config_for_path("/api/v1/orders")
        
        assert config.requests_per_minute == 30  # Orders limit

    def test_get_config_for_path_prefix_match(self):
        """_get_config_for_path finds prefix matches."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        config = middleware._get_config_for_path("/api/v1/orders/123")
        
        assert config.requests_per_minute == 30  # Orders limit via prefix

    def test_get_config_for_path_default_fallback(self):
        """_get_config_for_path falls back to default."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        config = middleware._get_config_for_path("/api/v1/unknown")
        
        assert config.requests_per_minute == 60  # Default limit

    def test_get_stats(self):
        """get_stats returns statistics."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        stats = middleware.get_stats()
        
        assert "allowed" in stats
        assert "rejected" in stats
        assert "rejection_rate" in stats


class TestRateLimitHeaderValues:
    """Tests for rate limit header values."""

    @pytest.mark.asyncio
    async def test_remaining_decrements_correctly(self):
        """X-RateLimit-Remaining decrements with each request."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(
            app,
            rate_limits={"/api/v1/test": RateLimitConfig(requests_per_minute=10)}
        )
        
        request = MagicMock(spec=Request)
        request.url = URL("http://localhost/api/v1/test")
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        request.state.user_id = "test_user"
        
        response1 = await middleware.dispatch(request, mock_call_next)
        remaining1 = int(response1.headers["X-RateLimit-Remaining"])
        
        response2 = await middleware.dispatch(request, mock_call_next)
        remaining2 = int(response2.headers["X-RateLimit-Remaining"])
        
        # Remaining should decrement
        assert remaining2 < remaining1

    @pytest.mark.asyncio
    async def test_reset_time_is_in_future(self):
        """X-RateLimit-Reset is in the future."""
        async def mock_call_next(request):
            return Response(content="OK", status_code=200)
        
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        request = MagicMock(spec=Request)
        request.url = URL("http://localhost/api/v1/orders")
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        request.state.user_id = "test_user"
        
        response = await middleware.dispatch(request, mock_call_next)
        
        reset_time = int(response.headers["X-RateLimit-Reset"])
        current_time = int(time.time())
        
        assert reset_time >= current_time
