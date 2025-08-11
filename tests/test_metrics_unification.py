"""
Test metrics registry unification to verify blocking issues are resolved.

This test validates that:
1. Each test gets an isolated metrics registry (no conflicts)
2. WebSocket manager accepts metrics registry parameter
3. HTTP middleware uses centralized app.state.metrics
4. Multiple tests can run in parallel without registry conflicts
"""

from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
import pytest


@pytest.mark.metrics
def test_metrics_registry_isolation(isolated_metrics_registry):
    """Test that each test gets an isolated metrics registry"""
    # Verify we get a fresh CollectorRegistry instance
    assert isinstance(isolated_metrics_registry, CollectorRegistry)

    # Registry should be empty initially
    metric_families = list(isolated_metrics_registry.collect())
    assert len(metric_families) == 0


@pytest.mark.metrics
def test_app_has_metrics_registry(test_app, isolated_metrics_registry):
    """Test that the app factory correctly sets up metrics registry"""
    # Verify app has metrics in state
    assert hasattr(test_app.state, "metrics")

    # Verify the registry is the one we provided
    assert test_app.state.metrics.registry is isolated_metrics_registry


@pytest.mark.metrics
def test_websocket_manager_has_metrics(test_app, mock_dependencies):
    """Test that WebSocket manager gets metrics registry"""
    ws_manager = test_app.state.ws_manager

    # Verify WebSocket manager has metrics registry
    assert hasattr(ws_manager, "metrics_registry")
    assert ws_manager.metrics_registry is not None


@pytest.mark.metrics
def test_metrics_endpoint_isolation(metrics_test_client):
    """Test that /metrics endpoint works with isolated registry"""
    response = metrics_test_client.get("/metrics")

    # Should succeed (not 501 error)
    assert response.status_code == 200

    # Should return Prometheus format
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.metrics
def test_http_middleware_metrics(metrics_test_client, isolated_metrics_registry):
    """Test that HTTP requests generate metrics in isolated registry"""
    # Make a request to generate metrics
    response = metrics_test_client.get("/health")
    assert response.status_code == 200

    # Check that metrics were recorded in our isolated registry
    metric_families = list(isolated_metrics_registry.collect())

    # Should have some metrics now (http_requests_total, etc.)
    metric_names = [mf.name for mf in metric_families]

    # Verify HTTP metrics are present
    assert any("http_requests" in name for name in metric_names)


@pytest.mark.metrics
def test_parallel_test_isolation():
    """Test that multiple tests can run in parallel without conflicts"""
    from prometheus_client import CollectorRegistry

    from backend.api.factory import create_app

    # Create two separate app instances with isolated registries
    registry1 = CollectorRegistry()
    registry2 = CollectorRegistry()

    app1 = create_app(registry=registry1)
    app2 = create_app(registry=registry2)

    # Verify each app has its own registry
    assert app1.state.metrics.registry is registry1
    assert app2.state.metrics.registry is registry2
    assert app1.state.metrics.registry is not app2.state.metrics.registry

    # Create clients for both apps
    with TestClient(app1) as client1, TestClient(app2) as client2:
        # Make requests to both
        response1 = client1.get("/health")
        response2 = client2.get("/health")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Verify metrics are isolated
        metrics1 = list(registry1.collect())
        metrics2 = list(registry2.collect())

        # Both should have metrics, but in separate registries
        assert len(metrics1) > 0
        assert len(metrics2) > 0

        # Registries should contain different instances
        assert metrics1 != metrics2  # Different objects


@pytest.mark.metrics
def test_websocket_metrics_integration(test_app, isolated_metrics_registry, mock_dependencies):
    """Test WebSocket metrics are recorded in isolated registry"""
    from backend.api.main import WebSocketClientManager
    from backend.infra.metrics import MetricsRegistry

    # Create WebSocket manager with isolated metrics
    metrics_registry = MetricsRegistry(namespace="test", registry=isolated_metrics_registry)
    ws_manager = WebSocketClientManager(metrics_registry=metrics_registry)

    # Verify the manager has the metrics registry
    assert ws_manager.metrics_registry is metrics_registry

    # Test that metrics registry can record metrics
    if ws_manager.metrics_registry:
        counter = ws_manager.metrics_registry.counter("websocket_test_metric", {"test": "value"})
        counter.inc()

        # Verify metric was recorded
        metric_families = list(isolated_metrics_registry.collect())
        metric_names = [mf.name for mf in metric_families]
        assert "websocket_test_metric" in metric_names


if __name__ == "__main__":
    # Run the tests to verify metrics unification
    pytest.main([__file__, "-v", "-m", "metrics"])
