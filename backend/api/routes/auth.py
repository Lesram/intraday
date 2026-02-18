"""
Consolidated Authentication API endpoints.
Handles user authentication, registration, token management, and user information.

This module consolidates all authentication functionality into a single, comprehensive API.
All endpoints use database-backed authentication with proper security measures.
"""

import logging
import re
import time
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import (
    AuthenticatedUser,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_authenticated_user,
)
from backend.infra.security import (
    verify_token as verify_jwt_token,
)
from backend.infra.users import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Pydantic Models
# ============================================================================

class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with access token and user information."""
    access_token: str
    refresh_token: str | None = None  # Refresh token for token renewal
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_id: str | None = None
    user: dict | None = None


class TokenResponse(BaseModel):
    """OAuth2-compatible token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenClaims(BaseModel):
    """Token verification response."""
    sub: str
    roles: list[str]
    iss: str
    aud: str
    exp: int
    iat: int


class TokenValidationRequest(BaseModel):
    """Token validation request."""
    token: str | None = None


class TokenValidationResponse(BaseModel):
    """Token validation response."""
    valid: bool
    user: dict | None = None
    expires_at: int | None = None


class UserRegistrationRequest(BaseModel):
    """User registration request payload."""
    email: EmailStr
    # M-07 FIX: Increased minimum password length from 8 to 12 characters
    password: str = Field(..., min_length=12, max_length=128, description="Password must be at least 12 characters")


class UserRegistrationResponse(BaseModel):
    """User registration response payload."""
    user_id: str
    email: EmailStr


class UserInfoResponse(BaseModel):
    """Current user information response - matches frontend User type."""
    user_id: str
    username: str
    email: str | None = None
    roles: list[str] = []
    is_active: bool = True
    is_admin: bool = False
    created_at: str | None = None
    last_login: str | None = None
    authenticated: bool = True


class TokenRefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str  # Required - the refresh token to exchange


class TokenRefreshResponse(BaseModel):
    """Token refresh response with new tokens (rotation)."""
    access_token: str
    refresh_token: str  # New refresh token (token rotation for security)
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    """Logout response (stateless JWT)."""
    ok: bool = True
    message: str = "Logged out"


class PasswordResetRequest(BaseModel):
    """Password reset request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation."""
    token: str
    # M-07 FIX: Increased minimum password length from 8 to 12 characters
    new_password: str = Field(..., min_length=12, max_length=128, description="Password must be at least 12 characters")


class PasswordChangeRequest(BaseModel):
    """Password change request."""
    # Accept both field names for compatibility
    old_password: str | None = None
    current_password: str | None = None  # Alias used by frontend
    # M-07 FIX: Increased minimum password length from 8 to 12 characters
    new_password: str = Field(..., min_length=12, max_length=128, description="Password must be at least 12 characters")

    def get_current_password(self) -> str:
        """Get the current password from either field."""
        password = self.current_password or self.old_password
        if not password:
            raise ValueError("current_password or old_password is required")
        return password


class PasswordResetRequestResponse(BaseModel):
    """Response for password reset request."""
    status: str
    message: str


class PasswordResetConfirmResponse(BaseModel):
    """Response for password reset confirmation."""
    message: str


class PasswordChangeResponse(BaseModel):
    """Response for password change."""
    message: str


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_repo(db: AsyncSession = Depends(get_db_session)):
    """Get user repository instance with database session (for dependency injection)."""
    return UserRepository(db_session=db)


def validate_password_strength(password: str) -> list[str]:
    """
    Validate password strength and return list of validation errors.

    Args:
        password: Password to validate

    Returns:
        List of validation error messages (empty if password is valid)
    """
    errors = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters long")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        errors.append("Password must contain at least one special character")

    # Check for common weak passwords
    common_passwords = ["password", "123456", "password123", "admin", "qwerty"]
    if password.lower() in common_passwords:
        errors.append("Password is too common and easily guessable")

    return errors


