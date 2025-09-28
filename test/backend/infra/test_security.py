"""
Additional comprehensive tests for backend.infra.security module targeting remaining lines.
Tests additional functions like verify_token, get_current_user, verify_api_key, and edge cases.
"""

import pytest
import asyncio
import secrets
import json
import time
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

# Import the module under test
import backend.infra.security as security
from backend.infra.security import (
    verify_token, get_current_user, verify_api_key, 
    create_access_token, UserClaims, AuthenticatedUser,
    require_roles, check_user_roles, hash_password, _b64url, _b64url_decode
)


class TestVerifyToken:
    """Test verify_token function comprehensively."""
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_success(self, mock_jwt_verifier, mock_get_settings):
        """Test successful token verification."""
        # Lines 240-280: Test verify_token function
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.jwt_issuer = "test-issuer"
        mock_settings.security.jwt_audience = "test-audience"
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT payload
        mock_payload = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": "test-issuer",
            "aud": "test-audience",
            "exp": int(datetime.now(UTC).timestamp()) + 3600,
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "token-123"
        }
        mock_jwt_verifier.decode.return_value = mock_payload
        
        result = verify_token("valid.jwt.token")
        
        assert isinstance(result, UserClaims)
        assert result.sub == "testuser"
        assert result.roles == ["user"]
        assert result.jti == "token-123"
    
    @patch('backend.infra.security.get_settings')
    def test_verify_token_special_test_token(self, mock_get_settings):
        """Test special test token handling."""
        # Lines 250-265: Test special test token case
        
        # Mock settings for test environment
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.debug = True
        mock_settings.app.environment = "test"
        mock_settings.security = Mock()
        mock_settings.security.jwt_issuer = "test-issuer"
        mock_settings.security.jwt_audience = "test-audience"
        mock_get_settings.return_value = mock_settings
        
        result = verify_token("valid_token")
        
        assert isinstance(result, UserClaims)
        assert result.sub == "test_user"
        assert result.roles == ["trader"]
        assert result.jti == "test-token"
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_missing_subject(self, mock_jwt_verifier, mock_get_settings):
        """Test token verification with missing subject."""
        # Lines 268-273: Test missing subject validation
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Mock payload without subject
        mock_payload = {
            "roles": ["user"],
            "exp": int(datetime.now(UTC).timestamp()) + 3600
        }
        mock_jwt_verifier.decode.return_value = mock_payload
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("token.without.subject")
        
        assert exc_info.value.status_code == 401
        assert "missing subject" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_jwt_error_expired(self, mock_jwt_verifier, mock_get_settings):
        """Test JWT error handling - expired."""
        # Lines 277-287: Test JWT error handling
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT error
        mock_jwt_verifier.JWTError = Exception
        mock_jwt_verifier.decode.side_effect = mock_jwt_verifier.JWTError("Token expired")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("expired.token")
        
        assert exc_info.value.status_code == 401
        assert "Token expired" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_jwt_error_signature(self, mock_jwt_verifier, mock_get_settings):
        """Test JWT error handling - signature."""
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        mock_jwt_verifier.JWTError = Exception
        mock_jwt_verifier.decode.side_effect = mock_jwt_verifier.JWTError("Invalid signature")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.signature.token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid signature" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_jwt_error_audience(self, mock_jwt_verifier, mock_get_settings):
        """Test JWT error handling - audience."""
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        mock_jwt_verifier.JWTError = Exception
        mock_jwt_verifier.decode.side_effect = mock_jwt_verifier.JWTError("Wrong aud")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("wrong.audience.token")
        
        assert exc_info.value.status_code == 401
        assert "Wrong audience" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_jwt_error_issuer(self, mock_jwt_verifier, mock_get_settings):
        """Test JWT error handling - issuer."""
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        mock_jwt_verifier.JWTError = Exception
        mock_jwt_verifier.decode.side_effect = mock_jwt_verifier.JWTError("Wrong iss")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("wrong.issuer.token")
        
        assert exc_info.value.status_code == 401
        assert "Wrong issuer" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_jwt_error_generic(self, mock_jwt_verifier, mock_get_settings):
        """Test JWT error handling - generic."""
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        mock_jwt_verifier.JWTError = Exception
        mock_jwt_verifier.decode.side_effect = mock_jwt_verifier.JWTError("Other error")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("other.error.token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_validation_error(self, mock_jwt_verifier, mock_get_settings):
        """Test validation error handling."""
        # Lines 302-306: Test ValueError handling
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Mock validation error
        mock_jwt_verifier.decode.side_effect = ValueError("validation error occurred")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("validation.error.token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid token format" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_verify_token_generic_exception(self, mock_jwt_verifier, mock_get_settings):
        """Test generic exception handling."""
        # Lines 310-315: Test generic Exception handling
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Mock generic exception
        mock_jwt_verifier.decode.side_effect = RuntimeError("Unexpected error")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token("unexpected.error.token")
        
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail


class TestVerifyApiKey:
    """Test verify_api_key function."""
    
    @patch('backend.infra.security.get_settings')
    def test_verify_api_key_success(self, mock_get_settings):
        """Test successful API key verification."""
        # Lines 328-334: Test verify_api_key function
        
        # Mock settings with API keys
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.api_keys = ["valid-key-1", "valid-key-2"]
        mock_get_settings.return_value = mock_settings
        
        # Test valid key
        result = verify_api_key("valid-key-1")
        assert result is True
        
        result = verify_api_key("valid-key-2")
        assert result is True
    
    @patch('backend.infra.security.get_settings')
    def test_verify_api_key_invalid(self, mock_get_settings):
        """Test invalid API key verification."""
        
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.api_keys = ["valid-key-1", "valid-key-2"]
        mock_get_settings.return_value = mock_settings
        
        # Test invalid key
        result = verify_api_key("invalid-key")
        assert result is False
    
    @patch('backend.infra.security.get_settings')
    def test_verify_api_key_no_keys_configured(self, mock_get_settings):
        """Test API key verification with no keys configured."""
        
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.api_keys = None
        mock_get_settings.return_value = mock_settings
        
        result = verify_api_key("any-key")
        assert result is False


class TestGetCurrentUser:
    """Test get_current_user async function."""
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.verify_api_key')
    @pytest.mark.asyncio
    async def test_get_current_user_api_key_success(self, mock_verify_api_key, mock_get_settings):
        """Test get_current_user with valid API key."""
        # Lines 356-389: Test get_current_user function
        
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.dev_mode = False
        mock_get_settings.return_value = mock_settings
        
        # Mock API key verification
        mock_verify_api_key.return_value = True
        
        # Mock request with API key
        mock_request = Mock()
        mock_request.headers = {"X-API-Key": "valid-api-key"}
        
        result = await get_current_user(mock_request, None)
        
        assert isinstance(result, AuthenticatedUser)
        assert result.username == "api-client"
        assert "api" in result.roles
        assert "trader" in result.roles
        assert result.token_id == "api-key"
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.verify_token')
    @pytest.mark.asyncio
    async def test_get_current_user_jwt_success(self, mock_verify_token, mock_get_settings):
        """Test get_current_user with valid JWT."""
        
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.dev_mode = False
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT verification
        mock_claims = UserClaims(
            sub="testuser",
            roles=["user"],
            iss="test",
            aud="test", 
            exp=int(datetime.now(UTC).timestamp()) + 3600,
            iat=int(datetime.now(UTC).timestamp()),
            jti="token-123"
        )
        mock_verify_token.return_value = mock_claims
        
        # Mock request and credentials
        mock_request = Mock()
        mock_request.headers = {}
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid.jwt.token"
        )
        
        result = await get_current_user(mock_request, credentials)
        
        assert isinstance(result, AuthenticatedUser)
        assert result.username == "testuser"
        assert result.roles == ["user"]
        assert result.token_id == "token-123"
    
    @patch('backend.infra.security.get_settings')
    @pytest.mark.asyncio
    async def test_get_current_user_dev_bypass(self, mock_get_settings):
        """Test get_current_user with dev bypass."""
        # Lines 344-351: Test dev bypass functionality
        
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.dev_mode = True
        mock_get_settings.return_value = mock_settings
        
        # Mock request with dev bypass header
        mock_request = Mock()
        mock_request.headers = {"X-Dev-Bypass": "true"}
        
        result = await get_current_user(mock_request, None)
        
        assert isinstance(result, AuthenticatedUser)
        assert result.username == "dev-user"
        assert "admin" in result.roles
        assert "trader" in result.roles
        assert result.token_id == "dev-bypass"
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.verify_token')
    @pytest.mark.asyncio
    async def test_get_current_user_jwt_error_reraise(self, mock_verify_token, mock_get_settings):
        """Test get_current_user with JWT error that should be re-raised."""
        # Lines 375-383: Test JWT error handling
        
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.dev_mode = False
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT verification error that should be re-raised
        mock_verify_token.side_effect = HTTPException(
            status_code=401, 
            detail="Token expired"
        )
        
        # Mock request and credentials
        mock_request = Mock()
        mock_request.headers = {}
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="expired.jwt.token"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)
        
        assert exc_info.value.status_code == 401
        assert "Token expired" in exc_info.value.detail
    
    @patch('backend.infra.security.get_settings')
    @pytest.mark.asyncio
    async def test_get_current_user_no_auth(self, mock_get_settings):
        """Test get_current_user with no authentication."""
        
        mock_settings = Mock()
        mock_settings.app = Mock()
        mock_settings.app.dev_mode = False
        mock_get_settings.return_value = mock_settings
        
        # Mock request with no auth
        mock_request = Mock()
        mock_request.headers = {}
        
        result = await get_current_user(mock_request, None)
        assert result is None


