"""
Route registry test to prevent 404 regressions.
Validates that expected API endpoints are actually available.
"""

import pytest
from fastapi.routing import APIRoute

from backend.api.main import app


class TestRouteRegistry:
    """Test suite to ensure all expected routes are properly registered."""
    
    # Expected route paths that must be available
    EXPECT = {
        # Public system routes
        "/api/v1/health", 
        "/api/v1/readyz", 
        "/api/v1/livez",
        "/api/v1/healthz",
        "/api/v1/system/health",
        "/api/v1/system/status",
        "/api/v1/system/metrics",
        
        # Authentication routes (public)
        "/api/v1/auth/login",
        "/api/v1/auth/register", 
        "/api/v1/auth/token",
        "/api/v1/auth/token/validate",
        "/api/v1/auth/me",
        
        # Trading signals (protected)
        "/api/v1/signals/",
        "/api/v1/signals/{symbol}",
        "/api/v1/signals/act",
        "/api/v1/signals/batch",
        
        # Orders (protected)
        "/api/v1/orders/",
        "/api/v1/orders/submit", 
        "/api/v1/orders/{order_id}",
        "/api/v1/orders/{order_id}/cancel",
        "/api/v1/orders/{order_id}/audit",
        
        # Risk management (protected)
        "/api/v1/risk/limits",
        "/api/v1/risk/metrics",
        
        # Portfolio (protected)
        "/api/v1/portfolio/positions",
        "/api/v1/portfolio/performance",
        "/api/v1/positions",  # New positions endpoint
        
        # Trades (protected)
        "/api/v1/trades/",
        "/api/v1/trades/history",
        "/api/v1/trades/execute",
        "/api/v1/trades/stats",
        
        # Models (protected)
        "/api/v1/models/status",
        "/api/v1/models/train",
        
        # Strategy (protected)
        "/api/v1/strategy/status",
        "/api/v1/strategy/signals/submit",
        "/api/v1/strategy/signals/batch",
        
        # Legacy/compatibility routes
        "/health",
        "/readyz",
        "/livez",
        "/healthz",
        "/metrics",
        "/",
    }
    
    def test_route_registry_coverage(self):
        """
        Test that all expected routes are present in the actual FastAPI app.
        
        Validates EXPECT ⊆ ACTUAL to ensure no critical routes are missing.
        """
        # Get all actual route paths from the FastAPI app
        actual_routes = set()
        
        for route in app.routes:
            if isinstance(route, APIRoute):
                actual_routes.add(route.path)
        
        print(f"\n📋 Route Registry Validation")
        print(f"Expected routes: {len(self.EXPECT)}")
        print(f"Actual routes: {len(actual_routes)}")
        
        # Find missing routes (expected but not found)
        missing_routes = self.EXPECT - actual_routes
        
        # Find extra routes (found but not expected) - informational only
        extra_routes = actual_routes - self.EXPECT
        
        if missing_routes:
            print(f"\n❌ Missing routes ({len(missing_routes)}):")
            for route in sorted(missing_routes):
                print(f"  - {route}")
        
        if extra_routes:
            print(f"\n📋 Extra routes ({len(extra_routes)}) - informational:")
            for route in sorted(extra_routes):
                print(f"  + {route}")
        
        # The test passes if all expected routes are present
        assert not missing_routes, f"Missing {len(missing_routes)} expected routes: {sorted(missing_routes)}"
        
        print(f"\n✅ Route registry validation passed!")
        print(f"All {len(self.EXPECT)} expected routes are properly registered")
    
    def test_api_v1_prefix_consistency(self):
        """
        Test that all API routes use consistent /api/v1 prefix.
        
        Ensures we don't have routing inconsistencies or double prefixes.
        """
        actual_routes = []
        
        for route in app.routes:
            if isinstance(route, APIRoute):
                actual_routes.append(route.path)
        
        # Find routes that should have /api/v1 prefix but don't
        api_routes_without_prefix = []
        for route in actual_routes:
            # Skip root and system routes that are intentionally at root level
            if route in ["/", "/health", "/readyz", "/livez", "/healthz", "/metrics"]:
                continue
            # Skip legacy auth routes that are kept for compatibility
            if route.startswith("/auth/"):
                continue
            # Skip test routes
            if route.startswith("/test/"):
                continue
                
            # All other routes should have /api/v1 prefix
            if not route.startswith("/api/v1/"):
                api_routes_without_prefix.append(route)
        
        assert not api_routes_without_prefix, f"Routes missing /api/v1 prefix: {api_routes_without_prefix}"
        
        # Find routes with double prefix (would indicate misconfiguration)
        double_prefix_routes = []
        for route in actual_routes:
            if "/api/v1/api/v1/" in route:
                double_prefix_routes.append(route)
        
        assert not double_prefix_routes, f"Routes with double /api/v1 prefix: {double_prefix_routes}"
        
        print(f"✅ API v1 prefix consistency validated")
    
    def test_protected_vs_public_routes(self):
        """
        Test that routes are properly categorized as protected vs public.
        
        This is a documentation test to ensure we understand which routes require auth.
        """
        public_routes = {
            "/", "/health", "/readyz", "/livez", "/healthz", "/metrics",
            "/api/v1/system/health", "/api/v1/system/status", "/api/v1/system/metrics",
            "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/token",
            "/auth/login", "/auth/register", "/auth/token"  # Legacy compatibility
        }
        
        actual_routes = set()
        for route in app.routes:
            if isinstance(route, APIRoute):
                actual_routes.add(route.path)
        
        # All other /api/v1/ routes should be protected
        protected_routes = set()
        for route in actual_routes:
            if route.startswith("/api/v1/") and route not in public_routes:
                protected_routes.add(route)
        
        print(f"\n🔓 Public routes ({len(public_routes)}):")
        for route in sorted(public_routes & actual_routes):
            print(f"  {route}")
            
        print(f"\n🔒 Protected routes ({len(protected_routes)}):")
        for route in sorted(protected_routes):
            print(f"  {route}")
        
        # Ensure we have both public and protected routes
        assert len(public_routes & actual_routes) > 0, "No public routes found"
        assert len(protected_routes) > 0, "No protected routes found"
        
        print(f"\n✅ Route protection categorization validated")


def test_route_registry_standalone():
    """
    Standalone function version of the route registry test.
    Can be run independently without pytest.
    """
    test_instance = TestRouteRegistry()
    test_instance.test_route_registry_coverage()
    test_instance.test_api_v1_prefix_consistency()
    test_instance.test_protected_vs_public_routes()
    print("\n🎉 All route registry tests passed!")


if __name__ == "__main__":
    # Allow running this test file directly
    test_route_registry_standalone()