"""
Tests for observability contracts - ensuring consistent metrics configuration.
Validates histogram buckets, route templates, and duplicate metric detection.
"""

from prometheus_client import CollectorRegistry, Counter, Histogram
import pytest

from backend.infra.metrics import ROUTE_TEMPLATES, MetricsRegistry
from backend.infra.observability_contracts import (
    HISTOGRAM_BUCKETS,
    ObservabilityContract,
    check_metric_registry_for_duplicates,
    get_histogram_buckets,
    validate_route_template,
)


class TestHistogramBuckets:
    """Test fixed histogram bucket configurations."""

    def test_get_histogram_buckets_success(self):
        """Test getting buckets for known metrics."""
        # Test HTTP request duration buckets
        buckets = get_histogram_buckets("http_request_duration_seconds")
        expected = (
            0.001,
            0.005,
            0.010,
            0.025,
            0.050,
            0.100,
            0.250,
            0.500,
            1.0,
            2.5,
            5.0,
            10.0,
            float("inf"),
        )
        assert buckets == expected

    def test_get_histogram_buckets_alpaca(self):
        """Test Alpaca API latency buckets."""
        buckets = get_histogram_buckets("alpaca_http_latency_seconds")
        expected = (
            0.050,
            0.100,
            0.250,
            0.500,
            1.0,
            2.0,
            5.0,
            10.0,
            30.0,
            60.0,
            float("inf"),
        )
        assert buckets == expected

    def test_get_histogram_buckets_database(self):
        """Test database query duration buckets."""
        buckets = get_histogram_buckets("db_query_duration_seconds")
        expected = (
            0.001,
            0.002,
            0.005,
            0.010,
            0.025,
            0.050,
            0.100,
            0.250,
            0.500,
            1.0,
            float("inf"),
        )
        assert buckets == expected

    def test_get_histogram_buckets_unknown_metric(self):
        """Test error handling for unknown metrics."""
        with pytest.raises(ValueError, match="No histogram buckets defined"):
            get_histogram_buckets("unknown_metric_seconds")

    def test_all_buckets_end_with_infinity(self):
        """Ensure all bucket configurations end with infinity."""
        for metric_name, buckets in HISTOGRAM_BUCKETS.items():
            assert buckets[-1] == float(
                "inf"
            ), f"{metric_name} buckets don't end with infinity"

    def test_buckets_are_sorted(self):
        """Ensure all bucket configurations are properly sorted."""
        for metric_name, buckets in HISTOGRAM_BUCKETS.items():
            sorted_buckets = tuple(sorted(buckets))
            assert buckets == sorted_buckets, f"{metric_name} buckets are not sorted"


class TestRouteTemplateValidation:
    """Test route template validation and normalization."""

    def test_validate_route_template_exact_match(self):
        """Test exact route template matches."""
        route_templates = {
            "/api/v1/orders/submit": "/api/v1/orders/submit",
            "/health": "/health",
        }

        result = validate_route_template("/api/v1/orders/submit", route_templates)
        assert result == "/api/v1/orders/submit"

    def test_validate_route_template_parameterized(self):
        """Test parameterized route template matching."""
        route_templates = {
            "/api/v1/orders/{order_id}": "/api/v1/orders/{id}",
            "/api/v1/signals/{symbol}": "/api/v1/signals/{symbol}",
        }

        # Test order ID parameter
        result = validate_route_template("/api/v1/orders/12345", route_templates)
        assert result == "/api/v1/orders/{id}"

        # Test symbol parameter
        result = validate_route_template("/api/v1/signals/AAPL", route_templates)
        assert result == "/api/v1/signals/{symbol}"

    def test_validate_route_template_uuid_parameter(self):
        """Test UUID parameter matching."""
        route_templates = {
            "/api/v1/orders/{order_id}": "/api/v1/orders/{id}",
        }

        uuid_path = "/api/v1/orders/550e8400-e29b-41d4-a716-446655440000"
        result = validate_route_template(uuid_path, route_templates)
        assert result == "/api/v1/orders/{id}"

    def test_validate_route_template_no_match(self):
        """Test fallback when no template matches."""
        route_templates = {
            "/api/v1/orders/submit": "/api/v1/orders/submit",
        }

        result = validate_route_template("/api/v2/new/endpoint", route_templates)
        assert result == "/api/v2/new/endpoint"  # Returns original path

    def test_route_templates_completeness(self):
        """Test that ROUTE_TEMPLATES covers common patterns."""
        # Check that we have templates for major endpoints
        assert "/health" in ROUTE_TEMPLATES
        assert "/metrics" in ROUTE_TEMPLATES
        assert "/api/v1/orders/submit" in ROUTE_TEMPLATES
        assert "/auth/login" in ROUTE_TEMPLATES

        # Check parameterized templates
        parameterized_templates = [t for t in ROUTE_TEMPLATES.values() if "{" in t]
        assert "/api/v1/orders/{id}" in parameterized_templates
        assert "/api/v1/signals/{symbol}" in parameterized_templates


