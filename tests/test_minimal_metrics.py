"""
Minimal test for metrics registry isolation - core functionality only.

This test validates the core metrics unification without requiring
full app dependencies, focusing specifically on the blocking issue resolution.
"""

from prometheus_client import CollectorRegistry
import pytest


def test_isolated_registry_creation():
    """Test basic registry isolation without FastAPI dependencies"""
    # Create two isolated registries
    registry1 = CollectorRegistry()
    registry2 = CollectorRegistry()

    # Verify they're different instances
    assert registry1 is not registry2

    # Verify they start empty
    assert list(registry1.collect()) == []
    assert list(registry2.collect()) == []


def test_metrics_registry_class():
    """Test MetricsRegistry wrapper with isolated registries"""
    from backend.infra.metrics import MetricsRegistry

    # Create two registries with different namespaces
    registry1 = CollectorRegistry()
    registry2 = CollectorRegistry()

    metrics1 = MetricsRegistry(namespace="test1", registry=registry1)
    metrics2 = MetricsRegistry(namespace="test2", registry=registry2)

    # Verify they use different registries
    assert metrics1.registry is registry1
    assert metrics2.registry is registry2
    assert metrics1.registry is not metrics2.registry


def test_factory_creates_app_with_registry():
    """Test that factory creates app with registry without full imports"""
    from prometheus_client import CollectorRegistry

    from backend.api.factory import create_app

    # Create isolated registry
    registry = CollectorRegistry()

    # Create app with registry (this should work even without routes)
    app = create_app(registry=registry)

    # Verify app has metrics in state
    assert hasattr(app.state, "metrics")
    assert app.state.metrics.registry is registry


def test_websocket_manager_accepts_registry():
    """Test WebSocketClientManager accepts metrics_registry parameter"""
    from prometheus_client import CollectorRegistry

    from backend.api.main import WebSocketClientManager
    from backend.infra.metrics import MetricsRegistry

    # Create isolated registry and metrics wrapper
    registry = CollectorRegistry()
    metrics_registry = MetricsRegistry(namespace="test", registry=registry)

    # Create WebSocket manager with metrics
    ws_manager = WebSocketClientManager(metrics_registry=metrics_registry)

    # Verify it has the metrics registry
    assert ws_manager.metrics_registry is metrics_registry
    assert ws_manager.metrics_registry.registry is registry


def test_prometheus_import_minimal():
    """Test prometheus_client imports work for core functionality"""
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    # Create isolated registry
    registry = CollectorRegistry()

    # Create metrics
    counter = Counter("test_counter", "Test counter", ["label"], registry=registry)
    gauge = Gauge("test_gauge", "Test gauge", ["label"], registry=registry)
    histogram = Histogram(
        "test_histogram", "Test histogram", ["label"], registry=registry
    )

    # Use metrics
    counter.labels(label="test").inc()
    gauge.labels(label="test").set(42)
    histogram.labels(label="test").observe(1.5)

    # Generate metrics output
    output = generate_latest(registry)

    # Verify metrics are present
    assert b"test_counter" in output
    assert b"test_gauge" in output
    assert b"test_histogram" in output


def test_parallel_registry_isolation():
    """Test that parallel registries don't interfere"""
    from prometheus_client import CollectorRegistry

    from backend.infra.metrics import MetricsRegistry

    # Create multiple isolated registries
    registries = [CollectorRegistry() for _ in range(5)]
    metrics_wrappers = [
        MetricsRegistry(namespace=f"test_{i}", registry=reg)
        for i, reg in enumerate(registries)
    ]

    # Create metrics in each registry using standard metric names from allowlist
    for i, metrics in enumerate(metrics_wrappers):
        # Use a known metric name from the allowlist with correct labels
        counter = metrics.counter(
            "http_requests_total",
            {
                "route": f"/test_{i}",
                "method": "GET",
                "status": "success",  # Use allowed status value
            },
        )
        counter.inc()

    # Verify metrics are isolated
    for i, registry in enumerate(registries):
        metric_families = list(registry.collect())

        # Should have metrics now
        assert len(metric_families) > 0

        # Each registry should only contain its own namespaced metrics
        expected_metric_name = f"test_{i}_http_requests"
        found_expected_metric = False

        for mf in metric_families:
            if mf.name == expected_metric_name:
                found_expected_metric = True
                # Verify this metric has the correct labels for this instance
                for sample in mf.samples:
                    if "route" in sample.labels:
                        assert sample.labels["route"] == f"/test_{i}"

        assert (
            found_expected_metric
        ), f"Registry {i} should contain {expected_metric_name} metric"

        # Verify no cross-contamination - shouldn't contain metrics from other registries
        for j in range(len(registries)):
            if j != i:
                unexpected_metric_name = f"test_{j}_http_requests"
                for mf in metric_families:
                    assert (
                        mf.name != unexpected_metric_name
                    ), f"Registry {i} should not contain {unexpected_metric_name}"


if __name__ == "__main__":
    # Run minimal tests
    pytest.main([__file__, "-v"])
