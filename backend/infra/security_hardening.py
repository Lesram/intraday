"""
Enhanced Security Hardening - Pydantic settings, strict CORS, JWT checks, and rate limiting
Provides production-ready security configurations and middleware.
"""
from collections import defaultdict
import time
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from starlette.middleware.base import BaseHTTPMiddleware


class SecuritySettings(BaseSettings):
    """Enhanced security settings with strict validation."""

    class Config:
        env_prefix = "SECURITY_"
        case_sensitive = False

    # CORS Configuration - Strict by default
    cors_allow_origins: list[str] = Field(
        default=[],  # Empty by default - must be explicitly configured
        description="Allowed CORS origins - must be explicitly configured",
    )
    cors_allow_credentials: bool = Field(
        default=False, description="Allow credentials in CORS requests"
    )
    cors_allow_methods: list[str] = Field(
        default=["GET", "POST"], description="Allowed HTTP methods for CORS"
    )
    cors_allow_headers: list[str] = Field(
        default=["Authorization", "Content-Type"], description="Allowed headers for CORS"
    )
    cors_max_age: int = Field(
        default=600,  # 10 minutes
        description="CORS preflight cache duration in seconds",
    )

    # Rate Limiting Configuration
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Maximum requests per minute per IP"
    )
    rate_limit_burst_size: int = Field(default=10, description="Burst size for rate limiting")
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")

    # JWT Security Settings
    jwt_require_https: bool = Field(default=True, description="Require HTTPS for JWT tokens")
    jwt_require_aud: bool = Field(default=True, description="Require audience claim in JWT")
    jwt_require_iss: bool = Field(default=True, description="Require issuer claim in JWT")
    jwt_leeway_seconds: int = Field(default=10, description="JWT validation leeway in seconds")

    # Trusted Hosts - Production security
    trusted_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1"], description="Trusted host names"
    )

    # Security Headers
    enable_security_headers: bool = Field(
        default=True, description="Enable security headers middleware"
    )
    hsts_max_age: int = Field(
        default=31536000,  # 1 year
        description="HSTS max age in seconds",
    )

    @validator("cors_allow_origins")
    def validate_cors_origins(cls, v):
        """Validate CORS origins - must be explicit."""
        if not v:
            raise ValueError(
                "CORS origins must be explicitly configured. "
                "Use ['*'] for development only, never in production."
            )

        # Check for wildcard in production
        if "*" in v:
            import os

            env = os.getenv("APP_ENVIRONMENT", "development")
            if env == "production":
                raise ValueError("Wildcard CORS origins not allowed in production")

        # Validate each origin
        for origin in v:
            if origin != "*" and not (origin.startswith(("http://", "https://"))):
                raise ValueError(f"Invalid CORS origin format: {origin}")

        return v

    @validator("trusted_hosts")
    def validate_trusted_hosts(cls, v):
        """Validate trusted hosts."""
        if not v:
            raise ValueError("At least one trusted host must be configured")
        return v

    @validator("rate_limit_requests_per_minute")
    def validate_rate_limit(cls, v):
        """Validate rate limit settings."""
        if v <= 0:
            raise ValueError("Rate limit must be positive")
        if v > 10000:  # Reasonable upper bound
            raise ValueError("Rate limit too high - maximum 10000 requests/minute")
        return v


class SimpleRateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    For production, consider Redis-based rate limiting.
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.clients: dict[str, list[float]] = defaultdict(list)
        self.last_cleanup = time.time()

    def _cleanup_old_requests(self, client_ip: str, current_time: float) -> None:
        """Remove requests older than 1 minute."""
        cutoff_time = current_time - 60.0  # 1 minute ago
        self.clients[client_ip] = [
            req_time for req_time in self.clients[client_ip] if req_time > cutoff_time
        ]

    def _global_cleanup(self, current_time: float) -> None:
        """Periodic cleanup of all clients."""
        if current_time - self.last_cleanup > 300:  # Every 5 minutes
            cutoff_time = current_time - 60.0
            for client_ip in list(self.clients.keys()):
                self.clients[client_ip] = [
                    req_time for req_time in self.clients[client_ip] if req_time > cutoff_time
                ]
                if not self.clients[client_ip]:
                    del self.clients[client_ip]
            self.last_cleanup = current_time

    def is_allowed(self, client_ip: str) -> tuple[bool, dict[str, Any]]:
        """
        Check if request is allowed for client IP.

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        current_time = time.time()

        # Cleanup old requests
        self._cleanup_old_requests(client_ip, current_time)
        self._global_cleanup(current_time)

        client_requests = self.clients[client_ip]
        request_count = len(client_requests)

        # Check burst limit
        if request_count >= self.burst_size:
            # Check if we're within rate limit over the full minute
            if request_count >= self.requests_per_minute:
                oldest_request = min(client_requests) if client_requests else current_time
                reset_time = oldest_request + 60.0

                return False, {
                    "requests_made": request_count,
                    "requests_allowed": self.requests_per_minute,
                    "reset_time": reset_time,
                    "retry_after": max(1, int(reset_time - current_time)),
                }

        # Allow request and record it
        self.clients[client_ip].append(current_time)

        return True, {
            "requests_made": request_count + 1,
            "requests_allowed": self.requests_per_minute,
            "reset_time": current_time + 60.0,
            "retry_after": 0,
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""

    def __init__(self, app, rate_limiter: SimpleRateLimiter, enabled: bool = True):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to requests."""
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz", "/readyz"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Check rate limit
        is_allowed, rate_info = self.rate_limiter.is_allowed(client_ip)

        if not is_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests",
                        "details": {
                            "requests_made": rate_info["requests_made"],
                            "requests_allowed": rate_info["requests_allowed"],
                            "retry_after": rate_info["retry_after"],
                        },
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(rate_info["requests_allowed"]),
                    "X-RateLimit-Remaining": str(
                        max(0, rate_info["requests_allowed"] - rate_info["requests_made"])
                    ),
                    "X-RateLimit-Reset": str(int(rate_info["reset_time"])),
                    "Retry-After": str(rate_info["retry_after"]),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(rate_info["requests_allowed"])
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, rate_info["requests_allowed"] - rate_info["requests_made"])
        )
        response.headers["X-RateLimit-Reset"] = str(int(rate_info["reset_time"]))

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers middleware."""

    def __init__(self, app, hsts_max_age: int = 31536000, enabled: bool = True):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        """Add security headers to responses."""
        response = await call_next(request)

        if not self.enabled:
            return response

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # HSTS for HTTPS
        if request.url.scheme == "https":
            response.headers[
                "Strict-Transport-Security"
            ] = f"max-age={self.hsts_max_age}; includeSubDomains"

        # Content Security Policy (basic)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        return response


def configure_security_middleware(app, security_settings: SecuritySettings):
    """
    Configure all security middleware based on settings.

    Args:
        app: FastAPI application instance
        security_settings: Security configuration settings
    """

    # Trusted Host middleware (should be first)
    if security_settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=security_settings.trusted_hosts)

    # Security headers middleware
    if security_settings.enable_security_headers:
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_max_age=security_settings.hsts_max_age,
            enabled=security_settings.enable_security_headers,
        )

    # Rate limiting middleware
    if security_settings.rate_limit_enabled:
        rate_limiter = SimpleRateLimiter(
            requests_per_minute=security_settings.rate_limit_requests_per_minute,
            burst_size=security_settings.rate_limit_burst_size,
        )
        app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=rate_limiter,
            enabled=security_settings.rate_limit_enabled,
        )

    # CORS middleware (should be last in the stack)
    if security_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=security_settings.cors_allow_origins,
            allow_credentials=security_settings.cors_allow_credentials,
            allow_methods=security_settings.cors_allow_methods,
            allow_headers=security_settings.cors_allow_headers,
            max_age=security_settings.cors_max_age,
        )


class JWTValidator:
    """Enhanced JWT validation with strict checks."""

    def __init__(self, security_settings: SecuritySettings):
        self.settings = security_settings

    def validate_request_context(self, request: Request) -> None:
        """
        Validate request context for JWT security requirements.

        Args:
            request: FastAPI request object

        Raises:
            HTTPException: If request context is invalid
        """
        # Check HTTPS requirement
        if self.settings.jwt_require_https:
            if request.url.scheme != "https":
                # Allow localhost for development
                if request.client and request.client.host not in ["127.0.0.1", "localhost"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="HTTPS required for JWT authentication",
                    )

    def get_enhanced_jwt_verification_options(self) -> dict[str, Any]:
        """
        Get JWT verification options based on security settings.

        Returns:
            JWT verification options dictionary
        """
        options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "require_exp": True,
            "require_iat": True,
        }

        if self.settings.jwt_require_aud:
            options["verify_aud"] = True
            options["require_aud"] = True

        if self.settings.jwt_require_iss:
            options["verify_iss"] = True
            options["require_iss"] = True

        return options
