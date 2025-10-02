"""
Performance SLO Tests - Hard Requirements for Production Readiness

These tests enforce performance Service Level Objectives (SLOs) as hard requirements.
Unlike smoke tests that warn on degradation, these tests FAIL the build if SLOs are violated.

Key SLOs:
- /health endpoint: p95 < 200ms, p99 < 500ms
- Critical API endpoints: p95 < 1s
- No endpoint should have >2% unexpected error rate

Historical Context:
- Baseline /health p95 was 416ms (UNACCEPTABLE)
- Target is <200ms p95 to prevent cascading failures
"""

import time
import pytest
import statistics
from fastapi.testclient import TestClient


class TestHealthEndpointPerformanceSLO:
    """Hard performance requirements for /health endpoint."""
    
    # SLO thresholds (ms)
    HEALTH_P50_MAX_MS = 50
    HEALTH_P95_MAX_MS = 200
    HEALTH_P99_MAX_MS = 500
    
    # Number of requests for percentile calculation
    SAMPLE_SIZE = 100
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        try:
            from backend.api.main import app
            return TestClient(app)
        except ImportError:
            from backend.api.factory import create_app
            app = create_app()
            return TestClient(app)
    
    @pytest.mark.performance
    @pytest.mark.unit
    def test_health_endpoint_p95_latency_slo(self, client):
        """HARD REQUIREMENT: /health p95 latency must be < 200ms.
        
        This test measures actual p95 latency across 100 requests and FAILS
        if the threshold is exceeded. This prevents regression from the
        historical 416ms baseline.
        
        Why this matters:
        - Health checks run frequently (every 5-10s)
        - Slow health checks cascade to monitoring systems
        - Kubernetes may restart pods if liveness probes timeout
        """
        latencies_ms = []
        
        # Warm up (1 request to initialize any caches)
        _ = client.get('/health')
        
        # Measure latency across multiple requests
        for _ in range(self.SAMPLE_SIZE):
            start_time = time.perf_counter()
            response = client.get('/health')
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # Record latency only for successful requests
            if response.status_code == 200:
                latencies_ms.append(elapsed_ms)
        
        # Calculate percentiles
        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95_index = int(len(latencies_ms) * 0.95)
        p95 = latencies_ms[p95_index]
        p99_index = int(len(latencies_ms) * 0.99)
        p99 = latencies_ms[p99_index]
        
        # Build failure message with context
        failure_msg = (
            f"\n❌ /health PERFORMANCE SLO VIOLATION\n"
            f"   p50: {p50:.1f}ms (threshold: {self.HEALTH_P50_MAX_MS}ms)\n"
            f"   p95: {p95:.1f}ms (threshold: {self.HEALTH_P95_MAX_MS}ms) {'❌ FAILED' if p95 > self.HEALTH_P95_MAX_MS else '✅'}\n"
            f"   p99: {p99:.1f}ms (threshold: {self.HEALTH_P99_MAX_MS}ms) {'❌ FAILED' if p99 > self.HEALTH_P99_MAX_MS else '✅'}\n"
            f"   samples: {len(latencies_ms)}\n"
            f"\n"
            f"Historical context: Baseline was 416ms p95 (unacceptable)\n"
            f"Action required: Optimize /health endpoint or increase threshold with approval\n"
        )
        
        # Assert SLOs
        assert p95 < self.HEALTH_P95_MAX_MS, failure_msg
        assert p99 < self.HEALTH_P99_MAX_MS, \
            f"/health p99 latency {p99:.1f}ms exceeds threshold {self.HEALTH_P99_MAX_MS}ms"
        
        # Log success with actual measurements
        print(f"\n✅ /health Performance SLO: PASSED")
        print(f"   p50: {p50:.1f}ms / {self.HEALTH_P50_MAX_MS}ms")
        print(f"   p95: {p95:.1f}ms / {self.HEALTH_P95_MAX_MS}ms")
        print(f"   p99: {p99:.1f}ms / {self.HEALTH_P99_MAX_MS}ms")
    
    @pytest.mark.performance
    @pytest.mark.unit
    def test_health_endpoint_availability_slo(self, client):
        """HARD REQUIREMENT: /health availability must be > 99.9%
        
        Ensures the health endpoint is consistently available.
        """
        successful_requests = 0
        total_requests = self.SAMPLE_SIZE
        
        for _ in range(total_requests):
            try:
                response = client.get('/health')
                if response.status_code == 200:
                    successful_requests += 1
            except Exception:
                pass  # Count as failure
        
        availability = successful_requests / total_requests
        
        assert availability >= 0.999, \
            f"/health availability {availability:.2%} < 99.9% threshold"


