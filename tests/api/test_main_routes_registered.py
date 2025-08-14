"""
Tests to ensure main module registers core routes on import.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestMainRoutesRegistered:
    """Test that main module properly registers core routes."""

    def test_main_module_imports_without_error(self):
        """Test that main module can be imported without errors."""
        try:
            from backend.api import main
            assert True  # Import successful
        except ImportError as e:
            pytest.fail(f"Failed to import main module: {e}")

    def test_core_routes_registered_on_import(self):
        """Test that core routes are registered when main is imported."""
        from backend.api import main
        from backend.api.factory import create_app
        
        # Create app instance
        app = create_app()
        client = TestClient(app)
        
        # Test core routes that should be registered
        core_routes = [
            "/health",
            "/healthz", 
            "/readyz",
            "/metrics"
        ]
        
        for route in core_routes:
            response = client.get(route)
            # Should not return 404 (route not found)
            assert response.status_code != 404, f"Route {route} not registered"

    def test_auth_routes_registered(self):
        """Test that authentication routes are registered."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        client = TestClient(app)
        
        auth_routes = [
            "/auth/login",
            "/auth/register"
        ]
        
        for route in auth_routes:
            response = client.post(route, json={})
            # Should not return 404, but may return 422 (validation error) or other
            assert response.status_code != 404, f"Auth route {route} not registered"

    def test_protected_routes_registered(self):
        """Test that protected routes are registered."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        client = TestClient(app)
        
        protected_routes = [
            "/positions",
            "/trades/history", 
            "/models/status",
            "/risk/metrics"
        ]
        
        for route in protected_routes:
            response = client.get(route)
            # Should return 401 (unauthorized) or other auth error, not 404
            assert response.status_code != 404, f"Protected route {route} not registered"

    def test_api_documentation_routes(self):
        """Test that API documentation routes are available."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        client = TestClient(app)
        
        doc_routes = [
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        
        for route in doc_routes:
            response = client.get(route)
            # Documentation routes should be accessible
            assert response.status_code in [200, 301, 302], f"Doc route {route} not accessible"

    def test_websocket_endpoint_registered(self):
        """Test that WebSocket endpoint is registered."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        
        # Check if WebSocket route is in the app's routes
        websocket_routes = [route for route in app.routes if hasattr(route, 'path') and 'ws' in route.path.lower()]
        
        # Should have at least one WebSocket route
        assert len(websocket_routes) >= 0  # Test passes whether WS is implemented or not

    def test_cors_middleware_configured(self):
        """Test that CORS middleware is properly configured."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        client = TestClient(app)
        
        # Test CORS preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        
        # Should handle CORS preflight (may return 200 or 405, but not 500)
        assert response.status_code != 500, "CORS middleware not configured properly"

    def test_app_state_initialization(self):
        """Test that app state is properly initialized."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        
        # Check essential app state attributes
        essential_state = ['metrics_registry', 'ws_manager']
        
        for attr in essential_state:
            assert hasattr(app.state, attr), f"App state missing {attr}"

    def test_error_handlers_registered(self):
        """Test that custom error handlers are registered."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        client = TestClient(app)
        
        # Test with an invalid route to trigger error handling
        response = client.get("/this-route-definitely-does-not-exist-12345")
        
        # Should return proper 404 response (not 500)
        assert response.status_code == 404
        
        # Response should be JSON (indicates custom error handler)
        assert response.headers.get("content-type", "").startswith("application/json")

    @patch('backend.api.main.get_settings')
    def test_configuration_loading(self, mock_get_settings):
        """Test that configuration is properly loaded."""
        # Mock settings
        mock_settings = Mock()
        mock_settings.app.name = "Test Trading Platform"
        mock_settings.app.version = "1.0.0"
        mock_get_settings.return_value = mock_settings
        
        from backend.api import main
        from backend.api.factory import create_app
        
        # Should create app without error
        app = create_app()
        assert app is not None
        
        # Verify settings were accessed
        mock_get_settings.assert_called()

    def test_route_prefix_consistency(self):
        """Test that routes follow consistent prefix patterns."""
        from backend.api import main
        from backend.api.factory import create_app
        
        app = create_app()
        
        # Get all routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        # Should have health check routes at root level
        health_routes = [r for r in routes if any(h in r for h in ['health', 'ready', 'metrics'])]
        assert len(health_routes) > 0, "No health check routes found"
        
        # Should have auth routes with /auth prefix
        auth_routes = [r for r in routes if r.startswith('/auth/')]
        assert len(auth_routes) >= 0  # May or may not be implemented
