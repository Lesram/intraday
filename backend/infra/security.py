"""
Security utilities for JWT authentication, password hashing, and RBAC.
Provides FastAPI dependencies for authentication and authorization.
"""

from datetime import UTC, datetime, timedelta
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.config import get_settings
from backend.infra.security_hardening import jwt_verifier


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

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Previously hashed password

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    subject: str, roles: list[str], expires_minutes: int | None = None
) -> str:
    """
    Create a JWT access token with user claims.

    Args:
        subject: Username or user identifier
        roles: List of user roles for RBAC
        expires_minutes: Token expiration in minutes (default from config)

    Returns:
        Encoded JWT token string

    Raises:
        ValueError: If token creation fails
    """
    settings = get_settings()

    if expires_minutes is None:
        expires_minutes = settings.security.jwt_expire_minutes

    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes)

    claims = UserClaims(
        sub=subject,
        roles=roles,
        iss=settings.security.jwt_issuer,
        aud=settings.security.jwt_audience,
        exp=int(expire.timestamp()),
        iat=int(now.timestamp()),
        jti=secrets.token_urlsafe(16),  # Unique token ID
    )

    try:
        encoded_jwt = jwt_verifier.encode(
            claims.model_dump(),
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm,
        )
        return encoded_jwt
    except Exception as e:
        raise ValueError(f"Failed to create access token: {str(e)}")


def verify_token(token: str) -> UserClaims:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded user claims

    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    settings = get_settings()

    try:
        payload = jwt_verifier.decode(
            token,
            settings.security.jwt_secret_key,
            algorithms=[settings.security.jwt_algorithm],
            issuer=settings.security.jwt_issuer,
            audience=settings.security.jwt_audience,
        )

        # Validate required claims
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )

        return UserClaims(**payload)

    except jwt_verifier.JWTError as e:
        if "expired" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )
        elif "issuer" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer"
            )
        elif "audience" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


def verify_api_key(api_key: str) -> bool:
    """
    Verify an API key using constant-time comparison.

    Args:
        api_key: API key to verify

    Returns:
        True if API key is valid, False otherwise
    """
    settings = get_settings()

    if not settings.api_keys:
        return False

    # Use constant-time comparison to prevent timing attacks
    return any(
        secrets.compare_digest(api_key, valid_key) for valid_key in settings.api_keys
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser | None:
    """
    FastAPI dependency to extract current user from JWT token or API key.

    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials

    Returns:
        Authenticated user or None if not authenticated

    Raises:
        HTTPException: If token is invalid
    """
    settings = get_settings()

    # In dev mode, allow bypass
    if settings.app.dev_mode:
        # Check for dev bypass header
        if request.headers.get("X-Dev-Bypass") == "true":
            return AuthenticatedUser(
                username="dev-user", roles=["admin", "trader"], token_id="dev-bypass"
            )

    # Try API key authentication first (X-API-Key header)
    api_key = request.headers.get("X-API-Key")
    if api_key and verify_api_key(api_key):
        return AuthenticatedUser(
            username="api-client",
            roles=["trader", "api"],  # API keys get trader permissions
            token_id="api-key",
        )

    # Try JWT authentication
    if credentials and credentials.credentials:
        claims = verify_token(credentials.credentials)
        return AuthenticatedUser(
            username=claims.sub, roles=claims.roles, token_id=claims.jti
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
        FastAPI dependency function

    Usage:
        @app.get("/admin-only")
        async def admin_endpoint(user: AuthenticatedUser = Depends(require_roles("admin"))):
            pass
    """

    async def check_roles(
        current_user: AuthenticatedUser = Depends(get_authenticated_user),
    ) -> AuthenticatedUser:
        user_roles = set(current_user.roles)
        required_roles_set = set(required_roles)

        if not required_roles_set.intersection(user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
            )

        return current_user

    return check_roles


# Common role-based dependencies
require_admin = require_roles("admin")
require_trader = require_roles("trader", "admin")  # Admin can also trade
require_api = require_roles("api", "admin")  # API access or admin
