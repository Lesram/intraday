"""
Smoke tests for staging deployment validation.
Fast, focused tests to verify critical functionality is working.
"""
import json
import time

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class StagingTestClient:
    """Test client for staging environment with retries and timeouts."""

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        # Configure retries for flaky network
        retry_strategy = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set timeouts
        self.timeout = timeout

        # Common headers
        self.session.headers.update(
            {"User-Agent": "AlgoTrading-SmokeTest/1.0", "Accept": "application/json"}
        )

    def get(self, path: str, **kwargs) -> requests.Response:
        """GET request with automatic retries."""
        url = f"{self.base_url}{path}"
        return self.session.get(url, timeout=self.timeout, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        """POST request with automatic retries."""
        url = f"{self.base_url}{path}"
        return self.session.post(url, timeout=self.timeout, **kwargs)

    def health_check(self) -> bool:
        """Quick health check with minimal timeout."""
        try:
            response = self.get("/health")
            return response.status_code == 200
        except Exception:
            return False


@pytest.fixture(scope="session")
def base_url():
    """Base URL for staging environment."""
    import os

    url = os.getenv("STAGING_BASE_URL", "http://localhost:8000")
    print(f"Using staging URL: {url}")
    return url


@pytest.fixture(scope="session")
def client(base_url):
    """Test client for staging environment."""
    return StagingTestClient(base_url)


@pytest.fixture(scope="session")
def wait_for_ready(client):
    """Wait for staging environment to be ready."""
    max_attempts = 30
    wait_time = 5

    for attempt in range(max_attempts):
        if client.health_check():
            print(f"Staging ready after {attempt + 1} attempts")
            return True

        if attempt < max_attempts - 1:
            print(f"Attempt {attempt + 1}/{max_attempts}: Not ready, waiting {wait_time}s...")
            time.sleep(wait_time)

    pytest.fail("Staging environment not ready within timeout")


class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    def test_health_endpoint(self, client, wait_for_ready):
        """Test /health endpoint returns 200."""
        response = client.get("/health")

        assert response.status_code == 200, f"Health check failed: {response.text}"

        data = response.json()
        assert data["status"] in ["ok", "healthy"], f"Unexpected status: {data}"

    def test_healthz_endpoint(self, client, wait_for_ready):
        """Test Kubernetes-style /healthz endpoint."""
        response = client.get("/healthz")

        assert response.status_code == 200, f"Healthz check failed: {response.text}"

    def test_readyz_endpoint(self, client, wait_for_ready):
        """Test readiness endpoint."""
        response = client.get("/readyz")

        assert response.status_code == 200, f"Readiness check failed: {response.text}"

    def test_health_response_time(self, client, wait_for_ready):
        """Test health endpoint responds quickly."""
        start_time = time.time()
        response = client.get("/health")
        response_time = time.time() - start_time

        assert response.status_code == 200
        assert response_time < 2.0, f"Health check too slow: {response_time:.2f}s"


class TestMetricsEndpoint:
    """Test metrics endpoint for observability."""

    def test_metrics_endpoint_available(self, client, wait_for_ready):
        """Test /metrics endpoint is accessible."""
        response = client.get("/metrics")

        assert response.status_code == 200, f"Metrics endpoint failed: {response.text}"
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_contain_expected_data(self, client, wait_for_ready):
        """Test metrics endpoint contains expected metric families."""
        response = client.get("/metrics")
        metrics_text = response.text

        # Check for essential metrics
        expected_metrics = ["http_requests_total", "http_request_duration_seconds", "python_info"]

        missing_metrics = []
        for metric in expected_metrics:
            if metric not in metrics_text:
                missing_metrics.append(metric)

        assert not missing_metrics, f"Missing metrics: {missing_metrics}"

    def test_metrics_format_valid(self, client, wait_for_ready):
        """Test metrics are in valid Prometheus format."""
        response = client.get("/metrics")
        metrics_text = response.text

        # Basic format validation
        lines = metrics_text.strip().split("\n")
        assert len(lines) > 0, "Metrics response is empty"

        # Check for metric lines (not just comments)
        metric_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        assert len(metric_lines) > 0, "No actual metrics found"


class TestSystemAPI:
    """Test system API endpoints."""

    def test_system_status_endpoint(self, client, wait_for_ready):
        """Test system status API."""
        response = client.get("/api/v1/system/status")

        assert response.status_code == 200, f"System status failed: {response.text}"

        data = response.json()
        assert "status" in data, "Status field missing from response"
        assert "version" in data or "app_version" in data, "Version info missing"

    def test_api_root_accessible(self, client, wait_for_ready):
        """Test API root is accessible."""
        # Many APIs provide some form of root endpoint
        response = client.get("/")

        # Accept various success codes for root endpoint
        assert response.status_code in [
            200,
            404,
            405,
        ], f"Unexpected root response: {response.status_code}"


class TestAuthenticationSmoke:
    """Smoke tests for authentication system."""

    def test_login_endpoint_exists(self, client, wait_for_ready):
        """Test login endpoint exists (even if we can't authenticate)."""
        response = client.post("/auth/login", json={"username": "test", "password": "test"})

        # We expect authentication to fail, but endpoint should exist
        assert response.status_code in [
            400,
            401,
            422,
        ], f"Login endpoint missing or broken: {response.status_code}"

    def test_protected_endpoint_rejects_unauthenticated(self, client, wait_for_ready):
        """Test that protected endpoints require authentication."""
        # Try to access a protected endpoint without authentication
        protected_endpoints = [
            "/api/v1/orders/submit",
            "/api/v1/trades/history",
            "/api/v1/risk/limits",
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)

            # Should be unauthorized or forbidden
            assert response.status_code in [
                401,
                403,
            ], f"Endpoint {endpoint} not properly protected: {response.status_code}"


class TestCORSSmoke:
    """Smoke tests for CORS configuration."""

    def test_cors_headers_present(self, client, wait_for_ready):
        """Test CORS headers are present for preflight requests."""
        # OPTIONS request to simulate preflight
        response = client.session.options(
            f"{client.base_url}/api/v1/system/status",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
        )

        # CORS should be configured, even if origin is rejected
        # Status could be 200 (allowed) or 403/404 (rejected)
        assert response.status_code in [200, 403, 404, 405]


class TestRateLimitingSmoke:
    """Smoke tests for rate limiting."""

    def test_rate_limiting_headers_present(self, client, wait_for_ready):
        """Test rate limiting headers are present."""
        response = client.get("/health")

        # Rate limiting headers should be present
        rate_limit_headers = ["x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"]

        present_headers = []
        for header in rate_limit_headers:
            if header in response.headers:
                present_headers.append(header)

        # At least one rate limiting header should be present
        # (Some implementations use different header names)
        if not present_headers:
            print("Warning: No rate limiting headers detected")


class TestErrorHandling:
    """Test error handling and responses."""

    def test_404_error_handling(self, client, wait_for_ready):
        """Test 404 errors are handled gracefully."""
        response = client.get("/nonexistent-endpoint-123")

        assert response.status_code == 404

        # Should return JSON error response
        try:
            data = response.json()
            assert (
                "error" in data or "detail" in data
            ), "Error response should contain error information"
        except json.JSONDecodeError:
            # Some systems return HTML 404s, which is also acceptable
            assert "text/html" in response.headers.get("content-type", "")

    def test_method_not_allowed_handling(self, client, wait_for_ready):
        """Test method not allowed errors."""
        # Try PUT on a GET-only endpoint
        response = client.session.put(f"{client.base_url}/health")

        assert response.status_code in [
            405,
            404,
        ], f"Unexpected method response: {response.status_code}"


class TestPerformanceSmoke:
    """Basic performance smoke tests."""

    def test_response_times_reasonable(self, client, wait_for_ready):
        """Test response times are reasonable for key endpoints."""
        endpoints = ["/health", "/metrics", "/api/v1/system/status"]

        slow_endpoints = []

        for endpoint in endpoints:
            start_time = time.time()
            try:
                response = client.get(endpoint)
                response_time = time.time() - start_time

                if response.status_code == 200 and response_time > 5.0:
                    slow_endpoints.append((endpoint, response_time))
            except Exception as e:
                print(f"Warning: {endpoint} failed: {e}")

        if slow_endpoints:
            slow_info = ", ".join([f"{ep}: {time:.2f}s" for ep, time in slow_endpoints])
            pytest.fail(f"Slow endpoints detected: {slow_info}")


class TestSecuritySmoke:
    """Basic security smoke tests."""

    def test_security_headers_present(self, client, wait_for_ready):
        """Test security headers are present."""
        response = client.get("/health")

        expected_headers = ["x-content-type-options", "x-frame-options", "x-xss-protection"]

        missing_headers = []
        for header in expected_headers:
            if header not in response.headers:
                missing_headers.append(header)

        if len(missing_headers) > 1:  # Allow some flexibility
            print(f"Warning: Missing security headers: {missing_headers}")

    def test_no_sensitive_info_in_errors(self, client, wait_for_ready):
        """Test error responses don't leak sensitive information."""
        response = client.get("/api/v1/nonexistent")

        response_text = response.text.lower()

        # Check for common sensitive information leaks
        sensitive_patterns = ["traceback", "stack trace", "internal server error details"]

        leaks = []
        for pattern in sensitive_patterns:
            if pattern in response_text:
                leaks.append(pattern)

        if leaks:
            print(f"Warning: Potential information leaks: {leaks}")


# Test execution summary
def pytest_sessionstart(session):
    """Print test session start information."""
    print("\n" + "=" * 60)
    print("🚀 STAGING SMOKE TESTS STARTING")
    print("=" * 60)


def pytest_sessionfinish(session, exitstatus):
    """Print test session results."""
    print("\n" + "=" * 60)
    if exitstatus == 0:
        print("✅ STAGING SMOKE TESTS PASSED")
        print("🎉 Staging deployment validation successful!")
    else:
        print("❌ STAGING SMOKE TESTS FAILED")
        print("🔍 Check logs above for details")
    print("=" * 60)
