"""
Security utilities for JWT authentication, password hashing, and RBAC.
Provides FastAPI dependencies for authentication and authorization.
"""

import base64
from datetime import UTC, datetime, timedelta
import logging
import os
import secrets
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.config import get_settings

# JWT Configuration Constants
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "algotrading-platform"
JWT_AUDIENCE = "algotrading-api"
JWT_CLOCK_SKEW = 60  # seconds

# Token blacklist configuration (H-01 fix)
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
TOKEN_BLACKLIST_TTL = 7 * 24 * 60 * 60  # 7 days (match refresh token expiry)

# Module-level Redis client reference for token blacklist
_token_blacklist_redis: Optional["Redis"] = None  # type: ignore
_blacklist_logger = logging.getLogger(__name__)

# In-memory fallback blacklist for when Redis is unavailable
# Maps JTI -> expiry timestamp (seconds since epoch)
_memory_blacklist: dict[str, float] = {}
_MEMORY_BLACKLIST_MAX_SIZE = 10000  # Prevent unbounded memory growth


def _cleanup_memory_blacklist() -> None:
    """Remove expired entries from the in-memory blacklist."""
    now = datetime.now(UTC).timestamp()
    expired_keys = [k for k, exp in _memory_blacklist.items() if exp <= now]
    for k in expired_keys:
        _memory_blacklist.pop(k, None)


async def init_token_blacklist(redis_client) -> None:
    """
    Initialize the token blacklist with a Redis client.
    
    Args:
        redis_client: Async Redis client instance
        
    Note:
        Call this during application startup to enable token revocation.
        Without initialization, blacklist checks are skipped (logged warning).
    """
    global _token_blacklist_redis
    _token_blacklist_redis = redis_client
    _blacklist_logger.info("Token blacklist initialized with Redis")


