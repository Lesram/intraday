"""
Test authentication utilities for generating JWT tokens.
Provides get_test_token() for smoke tests and endpoint validation.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.config import get_settings


def get_test_token(username: str = "testuser", expires_minutes: int = 60, **claims) -> str:
    """
    Create or retrieve a test user and return a short-lived JWT string.

    Uses existing JWT settings and the same signing key as the app.
    Perfect for smoke tests and endpoint validation.

    Args:
        username: Username for the test token (default: "testuser")
        expires_minutes: Token expiration in minutes (default: 60)
        **claims: Additional JWT claims to include

    Returns:
        JWT token string ready for Authorization: Bearer {token}

    Example:
        >>> token = get_test_token()
        >>> headers = {"Authorization": f"Bearer {token}"}
        >>> response = client.get("/api/v1/signals", headers=headers)
    """
    try:
        settings = get_settings()

        # Get JWT configuration from settings
        if hasattr(settings, 'security'):
            secret_key = getattr(settings.security, 'jwt_secret', 'test-jwt-secret')
            algorithm = getattr(settings.security, 'jwt_algorithm', 'HS256')
        else:
            # Fallback for test environments
            secret_key = 'test-jwt-secret'
            algorithm = 'HS256'

    except Exception:
        # Fallback configuration if settings unavailable
        secret_key = 'test-jwt-secret'
        algorithm = 'HS256'

    # Create JWT payload with standard claims
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes)

    payload = {
        # Standard JWT claims
        "sub": username,  # Subject (user identifier)
        "iat": int(now.timestamp()),  # Issued at
        "exp": int(expire.timestamp()),  # Expiration
        "nbf": int(now.timestamp()),  # Not before

        # Application-specific claims
        "username": username,
        "user_id": f"test_user_{username}",
        "roles": ["user", "trader"],  # Standard test roles
        "permissions": ["read", "write", "trade"],

        # Add any additional claims
        **claims
    }

    # Generate and return JWT token
    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return token


def get_test_headers(username: str = "testuser", **token_kwargs) -> dict[str, str]:
    """
    Convenience function to get authorization headers with test token.

    Args:
        username: Username for the test token
        **token_kwargs: Additional arguments passed to get_test_token()

    Returns:
        Dictionary with Authorization header ready for requests

    Example:
        >>> headers = get_test_headers()
        >>> response = client.get("/api/v1/orders", headers=headers)
    """
    token = get_test_token(username=username, **token_kwargs)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def create_test_user(username: str = "testuser") -> dict[str, Any]:
    """
    Create a test user object for use in tests.

    Returns user data structure that matches what get_authenticated_user() expects.
    """
    return {
        "id": f"test_user_{username}",
        "username": username,
        "email": f"{username}@test.com",
        "roles": ["user", "trader"],
        "permissions": ["read", "write", "trade"],
        "is_active": True,
        "created_at": datetime.now(UTC).isoformat()
    }


# Quick test to verify token generation works
if __name__ == "__main__":
    try:
        token = get_test_token()
        print("✅ Test token generated successfully")
        print(f"Token: {token[:50]}...")

        headers = get_test_headers()
        print("✅ Test headers generated successfully")
        print(f"Headers: {headers}")

    except Exception as e:
        print(f"❌ Token generation failed: {e}")
