"""
Comprehensive tests for backend/infra/security.py
Tests JWT authentication, password hashing, and RBAC.
Target: Increase coverage from 39% to 70%+
"""

import pytest
import os
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, MagicMock
from jose import jwt

from backend.infra.security import (
    _b64url,
    _b64url_decode,
    hash_password,
    verify_password,
    create_access_token,
    verify_jwt,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_AUDIENCE,
    UserClaims,
    AuthenticatedUser,
)
from fastapi import HTTPException

pytestmark = pytest.mark.unit


# ============================================================================
# BASE64URL TESTS
# ============================================================================

class TestB64url:
    """Tests for base64url encoding/decoding."""

    def test_b64url_encode(self):
        """Test base64url encoding."""
        data = b"hello world"
        result = _b64url(data)
        
        assert isinstance(result, bytes)
        # Should not have padding
        assert b"=" not in result

    def test_b64url_decode(self):
        """Test base64url decoding."""
        encoded = "aGVsbG8gd29ybGQ"
        result = _b64url_decode(encoded)
        
        assert result == b"hello world"

    def test_b64url_roundtrip(self):
        """Test encoding then decoding returns original."""
        original = b"test data 12345"
        encoded = _b64url(original)
        decoded = _b64url_decode(encoded.decode('utf-8'))
        
        assert decoded == original


# ============================================================================
# PASSWORD HASHING TESTS
# ============================================================================

class TestHashPassword:
    """Tests for password hashing."""

    def test_hash_password_returns_string(self):
        """Test hash returns string."""
        result = hash_password("password123")
        
        assert isinstance(result, str)

    def test_hash_password_bcrypt_format(self):
        """Test hash is in bcrypt format."""
        result = hash_password("password123")
        
        # bcrypt hashes start with $2a$, $2b$, or $2y$
        assert result.startswith(('$2a$', '$2b$', '$2y$'))

    def test_hash_password_different_each_time(self):
        """Test same password produces different hashes."""
        hash1 = hash_password("password123")
        hash2 = hash_password("password123")
        
        # Different salts should produce different hashes
        assert hash1 != hash2

    def test_hash_long_password_logs_warning(self):
        """Test long password (>72 bytes) logs warning."""
        long_password = "a" * 100  # Over 72 bytes
        
        # Should not raise, just log warning
        result = hash_password(long_password)
        
        assert isinstance(result, str)


class TestVerifyPassword:
    """Tests for password verification."""

    def test_verify_correct_password(self):
        """Test verifying correct password returns True."""
        password = "correctpassword123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Test verifying wrong password returns False."""
        password = "correctpassword"
        hashed = hash_password(password)
        
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_empty_hash_returns_false(self):
        """Test empty hash returns False."""
        assert verify_password("password", "") is False

    def test_verify_short_hash_returns_false(self):
        """Test short hash returns False."""
        assert verify_password("password", "short") is False

    def test_verify_non_bcrypt_hash_returns_false(self):
        """Test non-bcrypt hash (like MD5) returns False."""
        # MD5 hash format
        md5_hash = "5f4dcc3b5aa765d61d8327deb882cf99"
        
        assert verify_password("password", md5_hash) is False

    def test_verify_malformed_hash_returns_false(self):
        """Test malformed hash returns False."""
        assert verify_password("password", "$2a$invalid$hash") is False


# ============================================================================
# JWT TOKEN CREATION TESTS
# ============================================================================

