"""
Comprehensive tests for backend/api/test_utils/auth.py

Tests for test authentication utilities.
"""

import pytest
import jwt
from datetime import datetime, timedelta, UTC
from unittest.mock import patch, MagicMock


class TestGetTestToken:
    """Tests for get_test_token function."""

    def test_get_test_token_returns_string(self):
        """get_test_token returns a string JWT token."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token()
        
        assert isinstance(token, str)
        assert len(token) > 0

    def test_get_test_token_is_valid_jwt(self):
        """Token returned is a valid JWT."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token()
        
        # Should have 3 parts separated by dots
        parts = token.split(".")
        assert len(parts) == 3

    def test_get_test_token_with_custom_username(self):
        """Token can use custom username."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token(username="admin")
        
        # Decode without verification to check payload
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == "admin"
        assert payload["username"] == "admin"

    def test_get_test_token_with_custom_expiry(self):
        """Token can have custom expiration."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token(expires_minutes=120)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Check expiration is roughly 2 hours from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=UTC)
        now = datetime.now(UTC)
        diff = exp_time - now
        
        assert 119 <= diff.total_seconds() / 60 <= 121

    def test_get_test_token_with_additional_claims(self):
        """Token can include additional claims."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token(custom_claim="custom_value", role="admin")
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["custom_claim"] == "custom_value"
        assert payload["role"] == "admin"

    def test_get_test_token_contains_standard_claims(self):
        """Token contains standard JWT claims."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token()
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert "sub" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert "nbf" in payload

    def test_get_test_token_contains_app_claims(self):
        """Token contains application-specific claims."""
        from backend.api.test_utils.auth import get_test_token
        
        token = get_test_token()
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert "user_id" in payload
        assert "roles" in payload
        assert "permissions" in payload

    def test_get_test_token_fallback_when_settings_fail(self):
        """Token generation works with fallback when settings unavailable."""
        from backend.api.test_utils.auth import get_test_token
        
        with patch("backend.api.test_utils.auth.get_settings", side_effect=Exception("Settings error")):
            token = get_test_token()
        
        # Should still return a valid token using fallback
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3


class TestGetTestHeaders:
    """Tests for get_test_headers function."""

    def test_get_test_headers_returns_dict(self):
        """get_test_headers returns a dictionary."""
        from backend.api.test_utils.auth import get_test_headers
        
        headers = get_test_headers()
        
        assert isinstance(headers, dict)

    def test_get_test_headers_contains_authorization(self):
        """Headers contain Authorization header."""
        from backend.api.test_utils.auth import get_test_headers
        
        headers = get_test_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_get_test_headers_contains_content_type(self):
        """Headers contain Content-Type header."""
        from backend.api.test_utils.auth import get_test_headers
        
        headers = get_test_headers()
        
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"

    def test_get_test_headers_with_custom_username(self):
        """Headers can use custom username."""
        from backend.api.test_utils.auth import get_test_headers
        
        headers = get_test_headers(username="custom_user")
        
        # Extract token and verify username
        token = headers["Authorization"].replace("Bearer ", "")
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["username"] == "custom_user"


class TestCreateTestUser:
    """Tests for create_test_user function."""

    def test_create_test_user_returns_dict(self):
        """create_test_user returns a dictionary."""
        from backend.api.test_utils.auth import create_test_user
        
        user = create_test_user()
        
        assert isinstance(user, dict)

    def test_create_test_user_contains_required_fields(self):
        """User dict contains required fields."""
        from backend.api.test_utils.auth import create_test_user
        
        user = create_test_user()
        
        assert "id" in user
        assert "username" in user
        assert "email" in user
        assert "roles" in user
        assert "permissions" in user
        assert "is_active" in user
        assert "created_at" in user

    def test_create_test_user_default_username(self):
        """Default username is testuser."""
        from backend.api.test_utils.auth import create_test_user
        
        user = create_test_user()
        
        assert user["username"] == "testuser"
        assert "testuser" in user["email"]

    def test_create_test_user_custom_username(self):
        """Custom username can be specified."""
        from backend.api.test_utils.auth import create_test_user
        
        user = create_test_user(username="admin")
        
        assert user["username"] == "admin"
        assert user["id"] == "test_user_admin"
        assert user["email"] == "admin@test.com"

    def test_create_test_user_is_active(self):
        """Test user is active by default."""
        from backend.api.test_utils.auth import create_test_user
        
        user = create_test_user()
        
        assert user["is_active"] is True
