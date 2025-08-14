"""
High-yield HTTP routes matrix testing with comprehensive parametrized coverage.
Tests HTTP status codes (200, 401, 403, 422, 500), authentication flows, 
validation errors, and Prometheus metrics (http_requests_total, http_request_duration_seconds).
Windows-friendly deterministic testing with create_app() + FakeJwtVerifier pattern.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, Histogram
import time

from backend.api.factory import create_app


def create_test_app():
    """Create test app with FakeJwtVerifier and mocked dependencies."""
    # Create app with isolated metrics registry
    app = create_app(registry=CollectorRegistry())
    
    # Add fake JWT verifier directly to app state
    app.state.jwt_verifier = FakeJwtVerifier()
    
    # Mock database session factory if needed
    app.state.db_sessionmaker = AsyncMock()
    
    # Mock WebSocket manager 
    mock_ws_manager = MagicMock()
    app.state.ws_manager = mock_ws_manager
    
    yield app


"""
High-yield HTTP routes matrix testing with comprehensive parametrized coverage.
Tests all routes: 200 success, 401/403 auth, 422 validation, 500 errors via monkeypatch.
Includes Prometheus route-template labels and latency bucket validation.
Uses create_app() + FakeJwtVerifier for deterministic Windows-friendly testing.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, Mock
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, REGISTRY, generate_latest
import time
import json
import re

from backend.api.factory import create_app
from tests.helpers.fake_jwt import FakeJwtVerifier, create_test_token


# Comprehensive routes data for matrix testing
COMPREHENSIVE_ROUTES_DATA = [
    # (method, path, requires_auth, body_data, expected_success_status, description, route_template)
    ("GET", "/", False, None, 200, "Root endpoint", "/"),
    ("GET", "/health", False, None, 200, "Health check endpoint", "/health"),
    ("GET", "/readyz", False, None, 503, "Readiness probe", "/readyz"),
    ("GET", "/docs", False, None, 200, "API documentation", "/docs"),
    ("GET", "/redoc", False, None, 200, "ReDoc documentation", "/redoc"),
    ("GET", "/openapi.json", False, None, 200, "OpenAPI schema", "/openapi.json"),
    ("GET", "/metrics", False, None, 200, "Prometheus metrics", "/metrics"),
    
    # Auth endpoints
    ("POST", "/auth/login", False, {"username": "testuser", "password": "testpass"}, 200, "Login endpoint", "/auth/login"),
    ("POST", "/auth/register", False, {"email": "test@example.com", "password": "testpass123"}, 201, "Registration endpoint", "/auth/register"),
    
    # Protected API endpoints with real route templates
    ("GET", "/portfolio/positions", True, None, 200, "Portfolio positions", "/portfolio/positions"),
    ("POST", "/orders", True, {"symbol": "AAPL", "side": "buy", "qty": 100}, 200, "Create order", "/orders"),
    ("GET", "/orders/test-123", True, None, 200, "Get specific order", "/orders/{order_id}"),
    ("POST", "/orders/test-123/cancel", True, None, 200, "Cancel order", "/orders/{order_id}/cancel"),
    ("GET", "/signals", True, None, 200, "Get trading signals", "/signals"),
    ("GET", "/signals/AAPL", True, None, 200, "Get symbol signals", "/signals/{symbol}"),
    ("POST", "/models/train", True, {"model_type": "regression"}, 200, "Train ML model", "/models/train"),
    ("GET", "/models/status", True, None, 200, "Get model status", "/models/status"),
    ("PUT", "/risk/limits", True, {"max_position": 10000}, 200, "Update risk limits", "/risk/limits"),
    ("GET", "/risk/metrics", True, None, 200, "Get risk metrics", "/risk/metrics"),
    ("GET", "/portfolio/performance", True, None, 200, "Portfolio performance", "/portfolio/performance"),
    ("GET", "/market/data/AAPL", True, None, 200, "Market data", "/market/data/{symbol}"),
    ("POST", "/strategies/backtest", True, {"strategy": "mean_reversion"}, 200, "Run backtest", "/strategies/backtest"),
    ("GET", "/audit/logs", True, None, 200, "Audit logs", "/audit/logs"),
    ("POST", "/notifications/webhook", False, {"event": "order_filled"}, 200, "Webhook", "/notifications/webhook"),
]

