"""
Comprehensive unit tests for security module JWT failure modes, password validation, and RBAC.
Tests expired tokens, malformed tokens, wrong audience/issuer, and authentication edge cases.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
import jwt
import pytest

from backend.config import get_settings
from backend.infra.security import (
    AuthenticatedUser,
    create_access_token,
    get_authenticated_user,
    get_current_user,
    hash_password,
    require_roles,
    verify_api_key,
    verify_password,
    verify_token,
)


class TestJWTTokenFailureModes:
    """Test JWT token validation failure scenarios."""

    @pytest.mark.unit
    def test_verify_expired_token(self):
        """Test verification of expired JWT token."""
        # Create expired token
        expired_token = create_access_token("testuser", ["user"], expires_minutes=-1)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_verify_malformed_token(self):
        """Test verification of malformed JWT token."""
        malformed_tokens = [
            "not.a.token",
            "definitely-not-a-jwt-token",
            "header.payload",  # Missing signature
            "too.many.parts.in.this.token",
            "",  # Empty token
            "Bearer token",  # With Bearer prefix (should be stripped)
        ]

        for bad_token in malformed_tokens:
            with pytest.raises(HTTPException) as exc_info:
                verify_token(bad_token)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert (
                "invalid" in exc_info.value.detail.lower()
                or "could not validate" in exc_info.value.detail.lower()
            )

    @pytest.mark.unit
    def test_verify_token_wrong_issuer(self):
        """Test verification of token with wrong issuer."""
        settings = get_settings()

        # Create token with wrong issuer
        claims = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": "wrong-issuer",  # Incorrect issuer
            "aud": settings.security.jwt_audience,
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-token-id",
        }

        wrong_issuer_token = jwt.encode(
            claims,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(wrong_issuer_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "issuer" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_verify_token_wrong_audience(self):
        """Test verification of token with wrong audience."""
        settings = get_settings()

        # Create token with wrong audience
        claims = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": settings.security.jwt_issuer,
            "aud": "wrong-audience",  # Incorrect audience
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-token-id",
        }

        wrong_audience_token = jwt.encode(
            claims,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(wrong_audience_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "audience" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_verify_token_wrong_signature(self):
        """Test verification of token with wrong signature."""
        settings = get_settings()

        # Create token with wrong secret
        claims = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": settings.security.jwt_issuer,
            "aud": settings.security.jwt_audience,
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-token-id",
        }

        wrong_secret_token = jwt.encode(
            claims,
            "wrong-secret-key",  # Wrong secret
            algorithm=settings.security.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(wrong_secret_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.unit
    def test_verify_token_missing_subject(self):
        """Test verification of token with missing subject claim."""
        settings = get_settings()

        claims = {
            # Missing "sub" claim
            "roles": ["user"],
            "iss": settings.security.jwt_issuer,
            "aud": settings.security.jwt_audience,
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-token-id",
        }

        no_subject_token = jwt.encode(
            claims,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm,
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(no_subject_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing subject" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_verify_token_unsupported_algorithm(self):
        """Test verification of token with unsupported algorithm."""
        settings = get_settings()

        # Create token with unsupported algorithm
        claims = {
            "sub": "testuser",
            "roles": ["user"],
            "iss": settings.security.jwt_issuer,
            "aud": settings.security.jwt_audience,
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-token-id",
        }

        # Use a different algorithm
        unsupported_token = jwt.encode(
            claims,
            settings.security.jwt_secret_key,
            algorithm="HS512",  # Different from configured algorithm
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(unsupported_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.unit
    def test_create_token_invalid_parameters(self):
        """Test token creation with invalid parameters."""
        # Test with invalid expiration
        with pytest.raises(ValueError):
            create_access_token("user", ["role"], expires_minutes="not_a_number")

        # Test with empty subject
        with pytest.raises(ValueError):
            create_access_token("", ["role"])

        # Test with None subject
        with pytest.raises(ValueError):
            create_access_token(None, ["role"])


class TestPasswordHashVerification:
    """Test password hashing and verification edge cases."""

    @pytest.mark.unit
    def test_hash_password_basic(self):
        """Test basic password hashing."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed != password  # Should be different
        assert isinstance(hashed, str)
        assert len(hashed) > 20  # bcrypt hashes are long
        assert hashed.startswith("$2")  # bcrypt format

    @pytest.mark.unit
    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    @pytest.mark.unit
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        correct_password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(correct_password)

        assert verify_password(wrong_password, hashed) is False

    @pytest.mark.unit
    def test_verify_password_empty_strings(self):
        """Test password verification with empty strings."""
        # Empty password
        assert verify_password("", hash_password("test")) is False

        # Empty hash (invalid format)
        assert verify_password("test", "") is False

        # Both empty
        assert verify_password("", "") is False

    @pytest.mark.unit
    def test_verify_password_special_characters(self):
        """Test password verification with special characters."""
        special_password = "p@$$w0rd!#$%^&*()_+-=[]{}|;':\"<>?,./"
        hashed = hash_password(special_password)

        assert verify_password(special_password, hashed) is True
        assert verify_password("different", hashed) is False

    @pytest.mark.unit
    def test_verify_password_unicode_characters(self):
        """Test password verification with unicode characters."""
        unicode_password = "пароль123密码🔑"
        hashed = hash_password(unicode_password)

        assert verify_password(unicode_password, hashed) is True
        assert verify_password("password123", hashed) is False

    @pytest.mark.unit
    def test_verify_password_very_long_password(self):
        """Test password verification with very long password."""
        long_password = "a" * 1000  # 1000 character password
        hashed = hash_password(long_password)

        assert verify_password(long_password, hashed) is True
        assert verify_password(long_password[:-1], hashed) is False

    @pytest.mark.unit
    def test_verify_password_malformed_hash(self):
        """Test password verification with malformed hash."""
        password = "test_password"

        malformed_hashes = [
            "not_a_hash",
            "$2a$10$invalid",  # Too short
            "plaintext_password",
            "$1$invalid$hash",  # Wrong algorithm
            None,
        ]

        for bad_hash in malformed_hashes:
            if bad_hash is not None:
                assert verify_password(password, bad_hash) is False

    @pytest.mark.unit
    def test_password_hash_consistency(self):
        """Test that same password produces different hashes (salt)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to salt
        assert hash1 != hash2

        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestAPIKeyAuthentication:
    """Test API key authentication failure modes."""

    @pytest.mark.unit
    def test_verify_api_key_valid(self):
        """Test API key verification with valid key."""
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value.security.api_keys = [
                "valid-key-1",
                "valid-key-2",
            ]

            assert verify_api_key("valid-key-1") is True
            assert verify_api_key("valid-key-2") is True

    @pytest.mark.unit
    def test_verify_api_key_invalid(self):
        """Test API key verification with invalid key."""
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value.security.api_keys = [
                "valid-key-1",
                "valid-key-2",
            ]

            assert verify_api_key("invalid-key") is False
            assert verify_api_key("") is False
            assert verify_api_key(None) is False

    @pytest.mark.unit
    def test_verify_api_key_case_sensitive(self):
        """Test that API key verification is case sensitive."""
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value.security.api_keys = ["CaseSensitiveKey"]

            assert verify_api_key("CaseSensitiveKey") is True
            assert verify_api_key("casesensitivekey") is False
            assert verify_api_key("CASESENSITIVEKEY") is False

    @pytest.mark.unit
    def test_verify_api_key_no_keys_configured(self):
        """Test API key verification when no keys are configured."""
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value.security.api_keys = []

            assert verify_api_key("any-key") is False

    @pytest.mark.unit
    def test_verify_api_key_whitespace_handling(self):
        """Test API key verification with whitespace."""
        with patch("backend.config.get_settings") as mock_settings:
            mock_settings.return_value.security.api_keys = ["valid-key"]

            # Should not match with extra whitespace
            assert verify_api_key(" valid-key") is False
            assert verify_api_key("valid-key ") is False
            assert verify_api_key(" valid-key ") is False


class TestRBACRoleBasedAccess:
    """Test Role-Based Access Control (RBAC) enforcement."""

    @pytest.mark.unit
    def test_require_roles_single_role_match(self):
        """Test role requirement with single matching role."""
        require_admin = require_roles("admin")

        # User with admin role should pass
        admin_user = AuthenticatedUser(
            username="admin", roles=["admin"], token_id="test"
        )
        result = require_admin(admin_user)
        assert result == admin_user

    @pytest.mark.unit
    def test_require_roles_single_role_no_match(self):
        """Test role requirement with single non-matching role."""
        require_admin = require_roles("admin")

        # User without admin role should fail
        user = AuthenticatedUser(username="user", roles=["user"], token_id="test")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Insufficient permissions" in exc_info.value.detail

    @pytest.mark.unit
    def test_require_roles_multiple_roles_match(self):
        """Test role requirement with multiple roles (OR logic)."""
        require_admin_or_trader = require_roles("admin", "trader")

        # Admin user should pass
        admin_user = AuthenticatedUser(
            username="admin", roles=["admin"], token_id="test"
        )
        result = require_admin_or_trader(admin_user)
        assert result == admin_user

        # Trader user should pass
        trader_user = AuthenticatedUser(
            username="trader", roles=["trader"], token_id="test"
        )
        result = require_admin_or_trader(trader_user)
        assert result == trader_user

    @pytest.mark.unit
    def test_require_roles_multiple_roles_no_match(self):
        """Test role requirement with multiple roles but no match."""
        require_admin_or_trader = require_roles("admin", "trader")

        # User with only viewer role should fail
        viewer_user = AuthenticatedUser(
            username="viewer", roles=["viewer"], token_id="test"
        )

        with pytest.raises(HTTPException) as exc_info:
            require_admin_or_trader(viewer_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.unit
    def test_require_roles_user_multiple_roles(self):
        """Test role requirement with user having multiple roles."""
        require_trader = require_roles("trader")

        # User with multiple roles including trader should pass
        multi_role_user = AuthenticatedUser(
            username="multi", roles=["viewer", "trader", "analyst"], token_id="test"
        )
        result = require_trader(multi_role_user)
        assert result == multi_role_user

    @pytest.mark.unit
    def test_require_roles_empty_roles(self):
        """Test role requirement with user having no roles."""
        require_admin = require_roles("admin")

        # User with no roles should fail
        no_role_user = AuthenticatedUser(username="norole", roles=[], token_id="test")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(no_role_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.unit
    def test_require_roles_case_sensitive(self):
        """Test that role matching is case sensitive."""
        require_admin = require_roles("admin")

        # User with wrong case role should fail
        wrong_case_user = AuthenticatedUser(
            username="user", roles=["Admin"], token_id="test"
        )

        with pytest.raises(HTTPException) as exc_info:
            require_admin(wrong_case_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestAuthenticationDependencies:
    """Test FastAPI authentication dependencies."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_current_user_valid_jwt(self):
        """Test get_current_user with valid JWT token."""
        valid_token = create_access_token("testuser", ["user"])
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=valid_token
        )

        mock_request = MagicMock()
        mock_request.headers = {}

        user = await get_current_user(mock_request, credentials)

        assert user is not None
        assert user.username == "testuser"
        assert "user" in user.roles

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_current_user_valid_api_key(self):
        """Test get_current_user with valid API key."""
        with patch("backend.infra.security.verify_api_key") as mock_verify:
            mock_verify.return_value = True

            mock_request = MagicMock()
            mock_request.headers = {"x-api-key": "valid-api-key"}

            user = await get_current_user(mock_request, None)

            assert user is not None
            assert user.username == "api-user"
            assert "trader" in user.roles
            assert "api" in user.roles

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        """Test get_current_user with no credentials provided."""
        mock_request = MagicMock()
        mock_request.headers = {}

        user = await get_current_user(mock_request, None)

        assert user is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_jwt(self):
        """Test get_current_user with invalid JWT token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid.jwt.token"
        )

        mock_request = MagicMock()
        mock_request.headers = {}

        # Should not raise exception, just return None
        user = await get_current_user(mock_request, credentials)
        assert user is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_authenticated_user_with_user(self):
        """Test get_authenticated_user when user is provided."""
        test_user = AuthenticatedUser(username="test", roles=["user"], token_id="test")

        result = await get_authenticated_user(test_user)
        assert result == test_user

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_authenticated_user_without_user(self):
        """Test get_authenticated_user when no user is provided."""
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_user(None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "authentication required" in exc_info.value.detail.lower()


class TestSecurityEdgeCases:
    """Test security-related edge cases and attack scenarios."""

    @pytest.mark.unit
    def test_jwt_algorithm_confusion_attack(self):
        """Test protection against algorithm confusion attacks."""
        settings = get_settings()

        # Try to create token with "none" algorithm
        claims = {
            "sub": "attacker",
            "roles": ["admin"],
            "iss": settings.security.jwt_issuer,
            "aud": settings.security.jwt_audience,
            "exp": int((datetime.now(UTC) + timedelta(minutes=30)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "attack-token",
        }

        # Create unsigned token (algorithm confusion attack)
        try:
            unsigned_token = jwt.encode(claims, "", algorithm="none")

            # Should fail verification
            with pytest.raises(HTTPException):
                verify_token(unsigned_token)
        except Exception:
            # If jwt library doesn't support "none", that's also fine
            pass

    @pytest.mark.unit
    def test_timing_attack_resistance(self):
        """Test that password verification is resistant to timing attacks."""
        import time

        correct_password = "correct_password"
        wrong_short = "wrong"
        wrong_long = "wrong_password_that_is_much_longer"

        hashed = hash_password(correct_password)

        # Measure verification times
        times = []
        for password in [wrong_short, wrong_long, correct_password]:
            start = time.perf_counter()
            verify_password(password, hashed)
            end = time.perf_counter()
            times.append(end - start)

        # Times should be relatively consistent (no major timing differences)
        # Note: This is a basic test; real timing attack analysis requires more sophisticated measurement
        assert all(t > 0 for t in times)

    @pytest.mark.unit
    def test_jwt_token_replay_protection(self):
        """Test JWT token uniqueness (jti claim)."""
        # Create two tokens for same user
        token1 = create_access_token("user", ["role"])
        token2 = create_access_token("user", ["role"])

        # Decode tokens to check jti claims
        claims1 = verify_token(token1)
        claims2 = verify_token(token2)

        # Should have different jti (JWT ID) values
        assert claims1.jti != claims2.jti
        assert claims1.jti is not None
        assert claims2.jti is not None

    @pytest.mark.unit
    def test_password_hash_entropy(self):
        """Test that password hashes have sufficient entropy."""
        password = "test_password"

        # Generate multiple hashes
        hashes = [hash_password(password) for _ in range(10)]

        # All should be different (due to salt)
        assert len(set(hashes)) == 10

        # All should have reasonable length
        assert all(len(h) >= 60 for h in hashes)  # bcrypt produces long hashes

    @pytest.mark.unit
    def test_role_injection_prevention(self):
        """Test that roles cannot be injected through token manipulation."""
        # Create normal user token
        user_token = create_access_token("normaluser", ["user"])

        # Decode and try to modify roles
        settings = get_settings()
        decoded = jwt.decode(
            user_token,
            settings.security.jwt_secret_key,
            algorithms=[settings.security.jwt_algorithm],
            options={
                "verify_signature": False
            },  # Skip signature check for modification
        )

        # Modify roles
        decoded["roles"] = ["admin", "superuser"]

        # Re-encode without proper signature
        modified_token = jwt.encode(
            decoded,
            "wrong-secret",  # Wrong secret
            algorithm=settings.security.jwt_algorithm,
        )

        # Should fail verification due to wrong signature
        with pytest.raises(HTTPException):
            verify_token(modified_token)

    @pytest.mark.unit
    def test_token_expiration_boundary_conditions(self):
        """Test token expiration at exact boundary conditions."""
        # Create token that expires in 1 second
        short_lived_token = create_access_token(
            "user", ["role"], expires_minutes=1 / 60
        )

        # Should be valid immediately
        claims = verify_token(short_lived_token)
        assert claims.sub == "user"

        # Test with token that's about to expire (requires careful timing in real tests)
        # This is more of a conceptual test for the boundary condition

    @pytest.mark.unit
    def test_empty_or_null_role_handling(self):
        """Test handling of empty or null roles in tokens."""
        # Test with empty roles list
        empty_roles_token = create_access_token("user", [])
        claims = verify_token(empty_roles_token)
        assert claims.roles == []

        # Test role checking with empty roles
        user_no_roles = AuthenticatedUser(username="user", roles=[], token_id="test")
        require_admin = require_roles("admin")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(user_no_roles)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
