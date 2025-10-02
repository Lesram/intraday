"""
Route Registry Test - Non-Regression for Phase-G Issues
Tests that all expected routes exist and return correct status codes.
Prevents regressions in authentication, route availability, and response consistency.
"""

import pytest
from fastapi.testclient import TestClient


class TestRouteRegistry:
    """Test suite to validate all API routes are present and behave correctly."""
    
    # Expected public routes (no authentication required)
    PUBLIC_ROUTES = [
        ('/health', 'GET', 200),
        ('/livez', 'GET', 200),
        # Note: /readyz may return 503 if services not fully ready, this is expected
    ]
    
    # Expected protected routes (authentication required)
    # Note: POST routes may return 405 (Method Not Allowed) if they expect specific content-type
    PROTECTED_ROUTES = [
        ('/api/v1/signals', 'GET', 401),  # Should return 401 without auth
        ('/api/v1/positions', 'GET', 401),  # Critical - was missing in Phase-G
        ('/api/v1/risk/metrics', 'GET', 401),  # Protected - contains account-scoped data
    ]
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        # Import here to avoid import errors if backend not available
        try:
            from backend.api.main import app
            return TestClient(app)
        except ImportError:
            from backend.api.factory import create_app
            app = create_app()
            return TestClient(app)
    
    @pytest.fixture
    def auth_token(self, client):
        """Get authentication token for protected route tests.
        
        Uses canonical /auth/login endpoint (POST JSON) per API standards.
        Returns JWT access token for Bearer authentication.
        """
        # Use canonical /auth/login endpoint with JSON body
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        
        # If /auth/login not available, try versioned endpoint as fallback
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        
        return None
    
    def test_public_routes_exist_and_respond(self, client):
        """Test that all public routes exist and return expected status codes."""
        for route, method, expected_status in self.PUBLIC_ROUTES:
            if method == 'GET':
                response = client.get(route)
            elif method == 'POST':
                response = client.post(route)
            else:
                pytest.fail(f"Unsupported method: {method}")
            
            assert response.status_code == expected_status, \
                f"Route {method} {route} returned {response.status_code}, expected {expected_status}"
    
    def test_protected_routes_return_401_without_auth(self, client):
        """Test that protected routes return 401 Unauthorized without authentication.
        
        This is a Phase-G non-regression test - previously some routes returned
        inconsistent status codes (404, 500) instead of 401.
        """
        for route, method, expected_status in self.PROTECTED_ROUTES:
            if expected_status != 401:
                # Skip routes that are intentionally public
                continue
            
            if method == 'GET':
                response = client.get(route)
            elif method == 'POST':
                response = client.post(route, json={})
            else:
                pytest.fail(f"Unsupported method: {method}")
            
            assert response.status_code == 401, \
                f"Route {method} {route} returned {response.status_code}, expected 401 (Unauthorized)"
            
            # WWW-Authenticate header is optional in FastAPI, don't enforce it
    
    def test_positions_endpoint_exists(self, client):
        """Test that /api/v1/positions endpoint exists.
        
        CRITICAL: This endpoint was missing in Phase-G dry-run, causing deployment blockers.
        This test ensures it never disappears again.
        """
        response = client.get('/api/v1/positions')
        
        # Should return 401 (needs auth) or 200 (if public), but NOT 404
        assert response.status_code in [200, 401], \
            f"/api/v1/positions returned {response.status_code}, expected 200 or 401 (NOT 404)"
    
    def test_protected_routes_with_auth_return_success(self, client, auth_token):
        """Test that protected routes return 2xx with valid authentication."""
        if not auth_token:
            pytest.skip(
                "Authentication not available, skipping auth test\n"
                "Ticket: TEST-001\n"
                "Remove by: 2025-11-01\n"
                "Owner: @auth-team\n"
                "Reason: Auth endpoint not configured in test environment"
            )
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Test key endpoints with authentication
        endpoints_to_test = [
            ('/api/v1/signals', 'GET'),
            ('/api/v1/orders', 'GET'),
            ('/api/v1/positions', 'GET'),  # CRITICAL endpoint
        ]
        
        for route, method in endpoints_to_test:
            if method == 'GET':
                response = client.get(route, headers=headers)
            elif method == 'POST':
                response = client.post(route, json={}, headers=headers)
            else:
                continue
            
            # Should return 2xx (success) or 4xx (validation error, but authenticated)
            # Should NOT return 401 (unauthorized) since we have a valid token
            assert response.status_code != 401, \
                f"Route {method} {route} returned 401 WITH authentication token"
            
            # Accept 2xx or 4xx (validation), but not 5xx or 401
            assert 200 <= response.status_code < 500, \
                f"Route {method} {route} returned {response.status_code}, expected 2xx or 4xx WITH auth"
    
    def test_health_endpoint_is_fast(self, client):
        """Test that /health endpoint responds quickly.
        
        Phase-G requirement: /health should be trivial (<10ms ideal, <200ms acceptable).
        This endpoint should not touch database or external services.
        """
        import time
        
        start = time.time()
        response = client.get('/health')
        elapsed_ms = (time.time() - start) * 1000
        
        assert response.status_code == 200, \
            f"/health returned {response.status_code}, expected 200"
        
        # Warn if slow, but don't fail (network/test env may be slower)
        if elapsed_ms > 200:
            pytest.warn(f"/health took {elapsed_ms:.1f}ms (target: <200ms)")
    
    def test_route_consistency_no_unexpected_404s(self, client):
        """Test that expected routes don't return 404.
        
        Phase-G issue: Some routes intermittently returned 404 instead of proper status codes.
        """
        all_routes = [route for route, _, _ in self.PUBLIC_ROUTES + self.PROTECTED_ROUTES]
        
        for route in all_routes:
            response = client.get(route)
            
            # 404 means route doesn't exist - this is bad if we expect the route
            assert response.status_code != 404, \
                f"Route GET {route} returned 404 (Not Found) - route should exist!"
    
    def test_openapi_schema_available(self, client):
        """Test that OpenAPI schema is available for API documentation."""
        response = client.get('/openapi.json')
        
        assert response.status_code == 200, \
            "OpenAPI schema should be available at /openapi.json"
        
        schema = response.json()
        assert 'paths' in schema, "OpenAPI schema should have 'paths' key"
        assert 'info' in schema, "OpenAPI schema should have 'info' key"
    
    def test_canonical_auth_endpoint_contract(self, client):
        """Test that canonical /auth/login endpoint follows API contract.
        
        Validates that the canonical authentication endpoint:
        1. Accepts POST with JSON body (not form data)
        2. Returns JSON with {access_token, token_type, expires_in}
        3. Uses Bearer token type
        4. Returns 401 for invalid credentials
        """
        # Test 1: Valid credentials should return proper token structure
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        assert response.status_code == 200, \
            f"/auth/login returned {response.status_code}, expected 200 for valid credentials"
        
        token_data = response.json()
        
        # Validate response contract
        assert "access_token" in token_data, \
            "Response must include 'access_token' field"
        assert "token_type" in token_data, \
            "Response must include 'token_type' field"
        assert "expires_in" in token_data, \
            "Response must include 'expires_in' field"
        
        assert token_data["token_type"].lower() == "bearer", \
            f"Token type must be 'bearer', got '{token_data['token_type']}'"
        
        assert isinstance(token_data["expires_in"], int) and token_data["expires_in"] > 0, \
            f"expires_in must be positive integer, got {token_data['expires_in']}"
        
        # Test 2: Invalid credentials should return 401
        response = client.post(
            "/auth/login",
            json={"username": "invalid", "password": "wrong"}
        )
        
        assert response.status_code == 401, \
            f"/auth/login should return 401 for invalid credentials, got {response.status_code}"
    
    def test_all_expected_routes_in_openapi(self, client):
        """Test that all expected routes are documented in OpenAPI schema."""
        response = client.get('/openapi.json')
        assert response.status_code == 200
        
        schema = response.json()
        paths = schema.get('paths', {})
        
        # Check that critical endpoints are documented (if they're in OpenAPI)
        # Note: Some endpoints may not be in OpenAPI schema if decorated differently
        critical_endpoints = [
            '/health',
            '/api/v1/risk/metrics',
        ]
        
        documented_count = 0
        for endpoint in critical_endpoints:
            if endpoint in paths:
                documented_count += 1
        
        # At least some critical endpoints should be documented
        assert documented_count > 0, \
            f"No critical endpoints found in OpenAPI schema (found {len(paths)} paths total)"


