"""
Test route registration to ensure all endpoints are properly registered via create_app().
Validates that the factory-based app creation includes all expected routes.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.factory import create_app


class TestRouteRegistration:
    """Test that all expected routes are registered correctly via create_app()."""

    def test_factory_creates_app_with_all_routes(self):
        """Test that create_app() registers all expected routes"""
        app = create_app()
        client = TestClient(app)
        
        # Test system routes
        response = client.get("/")
        assert response.status_code == 200, f"Root endpoint failed: {response.text}"
        
        response = client.get("/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.text}"
        
        response = client.get("/healthz")
        assert response.status_code == 200, f"Liveness probe failed: {response.text}"
        
        response = client.get("/metrics")
        # Should return 200 or 501 (if prometheus not available)
        assert response.status_code in [200, 501], f"Metrics endpoint failed: {response.text}"

    def test_auth_routes_registered(self):
        """Test that authentication routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test auth register endpoint exists
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        # Should process the request (not return 404)
        assert response.status_code != 404, f"Auth register route not found: {response.text}"
        
        # Test auth login endpoint exists
        response = client.post("/auth/login", data={
            "username": "test",
            "password": "test"
        })
        # Should process the request (not return 404)
        assert response.status_code != 404, f"Auth login route not found: {response.text}"

    def test_portfolio_routes_registered(self):
        """Test that portfolio routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test positions endpoint exists
        response = client.get("/api/v1/positions")
        # Should process the request (not return 404)
        assert response.status_code != 404, f"Positions route not found: {response.text}"

    def test_orders_routes_registered(self):
        """Test that order routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test order submission endpoint exists
        response = client.post("/api/v1/orders/submit", json={
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 10
        })
        # Should process the request (not return 404), might return 401/422 for auth/validation
        assert response.status_code != 404, f"Order submit route not found: {response.text}"

    def test_signals_routes_registered(self):
        """Test that signal routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test signals endpoint exists
        response = client.get("/api/v1/signals/AAPL")
        # Should process the request (not return 404)
        assert response.status_code != 404, f"Signals route not found: {response.text}"

    def test_models_routes_registered(self):
        """Test that ML model routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test model status endpoint exists
        response = client.get("/api/v1/models/status")
        # Should process the request (not return 404), might return 401 for auth
        assert response.status_code != 404, f"Model status route not found: {response.text}"

    def test_risk_routes_registered(self):
        """Test that risk management routes are registered"""
        app = create_app()
        client = TestClient(app)
        
        # Test risk limits endpoint exists
        response = client.get("/api/v1/risk/limits")
        # Should process the request (not return 404), might return 401 for auth
        assert response.status_code != 404, f"Risk limits route not found: {response.text}"

    def test_readiness_probe_registered(self):
        """Test that readiness probe is registered in both places"""
        app = create_app()
        client = TestClient(app)
        
        # Test /readyz from system router
        response = client.get("/readyz")
        # Should process the request (not return 404)
        assert response.status_code != 404, f"Readyz route not found: {response.text}"
        
        # The response might be 503 (not ready) or 200 (ready) depending on app state
        assert response.status_code in [200, 503], f"Readyz unexpected status: {response.status_code}"

    def test_all_expected_paths_exist(self):
        """Comprehensive test that all expected paths are registered"""
        app = create_app()
        
        # Get all registered routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        # Expected core paths
        expected_paths = [
            "/",
            "/health", 
            "/healthz",
            "/readyz", 
            "/metrics",
            "/auth/register",
            "/auth/login", 
            "/api/v1/positions",
            "/api/v1/orders/submit",
            "/api/v1/orders/{order_id}",
            "/api/v1/signals/{symbol}",
            "/api/v1/models/status",
            "/api/v1/risk/limits"
        ]
        
        missing_paths = []
        for expected in expected_paths:
            if expected not in routes:
                missing_paths.append(expected)
        
        assert not missing_paths, f"Missing expected routes: {missing_paths}. Registered routes: {routes}"

    def test_no_duplicate_routes(self):
        """Test that there are no duplicate route registrations"""
        app = create_app()
        
        # Get all registered routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                for method in route.methods:
                    routes.append(f"{method} {route.path}")
        
        # Check for duplicates
        unique_routes = set(routes)
        
        if len(routes) != len(unique_routes):
            duplicates = []
            seen = set()
            for route in routes:
                if route in seen:
                    duplicates.append(route)
                seen.add(route)
            
            pytest.fail(f"Duplicate routes found: {duplicates}")