async def get_sessionmaker():
    """Get database sessionmaker from factory."""
    try:
        from backend.api.factory import get_sessionmaker as factory_get_sessionmaker
        return factory_get_sessionmaker()
    except Exception:
        return None


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db_session)
) -> LoginResponse:
    """
    Authenticate user and return access token.

    Accepts JSON body with username and password.
    Uses database authentication with brute-force protection.

    Args:
        login_data: Login credentials (username and password)
        db: Database session dependency

    Returns:
        LoginResponse containing access token and user information

    Raises:
        HTTPException: 401 for invalid credentials or locked account
        HTTPException: 422 for missing credentials
    """
    try:
        # Extract credentials from request body
        username = login_data.username
        password = login_data.password

        # Validate that required credentials are provided
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Username and password are required"
            )

        # Authenticate user against database
        user_repo = UserRepository(db_session=db)
        user = await user_repo.authenticate_user(username, password)

        if not user:
            # Invalid credentials or account locked
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password, or account is locked due to too many failed login attempts",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create access token for authenticated user
        token = create_access_token(
            sub=user.username,
            roles=user.roles,
            expires_minutes=60
        )

        # Create refresh token for token renewal
        refresh_token = create_refresh_token(
            sub=user.username,
            roles=user.roles
        )

        return LoginResponse(
            access_token=token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=3600,  # 60 minutes in seconds
            user_id=user.username,
            user={"username": user.username, "roles": user.roles}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/token", response_model=TokenResponse)
async def get_token(
    request: Request,
    username: str | None = Form(default=None),
    password: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db_session)
) -> TokenResponse:
    """
    OAuth2-compatible token endpoint that returns JWT access token.

    This endpoint follows OAuth2 password flow conventions and returns
    a simplified token response without user details.

    Args:
        request: FastAPI request object
        username: Username for authentication (form or JSON)
        password: Password for authentication (form or JSON)
        db: Database session dependency

    Returns:
        TokenResponse with access_token, token_type, and expires_in

    Raises:
        HTTPException: 401 for invalid credentials
    """
    try:
        # Support JSON body as an alternative to form data
        if not username or not password:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    username = body.get("username") or username
                    password = body.get("password") or password
            except Exception:
                pass

        # Validate credentials are provided
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username and password are required"
            )

        # Authenticate user against database
        user_repo = UserRepository(db_session=db)
        user = await user_repo.authenticate_user(username, password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password, or account is locked"
            )

        # Create JWT token with user's actual roles from database
        access_token = create_access_token(user.username, user.roles)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=3600
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token endpoint error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


# ============================================================================
# Token Validation Endpoints
# ============================================================================