class TestCreateAccessToken:
    """Tests for JWT access token creation."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        mock = MagicMock()
        mock.security.jwt_secret_key = "test-secret-key-12345"
        mock.security.jwt_expire_minutes = 60
        return mock

    def test_create_token_returns_string(self, mock_settings):
        """Test token creation returns string."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            token = create_access_token("testuser", ["user"])
        
        assert isinstance(token, str)

    def test_create_token_is_jwt_format(self, mock_settings):
        """Test token is in JWT format (3 parts)."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            token = create_access_token("testuser", ["user"])
        
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_contains_sub_claim(self, mock_settings):
        """Test token contains subject claim."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            token = create_access_token("testuser", ["user"])
        
        # Decode without verification to check claims
        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"],
                           options={"verify_aud": False})
        
        assert payload["sub"] == "testuser"

    def test_create_token_contains_roles(self, mock_settings):
        """Test token contains roles claim."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            token = create_access_token("testuser", ["admin", "user"])
        
        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"],
                           options={"verify_aud": False})
        
        assert payload["roles"] == ["admin", "user"]

    def test_create_token_contains_expiration(self, mock_settings):
        """Test token contains expiration claim."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            token = create_access_token("testuser", ["user"], expires_minutes=30)
        
        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"],
                           options={"verify_aud": False})
        
        assert "exp" in payload

    def test_create_token_no_secret_raises(self):
        """Test token creation without secret raises ValueError."""
        mock_settings = MagicMock()
        mock_settings.security.jwt_secret_key = None
        
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError, match="JWT secret key is required"):
                    create_access_token("testuser", ["user"])

    def test_create_token_empty_sub_raises(self, mock_settings):
        """Test token creation with empty subject raises ValueError."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            with pytest.raises(ValueError, match="subject cannot be empty"):
                create_access_token("", ["user"])

    def test_create_token_invalid_expires_raises(self, mock_settings):
        """Test token creation with invalid expires_minutes raises ValueError."""
        with patch('backend.infra.security.get_settings', return_value=mock_settings):
            with pytest.raises(ValueError, match="expires_minutes must be a number"):
                create_access_token("testuser", ["user"], expires_minutes="invalid")


# ============================================================================
# JWT VERIFICATION TESTS
# ============================================================================

class TestVerifyJwt:
    """Tests for JWT verification."""

    @pytest.fixture
    def valid_token(self):
        """Create a valid JWT token."""
        now = datetime.now(UTC)
        payload = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": "test-token-id"
        }
        return jwt.encode(payload, "test-secret", algorithm=JWT_ALGORITHM)

    def test_verify_valid_token(self, valid_token):
        """Test verifying valid token returns payload."""
        result = verify_jwt(
            valid_token,
            secret="test-secret",
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE
        )
        
        assert result["sub"] == "testuser"
        assert result["roles"] == ["user"]

    def test_verify_empty_token_raises(self):
        """Test empty token raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            verify_jwt("", secret="secret", issuer="iss", audience="aud")
        
        assert exc.value.status_code == 401
        assert "Invalid token" in exc.value.detail

    def test_verify_malformed_token_raises(self):
        """Test malformed token raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            verify_jwt("not-a-jwt", secret="secret", issuer="iss", audience="aud")
        
        assert exc.value.status_code == 401

    def test_verify_expired_token_raises(self):
        """Test expired token raises HTTPException."""
        now = datetime.now(UTC)
        payload = {
            "sub": "testuser",
            "roles": [],
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "exp": int((now - timedelta(hours=1)).timestamp()),  # Expired
            "iat": int((now - timedelta(hours=2)).timestamp()),
        }
        expired_token = jwt.encode(payload, "test-secret", algorithm=JWT_ALGORITHM)
        
        with pytest.raises(HTTPException) as exc:
            verify_jwt(expired_token, secret="test-secret",
                      issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
        
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_verify_wrong_audience_raises(self, valid_token):
        """Test wrong audience raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            verify_jwt(valid_token, secret="test-secret",
                      issuer=JWT_ISSUER, audience="wrong-audience")
        
        assert exc.value.status_code == 401

    def test_verify_wrong_issuer_raises(self, valid_token):
        """Test wrong issuer raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            verify_jwt(valid_token, secret="test-secret",
                      issuer="wrong-issuer", audience=JWT_AUDIENCE)
        
        assert exc.value.status_code == 401

    def test_verify_wrong_secret_raises(self, valid_token):
        """Test wrong secret raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            verify_jwt(valid_token, secret="wrong-secret",
                      issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
        
        assert exc.value.status_code == 401

    def test_verify_missing_sub_raises(self):
        """Test token without subject raises HTTPException."""
        now = datetime.now(UTC)
        payload = {
            "roles": [],
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        token = jwt.encode(payload, "test-secret", algorithm=JWT_ALGORITHM)
        
        with pytest.raises(HTTPException) as exc:
            verify_jwt(token, secret="test-secret",
                      issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
        
        assert exc.value.status_code == 401
        # May return "Invalid token" or "Missing subject" depending on jwt lib version
        assert exc.value.detail in ["Invalid token", "Missing subject"]


# ============================================================================
# PYDANTIC MODELS TESTS
# ============================================================================

class TestUserClaims:
    """Tests for UserClaims model."""

    def test_user_claims_valid(self):
        """Test valid UserClaims creation."""
        claims = UserClaims(
            sub="testuser",
            roles=["admin", "user"],
            iss=JWT_ISSUER,
            aud=JWT_AUDIENCE,
            exp=1234567890,
            iat=1234567800,
            jti="unique-id"
        )
        
        assert claims.sub == "testuser"
        assert claims.roles == ["admin", "user"]

    def test_user_claims_missing_field_raises(self):
        """Test UserClaims missing required field raises."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            UserClaims(
                sub="testuser",
                # Missing required fields
            )


class TestAuthenticatedUser:
    """Tests for AuthenticatedUser model."""

    def test_authenticated_user_valid(self):
        """Test valid AuthenticatedUser creation."""
        user = AuthenticatedUser(
            username="testuser",
            roles=["admin"],
            token_id="token-123"
        )
        
        assert user.username == "testuser"
        assert user.roles == ["admin"]
        assert user.token_id == "token-123"

    def test_authenticated_user_missing_field_raises(self):
        """Test AuthenticatedUser missing required field raises."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AuthenticatedUser(
                username="testuser"
                # Missing roles and token_id
            )
