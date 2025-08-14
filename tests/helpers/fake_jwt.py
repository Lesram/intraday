"""
Fake JWT implementation for testing without jose dependency.
"""

import json
import base64
from datetime import UTC, datetime
from typing import Any


class FakeJWTError(Exception):
    """Fake JWT error for testing"""
    pass


class FakeJwtVerifier:
    """Fake JWT verifier that mimics jose.jwt behavior for tests"""
    
    def __init__(self):
        self.JWTError = FakeJWTError
    
    async def async_mock_enter(self, mock_session):
        """Async context manager enter for database sessions."""
        return mock_session
    
    async def async_mock_exit(self, exc_type, exc_val, exc_tb):
        """Async context manager exit for database sessions.""" 
        return None
    
    def encode(self, payload: dict, key: str, algorithm: str = "HS256") -> str:
        """
        Create a fake JWT token that can be decoded by the same instance.
        Format: header.payload.signature (all base64 encoded)
        """
        header = {"alg": algorithm, "typ": "JWT"}
        
        # Encode header and payload as base64
        header_b64 = base64.urlsafe_b64encode(
            json.dumps(header).encode()
        ).decode().rstrip("=")
        
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip("=")
        
        # Create a predictable "signature" based on payload and key
        signature_content = f"{header_b64}.{payload_b64}.{key}"
        signature_b64 = base64.urlsafe_b64encode(
            signature_content.encode()
        ).decode().rstrip("=")[:10]  # Truncate for readability
        
        return f"{header_b64}.{payload_b64}.{signature_b64}"
    
    def decode(
        self, 
        token: str, 
        key: str, 
        algorithms: list[str] = None, 
        options: dict = None,
        audience: str = None,
        issuer: str = None,
        leeway: int = 0
    ) -> dict:
        """
        Decode a fake JWT token with basic validation.
        """
        if not token or not isinstance(token, str):
            raise FakeJWTError("Invalid token format")
        
        parts = token.split(".")
        if len(parts) != 3:
            raise FakeJWTError("Invalid token format")
        
        header_b64, payload_b64, signature_b64 = parts
        
        try:
            # Decode payload
            # Add padding if needed
            payload_b64_padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64_padded).decode()
            payload = json.loads(payload_json)
        except Exception as e:
            raise FakeJWTError(f"Invalid payload: {e}")
        
        # Basic validation
        now = datetime.now(UTC).timestamp()
        
        # Check expiration
        if "exp" in payload:
            if payload["exp"] < now - leeway:
                raise FakeJWTError("Token has expired")
        
        # Check not before
        if "nbf" in payload:
            if payload["nbf"] > now + leeway:
                raise FakeJWTError("Token not yet valid")
        
        # Check issuer if required
        if issuer and payload.get("iss") != issuer:
            raise FakeJWTError(f"Invalid issuer. Expected {issuer}")
        
        # Check audience if required
        if audience:
            token_aud = payload.get("aud")
            if isinstance(token_aud, str):
                token_aud = [token_aud]
            if not token_aud or audience not in token_aud:
                raise FakeJWTError(f"Invalid audience. Expected {audience}")
        
        return payload


def create_test_token(
    sub: str = "test_user",
    roles: list[str] = None,
    iss: str = "test_issuer", 
    aud: str = "test_audience",
    exp_minutes: int = 60,
    **extra_claims
) -> str:
    """Create a test JWT token with standard claims"""
    if roles is None:
        roles = ["user"]
    
    now = datetime.now(UTC)
    exp = now.timestamp() + (exp_minutes * 60)
    
    claims = {
        "sub": sub,
        "roles": roles,
        "iss": iss,
        "aud": aud,
        "exp": int(exp),
        "iat": int(now.timestamp()),
        "jti": f"test_token_{sub}",
        **extra_claims
    }
    
    verifier = FakeJwtVerifier()
    return verifier.encode(claims, "test_secret")


def create_expired_token(
    sub: str = "test_user",
    roles: list[str] = None,
    iss: str = "test_issuer",
    aud: str = "test_audience"
) -> str:
    """Create an expired test token"""
    if roles is None:
        roles = ["user"]
    
    now = datetime.now(UTC)
    exp = now.timestamp() - 3600  # Expired 1 hour ago
    
    claims = {
        "sub": sub,
        "roles": roles,
        "iss": iss,
        "aud": aud,
        "exp": int(exp),
        "iat": int(now.timestamp() - 7200),  # Issued 2 hours ago
        "jti": f"expired_token_{sub}",
    }
    
    verifier = FakeJwtVerifier()
    return verifier.encode(claims, "test_secret")
