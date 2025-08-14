"""Comprehensive JWT flow tests to verify token encoding/decoding."""

import pytest
from datetime import datetime, timezone
import time

from backend.infra.security_hardening import JwtVerifier
from tests.helpers.fake_jwt import FakeJwtVerifier, FakeJWTError


class TestJwtVerifier:
    """Test the production JWT verifier with proper validation."""
    
    def test_encode_with_required_claims(self):
        """Test JWT encoding with all required claims."""
        jwt_verifier = JwtVerifier()
        
        payload = {
            "user_id": "123",
            "username": "testuser",
            "iss": "algotrading-platform",
            "aud": "api-users",
            "exp": int(time.time()) + 3600,  # 1 hour expiry
            "alg": "HS256"
        }
        
        token = jwt_verifier.encode(payload)
        
        # Token should be a valid JWT string with 3 parts
        assert isinstance(token, str)
        assert len(token.split('.')) == 3
    
    def test_encode_missing_required_claims(self):
        """Test JWT encoding fails with missing required claims."""
        jwt_verifier = JwtVerifier()
        
        # Missing 'iss' and 'aud' claims
        payload = {
            "user_id": "123", 
            "exp": int(time.time()) + 3600
        }
        
        with pytest.raises(ValueError) as exc_info:
            jwt_verifier.encode(payload)
        
        assert "Missing required JWT claims" in str(exc_info.value)
        assert "iss" in str(exc_info.value)
        assert "aud" in str(exc_info.value)
    
    def test_decode_valid_token(self):
        """Test JWT decoding with valid token."""
        jwt_verifier = JwtVerifier()
        
        # Create valid payload
        payload = {
            "user_id": "123",
            "username": "testuser", 
            "iss": "algotrading-platform",
            "aud": "api-users",
            "exp": int(time.time()) + 3600,  # 1 hour expiry
            "alg": "HS256"
        }
        
        # Encode then decode
        token = jwt_verifier.encode(payload)
        decoded = jwt_verifier.decode(token)
        
        # Verify decoded payload contains expected data
        assert decoded["user_id"] == "123"
        assert decoded["username"] == "testuser"
        assert decoded["iss"] == "algotrading-platform"
        assert decoded["aud"] == "api-users"
        assert "exp" in decoded
    
    def test_decode_expired_token(self):
        """Test JWT decoding fails with expired token."""
        jwt_verifier = JwtVerifier()
        
        # Create expired payload
        payload = {
            "user_id": "123",
            "iss": "algotrading-platform",
            "aud": "api-users", 
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
            "alg": "HS256"
        }
        
        token = jwt_verifier.encode(payload)
        
        with pytest.raises(jwt_verifier.JWTError):
            jwt_verifier.decode(token)
    
    def test_decode_invalid_token(self):
        """Test JWT decoding fails with malformed token."""
        jwt_verifier = JwtVerifier()
        
        invalid_tokens = [
            "invalid.token.string",
            "not.a.jwt",
            "",
            "single-string",
            "too.many.parts.here.invalid"
        ]
        
        for invalid_token in invalid_tokens:
            with pytest.raises(jwt_verifier.JWTError):
                jwt_verifier.decode(invalid_token)
    
    def test_unsupported_algorithm_in_payload(self):
        """Test JWT decoding validates algorithm in payload."""
        jwt_verifier = JwtVerifier()
        
        # Create a payload that will have unsupported algorithm claim
        payload = {
            "user_id": "123",
            "iss": "algotrading-platform", 
            "aud": "api-users",
            "exp": int(time.time()) + 3600,
            "alg": "none"  # This will be in the payload after decoding
        }
        
        # Encode with HS256 (supported)
        token = jwt_verifier.encode(payload)
        
        # When we decode, the payload will contain 'alg': 'none'
        # which should trigger our validation
        with pytest.raises(jwt_verifier.JWTError) as exc_info:
            jwt_verifier.decode(token)
        
        assert "Unsupported algorithm: none" in str(exc_info.value)


