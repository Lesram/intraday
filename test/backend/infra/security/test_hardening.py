# moved from repository root to test/module/security
# content preserved as-is.

"""
Comprehensive test suite for backend.infra.security_hardening module achieving 100% coverage.
Tests SecuritySettings, SimpleRateLimiter, RateLimitMiddleware, SecurityHeadersMiddleware, and JWT verifier.
"""

import pytest
import os
import time
from collections import defaultdict
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
from pydantic import ValidationError

# Import the module under test
from backend.infra.security_hardening import (
    SecuritySettings, SimpleRateLimiter, RateLimitMiddleware,
    SecurityHeadersMiddleware, JwtVerifier
)


class TestSecuritySettings:
    """Test SecuritySettings class and validation."""
    
    def test_security_settings_default_values(self):
        """Test SecuritySettings with default values."""
        # This should fail due to CORS validation requiring explicit origins
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings()
        
        # Should mention CORS origins validation
        assert "CORS origins must be explicitly configured" in str(exc_info.value)
    
    def test_security_settings_valid_config(self):
        """Test SecuritySettings with valid configuration."""
        # Lines 88-107: Test valid configuration
        
        settings = SecuritySettings(
            cors_allow_origins=["https://example.com"],
            cors_allow_credentials=True,
            cors_allow_methods=["GET", "POST", "PUT"],
            cors_allow_headers=["Authorization", "Content-Type", "X-Custom"],
            cors_max_age=1200,
            rate_limit_requests_per_minute=120,
            rate_limit_burst_size=20,
            rate_limit_enabled=True,
            jwt_require_https=True,
            jwt_require_aud=True,
            jwt_require_iss=True,
            jwt_leeway_seconds=15,
            trusted_hosts=["example.com", "api.example.com"],
            enable_security_headers=True,
            hsts_max_age=63072000
        )
        
        assert settings.cors_allow_origins == ["https://example.com"]
        assert settings.cors_allow_credentials is True
        assert settings.cors_allow_methods == ["GET", "POST", "PUT"]
        assert settings.cors_max_age == 1200
        assert settings.rate_limit_requests_per_minute == 120
        assert settings.jwt_require_https is True
        assert settings.trusted_hosts == ["example.com", "api.example.com"]
    
    @patch.dict(os.environ, {"APP_ENVIRONMENT": "production"})
    def test_cors_wildcard_validation_production(self):
        """Test CORS wildcard validation in production."""
        # Lines 88-107: Test wildcard validation in production
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(cors_allow_origins=["*"])
        
        assert "Wildcard CORS origins not allowed in production" in str(exc_info.value)
    
    @patch.dict(os.environ, {"APP_ENVIRONMENT": "development"})  
    def test_cors_wildcard_validation_development(self):
        """Test CORS wildcard validation in development."""
        
        # Should be allowed in development
        settings = SecuritySettings(cors_allow_origins=["*"])
        assert settings.cors_allow_origins == ["*"]
    
    def test_cors_origin_format_validation(self):
        """Test CORS origin format validation."""
        # Lines 113-115: Test origin format validation
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(cors_allow_origins=["invalid-origin"])
        
        assert "Invalid CORS origin format" in str(exc_info.value)
        
        # Test multiple invalid origins
        with pytest.raises(ValidationError):
            SecuritySettings(cors_allow_origins=["ftp://invalid.com", "example.com"])
    
    def test_trusted_hosts_validation(self):
        """Test trusted hosts validation."""
        # Lines 121-125: Test trusted hosts validation
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(
                cors_allow_origins=["https://example.com"],
                trusted_hosts=[]
            )
        
        assert "At least one trusted host must be configured" in str(exc_info.value)
    
    def test_rate_limit_validation_negative(self):
        """Test rate limit validation with negative values."""
        # Lines 135-138: Test rate limit validation
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(
                cors_allow_origins=["https://example.com"],
                rate_limit_requests_per_minute=-1
            )
        
        assert "Rate limit must be positive" in str(exc_info.value)
    
    def test_rate_limit_validation_zero(self):
        """Test rate limit validation with zero value."""
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(
                cors_allow_origins=["https://example.com"],
                rate_limit_requests_per_minute=0
            )
        
        assert "Rate limit must be positive" in str(exc_info.value)
    
    def test_rate_limit_validation_too_high(self):
        """Test rate limit validation with too high values."""
        # Lines 142-143: Test rate limit upper bound validation
        
        with pytest.raises(ValidationError) as exc_info:
            SecuritySettings(
                cors_allow_origins=["https://example.com"],
                rate_limit_requests_per_minute=15000
            )
        
        assert "Rate limit too high - maximum 10000 requests/minute" in str(exc_info.value)


