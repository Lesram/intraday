"""
Integration tests for authentication, authorization, and RBAC.
Tests JWT authentication, API key authentication, and role-based access control.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from backend.api.main import app
from backend.config import get_settings
from backend.infra.security import create_access_token
from backend.infra.users import get_user_repository


@pytest.fixture
def mock_app_state():
    """Mock application state for testing."""
    mock_state = MagicMock()

    # Mock all the dependencies
    mock_state.risk_manager = MagicMock()
    mock_state.ensemble_model = MagicMock()
    mock_state.strategy_manager = MagicMock()
    mock_state.alpaca_client = MagicMock()
    mock_state.sentiment_analyzer = MagicMock()
    mock_state.feature_engineer = MagicMock()
    mock_state.model_manager = MagicMock()

    return mock_state


@pytest.fixture
def client(mock_app_state):
    """Test client fixture with mocked application state."""
    with patch("backend.api.main.app.state", mock_app_state):
        return TestClient(app)


@pytest.fixture
def settings():
    """Settings fixture with dev mode enabled."""
    return get_settings()


@pytest.fixture
def user_repo():
    """User repository fixture with test users."""
    repo = get_user_repository()
    # Clear any existing users and add test users
    repo._users.clear()

    # Create test users
    repo.create_user("admin", "admin123", ["admin", "trader"])
    repo.create_user("trader", "trader123", ["trader"])
    repo.create_user("viewer", "viewer123", ["read-only"])

    return repo


@pytest.fixture
def admin_token(user_repo):
    """Admin user JWT token."""
    return create_access_token("admin", ["admin", "trader"])


@pytest.fixture
def trader_token(user_repo):
    """Trader user JWT token."""
    return create_access_token("trader", ["trader"])


@pytest.fixture
def viewer_token(user_repo):
    """Read-only user JWT token."""
    return create_access_token("viewer", ["read-only"])


class TestAuthentication:
    """Test authentication endpoints."""

    @pytest.mark.unit
    def test_login_with_valid_credentials(self, client, user_repo):
        """Test successful login with valid credentials."""
        response = client.post(
            "/auth/login", data={"username": "admin", "password": "admin123"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["username"] == "admin"
        assert "admin" in data["user"]["roles"]
        assert "trader" in data["user"]["roles"]

    @pytest.mark.unit
    def test_login_with_invalid_credentials(self, client, user_repo):
        """Test login failure with invalid credentials."""
        response = client.post(
            "/auth/login", data={"username": "admin", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        data = response.json()
        # Check for error in either 'detail' or nested error structure
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "Invalid username or password" in error_message

    @pytest.mark.unit
    def test_login_with_nonexistent_user(self, client, user_repo):
        """Test login failure with non-existent user."""
        response = client.post(
            "/auth/login", data={"username": "nonexistent", "password": "password"}
        )

        assert response.status_code == 401
        data = response.json()
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "Invalid username or password" in error_message

    @pytest.mark.unit
    def test_token_validation_with_valid_token(self, client, admin_token):
        """Test token validation with valid JWT."""
        response = client.post(
            "/auth/token/validate", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is True
        assert data["user"]["username"] == "admin"
        assert "expires_at" in data

    @pytest.mark.unit
    def test_token_validation_without_token(self, client):
        """Test token validation without token."""
        response = client.post("/auth/token/validate")

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is False
        assert data["user"] is None

    @pytest.mark.unit
    def test_get_current_user_info(self, client, admin_token):
        """Test getting current user information."""
        response = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["username"] == "admin"
        assert data["authenticated"] is True
        assert "admin" in data["roles"]
        assert "trader" in data["roles"]

    @pytest.mark.unit
    def test_get_current_user_info_without_auth(self, client):
        """Test getting user info without authentication."""
        response = client.get("/auth/me")

        assert response.status_code == 401
        data = response.json()
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "Authentication required" in error_message


class TestAPIKeyAuthentication:
    """Test API key authentication."""

    @pytest.mark.unit
    def test_api_key_authentication(self, client):
        """Test API key authentication for machine-to-machine access."""
        # Use patch to mock the settings for the duration of this test
        with patch("backend.infra.security.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.api_keys = ["test-api-key-123"]
            mock_settings.security_dev_mode = False
            mock_get_settings.return_value = mock_settings

            response = client.get("/auth/me", headers={"X-API-Key": "test-api-key-123"})

            assert response.status_code == 200
            data = response.json()

            assert data["username"] == "api-client"
            assert "trader" in data["roles"]
            assert "api" in data["roles"]

    @pytest.mark.unit
    def test_invalid_api_key(self, client):
        """Test rejection of invalid API key."""
        with patch("backend.infra.security.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.api_keys = ["valid-key"]
            mock_settings.security_dev_mode = False
            mock_get_settings.return_value = mock_settings

            response = client.get("/auth/me", headers={"X-API-Key": "invalid-key"})

            assert response.status_code == 401


class TestDevMode:
    """Test development mode bypass."""

    @pytest.mark.unit
    def test_dev_mode_bypass(self, client):
        """Test development mode authentication bypass."""
        with patch("backend.infra.security.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.security_dev_mode = True
            mock_get_settings.return_value = mock_settings

            response = client.get("/auth/me", headers={"X-Dev-Bypass": "true"})

            assert response.status_code == 200
            data = response.json()

            assert data["username"] == "dev-user"
            assert "admin" in data["roles"]
            assert "trader" in data["roles"]


class TestRoleBasedAccessControl:
    """Test role-based access control on protected endpoints."""

    @pytest.mark.unit
    def test_trader_can_access_trading_endpoints(self, client, trader_token):
        """Test that trader role can access trading endpoints."""
        response = client.get(
            "/api/v1/trades/history",
            headers={"Authorization": f"Bearer {trader_token}"},
        )

        assert response.status_code == 200
        assert "trades" in response.json()

    @pytest.mark.unit
    def test_trader_can_access_model_status(self, client, trader_token):
        """Test that trader role can access model status."""
        response = client.get(
            "/api/v1/models/status", headers={"Authorization": f"Bearer {trader_token}"}
        )

        assert response.status_code == 200
        assert "models" in response.json()

    @pytest.mark.unit
    def test_trader_can_access_risk_metrics(self, client, trader_token):
        """Test that trader role can access risk metrics."""
        response = client.get(
            "/api/v1/risk/metrics", headers={"Authorization": f"Bearer {trader_token}"}
        )

        assert response.status_code == 200
        assert "portfolio_risk" in response.json()

    @pytest.mark.unit
    def test_trader_cannot_access_admin_endpoints(self, client, trader_token):
        """Test that trader role cannot access admin-only endpoints."""
        # Try to trigger model training (admin only)
        response = client.post(
            "/api/v1/models/train", headers={"Authorization": f"Bearer {trader_token}"}
        )

        assert response.status_code == 403
        data = response.json()
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "Insufficient permissions" in error_message

    @pytest.mark.unit
    def test_trader_cannot_update_risk_limits(self, client, trader_token):
        """Test that trader role cannot update risk limits."""
        response = client.put(
            "/api/v1/risk/limits",
            json={"max_position_size": 20000.0},
            headers={"Authorization": f"Bearer {trader_token}"},
        )

        assert response.status_code == 403
        data = response.json()
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "Insufficient permissions" in error_message

    @pytest.mark.unit
    def test_admin_can_access_all_endpoints(self, client, admin_token):
        """Test that admin role can access all endpoints."""
        # Test trading endpoints
        response = client.get(
            "/api/v1/trades/history", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

        # Test model training (admin only)
        response = client.post(
            "/api/v1/models/train", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

        # Test risk limits update (admin only)
        response = client.put(
            "/api/v1/risk/limits",
            json={"max_position_size": 20000.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.unit
    def test_viewer_cannot_access_protected_endpoints(self, client, viewer_token):
        """Test that read-only role cannot access any protected endpoints."""
        # Try trading endpoints
        response = client.get(
            "/api/v1/trades/history",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

        # Try model endpoints
        response = client.get(
            "/api/v1/models/status", headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403

        # Try risk endpoints
        response = client.get(
            "/api/v1/risk/metrics", headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403


class TestUnauthorizedAccess:
    """Test unauthorized access to protected endpoints."""

    @pytest.mark.unit
    def test_trading_endpoints_require_authentication(self, client):
        """Test that trading endpoints reject unauthenticated requests."""
        endpoints = [
            ("GET", "/api/v1/trades/history"),
            ("POST", "/api/v1/trades/execute"),
        ]

        for method, endpoint in endpoints:
            response = getattr(client, method.lower())(endpoint)
            assert response.status_code == 401
            data = response.json()
            error_message = data.get("detail") or data.get("error", {}).get(
                "message", ""
            )
            assert "Authentication required" in error_message

    @pytest.mark.unit
    def test_model_endpoints_require_authentication(self, client):
        """Test that model endpoints reject unauthenticated requests."""
        endpoints = [
            ("GET", "/api/v1/models/status"),
            ("POST", "/api/v1/models/train"),
        ]

        for method, endpoint in endpoints:
            response = getattr(client, method.lower())(endpoint)
            assert response.status_code == 401

    @pytest.mark.unit
    def test_risk_endpoints_require_authentication(self, client):
        """Test that risk endpoints reject unauthenticated requests."""
        endpoints = [
            ("GET", "/api/v1/risk/metrics"),
            ("PUT", "/api/v1/risk/limits"),
        ]

        for method, endpoint in endpoints:
            response = getattr(client, method.lower())(endpoint)
            assert response.status_code == 401


class TestPublicEndpoints:
    """Test that public endpoints remain accessible."""

    @pytest.mark.unit
    def test_health_check_public(self, client):
        """Test that health check is publicly accessible."""
        response = client.get("/health")
        assert response.status_code == 200

    @pytest.mark.unit
    def test_system_status_public(self, client):
        """Test that system status is publicly accessible."""
        response = client.get("/api/v1/system/status")
        assert response.status_code == 200

    @pytest.mark.unit
    def test_basic_signals_public(self, client):
        """Test that basic signals are publicly accessible."""
        response = client.get("/api/v1/signals/AAPL")
        assert response.status_code == 200

    @pytest.mark.unit
    def test_metrics_public(self, client):
        """Test that metrics endpoint is publicly accessible."""
        # This might fail if Prometheus is not available, but that's expected
        response = client.get("/metrics")
        # Should be either 200 (success) or 501 (not implemented)
        assert response.status_code in [200, 501]


class TestTokenSecurity:
    """Test JWT token security features."""

    @pytest.mark.unit
    def test_expired_token_rejection(self, client, user_repo):
        """Test that expired tokens are rejected."""
        # Create a token that expires very quickly
        expired_token = create_access_token("admin", ["admin"], expires_minutes=-1)

        response = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
        data = response.json()
        error_message = data.get("detail") or data.get("error", {}).get("message", "")
        assert "expired" in error_message.lower()

    @pytest.mark.unit
    def test_malformed_token_rejection(self, client):
        """Test that malformed tokens are rejected."""
        response = client.get(
            "/auth/me", headers={"Authorization": "Bearer invalid.token.format"}
        )

        assert response.status_code == 401

    @pytest.mark.unit
    def test_missing_bearer_prefix(self, client, admin_token):
        """Test that tokens without Bearer prefix are rejected."""
        response = client.get(
            "/auth/me",
            headers={"Authorization": admin_token},  # Missing "Bearer " prefix
        )

        assert response.status_code == 401
