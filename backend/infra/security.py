"""
Security utilities for JWT authentication, password hashing, and RBAC.
Provides FastAPI dependencies for authentication and authorization.
"""

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import logging
import math
import os
import secrets
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # V12 W75 (UU3-2 / F821): import Redis for the forward-ref type
    # annotation below.  Static analysers (ruff) flag string-quoted
    # forward refs without a TYPE_CHECKING import as F821 undefined.
    from redis.asyncio import Redis  # noqa: F401

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
from redis.exceptions import RedisError

from backend.config import get_settings

# JWT Configuration Constants
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "algotrading-platform"
JWT_AUDIENCE = "algotrading-api"
JWT_CLOCK_SKEW = 60  # seconds
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # lifetime of tokens minted by login/refresh

# Token blacklist configuration (H-01 fix)
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
TOKEN_BLACKLIST_TTL = 7 * 24 * 60 * 60  # 7 days (match refresh token expiry)

# Session revocation (audit 2026-10-05): tokens minted together by one login
# share a session id ("sid" claim); logout revokes the whole session. Tokens
# also carry a credential fingerprint ("cfp" claim) derived from the stored
# password hash; a password change or deactivation revokes the old fingerprint.
# Both live in the same blacklist store as revoked jtis, under these prefixes.
SESSION_REVOCATION_PREFIX = "sid:"
CREDENTIAL_REVOCATION_PREFIX = "cfp:"

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