class TestCreateAccessTokenEdgeCases:
    """Test create_access_token edge cases and error conditions."""
    
    @patch('backend.infra.security.get_settings')
    def test_create_access_token_invalid_expires_minutes(self, mock_get_settings):
        """Test create_access_token with invalid expires_minutes."""
        # Lines 208-243: Test validation errors
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Test with invalid expires_minutes type
        with pytest.raises(ValueError) as exc_info:
            create_access_token("user", ["role"], expires_minutes="invalid")
        
        assert "expires_minutes must be a number" in str(exc_info.value)
    
    @patch('backend.infra.security.get_settings') 
    def test_create_access_token_empty_subject(self, mock_get_settings):
        """Test create_access_token with empty subject."""
        
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Test with empty subject
        with pytest.raises(ValueError) as exc_info:
            create_access_token("", ["role"])
        
        assert "subject cannot be empty" in str(exc_info.value)
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security.jwt_verifier')
    def test_create_access_token_encoding_error(self, mock_jwt_verifier, mock_get_settings):
        """Test create_access_token with JWT encoding error."""
        
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.jwt_secret_key = "secret"
        mock_settings.security.jwt_expire_minutes = 60
        mock_settings.security.jwt_issuer = "test"
        mock_settings.security.jwt_audience = "test"
        mock_settings.security.jwt_algorithm = "HS256"
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT encoding error
        mock_jwt_verifier.encode.side_effect = Exception("Encoding failed")
        
        with pytest.raises(ValueError) as exc_info:
            create_access_token("user", ["role"])
        
        assert "Failed to create access token" in str(exc_info.value)


