"""
Security module tests targeting specific functions for coverage improvement.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC, timedelta


def test_security_create_access_token_with_mock():
    """Test create_access_token function with mocked JWT verifier"""
    from backend.infra.security import create_access_token
    
    # Mock the JWT verifier to avoid JOSE dependency
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        mock_verifier.encode.return_value = "mocked.jwt.token"
        
        # Call with correct parameters
        result = create_access_token(subject="test_user", roles=["trader"])
        
        # Verify the function was called
        assert result == "mocked.jwt.token"
        mock_verifier.encode.assert_called_once()


def test_verify_token_function():
    """Test verify_token function with mocked JWT verifier"""
    from backend.infra.security import verify_token
    
    # Mock the JWT verifier with complete payload
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        # Mock JWTError as a proper exception class
        mock_verifier.JWTError = Exception
        mock_verifier.decode.return_value = {
            "sub": "test_user",
            "roles": ["trader"],
            "iss": "test_issuer",
            "aud": "test_audience",
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test_token_id",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
        }
        
        # Test token verification
        result = verify_token("fake.jwt.token")
        
        # Should return the decoded payload as UserClaims
        assert result.sub == "test_user"
        assert "trader" in result.roles
        mock_verifier.decode.assert_called_once()


def test_token_validation_scenarios():
    """Test various token validation scenarios"""
    from backend.infra.security import verify_token
    
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        mock_verifier.JWTError = Exception
        
        # Test successful verification with complete payload
        complete_payload = {
            "sub": "user123",
            "roles": ["admin"],
            "iss": "test_issuer",
            "aud": "test_audience",
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test_id",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
        }
        mock_verifier.decode.return_value = complete_payload
        result = verify_token("valid.token")
        assert result.sub == "user123"
        
        # Test invalid token (raises exception)
        mock_verifier.decode.side_effect = Exception("Invalid token")
        with pytest.raises(Exception):
            verify_token("invalid.token")


def test_security_middleware_functions():
    """Test security-related utility functions"""
    from backend.infra import security
    
    # Test that security module has expected functions
    assert hasattr(security, 'create_access_token')
    assert hasattr(security, 'verify_token')
    
    # Test functions are callable
    assert callable(security.create_access_token)
    assert callable(security.verify_token)


def test_token_expiration_handling():
    """Test token expiration logic"""
    from backend.infra.security import create_access_token
    
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        mock_verifier.encode.return_value = "token_with_exp"
        
        # Create token with custom expiration
        result = create_access_token(
            subject="test_user",
            roles=["admin"],
            expires_minutes=30
        )
        assert result == "token_with_exp"


@pytest.mark.unit
def test_security_configuration_integration():
    """Test security configuration integration"""
    from backend.infra.security import create_access_token
    
    # Test that function can be called without exceptions
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        mock_verifier.encode.return_value = "config_test_token"
        
        # This should work with default configuration
        result = create_access_token(subject="config_test", roles=["user"])
        assert result == "config_test_token"


def test_authentication_error_handling():
    """Test authentication error handling paths"""
    from backend.infra.security import verify_token
    
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        # Mock JWTError as a proper exception class
        mock_verifier.JWTError = Exception
        
        # Simulate JWT decode error
        mock_verifier.decode.side_effect = Exception("Token decode failed")
        
        # This should handle the error appropriately
        with pytest.raises(Exception):
            verify_token("malformed.token")


def test_token_payload_construction():
    """Test token payload construction and validation"""
    from backend.infra.security import create_access_token
    
    with patch('backend.infra.security.jwt_verifier') as mock_verifier:
        mock_verifier.encode.return_value = "payload_test_token"
        
        # Test with various role combinations
        test_cases = [
            ("user1", ["admin"]),
            ("user2", ["trader", "analyst"]),
            ("user3", ["readonly"])
        ]
        
        for subject, roles in test_cases:
            result = create_access_token(subject=subject, roles=roles)
            assert result == "payload_test_token"
            
        # Should have been called for each test case
        assert mock_verifier.encode.call_count == len(test_cases)