# Validation error test data  
VALIDATION_ERROR_DATA = [
    # (method, path, invalid_body, expected_status, error_field, description)
    ("POST", "/auth/register", {"email": "invalid-email"}, 422, "email", "Invalid email format"),
    ("POST", "/auth/register", {"password": "short"}, 422, "password", "Password too short"),
    ("POST", "/orders", {"symbol": "INVALID_SYMBOL_TOO_LONG", "side": "buy"}, 422, "symbol", "Invalid symbol"),
    ("POST", "/orders", {"symbol": "AAPL", "side": "invalid", "qty": 100}, 422, "side", "Invalid order side"),
    ("POST", "/orders", {"symbol": "AAPL", "side": "buy", "qty": -100}, 422, "qty", "Negative quantity"),
    ("PUT", "/risk/limits", {"max_position": "not_a_number"}, 422, "max_position", "Invalid number format"),
    ("POST", "/models/train", {"model_type": "invalid_model"}, 422, "model_type", "Invalid model type"),
    ("POST", "/auth/register", {}, 422, "missing_fields", "Missing required fields"),
]

# Error forcing data for 500 testing
ERROR_FORCE_ROUTES = [
    # (method, path, monkeypatch_target, exception_to_raise, description)
    ("GET", "/portfolio/positions", "backend.api.portfolio.get_positions", Exception("Database error"), "Portfolio DB error"),
    ("POST", "/orders", "backend.services.order_service.submit_order", ConnectionError("Broker unreachable"), "Order service error"),
    ("GET", "/signals", "backend.services.signal_service.get_signals", TimeoutError("ML model timeout"), "Signal service timeout"),
    ("GET", "/risk/metrics", "backend.risk.risk_calculator.calculate_metrics", ValueError("Invalid risk data"), "Risk calculation error"),
]


# Test fixtures
@pytest.fixture
def isolated_prometheus_registry():
    """Isolated Prometheus registry for metrics testing."""
    registry = CollectorRegistry()
    with patch('prometheus_client.REGISTRY', registry):
        yield registry


@pytest.fixture
def test_app():
    """Create test app with FakeJwtVerifier and mocked dependencies."""
    # Create app with isolated metrics registry
    app = create_app(registry=CollectorRegistry())
    
    # Add fake JWT verifier directly to app state
    app.state.jwt_verifier = FakeJwtVerifier()
    
    # Mock database session factory if needed
    app.state.db_sessionmaker = AsyncMock()
    
    # Mock WebSocket manager 
    mock_ws_manager = MagicMock()
    app.state.ws_manager = mock_ws_manager
    
    yield app


@pytest.fixture
def auth_client(test_app):
    """Test client with authentication headers."""
    client = TestClient(test_app)
    token = create_test_token(user_id="test-user-123", email="test@example.com")
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


@pytest.fixture
def unauth_client(test_app):
    """Test client without authentication headers."""
    return TestClient(test_app)