class TestPasswordHashingEdgeCases:
    """Test password hashing edge cases."""
    
    @patch('logging.warning')
    def test_hash_password_long_password(self, mock_warning):
        """Test password hashing with long password."""
        # Lines 155-163: Test long password warning
        
        # Create a password longer than 72 bytes
        long_password = "a" * 80
        
        result = hash_password(long_password)
        
        # Should still return a hash
        assert isinstance(result, str)
        assert result.startswith("$2b$")
        
        # Should log a warning
        mock_warning.assert_called_once()
        assert "72-byte limit" in mock_warning.call_args[0][0]


class TestRequireRolesFunction:
    """Test require_roles function and its different modes."""
    
    def test_require_roles_sync_call(self):
        """Test require_roles function with direct sync call."""
        # Test the hybrid function behavior
        
        user = AuthenticatedUser(
            username="testuser",
            roles=["admin"],
            token_id="token-123"
        )
        
        # Get the hybrid function
        check_func = require_roles("admin")
        
        # Call it with a user directly (sync mode)
        result = check_func(user)
        assert result == user
    
    def test_require_roles_sync_call_failure(self):
        """Test require_roles function sync call with insufficient permissions."""
        
        user = AuthenticatedUser(
            username="testuser", 
            roles=["user"],
            token_id="token-123"
        )
        
        check_func = require_roles("admin")
        
        with pytest.raises(HTTPException) as exc_info:
            check_func(user)
        
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail


# ============================================================================
# COMPREHENSIVE COVERAGE TESTS - Merged from test_security_comprehensive.py
# ============================================================================

class TestBase64URLFunctions:
    """Test base64URL encoding/decoding functions."""
    
    def test_b64url_encoding(self):
        """Test _b64url function."""
        # Line 26: Test base64URL encoding without padding
        data = b"hello world"
        result = _b64url(data)
        
        # Should be base64URL encoded without padding
        assert isinstance(result, bytes)
        assert b"=" not in result  # No padding
        
        # Test with different data sizes
        assert _b64url(b"") == b""
        assert _b64url(b"a") == b"YQ"  # Single char
        assert _b64url(b"ab") == b"YWI"  # Two chars
    
    def test_b64url_decode(self):
        """Test _b64url_decode function."""
        # Lines 31-32: Test base64URL decoding with padding restoration
        
        # Test basic decoding
        encoded = b"aGVsbG8gd29ybGQ"  # "hello world" in base64url
        result = _b64url_decode(encoded)
        assert result == b"hello world"
        
        # Test with padding needed
        encoded_no_pad = b"YQ"  # "a" without padding
        result = _b64url_decode(encoded_no_pad)
        assert result == b"a"

