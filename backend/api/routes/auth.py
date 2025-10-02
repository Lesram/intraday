"""
Authentication routes for login and token verification.
Provides POST /auth/login and GET /auth/verify endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.infra.security import (
    AuthenticatedUser,
    create_access_token,
    get_authenticated_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with access token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenClaims(BaseModel):
    """Token verification response."""
    sub: str
    roles: list[str]
    iss: str
    aud: str
    exp: int
    iat: int


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Public endpoint for user authentication.
    
    Verifies username/password against database and returns JWT token.
    For demo/staging, accepts hardcoded admin credentials.
    """
    # TODO: Replace with proper database user lookup
    # For now, use hardcoded staging credentials
    if request.username == "admin" and request.password == "admin123":
        # Create access token for admin user
        token = create_access_token(
            sub=request.username,
            roles=["admin", "trader"],
            expires_minutes=60
        )
        
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            expires_in=3600  # 60 minutes in seconds
        )
    
    # Invalid credentials
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/verify", response_model=TokenClaims)
async def verify_token(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> TokenClaims:
    """
    Protected endpoint that returns current user's token claims.
    
    Useful for smoke tests and token validation.
    """
    return TokenClaims(
        sub=current_user.username,
        roles=current_user.roles,
        iss="algotrading-platform",
        aud="algotrading-api", 
        exp=0,  # Would need to extract from token
        iat=0,  # Would need to extract from token
    )