class TestHTTPRoutesMatrix:
    """Comprehensive HTTP routes matrix testing class."""

    @pytest.mark.parametrize("method,path,requires_auth,body,expected_status,description,route_template", 
                             COMPREHENSIVE_ROUTES_DATA)
    def test_routes_success_scenarios(self, method, path, requires_auth, body, expected_status, 
                                    description, route_template, auth_client, unauth_client):
        """Test all routes for successful responses (200, 201, etc.)."""
        client = auth_client if requires_auth else unauth_client
        
        # Make HTTP request based on method
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            if body:
                response = client.post(path, json=body)
            else:
                response = client.post(path)
        elif method == "PUT":
            response = client.put(path, json=body or {})
        else:
            pytest.skip(f"Unsupported method: {method}")
        
        # Assert expected success status
        assert response.status_code == expected_status, f"{description}: Expected {expected_status}, got {response.status_code}. Response: {response.text[:200]}"

    @pytest.mark.parametrize("method,path,requires_auth,body,expected_status,description,route_template", 
                             [route for route in COMPREHENSIVE_ROUTES_DATA if route[2]])  # Only protected routes
    def test_routes_authentication_required(self, method, path, requires_auth, body, expected_status, 
                                          description, route_template, unauth_client):
        """Test protected routes return 401 without authentication."""
        # Make request without authentication
        if method == "GET":
            response = unauth_client.get(path)
        elif method == "POST":
            response = unauth_client.post(path, json=body or {})
        elif method == "PUT":
            response = unauth_client.put(path, json=body or {})
        else:
            pytest.skip(f"Unsupported method: {method}")
        
        # Should return 401 Unauthorized
        assert response.status_code == 401, f"{description}: Expected 401 (Unauthorized), got {response.status_code}"
        
        # Verify error response format
        error_response = response.json()
        assert "detail" in error_response
        assert "unauthorized" in error_response["detail"].lower() or "not authenticated" in error_response["detail"].lower()

    @pytest.mark.parametrize("method,path,invalid_body,expected_status,error_field,description", 
                             VALIDATION_ERROR_DATA)
    def test_routes_validation_errors(self, method, path, invalid_body, expected_status, error_field, 
                                    description, auth_client):
        """Test routes return 422 for validation errors."""
        # Make request with invalid payload
        if method == "POST":
            response = auth_client.post(path, json=invalid_body)
        elif method == "PUT":
            response = auth_client.put(path, json=invalid_body)
        else:
            pytest.skip(f"Validation testing not applicable for {method}")
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == expected_status, f"{description}: Expected {expected_status}, got {response.status_code}"
        
        # Verify validation error format
        error_response = response.json()
        assert "detail" in error_response
        
        # Check that error details contain field information
        if isinstance(error_response["detail"], list):
            field_errors = [error.get("field", error.get("loc", [""])[0]) for error in error_response["detail"]]
            assert any(error_field in str(field).lower() for field in field_errors), f"Expected field '{error_field}' in validation errors"

    @pytest.mark.parametrize("method,path,monkeypatch_target,exception_to_raise,description", 
                             ERROR_FORCE_ROUTES)
    def test_routes_forced_500_errors(self, method, path, monkeypatch_target, exception_to_raise, 
                                    description, monkeypatch, auth_client):
        """Test routes return 500 when underlying services raise exceptions."""
        # Monkeypatch the target function to raise an exception
        with patch(monkeypatch_target, side_effect=exception_to_raise):
            # Make request
            if method == "GET":
                response = auth_client.get(path)
            elif method == "POST":
                response = auth_client.post(path, json={})
            else:
                pytest.skip(f"Error forcing not implemented for {method}")
            
            # Should return 500 Internal Server Error
            assert response.status_code == 500, f"{description}: Expected 500, got {response.status_code}"
            
            # Verify error response structure
            error_response = response.json()
            assert "detail" in error_response
            assert "internal server error" in error_response["detail"].lower() or "server error" in error_response["detail"].lower()

    def test_prometheus_route_template_labels(self, test_app, isolated_prometheus_registry):
        """Test Prometheus metrics include correct route template labels."""
        client = TestClient(test_app)
        
        # Make requests to different routes
        test_routes = [
            ("GET", "/", "/"),
            ("GET", "/health", "/health"), 
            ("GET", "/orders/test-123", "/orders/{order_id}"),
            ("GET", "/signals/AAPL", "/signals/{symbol}"),
        ]
        
        for method, path, expected_template in test_routes:
            response = client.get(path)
            # Don't assert status - just generate metrics
        
        # Get metrics output
        metrics_output = generate_latest(isolated_prometheus_registry).decode('utf-8')
        
        # Verify route template labels exist
        for method, path, expected_template in test_routes:
            # Look for http_requests_total metric with route template
            route_label_pattern = rf'http_requests_total.*route="{re.escape(expected_template)}"'
            assert re.search(route_label_pattern, metrics_output), f"Route template '{expected_template}' not found in metrics"

    def test_prometheus_latency_buckets(self, test_app, isolated_prometheus_registry):
        """Test Prometheus latency histograms include proper buckets.""" 
        client = TestClient(test_app)
        
        # Make some requests to generate latency metrics
        for _ in range(5):
            client.get("/")
            client.get("/health")
            time.sleep(0.01)  # Small delay to generate measurable latency
        
        # Get metrics output
        metrics_output = generate_latest(isolated_prometheus_registry).decode('utf-8')
        
        # Verify latency histogram buckets
        expected_buckets = ["0.005", "0.01", "0.025", "0.05", "0.075", "0.1", "0.25", "0.5", "0.75", "1.0", "2.5", "5.0", "7.5", "10.0"]
        
        for bucket in expected_buckets:
            bucket_pattern = rf'http_request_duration_seconds_bucket.*le="{bucket}"'
            assert re.search(bucket_pattern, metrics_output), f"Latency bucket le='{bucket}' not found in metrics"
        
        # Verify +Inf bucket exists
        inf_pattern = r'http_request_duration_seconds_bucket.*le="\+Inf"'
        assert re.search(inf_pattern, metrics_output), "Latency bucket le='+Inf' not found in metrics"

    def test_prometheus_metrics_endpoint_comprehensive(self, test_app):
        """Test /metrics endpoint returns comprehensive Prometheus metrics."""
        client = TestClient(test_app)
        
        # Make requests to generate various metrics
        client.get("/")
        client.get("/health") 
        client.get("/nonexistent", allow_redirects=False)  # Generate 404
        
        # Get metrics
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
        
        metrics_content = response.text
        
        # Verify essential metrics exist
        essential_metrics = [
            "http_requests_total",
            "http_request_duration_seconds", 
            "process_cpu_seconds_total",
            "process_virtual_memory_bytes",
            "process_resident_memory_bytes",
        ]
        
        for metric in essential_metrics:
            assert metric in metrics_content, f"Essential metric '{metric}' not found in /metrics output"
        
        # Verify metric labels
        assert 'method="GET"' in metrics_content
        assert 'status="200"' in metrics_content
        assert 'status="404"' in metrics_content

    @pytest.mark.parametrize("method,path,requires_auth,body,expected_status,description,route_template", 
                             COMPREHENSIVE_ROUTES_DATA[:10])  # Test subset for performance
    def test_routes_response_time_tracking(self, method, path, requires_auth, body, expected_status, 
                                         description, route_template, auth_client, unauth_client):
        """Test that routes complete within reasonable time limits."""
        client = auth_client if requires_auth else unauth_client
        
        # Measure response time
        start_time = time.time()
        
        if method == "GET":
            response = client.get(path, timeout=10.0)
        elif method == "POST":
            response = client.post(path, json=body or {}, timeout=10.0)
        elif method == "PUT":
            response = client.put(path, json=body or {}, timeout=10.0)
        else:
            pytest.skip(f"Unsupported method: {method}")
        
        response_time = time.time() - start_time
        
        # Assert reasonable response time (under 5 seconds for most operations)
        max_response_time = 5.0
        if "models/train" in path or "strategies/backtest" in path:
            max_response_time = 10.0  # Allow longer time for ML operations
        
        assert response_time < max_response_time, f"{description}: Response took {response_time:.2f}s, expected < {max_response_time}s"

    def test_routes_concurrent_access(self, test_app):
        """Test routes handle concurrent access properly."""
        import threading
        import queue
        
        client = TestClient(test_app)
        results = queue.Queue()
        
        def make_request():
            try:
                response = client.get("/health")
                results.put(("success", response.status_code))
            except Exception as e:
                results.put(("error", str(e)))
        
        # Create multiple threads
        threads = []
        num_concurrent = 10
        
        for _ in range(num_concurrent):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5.0)
        
        # Verify results
        success_count = 0
        while not results.empty():
            result_type, result_value = results.get()
            if result_type == "success":
                success_count += 1
                assert result_value == 200
        
        # All concurrent requests should succeed
        assert success_count == num_concurrent, f"Only {success_count}/{num_concurrent} concurrent requests succeeded"


# Helper function to mock database dependency
async def get_db_session():
    """Placeholder for database session dependency."""
    pass