class TestJWTVerificationComprehensive:
    """Test JWT verification functions comprehensively."""
    
    @patch('backend.infra.security.get_settings')
    @patch('backend.infra.security._b64url_decode')
    def test_verify_jwt_valid_token(self, mock_decode, mock_get_settings):
        """Test verify_jwt with valid token."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.security = Mock()
        mock_settings.security.jwt_secret_key = "test-secret-key"
        mock_settings.security.jwt_algorithm = "HS256"
        mock_settings.security.jwt_issuer = "test-issuer"
        mock_settings.security.jwt_audience = "test-audience"
        mock_get_settings.return_value = mock_settings
        
        # Mock JWT payload
        payload = {
            "sub": "testuser",
            "roles": ["user", "admin"],
            "iss": "test-issuer",
            "aud": "test-audience",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "jti": "unique-token-id"
        }
        
        # Mock base64 decode to return our payload
        mock_decode.return_value = json.dumps(payload).encode()
        
        # Create a mock JWT token
        token = "header.payload.signature"
        
        with patch('backend.infra.security.hmac.compare_digest', return_value=True):
            result = security.verify_jwt(token)
            
            # Should return UserClaims object
            assert isinstance(result, UserClaims)
            assert result.sub == "testuser"
            assert result.roles == ["user", "admin"]
            assert result.iss == "test-issuer"

class TestUserModelsComprehensive:
    """Test user model classes comprehensively."""
    
    def test_user_claims_initialization(self):
        """Test UserClaims model initialization."""
        # Test with all fields
        claims = UserClaims(
            sub="testuser",
            roles=["user", "admin"],
            iss="test-issuer",
            aud="test-audience",
            exp=1234567890,
            iat=1234567890,
            jti="token-123"
        )
        
        assert claims.sub == "testuser"
        assert claims.roles == ["user", "admin"]
        assert claims.iss == "test-issuer"
        assert claims.aud == "test-audience"
        assert claims.exp == 1234567890
        assert claims.iat == 1234567890
        assert claims.jti == "token-123"
    
    def test_authenticated_user_initialization(self):
        """Test AuthenticatedUser model initialization."""
        user = AuthenticatedUser(
            username="testuser",
            roles=["user"],
            token_id="token-123"
        )
        
        assert user.username == "testuser"
        assert user.roles == ["user"]
        assert user.token_id == "token-123"

class TestPasswordHashingComprehensive:
    """Test password hashing functions comprehensively."""
    
    def test_hash_password_comprehensive(self):
        """Test password hashing function."""
        password = "testpassword123"
        hashed = security.hash_password(password)
        
        # Should return a string
        assert isinstance(hashed, str)
        
        # Should be bcrypt format
        assert hashed.startswith("$2b$")
        
        # Should be different from original password
        assert hashed != password
        
        # Should be deterministic but with salt (different each time)
        hashed2 = hash_password(password)
        assert hashed != hashed2  # Different due to salt
    
    def test_verify_password_comprehensive(self):
        """Test password verification function."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        # Should verify correct password
        assert security.verify_password(password, hashed) is True
        
        # Should reject wrong password
        assert security.verify_password("wrongpassword", hashed) is False
        
        # Should handle empty password
        assert security.verify_password("", hashed) is False

class TestJWTTokenCreationComprehensive:
    """Test JWT token creation functions comprehensively."""
    
    @patch('backend.infra.security.jwt_verifier')
    def test_create_access_token_comprehensive(self, mock_jwt_verifier):
        """Test JWT token creation comprehensively."""
        mock_jwt_verifier.encode.return_value = "mock.jwt.token"
        
        # Mock get_settings
        with patch('backend.infra.security.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.security = Mock()
            mock_settings.security.jwt_secret_key = "test-secret"
            mock_settings.security.jwt_expire_minutes = 60
            mock_settings.security.jwt_issuer = "test-issuer"
            mock_settings.security.jwt_audience = "test-audience"
            mock_settings.security.jwt_algorithm = "HS256"
            mock_get_settings.return_value = mock_settings
            
            token = create_access_token(subject="testuser", roles=["user"])
            
            assert token == "mock.jwt.token"
            mock_jwt_verifier.encode.assert_called_once()

class TestSecurityDependenciesComprehensive:
    """Test FastAPI security dependencies comprehensively."""
    
    @patch('backend.infra.security.get_current_user')
    async def test_require_roles_async_comprehensive(self, mock_get_current_user):
        """Test require_roles dependency function async mode."""
        # Mock authenticated user
        mock_user = AuthenticatedUser(
            username="testuser",
            roles=["user", "admin"],
            token_id="token-123"
        )
        mock_get_current_user.return_value = mock_user
        
        # Create dependency function
        dependency = require_roles("admin")
        
        # Mock request and credentials
        mock_request = Mock()
        mock_credentials = Mock()
        
        # Should pass for user with admin role
        result = await dependency(mock_request, mock_credentials)
        assert result == mock_user


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])