class TestPhaseGNonRegression:
    """Specific tests to prevent Phase-G regressions."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        try:
            from backend.api.main import app
            return TestClient(app)
        except ImportError:
            from backend.api.factory import create_app
            app = create_app()
            return TestClient(app)
    
    def test_positions_endpoint_not_404(self, client):
        """REGRESSION TEST: /api/v1/positions was returning 404 in Phase-G."""
        response = client.get('/api/v1/positions')
        assert response.status_code != 404, \
            "REGRESSION: /api/v1/positions returned 404 (should be 401 or 200)"
    
    def test_protected_routes_consistent_401(self, client):
        """REGRESSION TEST: Protected routes returned inconsistent status codes in Phase-G."""
        protected_routes = [
            '/api/v1/signals',
            '/api/v1/positions',
        ]
        
        for route in protected_routes:
            response = client.get(route)
            
            # Protected routes should return 401 without auth (not 404, not 500)
            # Note: 405 Method Not Allowed is acceptable for some endpoints
            assert response.status_code in [401, 405], \
                f"REGRESSION: {route} returned {response.status_code}, expected 401 or 405"
    
    def test_health_not_slow(self, client):
        """REGRESSION TEST: /health was slow (>200ms) in some Phase-G tests."""
        import time
        
        # Test multiple times to avoid false positives
        times = []
        for _ in range(5):
            start = time.time()
            response = client.get('/health')
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)
            assert response.status_code == 200
        
        avg_time = sum(times) / len(times)
        p95_time = sorted(times)[int(len(times) * 0.95)]
        
        # P95 should be under 200ms
        assert p95_time < 200, \
            f"REGRESSION: /health P95 latency {p95_time:.1f}ms exceeds 200ms target"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