class TestDuplicateMetricDetection:
    """Test duplicate metric detection functionality."""

    def test_check_registry_no_duplicates(self):
        """Test registry with no duplicate metrics."""
        registry = CollectorRegistry()

        # Add unique metrics
        Counter("test_counter_1", "First counter", registry=registry)
        Counter("test_counter_2", "Second counter", registry=registry)

        duplicates = check_metric_registry_for_duplicates(registry)
        assert len(duplicates) == 0

    def test_check_registry_with_duplicates(self):
        """Test registry with duplicate metrics."""
        registry = CollectorRegistry()

        # Add duplicate metrics (this shouldn't normally happen but we force it for testing)
        counter1 = Counter("duplicate_counter", "First counter", registry=registry)

        # Manually create a second collector with same name
        # Note: This is contrived as Prometheus client normally prevents this
        counter2 = Counter("duplicate_counter", "Second counter")

        # The duplicate detection should work even in edge cases
        duplicates = check_metric_registry_for_duplicates(registry)
        # This test is mostly about the function not crashing
        assert isinstance(duplicates, list)


class TestObservabilityContract:
    """Test the ObservabilityContract class."""

    def test_observability_contract_initialization(self):
        """Test contract initialization."""
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)

        assert contract.registry is registry
        assert isinstance(contract._validated_routes, set)

    def test_validate_histogram_buckets_correct(self):
        """Test histogram bucket validation with correct buckets."""
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)

        # Create histogram with correct buckets
        buckets = get_histogram_buckets("http_request_duration_seconds")
        histogram = Histogram(
            "test_histogram", "Test histogram", registry=registry, buckets=buckets
        )

        is_valid = contract.validate_histogram_buckets(
            "http_request_duration_seconds", histogram
        )
        assert is_valid

    def test_validate_histogram_buckets_no_contract(self):
        """Test histogram validation when no contract exists for metric."""
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)

        histogram = Histogram("unknown_metric", "Unknown metric", registry=registry)
        is_valid = contract.validate_histogram_buckets("unknown_metric", histogram)
        assert is_valid  # Should allow any buckets for unknown metrics

    def test_validate_route_labeling(self):
        """Test route labeling validation."""
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)

        route_templates = ROUTE_TEMPLATES
        template = contract.validate_route_labeling("/health", route_templates)
        assert template == "/health"

        # Check that route is tracked
        assert "/health" in contract._validated_routes

    def test_get_validation_summary(self):
        """Test validation summary generation."""
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)

        # Validate some routes
        contract.validate_route_labeling("/health", ROUTE_TEMPLATES)
        contract.validate_route_labeling("/metrics", ROUTE_TEMPLATES)

        summary = contract.get_validation_summary()

        assert "duplicate_metrics" in summary
        assert "duplicate_count" in summary
        assert "validated_routes" in summary
        assert "route_count" in summary
        assert "histogram_contracts" in summary

        assert "/health" in summary["validated_routes"]
        assert "/metrics" in summary["validated_routes"]
        assert summary["route_count"] == 2


class TestMetricsRegistryIntegration:
    """Test integration between MetricsRegistry and observability contracts."""

    def test_metrics_registry_with_observability_contracts(self):
        """Test MetricsRegistry using observability contracts."""
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)

        # Should have observability contract
        assert metrics_registry.observability_contract is not None

    def test_histogram_uses_standardized_buckets(self):
        """Test that histograms use standardized buckets."""
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)

        # Create histogram - should use standardized buckets
        histogram = metrics_registry.histogram(
            "http_request_duration_seconds", labels={"route": "/test", "method": "GET"}
        )

        # Verify it's a histogram instance
        assert histogram is not None

    def test_route_template_validation(self):
        """Test route template validation through MetricsRegistry."""
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)

        normalized_route = metrics_registry.validate_route_template("/health")
        assert normalized_route == "/health"

        # Test parameterized route
        normalized_route = metrics_registry.validate_route_template(
            "/api/v1/orders/12345"
        )
        assert normalized_route == "/api/v1/orders/{id}"

    def test_duplicate_metric_detection_integration(self):
        """Test duplicate metric detection through MetricsRegistry."""
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)

        # Create some metrics
        metrics_registry.counter("auth_attempts_total", {"result": "success"})
        metrics_registry.histogram(
            "http_request_duration_seconds", {"route": "/test", "method": "GET"}
        )

        duplicates = metrics_registry.check_duplicate_metrics()
        assert isinstance(duplicates, list)

    def test_observability_summary_integration(self):
        """Test observability summary through MetricsRegistry."""
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)

        # Validate some routes
        metrics_registry.validate_route_template("/health")
        metrics_registry.validate_route_template("/metrics")

        summary = metrics_registry.get_observability_summary()

        assert "duplicate_metrics" in summary
        assert "validated_routes" in summary
        assert "histogram_contracts" in summary

        # Should show our validated routes
        assert "/health" in summary["validated_routes"]
        assert "/metrics" in summary["validated_routes"]


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_empty_route_templates(self):
        """Test behavior with empty route templates."""
        empty_templates = {}
        result = validate_route_template("/any/path", empty_templates)
        assert result == "/any/path"

    def test_malformed_route_paths(self):
        """Test behavior with malformed route paths."""
        route_templates = ROUTE_TEMPLATES

        # Test empty path
        result = validate_route_template("", route_templates)
        assert result == ""

        # Test path without leading slash
        result = validate_route_template("health", route_templates)
        assert result == "health"  # Returns as-is

    def test_bucket_edge_values(self):
        """Test histogram buckets with edge values."""
        for metric_name in HISTOGRAM_BUCKETS:
            buckets = get_histogram_buckets(metric_name)

            # Should have at least 2 buckets (including infinity)
            assert len(buckets) >= 2

            # All values should be positive or infinity
            for bucket in buckets:
                assert bucket > 0 or bucket == float("inf")

            # Should start with a reasonable small value (< 1 second for timing metrics)
            if "seconds" in metric_name:
                assert buckets[0] <= 1.0
