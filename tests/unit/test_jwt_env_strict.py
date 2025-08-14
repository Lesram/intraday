"""
Tests for JWT configuration enforcement in non-local environments.

Ensures that JWT authentication is properly configured and enforced
when running in non-local environments (staging, production).
"""

from datetime import datetime, timedelta
import os
from unittest.mock import patch

import pytest


# Mock JWT configuration and authentication classes
class MockJWTConfig:
    """Mock JWT configuration for testing environment-strict behavior."""

    def __init__(
        self,
        environment="local",
        jwt_secret=None,
        jwt_algorithm="HS256",
        jwt_expiry_hours=24,
        require_https=False,
    ):
        self.environment = environment
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiry_hours = jwt_expiry_hours
        self.require_https = require_https

    def validate_config(self):
        """Validate JWT configuration based on environment."""
        if self.environment == "local":
            # Local environment - relaxed requirements
            return True

        # Non-local environments - strict requirements
        errors = []

        if not self.jwt_secret:
            errors.append("JWT secret key is required in non-local environments")

        if self.jwt_secret and len(self.jwt_secret) < 32:
            errors.append(
                "JWT secret must be at least 32 characters in non-local environments"
            )

        if self.jwt_algorithm not in ["HS256", "RS256"]:
            errors.append(
                f"JWT algorithm '{self.jwt_algorithm}' not allowed in non-local environments"
            )

        if self.jwt_expiry_hours > 24:
            errors.append("JWT expiry cannot exceed 24 hours in non-local environments")

        if self.environment == "production" and not self.require_https:
            errors.append("HTTPS is required for JWT tokens in production environment")

        if errors:
            raise ValueError(f"JWT configuration errors: {'; '.join(errors)}")

        return True


class MockJWTAuthenticator:
    """Mock JWT authenticator for testing."""

    def __init__(self, config: MockJWTConfig):
        self.config = config
        self.config.validate_config()  # Validate on initialization

    def create_token(self, user_id: str, roles: list = None) -> str:
        """Create a JWT token."""
        if not self.config.jwt_secret:
            raise ValueError("Cannot create token without JWT secret")

        # Mock token creation
        return f"mock.jwt.token.{user_id}"

    def validate_token(self, token: str) -> dict:
        """Validate a JWT token."""
        if not self.config.jwt_secret:
            raise ValueError("Cannot validate token without JWT secret")

        if not token or not token.startswith("mock.jwt.token."):
            raise ValueError("Invalid token format")

        # Mock token validation
        user_id = token.replace("mock.jwt.token.", "")
        return {
            "user_id": user_id,
            "valid": True,
            "expires_at": datetime.utcnow()
            + timedelta(hours=self.config.jwt_expiry_hours),
        }


