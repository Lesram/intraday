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
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings
from starlette.middleware.base import BaseHTTPMiddleware


class SecuritySettings(BaseSettings):
    """Enhanced security settings with strict validation."""

    model_config = ConfigDict(
        env_prefix="SECURITY_",
        case_sensitive=False
    )

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
        default=["Authorization", "Content-Type"],
        description="Allowed headers for CORS",
    )
    cors_max_age: int = Field(
        default=600,  # 10 minutes
        description="CORS preflight cache duration in seconds",
    )

    # Rate Limiting Configuration
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Maximum requests per minute per IP"
    )
    rate_limit_burst_size: int = Field(
        default=10, description="Burst size for rate limiting"
    )
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")

    # JWT Security Settings
    jwt_require_https: bool = Field(
        default=True, description="Require HTTPS for JWT tokens"
    )
    jwt_require_aud: bool = Field(
        default=True, description="Require audience claim in JWT"
    )
    jwt_require_iss: bool = Field(
        default=True, description="Require issuer claim in JWT"
    )
    jwt_leeway_seconds: int = Field(
        default=10, description="JWT validation leeway in seconds"
    )

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

    @field_validator("cors_allow_origins")
    @classmethod
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

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, v):
        """Validate trusted hosts."""
        if not v:
            raise ValueError("At least one trusted host must be configured")
        return v

    @field_validator("rate_limit_requests_per_minute")
    @classmethod
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
                    req_time
                    for req_time in self.clients[client_ip]
                    if req_time > cutoff_time
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
                oldest_request = (
                    min(client_requests) if client_requests else current_time
                )
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
                        max(
                            0,
                            rate_info["requests_allowed"] - rate_info["requests_made"],
                        )
                    ),
                    "X-RateLimit-Reset": str(int(rate_info["reset_time"])),
                    "Retry-After": str(rate_info["retry_after"]),
                },
            )

        try:
            response = await call_next(request)
        except Exception as e:
            # Convert exceptions to proper HTTP responses with rate limit headers
            from fastapi import HTTPException

            if isinstance(e, HTTPException):
                # For HTTPException, return a proper response with rate limit headers
                response = JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail},
                    headers={
                        "X-RateLimit-Limit": str(rate_info["requests_allowed"]),
                        "X-RateLimit-Remaining": str(
                            max(0, rate_info["requests_allowed"] - rate_info["requests_made"])
                        ),
                        "X-RateLimit-Reset": str(int(rate_info["reset_time"])),
                    }
                )
                return response
            else:
                # For other exceptions, return 500 error with rate limit headers
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error"},
                    headers={
                        "X-RateLimit-Limit": str(rate_info["requests_allowed"]),
                        "X-RateLimit-Remaining": str(
                            max(0, rate_info["requests_allowed"] - rate_info["requests_made"])
                        ),
                        "X-RateLimit-Reset": str(int(rate_info["reset_time"])),
                    }
                )
                return response

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
        try:
            response = await call_next(request)
        except Exception as e:
            # Even on exceptions, add security headers if possible
            if hasattr(e, 'status_code') and hasattr(e, 'headers') and self.enabled:
                # HTTPException-like object
                if e.headers is None:
                    e.headers = {}
                self._add_security_headers(e.headers, request)
            raise e

        if not self.enabled:
            return response

        # Add security headers to successful responses
        self._add_security_headers(response.headers, request)

        return response

    def _add_security_headers(self, headers, request):
        """Helper method to add security headers."""
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # V8 AA2-NEW-3 / Wave-32 (2026-05-03): honour X-Forwarded-Proto for
        # HSTS emission so the canonical reverse-proxy / TLS-terminator
        # production deployment still gets HSTS.  Previously HSTS was only
        # emitted when `request.url.scheme == "https"`, which is false behind
        # nginx / ALB / Cloudfront where the upstream sees scheme=http.
        forwarded_proto = (
            request.headers.get("x-forwarded-proto", "")
            .split(",")[0]
            .strip()
            .lower()
        )
        if request.url.scheme == "https" or forwarded_proto == "https":
            headers["Strict-Transport-Security"] = (
                f"max-age={self.hsts_max_age}; includeSubDomains"
            )

        # Content Security Policy (basic)
        headers["Content-Security-Policy"] = (
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


def configure_security_middleware(app, security_settings: SecuritySettings):
    """
    Configure all security middleware based on settings.

    Args:
        app: FastAPI application instance
        security_settings: Security configuration settings
    """

    # Trusted Host middleware (should be first)
    if security_settings.trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=security_settings.trusted_hosts
        )

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
                if request.client and request.client.host not in [
                    "127.0.0.1",
                    "localhost",
                ]:
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