class TestFakeJwtVerifier:
    """Test the fake JWT verifier for test isolation."""
    
    def test_fake_encode_returns_predictable_token(self):
        """Test fake JWT encoder returns predictable token."""
        fake_jwt = FakeJwtVerifier()
        
        payload = {"user_id": "123", "username": "testuser"}
        token = fake_jwt.encode(payload, "secret")
        
        # Should return a valid JWT-like structure
        assert isinstance(token, str)
        assert len(token.split('.')) == 3
        
        # Should be deterministic for same payload
        token2 = fake_jwt.encode(payload, "secret")
        assert token == token2
    
    def test_fake_decode_returns_payload(self):
        """Test fake JWT decoder returns original payload."""
        fake_jwt = FakeJwtVerifier()
        
        payload = {
            "user_id": "123",
            "username": "testuser",
            "iss": "test-issuer",
            "aud": "test-audience",
            "exp": int(time.time()) + 3600
        }
        
        token = fake_jwt.encode(payload, "secret")
        decoded = fake_jwt.decode(token, "secret")
        
        # Should return the original payload
        assert decoded["user_id"] == payload["user_id"]
        assert decoded["username"] == payload["username"]
        assert decoded["iss"] == payload["iss"]
        assert decoded["aud"] == payload["aud"]
    
    def test_fake_decode_validates_expiry(self):
        """Test fake JWT decoder validates token expiry."""
        fake_jwt = FakeJwtVerifier()
        
        # Create expired token
        expired_payload = {
            "user_id": "123",
            "exp": int(time.time()) - 3600  # Expired 1 hour ago
        }
        
        token = fake_jwt.encode(expired_payload, "secret")
        
        with pytest.raises(FakeJWTError) as exc_info:
            fake_jwt.decode(token, "secret")
        
        assert "expired" in str(exc_info.value).lower()
    
    def test_fake_decode_validates_issuer(self):
        """Test fake JWT decoder validates issuer."""
        fake_jwt = FakeJwtVerifier()
        
        payload = {
            "user_id": "123",
            "iss": "wrong-issuer",
            "exp": int(time.time()) + 3600
        }
        
        token = fake_jwt.encode(payload, "secret")
        
        # Should fail when expecting different issuer
        with pytest.raises(FakeJWTError) as exc_info:
            fake_jwt.decode(token, "secret", issuer="expected-issuer")
        
        assert "issuer" in str(exc_info.value).lower()
    
    def test_fake_decode_validates_audience(self):
        """Test fake JWT decoder validates audience."""
        fake_jwt = FakeJwtVerifier()
        
        payload = {
            "user_id": "123", 
            "aud": "wrong-audience",
            "exp": int(time.time()) + 3600
        }
        
        token = fake_jwt.encode(payload, "secret")
        
        # Should fail when expecting different audience
        with pytest.raises(FakeJWTError) as exc_info:
            fake_jwt.decode(token, "secret", audience="expected-audience")
        
        assert "audience" in str(exc_info.value).lower()
    
    def test_fake_decode_invalid_format(self):
        """Test fake JWT decoder handles invalid token format."""
        fake_jwt = FakeJwtVerifier()
        
        invalid_tokens = [
            "invalid-token",
            "not.enough.parts",
            "",
            None
        ]
        
        for invalid_token in invalid_tokens:
            with pytest.raises(FakeJWTError):
                fake_jwt.decode(invalid_token, "secret")


class TestJwtFlowIntegration:
    """Integration tests for complete JWT flows."""
    
    def test_encode_decode_roundtrip(self):
        """Test complete encode->decode roundtrip with production verifier."""
        jwt_verifier = JwtVerifier()
        
        original_payload = {
            "user_id": "test-user-123",
            "username": "testuser",
            "email": "test@example.com",
            "roles": ["user", "trader"],
            "iss": "algotrading-platform",
            "aud": "api-users", 
            "exp": int(time.time()) + 3600,
            "alg": "HS256"
        }
        
        # Encode
        token = jwt_verifier.encode(original_payload)
        
        # Decode
        decoded_payload = jwt_verifier.decode(token)
        
        # Verify data integrity
        assert decoded_payload["user_id"] == original_payload["user_id"]
        assert decoded_payload["username"] == original_payload["username"]
        assert decoded_payload["email"] == original_payload["email"]
        assert decoded_payload["roles"] == original_payload["roles"]
        assert decoded_payload["iss"] == original_payload["iss"]
        assert decoded_payload["aud"] == original_payload["aud"]
    
    def test_fake_verifier_roundtrip(self):
        """Test complete encode->decode roundtrip with fake verifier."""
        fake_jwt = FakeJwtVerifier()
        
        original_payload = {
            "user_id": "test-user-456",
            "username": "fakeuser", 
            "email": "fake@example.com",
            "iss": "fake-issuer",
            "aud": "fake-audience",
            "exp": int(time.time()) + 3600
        }
        
        # Encode
        token = fake_jwt.encode(original_payload, "fake-secret")
        
        # Decode
        decoded_payload = fake_jwt.decode(token, "fake-secret")
        
        # Verify data integrity
        assert decoded_payload["user_id"] == original_payload["user_id"]
        assert decoded_payload["username"] == original_payload["username"]
        assert decoded_payload["email"] == original_payload["email"]
        assert decoded_payload["iss"] == original_payload["iss"]
        assert decoded_payload["aud"] == original_payload["aud"]
