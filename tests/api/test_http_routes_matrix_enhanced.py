"""
Enhanced comprehensive HTTP routes matrix testing with table-driven parametrization.
Tests all core routes for happy path, authentication, validation, and error scenarios.
Focuses on high-yield coverage improvements using create_app() + FakeJwtVerifier.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
import json

from backend.api.factory import create_app
from tests.helpers.fake_jwt import FakeJwtVerifier, create_test_token


# Enhanced test data tables for comprehensive parametrized testing
CORE_ROUTES_DATA = [
    # (method, path, requires_auth, body_data, expected_success_status, description)
    ("GET", "/", False, None, 200, "Root endpoint"),
    ("GET", "/health", False, None, 200, "Health check endpoint"),
    ("GET", "/readyz", False, None, 503, "Readiness probe - not ready by default"),
    ("GET", "/docs", False, None, 200, "API documentation"),
    ("GET", "/redoc", False, None, 200, "ReDoc documentation"),
    ("GET", "/openapi.json", False, None, 200, "OpenAPI schema"),
    ("GET", "/metrics", False, None, 200, "Prometheus metrics"),
    
    # Auth endpoints
    ("POST", "/auth/login", False, None, 200, "Login endpoint with form data"),
    ("POST", "/auth/register", False, None, 201, "Registration endpoint"),
    
    # Protected API endpoints  
    ("GET", "/portfolio/positions", True, None, 200, "Portfolio positions"),
    ("POST", "/orders", True, None, 200, "Create order"),
    ("GET", "/orders/test-123", True, None, 200, "Get specific order"),
    ("POST", "/orders/test-123/cancel", True, None, 200, "Cancel order"),
    ("GET", "/signals", True, None, 200, "Get trading signals"),
    ("GET", "/signals/AAPL", True, None, 200, "Get symbol-specific signals"),
    ("POST", "/models/train", True, None, 200, "Train ML model"),
    ("GET", "/models/status", True, None, 200, "Get model status"),
    ("PUT", "/risk/limits", True, None, 200, "Update risk limits"),
    ("GET", "/risk/metrics", True, None, 200, "Get risk metrics"),
]

# Test data for invalid payloads and validation errors
INVALID_PAYLOAD_DATA = [
    # (method, path, invalid_body, expected_status, description)
    ("POST", "/auth/register", {"email": "invalid-email"}, 422, "Invalid email format"),
    ("POST", "/auth/register", {"password": "short"}, 422, "Password too short"),
    ("POST", "/auth/register", {}, 422, "Missing required fields"),
    ("POST", "/orders", {"symbol": "", "qty": -1}, 422, "Invalid order parameters"),
    ("POST", "/models/train", {"invalid_field": "value"}, 422, "Invalid model training params"),
    ("PUT", "/risk/limits", {"max_position_size": -1000}, 422, "Invalid risk limits"),
]

# Routes that should trigger authentication errors
PROTECTED_ROUTES_DATA = [
    # (method, path, expected_auth_status)
    ("GET", "/portfolio/positions", 401),
    ("POST", "/orders", 401),
    ("GET", "/orders/test-123", 401),
    ("POST", "/orders/test-123/cancel", 401),
    ("GET", "/signals", 401),
    ("POST", "/models/train", 401),
    ("PUT", "/risk/limits", 401),
    ("GET", "/risk/metrics", 401),
]


@pytest.fixture
def test_app():
    """Create FastAPI test app with fake JWT verifier."""
    registry = CollectorRegistry()
    app = create_app(registry=registry)
    
    # Replace JWT verifier with fake one for auth testing
    fake_jwt = FakeJwtVerifier()
    
    # Mock dependencies for deterministic testing
    with patch('backend.api.routes.orders.get_order_service') as mock_order_service, \
         patch('backend.api.routes.signals.get_signal_service') as mock_signal_service, \
         patch('backend.api.routes.models.get_model_service') as mock_model_service, \
         patch('backend.api.routes.risk.get_risk_service') as mock_risk_service, \
         patch('backend.api.portfolio.get_portfolio_service') as mock_portfolio_service:
        
        # Configure mock services with success responses
        mock_order_service.return_value = MagicMock()
        mock_order_service.return_value.create_order = AsyncMock(return_value={"order_id": "test-123", "status": "submitted"})
        mock_order_service.return_value.get_order = AsyncMock(return_value={"order_id": "test-123", "status": "filled"})
        mock_order_service.return_value.cancel_order = AsyncMock(return_value={"order_id": "test-123", "status": "canceled"})
        
        mock_signal_service.return_value = MagicMock()
        mock_signal_service.return_value.get_signals = AsyncMock(return_value={"signals": [{"symbol": "AAPL", "signal": "buy"}]})
        mock_signal_service.return_value.get_symbol_signals = AsyncMock(return_value={"symbol": "AAPL", "signals": []})
        
        mock_model_service.return_value = MagicMock()
        mock_model_service.return_value.train_model = AsyncMock(return_value={"model_id": "test-model", "status": "training"})
        mock_model_service.return_value.get_status = AsyncMock(return_value={"models": []})
        
        mock_risk_service.return_value = MagicMock()
        mock_risk_service.return_value.update_limits = AsyncMock(return_value={"limits": {"max_position_size": 1000}})
        mock_risk_service.return_value.get_metrics = AsyncMock(return_value={"risk_metrics": {"var": 0.05}})
        
        mock_portfolio_service.return_value = MagicMock()
        mock_portfolio_service.return_value.get_positions = AsyncMock(return_value={"positions": []})
        
        # Store mocks in app state for test access
        app.state.test_mocks = {
            'order_service': mock_order_service,
            'signal_service': mock_signal_service,
            'model_service': mock_model_service,
            'risk_service': mock_risk_service,
            'portfolio_service': mock_portfolio_service,
        }
        
        yield app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def auth_headers():
    """Create valid auth headers with fake JWT token."""
    token = create_test_token(sub="testuser", roles=["user", "trader"])
    return {"Authorization": f"Bearer {token}"}


class TestEnhancedRoutesMatrix:
    """Enhanced table-driven tests for comprehensive HTTP route coverage."""
    
    @pytest.mark.parametrize("method,path,requires_auth,body,expected_status,description", CORE_ROUTES_DATA)
    def test_route_responses(self, client, auth_headers, method, path, requires_auth, body, expected_status, description):
        """Test route responses with comprehensive status assertions."""
        # Prepare headers and body
        headers = auth_headers if requires_auth else {}
        test_body = body or {}
        
        # Handle special cases for form data
        if path == "/auth/login":
            # Login expects form data
            response = client.post(path, data={"username": "testuser", "password": "testpass"}, headers=headers)
        elif path == "/auth/register":
            # Registration expects JSON
            response = client.post(path, json={"email": "test@example.com", "password": "testpass123"}, headers=headers)
        elif method == "GET":
            response = client.get(path, headers=headers)
        elif method == "POST":
            response = client.post(path, json=test_body, headers=headers)
        elif method == "PUT":
            response = client.put(path, json=test_body, headers=headers)
        else:
            pytest.skip(f"Unsupported method: {method}")
        
        # Assert expected status with descriptive error messages
        assert response.status_code == expected_status, (
            f"Route {method} {path} ({description}): "
            f"expected {expected_status}, got {response.status_code}. "
            f"Response: {response.text[:200]}"
        )

    @pytest.mark.parametrize("method,path,expected_auth_status", PROTECTED_ROUTES_DATA)
    def test_protected_routes_authentication(self, client, method, path, expected_auth_status):
        """Test that protected routes properly enforce authentication."""
        # Make request without auth headers
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        elif method == "PUT":
            response = client.put(path, json={})
        else:
            pytest.skip(f"Unsupported method: {method}")
        
        assert response.status_code == expected_auth_status, (
            f"Protected route {method} {path} should return {expected_auth_status} without auth, "
            f"got {response.status_code}"
        )

    @pytest.mark.parametrize("method,path,invalid_body,expected_status,description", INVALID_PAYLOAD_DATA)
    def test_request_validation_errors(self, client, auth_headers, method, path, invalid_body, expected_status, description):
        """Test request validation returns proper 422 errors."""
        headers = auth_headers if path.startswith(("/portfolio", "/orders", "/signals", "/models", "/risk")) else {}
        
        if method == "POST":
            response = client.post(path, json=invalid_body, headers=headers)
        elif method == "PUT":
            response = client.put(path, json=invalid_body, headers=headers)
        else:
            pytest.skip(f"Validation test not applicable to {method}")
        
        assert response.status_code == expected_status, (
            f"Validation test {description} for {method} {path}: "
            f"expected {expected_status}, got {response.status_code}. "
            f"Response: {response.text[:200]}"
        )

    def test_forced_500_error(self, client):
        """Test forced 500 error via monkeypatch."""
        with patch('backend.api.routes.system.get_health_status', side_effect=Exception("Forced error")):
            response = client.get("/health")
            assert response.status_code == 500, f"Expected forced 500 error, got {response.status_code}"


class TestPrometheusMetricsIntegration:
    """Test Prometheus metrics collection and route template labels."""
    
    def test_metrics_endpoint_content(self, client):
        """Test metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")
        
        if response.status_code == 200:
            content = response.text
            # Assert basic Prometheus metrics format
            assert "# HELP" in content or "# TYPE" in content, "Should contain Prometheus metric metadata"
        else:
            # If metrics unavailable, should return structured error
            assert response.status_code in [501, 503], "Metrics endpoint should return 501/503 if unavailable"

    @pytest.mark.parametrize("method,path,requires_auth,body,expected_success_status,description", 
                             CORE_ROUTES_DATA[:5])  # Test subset for performance
    def test_route_metrics_collection(self, client, auth_headers, method, path, requires_auth, body, expected_success_status, description):
        """Test that route metrics are collected with proper template labels."""
        # Make initial request to generate metrics
        headers = auth_headers if requires_auth else {}
        
        if method == "GET":
            client.get(path, headers=headers)
        elif method == "POST" and path == "/auth/login":
            client.post(path, data={"username": "test", "password": "test"}, headers=headers)
        elif method == "POST":
            client.post(path, json=body or {}, headers=headers)
            
        # Check metrics collection
        metrics_response = client.get("/metrics")
        if metrics_response.status_code == 200:
            metrics_content = metrics_response.text
            # Look for route-specific metrics or general HTTP metrics
            route_template = path.replace("{", "").replace("}", "")  # Normalize path template
            metrics_found = (
                f'path="{route_template}"' in metrics_content or
                f'route="{path}"' in metrics_content or
                "http_requests_total" in metrics_content or
                "http_request_duration_seconds" in metrics_content
            )
            assert metrics_found, f"No route metrics found for {method} {path} in: {metrics_content[:500]}..."

    def test_http_request_duration_buckets_present(self, client):
        """Test that HTTP request duration histogram buckets are present."""
        # Make a request to generate metrics
        client.get("/health")
        
        response = client.get("/metrics")
        if response.status_code == 200:
            content = response.text
            # Look for histogram bucket indicators
            buckets_found = content.count('le="') + content.count('_bucket{')
            assert buckets_found >= 2, f"Expected histogram bucket metrics, found {buckets_found} indicators"


class TestRouteErrorHandling:
    """Test error handling across different routes."""
    
    def test_large_payload_handling(self, client, auth_headers):
        """Test handling of large JSON payloads."""
        large_payload = {"data": "x" * 10000}  # 10KB payload
        
        response = client.post("/orders", json=large_payload, headers=auth_headers)
        assert response.status_code in [200, 413, 422], f"Expected success or payload too large, got {response.status_code}"


class TestRouteParameterValidation:
    """Test URL parameter validation across routes."""
    
    @pytest.mark.parametrize("order_id", ["123", "test-order-456", "very-long-order-id" * 5])
    def test_order_id_parameter_validation(self, client, auth_headers, order_id):
        """Test order ID parameter validation."""
        response = client.get(f"/orders/{order_id}", headers=auth_headers)
        assert response.status_code in [200, 400, 404, 422], f"Expected valid response for order_id '{order_id}', got {response.status_code}"