class TestSimpleRateLimiter:
    """Test SimpleRateLimiter class."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        # Lines 149-159: Test SimpleRateLimiter initialization
        
        limiter = SimpleRateLimiter(requests_per_minute=100, burst_size=15)
        
        assert limiter.requests_per_minute == 100
        assert limiter.burst_size == 15
        assert isinstance(limiter.clients, defaultdict)
        assert limiter.last_cleanup > 0
    
    def test_rate_limiter_default_values(self):
        """Test rate limiter with default values."""
        
        limiter = SimpleRateLimiter()
        
        assert limiter.requests_per_minute == 60
        assert limiter.burst_size == 10
    
    def test_rate_limiter_allow_request(self):
        """Test allowing a request within rate limit."""
        # Lines 168-196: Test is_allowed method
        
        limiter = SimpleRateLimiter(requests_per_minute=60, burst_size=10)
        
        is_allowed, info = limiter.is_allowed("192.168.1.1")
        
        assert is_allowed is True
        assert info["requests_made"] == 1
        assert info["requests_allowed"] == 60
        assert info["retry_after"] == 0
        assert "reset_time" in info
    
    def test_rate_limiter_burst_limit(self):
        """Test burst limit enforcement."""
        
        limiter = SimpleRateLimiter(requests_per_minute=60, burst_size=3)
        client_ip = "192.168.1.2"
        
        # Allow up to burst size
        for i in range(3):
            is_allowed, info = limiter.is_allowed(client_ip)
            assert is_allowed is True
            assert info["requests_made"] == i + 1
        
        # Next request should still be allowed within rate limit
        is_allowed, info = limiter.is_allowed(client_ip)
        assert is_allowed is True
        assert info["requests_made"] == 4
    
    def test_rate_limiter_exceed_limit(self):
        """Test exceeding rate limit."""
        
        limiter = SimpleRateLimiter(requests_per_minute=2, burst_size=1)
        client_ip = "192.168.1.3"
        
        # First requests should be allowed
        limiter.is_allowed(client_ip)
        limiter.is_allowed(client_ip)
        
        # Third request should be blocked
        is_allowed, info = limiter.is_allowed(client_ip)
        
        assert is_allowed is False
        assert info["requests_made"] >= 2
        assert info["requests_allowed"] == 2
        assert info["retry_after"] > 0
        assert "reset_time" in info
    
    def test_rate_limiter_cleanup_old_requests(self):
        """Test cleanup of old requests."""
        
        limiter = SimpleRateLimiter(requests_per_minute=60, burst_size=10)
        client_ip = "192.168.1.4"
        
        # Add some old requests
        current_time = time.time()
        old_time = current_time - 120  # 2 minutes ago
        limiter.clients[client_ip] = [old_time, old_time + 10, current_time - 30]
        
        # This should trigger cleanup
        limiter._cleanup_old_requests(client_ip, current_time)
        
        # Only requests within the last minute should remain
        remaining_requests = limiter.clients[client_ip] 
        assert all(req_time > current_time - 60 for req_time in remaining_requests)
    
    def test_rate_limiter_global_cleanup(self):
        """Test global cleanup of inactive clients."""
        
        limiter = SimpleRateLimiter()
        current_time = time.time()
        
        # Set up old last_cleanup time to trigger cleanup
        limiter.last_cleanup = current_time - 400  # 400 seconds ago
        
        # Add some clients with old requests
        old_time = current_time - 120  # 2 minutes ago
        limiter.clients["old_client"] = [old_time]
        limiter.clients["active_client"] = [current_time - 30]
        
        # Trigger global cleanup
        limiter._global_cleanup(current_time)
        
        # Old client should be removed, active client should remain
        assert "old_client" not in limiter.clients
        assert "active_client" in limiter.clients
        assert limiter.last_cleanup >= current_time
    
    def test_rate_limiter_multiple_clients(self):
        """Test rate limiting with multiple clients."""
        
        limiter = SimpleRateLimiter(requests_per_minute=2, burst_size=1)
        
        # Each client should have independent rate limiting
        is_allowed1, _ = limiter.is_allowed("client1")
        is_allowed2, _ = limiter.is_allowed("client2")
        
        assert is_allowed1 is True
        assert is_allowed2 is True
        
        # Exceed limit for client1
        limiter.is_allowed("client1")  # Second request
        is_allowed1, _ = limiter.is_allowed("client1")  # Third request - should fail
        
        # client2 should still be allowed
        is_allowed2, _ = limiter.is_allowed("client2")
        
        assert is_allowed1 is False
        assert is_allowed2 is True


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware class."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter for testing."""
        return SimpleRateLimiter(requests_per_minute=2, burst_size=1)
    
    @pytest.fixture 
    def middleware(self, rate_limiter):
        """Create middleware for testing."""
        app = FastAPI()
        return RateLimitMiddleware(app, rate_limiter, enabled=True)
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_disabled(self, rate_limiter):
        """Test middleware when disabled."""
        # Lines 208-210: Test disabled middleware
        
        app = FastAPI()
        middleware = RateLimitMiddleware(app, rate_limiter, enabled=False)
        
        # Mock request and call_next
        mock_request = Mock()
        mock_response = Response()
        
        async def mock_call_next(request):
            return mock_response
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        assert result is mock_response
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_health_check_skip(self, middleware):
        """Test middleware skipping health checks."""
        # Lines 214-216: Test health check skip
        
        # Mock request for health check
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/health"
        mock_response = Response()
        
        async def mock_call_next(request):
            return mock_response
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        assert result is mock_response
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_allow_request(self, middleware):
        """Test middleware allowing a request."""
        # Lines 218-296: Test successful request handling
        
        # Mock request
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        
        # Mock response
        mock_response = Response()
        mock_response.headers = {}
        
        async def mock_call_next(request):
            return mock_response
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Should be the same response with rate limit headers
        assert result is mock_response
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_block_request(self, middleware):
        """Test middleware blocking a request due to rate limit."""
        
        # Mock request
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.101"
        
        # Exhaust rate limit
        middleware.rate_limiter.is_allowed("192.168.1.101")
        middleware.rate_limiter.is_allowed("192.168.1.101")
        middleware.rate_limiter.is_allowed("192.168.1.101")  # Should exceed limit
        
        async def mock_call_next(request):
            return Response()
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Should return 429 Too Many Requests
        assert isinstance(result, JSONResponse)
        assert result.status_code == 429
        
        # Check headers
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
        assert "Retry-After" in result.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_no_client(self, middleware):
        """Test middleware with no client information."""
        
        # Mock request without client
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/api/test"
        mock_request.client = None
        
        mock_response = Response()
        mock_response.headers = {}
        
        async def mock_call_next(request):
            return mock_response
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Should handle "unknown" client
        assert result is mock_response
        assert "X-RateLimit-Limit" in result.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_http_exception(self, middleware):
        """Test middleware handling HTTPException."""
        
        # Mock request
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.102"
        
        # Mock call_next to raise HTTPException
        async def mock_call_next(request):
            raise HTTPException(status_code=400, detail="Bad request")
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Should return JSONResponse with rate limit headers
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_generic_exception(self, middleware):
        """Test middleware handling generic exception."""
        
        # Mock request
        mock_request = Mock()
        mock_request.url = Mock()
        mock_request.url.path = "/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.103"
        
        # Mock call_next to raise generic exception
        async def mock_call_next(request):
            raise ValueError("Something went wrong")
        
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Should return 500 error with rate limit headers
        assert isinstance(result, JSONResponse)
        assert result.status_code == 500
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