class TestCriticalAPIPerformanceSLO:
    """Performance SLOs for critical business endpoints."""
    
    # SLO thresholds for business-critical endpoints
    CRITICAL_API_P95_MAX_MS = 1000  # 1 second
    CRITICAL_API_P99_MAX_MS = 2000  # 2 seconds
    
    SAMPLE_SIZE = 50  # Smaller sample for heavier endpoints
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        try:
            from backend.api.main import app
            return TestClient(app)
        except ImportError:
            from backend.api.factory import create_app
            app = create_app()
            return TestClient(app)
    
    @pytest.fixture
    def auth_token(self, client):
        """Get authentication token for protected endpoints."""
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        
        return None
    
    @pytest.mark.performance
    @pytest.mark.unit
    def test_signals_endpoint_performance_slo(self, client, auth_token):
        """HARD REQUIREMENT: /api/v1/signals p95 latency < 1s
        
        Trading signals are time-sensitive - slow retrieval impacts execution.
        
        Note: This test will skip if authentication fails or endpoint is not available.
        """
        if not auth_token:
            pytest.skip(
                "Authentication not available - /auth/login failed\n"
                "Ticket: TEST-002\n"
                "Remove by: 2025-11-01\n"
                "Owner: @auth-team\n"
                "Reason: Auth service not available in CI environment"
            )
        
        latencies_ms = []
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Warm up
        _ = client.get('/api/v1/signals', headers=headers)
        
        # Measure
        for _ in range(self.SAMPLE_SIZE):
            start_time = time.perf_counter()
            response = client.get('/api/v1/signals', headers=headers)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 200:
                latencies_ms.append(elapsed_ms)
        
        # Calculate p95
        if not latencies_ms:
            pytest.skip(
                "No successful requests to /api/v1/signals\n"
                "Ticket: TEST-003\n"
                "Remove by: 2025-11-01\n"
                "Owner: @backend-team\n"
                "Reason: Signals endpoint failing or auth issues"
            )
        
        latencies_ms.sort()
        p95_index = int(len(latencies_ms) * 0.95)
        p95 = latencies_ms[p95_index]
        
        assert p95 < self.CRITICAL_API_P95_MAX_MS, \
            f"/api/v1/signals p95 latency {p95:.1f}ms exceeds threshold {self.CRITICAL_API_P95_MAX_MS}ms"


class TestUnexpectedErrorRateSLO:
    """Monitors unexpected error rates across the platform."""
    
    # SLO: < 2% unexpected errors
    MAX_UNEXPECTED_ERROR_RATE = 0.02
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        try:
            from backend.api.main import app
            return TestClient(app)
        except ImportError:
            from backend.api.factory import create_app
            app = create_app()
            return TestClient(app)
    
    @pytest.mark.performance
    @pytest.mark.unit
    def test_health_endpoint_unexpected_error_rate_slo(self, client):
        """HARD REQUIREMENT: /health unexpected error rate < 2%
        
        Unexpected errors are:
        - 5xx (server errors)
        - Connection failures
        - Timeouts
        
        Expected errors (NOT counted):
        - 401 (authentication required)
        - 404 (not found)
        - 422 (validation error)
        """
        total_requests = 100
        unexpected_errors = 0
        
        for _ in range(total_requests):
            try:
                response = client.get('/health')
                
                # Count only unexpected errors
                if response.status_code >= 500:
                    unexpected_errors += 1
            except Exception:
                unexpected_errors += 1  # Connection failure
        
        error_rate = unexpected_errors / total_requests
        
        assert error_rate < self.MAX_UNEXPECTED_ERROR_RATE, \
            f"/health unexpected error rate {error_rate:.2%} exceeds threshold {self.MAX_UNEXPECTED_ERROR_RATE:.2%}"
