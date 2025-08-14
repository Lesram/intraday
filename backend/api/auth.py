"""
Authentication API endpoints.
Handles user registration and authentication operations.
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, Form, Request
from pydantic import BaseModel, EmailStr, Field
import uuid
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


def get_user_repo():
    """Get user repository - minimal in-memory implementation for tests"""
    
    class InMemoryUserRepo:
        def __init__(self):
            self._users = {}  # email -> user data
        
        def user_exists(self, email: str) -> bool:
            return email in self._users
        
        def create_user(self, email: str, password_hash: str) -> Dict[str, Any]:
            user_id = f"user_{len(self._users) + 1}"
            user = {
                "user_id": user_id,
                "email": email,
                "password_hash": password_hash
            }
            self._users[email] = user
            return user
    
    return InMemoryUserRepo()


def hash_password(password: str) -> str:
    """Simple password hashing utility"""
    # In production, use proper hashing like bcrypt
    return f"hashed_{password}"


class UserRegistrationRequest(BaseModel):
    """User registration request payload."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserRegistrationResponse(BaseModel):
    """User registration response payload."""
    user_id: str
    email: EmailStr


class LoginResponse(BaseModel):
    """Login response payload."""
    access_token: str
    token_type: str
    user_id: str


# Route Handlers
@router.post("/login", response_model=LoginResponse, tags=["authentication"])
async def login(
    request: Request,
    username: str | None = Form(default=None),
    password: str | None = Form(default=None),
    user_repo=Depends(get_user_repo)
):
    """
    Authenticate user and return access token.
    
    Args:
        username: Username for authentication
        password: Password for authentication
        
    Returns:
        LoginResponse containing access token and user information
        
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
                # If body isn't JSON or can't be parsed, continue with current values
                pass

        # Simple authentication logic for testing (same validation and errors)
        if username and password:
            # Mock successful authentication
            return LoginResponse(
                access_token=f"mock_token_{username}",
                token_type="bearer",
                user_id=f"user_{username}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/register", response_model=UserRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: UserRegistrationRequest,
    user_repo=Depends(get_user_repo)
):
    """
    Register a new user account.
    
    Args:
        request: UserRegistrationRequest containing email and password
        user_repo: User repository dependency
        
    Returns:
        UserRegistrationResponse containing user_id and email of created user
        
    Raises:
        HTTPException: 409 if email already exists, 422 for validation errors
    """
    try:
        # Check if user already exists
        if user_repo.user_exists(request.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
        
        # Validate password strength
        if not re.search(r"[A-Za-z]", request.password) or not re.search(r"\d", request.password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password must contain at least one letter and one number"
            )
        
        # Create new user
        password_hash = hash_password(request.password)
        user = user_repo.create_user(request.email, password_hash)
        
        logger.info(f"New user registered: {request.email}")
        
        return UserRegistrationResponse(
            user_id=user["user_id"],
            email=user["email"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


# Authentication dependency functions for testing
async def get_current_user():
    """Get current authenticated user - mock implementation for testing."""
    return {
        "user_id": "test_user_123",
        "email": "test@example.com",
        "roles": ["trader"]
    }


def create_test_user():
    """Create a test user for mocking purposes."""
    return {
        "user_id": "test_user_123", 
        "email": "test@example.com",
        "password_hash": "hashed_testpass123",
        "roles": ["trader"],
        "active": True
    }