def _remember_revocation(key: str, ttl: int) -> None:
    """Record a revocation in the in-memory store (never shortens an entry)."""
    expiry = datetime.now(UTC).timestamp() + ttl
    _memory_blacklist[key] = max(_memory_blacklist.get(key, 0.0), expiry)
    # Evict oldest entries if memory blacklist exceeds max size
    if len(_memory_blacklist) > _MEMORY_BLACKLIST_MAX_SIZE:
        _cleanup_memory_blacklist()
        if len(_memory_blacklist) > _MEMORY_BLACKLIST_MAX_SIZE:
            # Still too large — evict oldest 20%
            sorted_items = sorted(_memory_blacklist.items(), key=lambda x: x[1])
            for k, _ in sorted_items[:_MEMORY_BLACKLIST_MAX_SIZE // 5]:
                _memory_blacklist.pop(k, None)


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
    _remember_revocation(jti, ttl)

    if not _token_blacklist_redis:
        _blacklist_logger.warning("Token blacklist Redis not initialized — using in-memory fallback only")
        return True

    try:
        key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
        await _token_blacklist_redis.setex(key, ttl, "revoked")
        _blacklist_logger.info("Token blacklisted: %s...", jti[:8])
        return True
    except (RedisError, OSError) as e:
        _blacklist_logger.error("Failed to blacklist token in Redis (in-memory fallback active): %s", e)
        return True  # Still blacklisted in memory


async def token_revocation_reason(
    jti: str,
    *,
    session_id: str | None = None,
    fingerprint: str | None = None,
) -> str | None:
    """Return why a token is revoked, or None.

    Checks, in one pass: the token's own jti ("token"), its login session
    ("session", revoked at logout) and its credential fingerprint
    ("credentials", revoked by a password change or deactivation).

    The in-memory store is checked first, then Redis in a single round trip.
    Redis lookups are bounded by the client's socket timeouts (see
    backend/api/lifespan.py). If Redis fails or times out, the check falls
    back to the in-memory store only (fail-open for entries that only Redis
    holds): every revocation made by this process is also kept in memory, so
    what is skipped is limited to revocations recorded before the last restart
    or by another process. Failing closed would turn a Redis outage into a
    complete authentication outage, including the emergency-stop and halt
    endpoints and every Socket.IO delivery.
    """
    keys = [("token", jti)]
    if session_id:
        keys.append(("session", f"{SESSION_REVOCATION_PREFIX}{session_id}"))
    if fingerprint:
        keys.append(("credentials", f"{CREDENTIAL_REVOCATION_PREFIX}{fingerprint}"))

    # Always check in-memory first (fastest path and fail-closed fallback)
    now = datetime.now(UTC).timestamp()
    for reason, key in keys:
        expiry = _memory_blacklist.get(key)
        if expiry is not None:
            if now < expiry:
                return reason
            _memory_blacklist.pop(key, None)  # Expired entry — clean up

    if not _token_blacklist_redis:
        # Since blacklist_token() always writes to memory first, absence from
        # the memory blacklist means the token was never revoked in this process.
        _blacklist_logger.warning("Token blacklist Redis unavailable — cannot verify token revocation status")
        return None

    redis_keys = [f"{TOKEN_BLACKLIST_PREFIX}{key}" for _, key in keys]
    try:
        if len(redis_keys) == 1:
            values = [await _token_blacklist_redis.get(redis_keys[0])]
        else:
            values = await _token_blacklist_redis.mget(redis_keys)
    except (RedisError, OSError) as e:
        _blacklist_logger.error("Failed to check token blacklist in Redis: %s", e)
        return None
    for (reason, _), value in zip(keys, values or ()):
        if value is not None:
            return reason
    return None


async def is_token_blacklisted(
    jti: str,
    *,
    session_id: str | None = None,
    fingerprint: str | None = None,
) -> bool:
    """
    Check if a token is revoked (H-01 fix).

    Args:
        jti: JWT ID to check
        session_id: optional ``sid`` claim (session revoked at logout)
        fingerprint: optional ``cfp`` claim (credentials changed)

    Returns:
        True if blacklisted, False otherwise

    Note:
        See token_revocation_reason for the Redis timeout / fallback behaviour.
    """
    reason = await token_revocation_reason(jti, session_id=session_id, fingerprint=fingerprint)
    return reason is not None


async def claim_token_once(jti: str, expires_in: int) -> bool:
    """Mark a single-use token id (a refresh token's jti) as used.

    Returns True only for the first caller. The in-memory claim is made before
    any await, so concurrent requests in this process cannot both succeed; the
    Redis ``SET NX`` extends the claim across restarts. If Redis fails, the
    in-memory claim stands (the API runs a single worker process).
    """
    expiry = _memory_blacklist.get(jti)
    if expiry is not None and datetime.now(UTC).timestamp() < expiry:
        return False
    ttl = max(1, int(expires_in))
    _remember_revocation(jti, ttl)
    if not _token_blacklist_redis:
        return True
    try:
        created = await _token_blacklist_redis.set(
            f"{TOKEN_BLACKLIST_PREFIX}{jti}", "revoked", ex=ttl, nx=True,
        )
    except (RedisError, OSError) as e:
        _blacklist_logger.error("Failed to record token use in Redis (in-memory claim stands): %s", e)
        return True
    return bool(created)


def revocation_ttl(exp: object) -> int:
    """Seconds a revocation entry for a token expiring at ``exp`` must live.

    Covers the token's remaining lifetime plus the JWT_CLOCK_SKEW leeway that
    decode_token accepts after ``exp``. Unknown expiry: the refresh lifetime.
    """
    if isinstance(exp, (int, float)) and not isinstance(exp, bool) and math.isfinite(exp):
        return max(1, int(exp - datetime.now(UTC).timestamp()) + JWT_CLOCK_SKEW + 1)
    return TOKEN_BLACKLIST_TTL + JWT_CLOCK_SKEW


def new_session_id() -> str:
    """Session id shared by the access and refresh tokens of one login."""
    return secrets.token_urlsafe(16)


def _jwt_secret() -> str | None:
    settings = get_settings()
    return getattr(settings.security, 'secret_key', None) or os.environ.get('SECURITY_JWT_SECRET')


def credential_fingerprint(username: str, hashed_password: str | None) -> str | None:
    """Keyed fingerprint of a user's stored password hash (``cfp`` claim).

    bcrypt salts every hash, so the fingerprint changes whenever the password
    is set, by any path. Refresh compares the token's fingerprint with the one
    computed from the database row; access-token checks consult the revoked
    fingerprints. HMAC-SHA256 keyed with the JWT secret, truncated to 18 bytes.
    """
    if (not isinstance(username, str) or not username
            or not isinstance(hashed_password, str) or not hashed_password):
        return None
    secret = _jwt_secret()
    if not secret:
        return None
    message = b"\x00".join((
        b"intra-credential-fingerprint-v1",
        username.encode("utf-8"),
        hashed_password.encode("utf-8"),
    ))
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode("ascii")


def _access_token_lifetime_seconds() -> int:
    configured = getattr(get_settings().security, "jwt_expire_minutes", ACCESS_TOKEN_EXPIRE_MINUTES)
    minutes = ACCESS_TOKEN_EXPIRE_MINUTES
    if isinstance(configured, (int, float)) and math.isfinite(configured):
        minutes = max(minutes, configured)
    return int(minutes * 60)


async def revoke_session(session_id: str) -> None:
    """Revoke every token of one login session (access and refresh)."""
    if session_id:
        await blacklist_token(
            f"{SESSION_REVOCATION_PREFIX}{session_id}",
            expires_in=TOKEN_BLACKLIST_TTL + JWT_CLOCK_SKEW,
        )


async def revoke_credential_fingerprint(fingerprint: str | None) -> None:
    """Revoke every access token carrying ``fingerprint``.

    Refresh tokens are checked against the database instead, so the entry only
    has to outlive access tokens issued before the change.
    """
    if fingerprint:
        await blacklist_token(
            f"{CREDENTIAL_REVOCATION_PREFIX}{fingerprint}",
            expires_in=_access_token_lifetime_seconds() + JWT_CLOCK_SKEW + 60,
        )


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
    sid: str | None = None  # login session id (shared with the refresh token)
    cfp: str | None = None  # credential fingerprint (see credential_fingerprint)


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


def create_access_token(
    sub: str,
    roles: list[str],
    expires_minutes: int | None = None,
    *,
    session_id: str | None = None,
    fingerprint: str | None = None,
) -> str:
    """
    Create a JWT access token with normalized claims.

    Args:
        sub: Subject (username or user identifier) - required
        roles: List of user roles for RBAC
        expires_minutes: Token expiration in minutes (default from config)
        session_id: login session id, added as the ``sid`` claim
        fingerprint: credential fingerprint, added as the ``cfp`` claim

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
    if session_id:
        claims["sid"] = session_id
    if fingerprint:
        claims["cfp"] = fingerprint

    try:
        encoded_jwt = jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    except Exception as e:
        raise ValueError(f"Failed to create access token: {str(e)}")


# Refresh token configuration
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Refresh tokens last 7 days
REFRESH_TOKEN_TYPE = "refresh"


def create_refresh_token(
    sub: str,
    roles: list[str],
    expires_days: int | None = None,
    *,
    session_id: str | None = None,
    fingerprint: str | None = None,
) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        sub: Subject (username or user identifier) - required
        roles: List of user roles for RBAC
        expires_days: Token expiration in days (default 7)
        session_id: login session id, added as the ``sid`` claim
        fingerprint: credential fingerprint, added as the ``cfp`` claim

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
    if session_id:
        claims["sid"] = session_id
    if fingerprint:
        claims["cfp"] = fingerprint

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


def decode_token_for_revocation(token: str) -> dict | None:
    """Return the claims of an access or refresh token for revocation only.

    Verifies signature, issuer and audience but not expiry, so logout can
    still revoke the session of an expired access token. Returns None when the
    token does not verify. Never use this to authenticate a request.
    """
    secret = _jwt_secret()
    if not secret or not isinstance(token, str) or not token:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": False,
                "verify_iss": True,
                "verify_aud": True,
            },
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except (JWTError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("token_type") not in (None, "access", REFRESH_TOKEN_TYPE):
        return None
    return payload


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
            # ensures a stolen token can be revoked.  Audit 2026-10-05:
            # the same lookup covers the token's login session (ended by
            # logout) and its credential fingerprint (revoked by a password
            # change or deactivation).
            try:
                if await is_token_blacklisted(
                    claims.jti, session_id=claims.sid, fingerprint=claims.cfp,
                ):
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
            # A dedicated observer token must not inherit permission from
            # legacy routes that require authentication but no trading role.
            # Enforce its scope centrally before any route receives a user.
            if "paper_monitor" in claims.roles:
                monitor_scope = {
                    ("GET", "/api/v1/paper-monitor/organism/status"),
                    ("GET", "/api/v1/paper-monitor/deploy"),
                    ("GET", "/api/v1/paper-monitor/data-integrity"),
                    ("GET", "/api/v1/paper-monitor/edge"),
                    ("GET", "/api/v1/auth/me"),
                    ("POST", "/api/v1/auth/logout"),
                }
                if (request.method, request.url.path) not in monitor_scope:
                    raise HTTPException(status_code=403, detail="paper_monitor_scope")
            return AuthenticatedUser(
                username=claims.sub, roles=claims.roles, token_id=claims.jti
            )
        except HTTPException as e:
            if e.detail == "paper_monitor_scope":
                raise  # Do not fall back to a different authentication method.
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