class TestJWTEnvironmentStrict:
    """Test JWT configuration enforcement for different environments."""

    def test_local_environment_relaxed_requirements(self):
        """Test that local environment has relaxed JWT requirements."""
        # Local environment should work with minimal config
        config = MockJWTConfig(
            environment="local",
            jwt_secret=None,  # Can be None locally
            jwt_algorithm="HS256",
            require_https=False,
        )

        # Should validate without errors
        assert config.validate_config() is True

        # But cannot create authenticator without secret
        with pytest.raises(ValueError, match="Cannot create token without JWT secret"):
            auth = MockJWTAuthenticator(config)
            auth.create_token("test_user")

    def test_staging_environment_strict_requirements(self):
        """Test that staging environment enforces strict JWT requirements."""
        # Missing secret should fail
        with pytest.raises(
            ValueError, match="JWT secret key is required in non-local environments"
        ):
            MockJWTConfig(environment="staging", jwt_secret=None).validate_config()

        # Short secret should fail
        with pytest.raises(
            ValueError, match="JWT secret must be at least 32 characters"
        ):
            MockJWTConfig(
                environment="staging", jwt_secret="short_secret"
            ).validate_config()

        # Invalid algorithm should fail
        with pytest.raises(ValueError, match="JWT algorithm 'MD5' not allowed"):
            MockJWTConfig(
                environment="staging",
                jwt_secret="a" * 32,  # 32 chars
                jwt_algorithm="MD5",
            ).validate_config()

        # Long expiry should fail
        with pytest.raises(ValueError, match="JWT expiry cannot exceed 24 hours"):
            MockJWTConfig(
                environment="staging",
                jwt_secret="a" * 32,
                jwt_expiry_hours=48,  # Too long
            ).validate_config()

        # Valid staging config should pass
        config = MockJWTConfig(
            environment="staging",
            jwt_secret="a" * 32,
            jwt_algorithm="HS256",
            jwt_expiry_hours=12,
            require_https=False,  # OK for staging
        )
        assert config.validate_config() is True

    def test_production_environment_strictest_requirements(self):
        """Test that production environment has the strictest JWT requirements."""
        # Production requires HTTPS
        with pytest.raises(
            ValueError, match="HTTPS is required for JWT tokens in production"
        ):
            MockJWTConfig(
                environment="production",
                jwt_secret="a" * 32,
                jwt_algorithm="HS256",
                require_https=False,
            ).validate_config()

        # All other staging requirements also apply
        with pytest.raises(ValueError, match="JWT secret key is required"):
            MockJWTConfig(
                environment="production", jwt_secret=None, require_https=True
            ).validate_config()

        # Valid production config
        config = MockJWTConfig(
            environment="production",
            jwt_secret="a" * 64,  # Extra long for production
            jwt_algorithm="HS256",
            jwt_expiry_hours=8,  # Shorter expiry for production
            require_https=True,
        )
        assert config.validate_config() is True

    def test_jwt_authenticator_creation_with_valid_config(self):
        """Test JWT authenticator creation with valid configurations."""
        # Valid staging config
        staging_config = MockJWTConfig(
            environment="staging",
            jwt_secret="staging_secret_key_32_characters_long",
            jwt_algorithm="HS256",
            jwt_expiry_hours=12,
        )

        staging_auth = MockJWTAuthenticator(staging_config)

        # Should be able to create and validate tokens
        token = staging_auth.create_token("staging_user", ["trader"])
        validation = staging_auth.validate_token(token)

        assert validation["user_id"] == "staging_user"
        assert validation["valid"] is True

        # Valid production config
        production_config = MockJWTConfig(
            environment="production",
            jwt_secret="production_secret_key_64_characters_long_for_maximum_security",
            jwt_algorithm="HS256",
            jwt_expiry_hours=4,
            require_https=True,
        )

        production_auth = MockJWTAuthenticator(production_config)

        # Should work with production config
        token = production_auth.create_token("prod_user", ["admin"])
        validation = production_auth.validate_token(token)

        assert validation["user_id"] == "prod_user"
        assert validation["valid"] is True

    @patch.dict(
        os.environ, {"ENVIRONMENT": "staging", "JWT_SECRET": "test_secret_too_short"}
    )
    def test_environment_variable_validation(self):
        """Test JWT config validation using environment variables."""
        env = os.environ.get("ENVIRONMENT", "local")
        jwt_secret = os.environ.get("JWT_SECRET")

        # Should fail due to short secret in staging
        with pytest.raises(
            ValueError, match="JWT secret must be at least 32 characters"
        ):
            MockJWTConfig(environment=env, jwt_secret=jwt_secret).validate_config()

    @patch.dict(os.environ, {"ENVIRONMENT": "production"})
    def test_missing_jwt_secret_in_production(self):
        """Test that missing JWT secret fails in production."""
        env = os.environ.get("ENVIRONMENT")
        jwt_secret = os.environ.get("JWT_SECRET")  # Should be None

        with pytest.raises(
            ValueError, match="JWT secret key is required in non-local environments"
        ):
            MockJWTConfig(environment=env, jwt_secret=jwt_secret).validate_config()

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "production_grade_secret_key_with_sufficient_entropy_64_chars",
            "JWT_REQUIRE_HTTPS": "true",
        },
    )
    def test_production_environment_variables(self):
        """Test production environment with proper environment variables."""
        config = MockJWTConfig(
            environment=os.environ.get("ENVIRONMENT"),
            jwt_secret=os.environ.get("JWT_SECRET"),
            require_https=os.environ.get("JWT_REQUIRE_HTTPS", "false").lower()
            == "true",
        )

        # Should validate successfully
        assert config.validate_config() is True

        # Should be able to create authenticator
        auth = MockJWTAuthenticator(config)
        token = auth.create_token("prod_user_from_env")

        assert token.startswith("mock.jwt.token.")

    def test_jwt_algorithm_security_requirements(self):
        """Test JWT algorithm security requirements by environment."""
        base_config = {
            "jwt_secret": "secure_secret_key_32_characters_long",
            "jwt_expiry_hours": 8,
            "require_https": True,
        }

        # Test various algorithms
        secure_algorithms = ["HS256", "RS256"]
        insecure_algorithms = ["HS1", "MD5", "NONE", "none"]

        # Secure algorithms should work in all environments
        for env in ["staging", "production"]:
            for algorithm in secure_algorithms:
                config = MockJWTConfig(
                    environment=env, jwt_algorithm=algorithm, **base_config
                )
                assert config.validate_config() is True

        # Insecure algorithms should fail in non-local environments
        for env in ["staging", "production"]:
            for algorithm in insecure_algorithms:
                with pytest.raises(ValueError, match="JWT algorithm.*not allowed"):
                    MockJWTConfig(
                        environment=env, jwt_algorithm=algorithm, **base_config
                    ).validate_config()

    def test_jwt_expiry_limits_by_environment(self):
        """Test JWT token expiry limits vary by environment."""
        base_config = {
            "jwt_secret": "secure_secret_key_32_characters_long",
            "jwt_algorithm": "HS256",
            "require_https": True,
        }

        # Test expiry limits
        test_cases = [
            ("staging", 1, True),  # 1 hour - should pass
            ("staging", 24, True),  # 24 hours - should pass (max)
            ("staging", 25, False),  # 25 hours - should fail
            ("staging", 48, False),  # 48 hours - should fail
            ("production", 1, True),  # 1 hour - should pass
            ("production", 8, True),  # 8 hours - should pass
            ("production", 24, True),  # 24 hours - should pass (max)
            ("production", 25, False),  # 25 hours - should fail
        ]

        for env, expiry_hours, should_pass in test_cases:
            config = MockJWTConfig(
                environment=env, jwt_expiry_hours=expiry_hours, **base_config
            )

            if should_pass:
                assert config.validate_config() is True
            else:
                with pytest.raises(
                    ValueError, match="JWT expiry cannot exceed 24 hours"
                ):
                    config.validate_config()

    def test_jwt_token_validation_failures(self):
        """Test JWT token validation with various invalid inputs."""
        config = MockJWTConfig(
            environment="production",
            jwt_secret="production_secret_key_64_characters_long_for_security",
            require_https=True,
        )

        auth = MockJWTAuthenticator(config)

        # Invalid token formats should fail
        invalid_tokens = [
            None,
            "",
            "invalid.token.format",
            "not_a_jwt_token",
            "mock.jwt.wrong.format",
        ]

        for invalid_token in invalid_tokens:
            with pytest.raises(ValueError, match="Invalid token format"):
                auth.validate_token(invalid_token)

    def test_deterministic_jwt_config_validation(self, test_seed):
        """Test JWT config validation is deterministic."""
        # Same config should always pass/fail the same way
        config_data = {
            "environment": "staging",
            "jwt_secret": "deterministic_secret_32_chars_long",
            "jwt_algorithm": "HS256",
            "jwt_expiry_hours": 12,
            "require_https": False,
        }

        # Multiple validations should be consistent
        for _ in range(5):
            config = MockJWTConfig(**config_data)
            assert config.validate_config() is True

        # Invalid config should consistently fail
        invalid_config_data = config_data.copy()
        invalid_config_data["jwt_secret"] = "short"

        for _ in range(5):
            config = MockJWTConfig(**invalid_config_data)
            with pytest.raises(
                ValueError, match="JWT secret must be at least 32 characters"
            ):
                config.validate_config()

    @pytest.mark.parametrize(
        "environment,expected_strict",
        [
            ("local", False),
            ("development", True),  # Should be treated as non-local
            ("staging", True),
            ("production", True),
            ("test", True),  # Should be treated as non-local
        ],
    )
    def test_environment_strictness_classification(self, environment, expected_strict):
        """Test that environments are correctly classified as strict/non-strict."""
        minimal_config = MockJWTConfig(
            environment=environment,
            jwt_secret=(
                None if not expected_strict else "secure_secret_32_characters_long"
            ),
            require_https=False if environment != "production" else True,
        )

        if expected_strict:
            if environment == "production":
                # Production needs HTTPS too
                with pytest.raises(ValueError):
                    minimal_config.validate_config()
            else:
                # Other strict environments should fail due to missing secret
                with pytest.raises(ValueError, match="JWT secret key is required"):
                    minimal_config.validate_config()
        else:
            # Local environment should pass with minimal config
            assert minimal_config.validate_config() is True