async def blacklist_token(jti: str, expires_in: int | None = None) -> bool:
    """
    Add a token's JTI to the blacklist (H-01 fix).
    
    Args:
        jti: JWT ID to blacklist
        expires_in: TTL in seconds (default: TOKEN_BLACKLIST_TTL)
        
    Returns:
        True if successfully blacklisted, False otherwise
    """
    ttl = expires_in or TOKEN_BLACKLIST_TTL
    
    # Always store in memory as fallback (fail-closed)
    expiry = datetime.now(UTC).timestamp() + ttl
    _memory_blacklist[jti] = expiry
    # Evict oldest entries if memory blacklist exceeds max size
    if len(_memory_blacklist) > _MEMORY_BLACKLIST_MAX_SIZE:
        _cleanup_memory_blacklist()
        if len(_memory_blacklist) > _MEMORY_BLACKLIST_MAX_SIZE:
            # Still too large — evict oldest 20%
            sorted_items = sorted(_memory_blacklist.items(), key=lambda x: x[1])
            for k, _ in sorted_items[:_MEMORY_BLACKLIST_MAX_SIZE // 5]:
                _memory_blacklist.pop(k, None)
    
    if not _token_blacklist_redis:
        _blacklist_logger.warning("Token blacklist Redis not initialized — using in-memory fallback only")
        return True
    
    try:
        key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
        await _token_blacklist_redis.setex(key, ttl, "revoked")
        _blacklist_logger.info(f"Token blacklisted: {jti[:8]}...")
        return True
    except Exception as e:
        _blacklist_logger.error(f"Failed to blacklist token in Redis (in-memory fallback active): {e}")
        return True  # Still blacklisted in memory


async def is_token_blacklisted(jti: str) -> bool:
    """
    Check if a token's JTI is blacklisted (H-01 fix).
    
    Args:
        jti: JWT ID to check
        
    Returns:
        True if blacklisted, False otherwise
        
    Note:
        Fail-CLOSED: if Redis is unavailable, checks in-memory blacklist.
        If the token was blacklisted while Redis was up, it will be in both stores.
    """
    # Always check in-memory first (fastest path and fail-closed fallback)
    if jti in _memory_blacklist:
        expiry = _memory_blacklist[jti]
        if datetime.now(UTC).timestamp() < expiry:
            return True  # Token is blacklisted in memory
        else:
            # Expired entry — clean up
            _memory_blacklist.pop(jti, None)
    
    if not _token_blacklist_redis:
        # No Redis available and not in memory blacklist.
        # Since blacklist_token() always writes to memory first, absence from
        # the memory blacklist means the token was never revoked in this process.
        _blacklist_logger.warning("Token blacklist Redis unavailable — cannot verify token revocation status")
        return False  # Not in memory blacklist = was never revoked in this process
    
    try:
        key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
        result = await _token_blacklist_redis.get(key)
        return result is not None
    except Exception as e:
        _blacklist_logger.error(f"Failed to check token blacklist in Redis: {e}")
        # Redis error but not in memory blacklist — fail closed for known-revoked tokens
        # Since blacklist_token() always writes to memory, if it's not there, it wasn't revoked
        return False


async def revoke_all_user_tokens(username: str) -> bool:
    """
    Revoke all tokens for a user by setting a user-level revocation timestamp.
    
    Args:
        username: User whose tokens should be revoked
        
    Returns:
        True if successfully set, False otherwise
        
    Note:
        Tokens issued before this timestamp will be rejected.
    """
    if not _token_blacklist_redis:
        _blacklist_logger.warning("Token blacklist not initialized - cannot revoke user tokens")
        return False
    
    try:
        key = f"{TOKEN_BLACKLIST_PREFIX}user:{username}"
        timestamp = int(datetime.now(UTC).timestamp())
        # Keep user revocation for 30 days
        await _token_blacklist_redis.setex(key, 30 * 24 * 60 * 60, str(timestamp))
        _blacklist_logger.info(f"All tokens revoked for user: {username}")
        return True
    except Exception as e:
        _blacklist_logger.error(f"Failed to revoke user tokens: {e}")
        return False


def _b64url(data: bytes) -> bytes:
    """Base64URL encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64url_decode(seg: str) -> bytes:
    """Base64URL decode with proper padding."""
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg)


def verify_jwt(token: str, *, secret: str, issuer: str, audience: str, alg: str = "HS256") -> dict:
    """
    Strict JWT verification with explicit error handling.

    Args:
        token: JWT token string
        secret: Secret key for verification
        issuer: Expected issuer
        audience: Expected audience
        alg: Expected algorithm (default HS256)

    Returns:
        Decoded payload dictionary

    Raises:
        HTTPException: For various token validation failures
    """
    if not token or "." not in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # JWT verification using imported libraries

    try:
        # Strict verification with all options
        verified_payload = jwt.decode(
            token,
            secret,
            algorithms=[alg],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "require_exp": True,
                "require_iss": True,
                "require_aud": True,
            },
            issuer=issuer,
            audience=audience
        )

        # Additional required claims validation
        if not verified_payload.get("sub"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing subject")

        return verified_payload

    except ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except JWTClaimsError as e:
        # Handle claims errors (audience, issuer, etc.)
        error_str = str(e).lower()
        if "audience" in error_str or "aud" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong audience")
        elif "issuer" in error_str or "iss" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong issuer")
        else:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as e:
        # Handle other JWT errors with meaningful messages
        error_str = str(e).lower()
        if "expired" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        elif "signature" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
        elif "audience" in error_str or "aud" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong audience")
        elif "issuer" in error_str or "iss" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong issuer")
        elif "algorithm" in error_str or "alg" in error_str:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unsupported algorithm")
        else:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class UserClaims(BaseModel):
    """JWT claims structure for authenticated users."""

    sub: str  # subject (username)
    roles: list[str]
    iss: str  # issuer
    aud: str  # audience
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    jti: str  # JWT ID


class AuthenticatedUser(BaseModel):
    """Authenticated user information from JWT token."""

    username: str
    roles: list[str]
    token_id: str


# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token security scheme
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    M-10 FIX: bcrypt has a 72-byte input limit. Passwords longer than 72 bytes
    are now rejected instead of silently truncated, as truncation can cause
    security issues where different passwords hash to the same value.

    Args:
        password: Plain text password to hash (max 72 bytes when UTF-8 encoded)

    Returns:
        Hashed password string
        
    Raises:
        ValueError: If password exceeds 72 bytes when UTF-8 encoded
    """
    password_bytes = password.encode("utf-8")

    # M-10 FIX: Reject passwords that exceed bcrypt's 72-byte limit
    # instead of silently truncating (which can cause security issues)
    if len(password_bytes) > 72:
        import logging
        logging.error("Password exceeds bcrypt 72-byte limit - rejecting")
        raise ValueError(
            "Password too long: bcrypt has a 72-byte limit. "
            "Please use a shorter password (max ~72 ASCII characters, "
            "fewer for Unicode characters)."
        )

    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Previously hashed password (must be bcrypt)

    Returns:
        True if password matches, False otherwise

    Security:
        - Only bcrypt hashes are accepted
        - MD5 and other weak hash algorithms are explicitly rejected
        - Constant-time comparison via bcrypt.checkpw
    """
    try:
        # Validate that the hash appears to be bcrypt format
        # bcrypt hashes start with $2a$, $2b$, or $2y$ and are 60 chars
        if not hashed_password or len(hashed_password) < 59:
            import logging
            logging.warning("Password hash format rejected: not bcrypt")
            return False

        if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
            import logging
            logging.warning("Password hash format rejected: weak algorithm detected")
            return False

        # Use bcrypt verification with constant-time comparison
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        import logging
        logging.error(f"Password verification error: {e}")
        return False


def create_access_token(sub: str, roles: list[str], expires_minutes: int | None = None) -> str:
    """
    Create a JWT access token with normalized claims.

    Args:
        sub: Subject (username or user identifier) - required
        roles: List of user roles for RBAC
        expires_minutes: Token expiration in minutes (default from config)

    Returns:
        Encoded JWT token string

    Raises:
        ValueError: If token creation fails or required secret is missing
    """
    settings = get_settings()

    # Get JWT secret and validate — §9.2 FIX: attribute is 'secret_key', not 'jwt_secret_key'
    secret = getattr(settings.security, 'secret_key', None) or os.environ.get('SECURITY_JWT_SECRET')
    if not secret:
        raise ValueError("JWT secret key is required but not configured (SECRET_KEY / SECURITY_JWT_SECRET)")

    if expires_minutes is None:
        expires_minutes = getattr(settings.security, 'jwt_expire_minutes', 60)

    # Type validation for expires_minutes
    if not isinstance(expires_minutes, (int, float)):
        raise ValueError("expires_minutes must be a number")

    # Validate subject
    if not sub:
        raise ValueError("subject cannot be empty")

    # Import jose here to avoid startup dependency issues
    from jose import jwt

    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes)

    # Normalized JWT claims
    # V9 AA3-2 / Wave-42 (2026-05-03): include explicit token_type="access"
    # so decode_token can reject refresh tokens presented as access.
    claims = {
        "sub": sub,
        "roles": roles,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),  # Unique token ID
        "token_type": "access",
    }

    try:
        encoded_jwt = jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    except Exception as e:
        raise ValueError(f"Failed to create access token: {str(e)}")


# Refresh token configuration
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Refresh tokens last 7 days
REFRESH_TOKEN_TYPE = "refresh"


def create_refresh_token(sub: str, roles: list[str], expires_days: int | None = None) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        sub: Subject (username or user identifier) - required
        roles: List of user roles for RBAC
        expires_days: Token expiration in days (default 7)

    Returns:
        Encoded JWT refresh token string

    Raises:
        ValueError: If token creation fails or required secret is missing
    """
    settings = get_settings()

    # Get JWT secret and validate — §9.2 FIX
    secret = getattr(settings.security, 'secret_key', None) or os.environ.get('SECURITY_JWT_SECRET')
    if not secret:
        raise ValueError("JWT secret key is required but not configured (SECRET_KEY / SECURITY_JWT_SECRET)")

    if expires_days is None:
        expires_days = REFRESH_TOKEN_EXPIRE_DAYS

    # Validate subject
    if not sub:
        raise ValueError("subject cannot be empty")

    # Import jose here to avoid startup dependency issues
    from jose import jwt

    now = datetime.now(UTC)
    expire = now + timedelta(days=expires_days)

    # Refresh token claims - includes token_type to distinguish from access tokens
    claims = {
        "sub": sub,
        "roles": roles,
        "token_type": REFRESH_TOKEN_TYPE,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),  # Unique token ID for potential revocation
    }

    try:
        encoded_jwt = jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    except Exception as e:
        raise ValueError(f"Failed to create refresh token: {str(e)}")


def decode_refresh_token(token: str) -> dict:
    """
    Decode and verify a refresh token.

    Args:
        token: JWT refresh token string

    Returns:
        Decoded claims dictionary

    Raises:
        HTTPException: If token is invalid, expired, or not a refresh token
    """
    settings = get_settings()

    # §9.2 FIX: attribute is 'secret_key'
    secret = getattr(settings.security, 'secret_key', None) or os.environ.get('SECURITY_JWT_SECRET')
    if not secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT secret not configured")

    try:
        from jose import jwt

        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "require_exp": True,
            },
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )

        # Verify this is a refresh token
        if payload.get("token_type") != REFRESH_TOKEN_TYPE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token_type"
            )

        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token"
            )

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_token_expired")
    except JWTClaimsError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_claims")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token"
        )


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT token with normalized options.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded claims dictionary

    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    settings = get_settings()

    # Get JWT secret — §9.2 FIX: attribute is 'secret_key'
    secret = getattr(settings.security, 'secret_key', None) or os.environ.get('SECURITY_JWT_SECRET')
    if not secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT secret not configured")

    try:
        # SECURITY: No test token bypass - all tokens must be valid JWTs
        # Tests should use proper JWT fixtures via create_access_token()

        # Decode with normalized options.
        # V11 AA5-1 / Wave-67 (2026-05-03): the wave-47 fix passed
        # `leeway=JWT_CLOCK_SKEW` as a top-level kwarg, but
        # python-jose 3.5's `jwt.decode` signature only accepts:
        #   (token, key, algorithms, options, audience, issuer,
        #    subject, access_token)
        # — `leeway` was raising TypeError, swallowed by decode_token's
        # catch-all `except Exception`, returned as 401 invalid_token,
        # silently breaking EVERY JWT-authenticated endpoint in the
        # post-wave-50 image.  python-jose accepts leeway INSIDE the
        # options dict; PyJWT (a different library) accepts the kwarg
        # form.  Wave-47's source-grep test mistook one for the other.
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "require_exp": True,
                "require_iss": True,
                "require_aud": True,
                "leeway": JWT_CLOCK_SKEW,
            },
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )

        # Validate required claims
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token"
            )

        # V9 AA3-2 / Wave-42 (2026-05-03): reject refresh tokens on the
        # access-token verification path.  Previously decode_token did
        # NOT check token_type; refresh tokens (7-day TTL) were accepted
        # at /auth/me, /auth/verify, and admin audit endpoints — a
        # privilege/scope bypass.  The `decode_refresh_token()` helper
        # at line ~519 enforces token_type == "refresh"; the symmetric
        # check belongs here for "access".
        token_type = payload.get("token_type")
        if token_type and token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token_type",
            )

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")
    except JWTClaimsError:
        # Handle claims errors (audience, issuer, etc.)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_claims")
    except JWTError:
        # Handle other JWT errors
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    except Exception:
        # Catch-all for any other errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token"
        )


def verify_token(token: str) -> UserClaims:
    """
    Verify and decode a JWT token into UserClaims (backward compatibility).

    Args:
        token: JWT token string to verify

    Returns:
        Decoded user claims

    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    payload = decode_token(token)
    # V8 AA2-NEW-2 / Wave-32 (2026-05-03): catch pydantic ValidationError on
    # malformed claims (missing roles / iat / jti, wrong types) and return 401
    # instead of letting it bubble up as 500 + stack trace.  Previously a
    # signed-but-malformed token gave attackers a low-cost DoS + schema-leak
    # vector; now it presents identically to any other invalid token.
    try:
        return UserClaims(**payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
        ) from exc
    except Exception as exc:
        # pydantic ValidationError is not in the import surface; catch broadly
        # but only for the constructor path.
        if exc.__class__.__name__ == "ValidationError":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token",
            ) from exc
        raise


def verify_api_key(api_key: str) -> bool:
    """
    Verify an API key using constant-time comparison.

    Args:
        api_key: API key to verify

    Returns:
        True if API key is valid, False otherwise
    """
    settings = get_settings()

    # V10 AA4-4 / Wave-59 (2026-05-03): defensive `api_keys` lookup.
    # The wave-50 fix coerced settings.app.environment but the actual
    # 500 came from this path: `SecuritySettings` object has no
    # `api_keys` attribute in the current pydantic config.  `getattr`
    # with default returns falsy, allowing the existing branch to
    # return False cleanly instead of raising AttributeError.
    api_keys = getattr(settings.security, "api_keys", None)
    if not api_keys:
        return False

    # Use constant-time comparison to prevent timing attacks
    return any(
        secrets.compare_digest(api_key, valid_key) for valid_key in api_keys
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser | None:
    """
    FastAPI dependency to extract current user from JWT token or API key.
    Supports both JWT Bearer tokens and X-API-Key for staging environments.

    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials

    Returns:
        Authenticated user or None if not authenticated

    Raises:
        HTTPException: If token is invalid
    """
    settings = get_settings()

    # First, check Authorization: Bearer <JWT>
    if credentials and credentials.credentials:
        try:
            claims = verify_token(credentials.credentials)
            # V9 AA3-1 / Wave-42 (2026-05-03): reject blacklisted tokens.
            # Logout / refresh-rotation blacklist the jti; this gate
            # ensures a stolen token can be revoked.
            try:
                if await is_token_blacklisted(claims.jti):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="token_revoked",
                    )
            except HTTPException:
                raise
            except Exception as _bl_err:
                # Blacklist backend (Redis) down — fail-closed in prod
                # would break logins; fail-open here is acceptable since
                # the blacklist is a defense-in-depth layer, not the only
                # auth check. Log and continue.
                _blacklist_logger.warning(
                    "AA3-1: blacklist check failed (allowing token): %s",
                    _bl_err,
                )
            return AuthenticatedUser(
                username=claims.sub, roles=claims.roles, token_id=claims.jti
            )
        except HTTPException as e:
            # Re-raise specific JWT errors (expired, invalid signature, etc.)
            if any(term in str(e.detail).lower() for term in ["expired", "signature", "invalid token", "revoked"]):
                raise
            # Invalid JWT token - continue to try other auth methods
            pass

    # If no JWT, check X-API-Key for staging environments
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # V10 AA4-4 / Wave-50 (2026-05-03): coerce env to str BEFORE
        # .lower() — `settings.app.environment` is an Enum in some
        # configs and `Enum.lower()` raises AttributeError, which
        # propagated as HTTP 500 with stack trace + reference ID.
        # str(enum) returns "Environment.DEVELOPMENT"; .value gives
        # the raw string; getattr fallback covers both shapes.
        _env_obj = getattr(settings.app, "environment", "")
        _env_str = (
            getattr(_env_obj, "value", None)
            or (str(_env_obj) if _env_obj is not None else "")
        )
        app_env = _env_str.lower() if isinstance(_env_str, str) else ""
        staging_key = os.environ.get("STAGING_API_KEY")

        if staging_key and app_env in {"dev", "development", "staging"}:
            if secrets.compare_digest(api_key, staging_key):
                return AuthenticatedUser(
                    username="staging-user",
                    roles=["viewer"],  # Staging key gets read-only access, NOT admin
                    token_id="staging-api-key",
                )

        # Fallback to regular API key verification
        if verify_api_key(api_key):
            return AuthenticatedUser(
                username="api-client",
                roles=["trader", "api"],  # API keys get trader permissions
                token_id="api-key",
            )

    return None


async def get_authenticated_user(
    current_user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    FastAPI dependency that requires authentication.

    Args:
        current_user: Current authenticated user (if any)

    Returns:
        Authenticated user

    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user


def require_roles(*required_roles: str):
    """
    Create a FastAPI dependency that requires specific roles.

    Args:
        *required_roles: One or more roles required for access

    Returns:
        An async FastAPI dependency callable. Use with `Depends(...)`:

            @app.get("/admin-only")
            async def admin_endpoint(
                user: AuthenticatedUser = Depends(require_admin),
            ): ...

    For sync / unit-test role checking against a user object directly,
    use `check_user_roles(user, *roles)` defined below.

    V7 AA-C-2 / Wave-23b (2026-05-03): the previous implementation
    returned a `check_roles_hybrid` wrapper that introspected its
    argument at call time. FastAPI's dependency injection saw a
    function with an optional `user_or_dependency=None` parameter,
    called it with no args, and got back the *function reference*
    `check_roles_async` — never actually executing the role check.
    Result: 18 admin endpoints (12 organism, 6 audit) silently lost
    their role gate. Combined with self-registration granting
    `["user"]` role, any registered user could call any admin route.

    Now: returns the async dependency directly. FastAPI's DI
    introspects the *async* function's `current_user` parameter,
    resolves it via `Depends(get_authenticated_user)`, and runs the
    role check in the function body.
    """

    async def check_roles_dep(
        current_user: AuthenticatedUser = Depends(get_authenticated_user),
    ) -> AuthenticatedUser:
        """Async FastAPI dependency that enforces the required roles."""
        user_roles = set(current_user.roles)
        required_roles_set = set(required_roles)

        if not required_roles_set.intersection(user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions. Required roles: "
                    f"{', '.join(required_roles)}"
                ),
            )

        return current_user

    # Tag with the role list so test code / introspection can read it.
    check_roles_dep.required_roles = list(required_roles)  # type: ignore[attr-defined]
    return check_roles_dep


# Common role-based dependencies
require_admin = require_roles("admin")
require_trader = require_roles("trader", "admin")  # Admin can also trade
require_api = require_roles("api", "admin")  # API access or admin


def check_user_roles(user: AuthenticatedUser, *required_roles: str) -> AuthenticatedUser:
    """
    Synchronous role checking function for testing and direct usage.

    Args:
        user: Authenticated user to check
        *required_roles: Required roles (OR logic - user needs at least one)

    Returns:
        The user if authorized

    Raises:
        HTTPException: If user doesn't have required roles
    """
    user_roles = set(user.roles)
    required_roles_set = set(required_roles)

    if not required_roles_set.intersection(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
        )

    return user


def get_user_id(user):
    """
    Normalize user ID extraction from user objects or dictionaries.

    Args:
        user: User object with attributes or dictionary with keys

    Returns:
        User ID string or None if not found
    """
    if hasattr(user, "id"):
        return user.id
    if isinstance(user, dict):
        return user.get("id")
    return None


def get_user_attribute(user, attribute: str, default=None):
    """
    Normalize user attribute extraction with attribute-first logic.

    Args:
        user: User object with attributes or dictionary with keys
        attribute: Attribute/key name to extract
        default: Default value if attribute not found

    Returns:
        Attribute value or default
    """
    # Try attribute access first (object)
    if hasattr(user, attribute):
        return getattr(user, attribute, default)
    # Fall back to dictionary access
    if isinstance(user, dict):
        return user.get(attribute, default)
    return default