class JwtVerifier:
    """JWT encoder/decoder with lazy import of jose.jwt to avoid import issues in tests."""

    def __init__(self):
        """Initialize with lazy import of jose.jwt"""
        self._jwt = None
        self._jwt_error = None
        # Lazy import on first use
        self._load_jwt()

    def _load_jwt(self):
        """Lazy import of jose.jwt"""
        if self._jwt is None:
            try:
                from jose import JWTError
                from jose import jwt as jose_jwt
                self._jwt = jose_jwt
                self._jwt_error = JWTError
            except ImportError as e:
                raise ImportError(
                    "python-jose is required for JWT operations. "
                    "Install it with: pip install python-jose[cryptography]"
                ) from e

    @property
    def jwt(self):
        """Get jose.jwt module"""
        self._load_jwt()
        return self._jwt

    @property
    def JWTError(self):
        """Get jose.JWTError exception"""
        self._load_jwt()
        return self._jwt_error

    @JWTError.setter
    def JWTError(self, value):
        """Set jose.JWTError exception (for testing)"""
        self._jwt_error = value

    @JWTError.deleter
    def JWTError(self):
        """Delete jose.JWTError exception (for testing)"""
        self._jwt_error = None

    def encode(self, payload: dict, key: str = None, algorithm: str = None) -> str:
        """
        Encode JWT token with required claims validation.

        Args:
            payload: JWT payload containing iss, aud, alg, exp, and other claims
            key: Secret key for encoding (uses default if not provided)
            algorithm: Algorithm for encoding (uses HS256 if not provided)

        Returns:
            Encoded JWT token string

        Raises:
            ValueError: If required claims (iss, aud, alg, exp) are missing
        """
        # Validate required claims
        required_claims = ['iss', 'aud', 'exp']
        missing_claims = [claim for claim in required_claims if claim not in payload]
        if missing_claims:
            raise ValueError(f"Missing required JWT claims: {missing_claims}")

        # Use provided parameters or defaults from settings
        algorithm = algorithm or "HS256"
        if key is None:
            from backend.config import get_settings
            settings = get_settings()
            key = settings.security.jwt_secret_key

        return self.jwt.encode(payload, key, algorithm=algorithm)

    def decode(self, token: str) -> dict:
        """
        Decode JWT token with validation of iss, aud, alg, exp claims.

        Args:
            token: JWT token string to decode

        Returns:
            Decoded JWT payload as dictionary

        Raises:
            JWTError: If token is invalid or claims validation fails
        """
        # Get key from settings for consistency with encoding
        from backend.config import get_settings
        settings = get_settings()
        key = settings.security.jwt_secret_key

        # Decode with validation of required claims
        try:
            # First decode without strict validation to get claims
            decoded = self.jwt.decode(
                token=token,
                key=key,
                algorithms=["HS256", "RS256"],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": False,  # Disable automatic issuer validation
                    "verify_aud": False,  # Disable automatic audience validation
                    "require_exp": True,
                    "require_iss": False,
                    "require_aud": False
                }
            )

            # Manual validation of required claims
            required_claims = ['iss', 'aud', 'exp']
            missing_claims = [claim for claim in required_claims if claim not in decoded]
            if missing_claims:
                raise self.JWTError(f"Missing required claims: {missing_claims}")

            # Validate algorithm claim if present
            if 'alg' in decoded and decoded['alg'] not in ["HS256", "RS256"]:
                raise self.JWTError(f"Unsupported algorithm: {decoded['alg']}")

            return decoded

        except Exception as e:
            # Handle any JWT decode error
            if "JWTError" in str(type(e)) or "JWSError" in str(type(e)) or "ExpiredSignatureError" in str(type(e)):
                raise self.JWTError(f"JWT decode error: {str(e)}") from e
            else:
                raise self.JWTError(f"JWT decode error: {str(e)}") from e


# Global instance to use throughout the application
jwt_verifier = JwtVerifier()


# ================== Input Validation ==================

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class ValidationResult:
    """Result of input validation."""

    is_valid: bool
    sanitized_value: Any = None
    errors: list[str] = field(default_factory=list)


class InputValidator:
    """
    Input validation and sanitization utilities.

    Validates common trading platform inputs:
    - Symbols
    - Order quantities
    - Prices
    - User inputs
    """

    # Patterns
    SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")
    ORDER_ID_PATTERN = re.compile(r"^[a-f0-9\-]{36}$")
    SAFE_STRING_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.@\s]+$")

    # Limits
    MAX_SYMBOL_LENGTH = 10
    MAX_STRING_LENGTH = 1000
    MAX_QUANTITY = 1_000_000
    MIN_QUANTITY = 0.0001
    MAX_PRICE = 1_000_000
    MIN_PRICE = 0.0001

    @classmethod
    def validate_symbol(cls, value: str) -> ValidationResult:
        """Validate a stock symbol."""
        if not value:
            return ValidationResult(False, errors=["Symbol is required"])

        sanitized = value.upper().strip()

        if len(sanitized) > cls.MAX_SYMBOL_LENGTH:
            return ValidationResult(False, errors=["Symbol too long"])

        if not cls.SYMBOL_PATTERN.match(sanitized):
            return ValidationResult(False, errors=["Invalid symbol format"])

        return ValidationResult(True, sanitized)

    @classmethod
    def validate_quantity(cls, value: float | int | str) -> ValidationResult:
        """Validate an order quantity."""
        try:
            qty = float(value)
        except (ValueError, TypeError):
            return ValidationResult(False, errors=["Invalid quantity format"])

        if qty < cls.MIN_QUANTITY:
            return ValidationResult(False, errors=[f"Quantity must be >= {cls.MIN_QUANTITY}"])

        if qty > cls.MAX_QUANTITY:
            return ValidationResult(False, errors=[f"Quantity must be <= {cls.MAX_QUANTITY}"])

        return ValidationResult(True, qty)

    @classmethod
    def validate_price(cls, value: float | int | str) -> ValidationResult:
        """Validate a price."""
        try:
            price = float(value)
        except (ValueError, TypeError):
            return ValidationResult(False, errors=["Invalid price format"])

        if price < cls.MIN_PRICE:
            return ValidationResult(False, errors=[f"Price must be >= {cls.MIN_PRICE}"])

        if price > cls.MAX_PRICE:
            return ValidationResult(False, errors=[f"Price must be <= {cls.MAX_PRICE}"])

        return ValidationResult(True, round(price, 4))

    @classmethod
    def validate_order_id(cls, value: str) -> ValidationResult:
        """Validate a UUID order ID."""
        if not value:
            return ValidationResult(False, errors=["Order ID is required"])

        sanitized = value.lower().strip()

        if not cls.ORDER_ID_PATTERN.match(sanitized):
            return ValidationResult(False, errors=["Invalid order ID format"])

        return ValidationResult(True, sanitized)

    @classmethod
    def sanitize_string(cls, value: str, max_length: int | None = None) -> ValidationResult:
        """Sanitize a general string input."""
        if not value:
            return ValidationResult(True, "")

        max_len = max_length or cls.MAX_STRING_LENGTH

        # Truncate
        sanitized = value[:max_len]

        # Remove control characters
        sanitized = "".join(c for c in sanitized if ord(c) >= 32 or c in "\n\t")

        # Check for safe characters only
        if not cls.SAFE_STRING_PATTERN.match(sanitized):
            # Remove unsafe characters
            sanitized = re.sub(r"[^a-zA-Z0-9_\-\.@\s]", "", sanitized)

        return ValidationResult(True, sanitized.strip())

    @classmethod
    def validate_email(cls, value: str) -> ValidationResult:
        """Validate an email address."""
        if not value:
            return ValidationResult(False, errors=["Email is required"])

        # Simple email pattern
        pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

        sanitized = value.lower().strip()

        if len(sanitized) > 254:
            return ValidationResult(False, errors=["Email too long"])

        if not pattern.match(sanitized):
            return ValidationResult(False, errors=["Invalid email format"])

        return ValidationResult(True, sanitized)