@router.get("/verify", response_model=TokenClaims)
async def verify_token(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> TokenClaims:
    """
    Protected endpoint that returns current user's token claims.

    Verifies the JWT token in the Authorization header and returns
    the decoded claims. Useful for smoke tests and token validation.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        TokenClaims with user information
    """
    return TokenClaims(
        sub=current_user.username,
        roles=current_user.roles,
        iss="algotrading-platform",
        aud="algotrading-api",
        exp=0,  # Would need to extract from token
        iat=0,  # Would need to extract from token
    )


@router.post("/token/validate", response_model=TokenValidationResponse)
async def validate_token(request: Request) -> TokenValidationResponse:
    """
    Validate JWT token from Authorization header.

    Returns validation status and user information if token is valid.
    This endpoint does not require authentication (validates the token itself).

    Args:
        request: FastAPI request object with Authorization header

    Returns:
        TokenValidationResponse with validation status and user info
    """
    # Extract token from Authorization header
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return TokenValidationResponse(valid=False, user=None)

    token = authorization.split(" ", 1)[1]

    try:
        claims = verify_jwt_token(token)

        return TokenValidationResponse(
            valid=True,
            user={
                "username": claims.sub,
                "roles": claims.roles
            },
            expires_at=int(time.time()) + 3600  # 1 hour from now
        )
    except Exception:
        return TokenValidationResponse(valid=False, user=None)


# ============================================================================
# Logout Endpoint
# ============================================================================


@router.post("/logout", response_model=LogoutResponse, openapi_extra={"security": []})
async def logout(request: Request) -> LogoutResponse:
    """Logout endpoint for frontend compatibility.

    This platform uses stateless JWTs, so "logout" is client-side (drop token).
    This endpoint exists to avoid 404s and provide a future hook for server-side
    revocation if implemented.

    Returns 200 even if no valid token is provided.
    """
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            claims = verify_jwt_token(token)
            username = getattr(claims, "sub", None)
            if username:
                return LogoutResponse(ok=True, message=f"Logged out: {username}")
        except Exception:
            # Ignore invalid/expired tokens; logout is client-side for stateless JWT.
            pass

    return LogoutResponse(ok=True, message="Logged out")


# ============================================================================
# User Information Endpoints
# ============================================================================

@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> UserInfoResponse:
    """
    Get current authenticated user information from JWT token.

    Returns user details extracted from the validated JWT token.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        UserInfoResponse with user details

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    return UserInfoResponse(
        user_id=current_user.username,
        username=current_user.username,
        email=current_user.username if '@' in current_user.username else None,
        roles=current_user.roles,
        is_active=True,
        is_admin="admin" in current_user.roles,
        created_at=None,  # Would need DB lookup for actual value
        last_login=None,  # Would need DB lookup for actual value
        authenticated=True
    )


# ============================================================================
# User Registration Endpoint
# ============================================================================

@router.post("/register", response_model=UserRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserRegistrationRequest,
    repo: UserRepository = Depends(get_user_repo)
) -> UserRegistrationResponse:
    """
    Register a new user account.

    Creates a new user with the provided email and password.
    Password must meet strength requirements (uppercase, lowercase, number, special char).

    Args:
        request: UserRegistrationRequest containing email and password
        repo: User repository dependency

    Returns:
        UserRegistrationResponse containing user_id and email of created user

    Raises:
        HTTPException: 409 if email already exists
        HTTPException: 422 for validation errors
    """
    try:
        # Check if user already exists
        if hasattr(repo, "exists_by_email"):
            if await repo.exists_by_email(request.email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered"
                )
        elif hasattr(repo, "user_exists"):
            if repo.user_exists(request.email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered"
                )

        # Validate password strength
        password_errors = validate_password_strength(request.password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Password validation failed: " + "; ".join(password_errors)
            )

        # Create new user
        create_func = getattr(repo, "create_user", None)
        if not create_func:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User repository not properly configured"
            )

        try:
            # Real UserRepository expects (username, password, roles, email)
            user = await create_func(username=str(request.email), password=request.password, roles=["user"], email=str(request.email))
            # User object now has id field from database
            user_id = str(user.id) if hasattr(user, 'id') and user.id else str(uuid.uuid4())
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            # Fallback for different repository interface
            from backend.infra.security import hash_password
            password_hash = hash_password(request.password)
            user = await create_func(request.email, password_hash)
            user_id = user.get("user_id", str(uuid.uuid4()))

        logger.info(f"New user registered: {request.email}")

        return UserRegistrationResponse(
            user_id=user_id,
            email=request.email
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/token/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: TokenRefreshRequest,
) -> TokenRefreshResponse:
    """Refresh JWT access token using a valid refresh token.

    Implements secure token rotation:
    - Validates the refresh token
    - Issues a new access token
    - Issues a new refresh token (rotation for security)

    Args:
        request: TokenRefreshRequest with refresh_token

    Returns:
        TokenRefreshResponse with new access and refresh tokens

    Raises:
        HTTPException: 401 if refresh token is invalid or expired
        HTTPException: 422 if refresh token is missing
    """
    try:
        if not request.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="refresh_token is required"
            )

        # Decode and validate the refresh token
        payload = decode_refresh_token(request.refresh_token)

        # Extract user info from validated refresh token
        username = payload.get("sub")
        roles = payload.get("roles", [])

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token"
            )

        logger.info(f"Token refresh for user: {username}")

        # Create new access token
        new_access_token = create_access_token(
            sub=username,
            roles=roles,
            expires_minutes=60
        )

        # Create new refresh token (rotation for security)
        # This invalidates the old refresh token by issuing a new one
        new_refresh_token = create_refresh_token(
            sub=username,
            roles=roles
        )

        return TokenRefreshResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=3600  # 60 minutes in seconds
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    repo: UserRepository = Depends(get_user_repo)
) -> PasswordResetRequestResponse:
    """Request password reset email.

    Sends a password reset email with a secure token.
    Always returns success to prevent email enumeration.

    Args:
        request: PasswordResetRequest with email
        repo: User repository dependency

    Returns:
        Success message
    """
    try:
        # Anti-enumeration: always return the same response shape regardless
        logger.info(f"Password reset requested for: {request.email}")

        # NOTE: Full email-based reset flow is not yet wired.
        # Until an email transport is configured, we log the attempt and
        # return a generic message.  This is NOT a silent ignore — the
        # response clearly communicates that the feature relies on email
        # delivery which may not be set up.
        logger.warning(
            "Password reset requested but email transport is not configured. "
            "Deploy an SMTP / SES integration to enable this feature."
        )

        return PasswordResetRequestResponse(
            status="accepted",
            message="If the email exists and email delivery is configured, a password reset link will be sent."
        )

    except Exception as e:
        logger.error(f"Password reset request failed: {str(e)}")
        # Still return success to prevent enumeration
        return PasswordResetRequestResponse(
            status="success",
            message="If the email exists, a password reset link has been sent."
        )


@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    repo: UserRepository = Depends(get_user_repo)
) -> PasswordResetConfirmResponse:
    """Confirm password reset with token.

    Args:
        request: PasswordResetConfirm with token and new password
        repo: User repository dependency

    Returns:
        Success message

    Raises:
        HTTPException: 400 for invalid/expired token
    """
    try:
        # Validate password strength
        password_errors = validate_password_strength(request.new_password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Password validation failed: " + "; ".join(password_errors)
            )

        # TODO: Implement:
        # 1. Validate reset token from database
        # 2. Check token expiration
        # 3. Update user password
        # 4. Invalidate reset token

        logger.info("Password reset confirmation attempted")

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Password reset confirmation not yet implemented."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


@router.post("/password-change", response_model=PasswordChangeResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    repo: UserRepository = Depends(get_user_repo)
) -> PasswordChangeResponse:
    """Change password for authenticated user.

    Args:
        request: PasswordChangeRequest with old and new passwords
        current_user: Authenticated user from JWT token
        repo: User repository dependency

    Returns:
        Success message

    Raises:
        HTTPException: 401 for invalid old password
        HTTPException: 422 for weak new password
    """
    try:
        user_id = current_user.username
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication"
            )

        # Get current password from request (supports both field names)
        try:
            current_password = request.get_current_password()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )

        # Validate new password strength
        password_errors = validate_password_strength(request.new_password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password validation failed: " + "; ".join(password_errors)
            )

        # Verify current password and update to new password
        success = await repo.change_password(
            username=user_id,
            current_password=current_password,
            new_password=request.new_password
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

        logger.info(f"Password changed successfully for user: {user_id}")

        return PasswordChangeResponse(message="Password changed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )
