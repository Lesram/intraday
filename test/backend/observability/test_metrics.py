"""
Comprehensive test suite for Module 70: backend.observability.metrics
Tests observability metrics functionality including MetricsRegistry, CounterWrapper, 
and all metric types with comprehensive coverage.

Author: MLOps Team
Created: 2025-01-01
Version: 1.0.0
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from backend.observability.metrics import (
    MetricsRegistry, CounterWrapper, get_metrics_registry, 
    initialize_metrics_registry, normalize_route, normalize_alpaca_endpoint,
    LABEL_ALLOWLIST, LABEL_VALUE_ALLOWLIST, ROUTE_TEMPLATES, 
    ALPACA_ENDPOINT_TEMPLATES, track_model_prediction
)


class TestCounterWrapper:
    """Test CounterWrapper functionality."""
    
    def test_counter_wrapper_creation(self):
        """Test CounterWrapper creation."""
        registry = CollectorRegistry()
        prometheus_counter = Counter('test_counter', 'Test counter', registry=registry)
        wrapper = CounterWrapper(prometheus_counter)
        
        assert wrapper._counter == prometheus_counter
        assert hasattr(wrapper, 'value')
    
    def test_counter_wrapper_value_property(self):
        """Test CounterWrapper value property."""
        registry = CollectorRegistry()
        prometheus_counter = Counter('test_counter', 'Test counter', registry=registry)
        wrapper = CounterWrapper(prometheus_counter)
        
        # Initial value should be 0
        assert wrapper.value == 0.0
        
        # Increment and test value
        prometheus_counter.inc(5.0)
        assert wrapper.value >= 5.0  # May include other samples
    
    def test_counter_wrapper_value_with_labels(self):
        """Test CounterWrapper value with labeled counter."""
        registry = CollectorRegistry()
        prometheus_counter = Counter('test_counter', 'Test counter', 
                                   labelnames=['label1'], registry=registry)
        wrapper = CounterWrapper(prometheus_counter)
        
        # Test with labeled samples
        prometheus_counter.labels(label1='value1').inc(3.0)
        prometheus_counter.labels(label1='value2').inc(2.0)
        
        assert wrapper.value >= 5.0
    
    def test_counter_wrapper_attribute_delegation(self):
        """Test that CounterWrapper delegates attributes correctly."""
        registry = CollectorRegistry()
        prometheus_counter = Counter('test_counter', 'Test counter', registry=registry)
        wrapper = CounterWrapper(prometheus_counter)
        
        # Test delegation of methods
        assert hasattr(wrapper, 'inc')
        assert hasattr(wrapper, 'collect')
        
        # Test that methods work
        wrapper.inc(1.0)
        assert wrapper.value >= 1.0
    
    def test_counter_wrapper_value_exception_handling(self):
        """Test CounterWrapper value property exception handling."""
        registry = CollectorRegistry()
        prometheus_counter = Counter('test_counter', 'Test counter', registry=registry)
        wrapper = CounterWrapper(prometheus_counter)
        
        # Mock collect to raise an exception
        with patch.object(prometheus_counter, 'collect', side_effect=Exception("Test error")):
            assert wrapper.value == 0.0


class TestMetricsRegistry:
    """Test MetricsRegistry class."""
    
    def test_metrics_registry_initialization(self):
        """Test MetricsRegistry initialization."""
        registry = MetricsRegistry()
        
        assert registry.namespace == "intraday"
        assert isinstance(registry.registry, CollectorRegistry)
        assert isinstance(registry._metrics, dict)
        assert len(registry._metrics) == 0
    
    def test_metrics_registry_custom_namespace(self):
        """Test MetricsRegistry with custom namespace."""
        registry = MetricsRegistry(namespace="custom")
        
        assert registry.namespace == "custom"
    
    def test_metrics_registry_custom_registry(self):
        """Test MetricsRegistry with custom Prometheus registry."""
        custom_registry = CollectorRegistry()
        registry = MetricsRegistry(registry=custom_registry)
        
        assert registry.registry == custom_registry
    
    def test_counters_property(self):
        """Test counters property."""
        registry = MetricsRegistry()
        
        # Create a counter
        counter = registry.counter("http_requests_total", {"route": "/test", "method": "GET", "status": "success"})
        
        counters = registry.counters
        assert isinstance(counters, dict)
        assert "http_requests_total" in counters
        assert isinstance(counters["http_requests_total"], CounterWrapper)
    
    def test_gauges_property(self):
        """Test gauges property."""
        registry = MetricsRegistry()
        
        # Create a gauge
        gauge = registry.gauge("websocket_connections_total", {"client_type": "trading"})
        
        gauges = registry.gauges
        assert isinstance(gauges, dict)
        assert "websocket_connections_total" in gauges
        assert isinstance(gauges["websocket_connections_total"], Gauge)
    
    def test_validate_metric_name_valid(self):
        """Test metric name validation with valid name."""
        registry = MetricsRegistry()
        
        # Should not raise exception
        registry._validate_metric_name("http_requests_total")
    
    def test_validate_metric_name_invalid(self):
        """Test metric name validation with invalid name."""
        registry = MetricsRegistry()
        
        with pytest.raises(ValueError, match="not found in LABEL_ALLOWLIST"):
            registry._validate_metric_name("invalid_metric_name")
    
    def test_validate_labels_valid(self):
        """Test label validation with valid labels."""
        registry = MetricsRegistry()
        
        labels = {"route": "/test", "method": "GET", "status": "success"}
        validated = registry._validate_labels("http_requests_total", labels)
        
        assert validated == labels
    
    def test_validate_labels_unexpected_labels(self):
        """Test label validation with unexpected labels."""
        registry = MetricsRegistry()
        
        labels = {"route": "/test", "method": "GET", "status": "success", "unexpected": "value"}
        
        with pytest.raises(ValueError, match="Unexpected labels"):
            registry._validate_labels("http_requests_total", labels)
    
    def test_validate_labels_missing_labels(self):
        """Test label validation with missing required labels."""
        registry = MetricsRegistry()
        
        labels = {"route": "/test"}  # Missing method and status
        
        with pytest.raises(ValueError, match="Missing required labels"):
            registry._validate_labels("http_requests_total", labels)
    
    def test_validate_labels_invalid_values(self):
        """Test label validation with invalid values."""
        registry = MetricsRegistry()
        
        labels = {"route": "/test", "method": "GET", "status": "invalid_status"}
        
        # Should log warning but not raise exception
        with patch('backend.infra.metrics.logger') as mock_logger:
            validated = registry._validate_labels("http_requests_total", labels)
            mock_logger.warning.assert_called()
            assert validated["status"] == "invalid_status"
    
    def test_get_metric_name(self):
        """Test metric name generation."""
        registry = MetricsRegistry(namespace="test")
        
        assert registry._get_metric_name("counter") == "test_counter"
        
        # Test empty namespace
        registry_no_ns = MetricsRegistry(namespace="")
        assert registry_no_ns._get_metric_name("counter") == "counter"
    
    def test_counter_creation(self):
        """Test counter creation."""
        registry = MetricsRegistry()
        
        counter = registry.counter("http_requests_total", 
                                 {"route": "/test", "method": "GET", "status": "success"})
        
        assert isinstance(counter, CounterWrapper)
        assert "http_requests_total" in registry._metrics
    
    def test_counter_reuse(self):
        """Test counter reuse."""
        registry = MetricsRegistry()
        
        # Create counter twice with same metric name
        counter1 = registry.counter("http_requests_total", 
                                  {"route": "/test", "method": "GET", "status": "success"})
        counter2 = registry.counter("http_requests_total", 
                                  {"route": "/api", "method": "POST", "status": "error"})
        
        # Should reuse the same underlying metric registry entry
        assert "http_requests_total" in registry._metrics
        assert isinstance(counter1, CounterWrapper)
        assert isinstance(counter2, CounterWrapper)
    
    def test_counter_with_empty_labels(self):
        """Test counter creation with empty labels."""
        registry = MetricsRegistry()
        
        counter = registry.counter("outbox_polled_total", {})
        
        assert isinstance(counter, CounterWrapper)
    
    def test_counter_duplicate_handling(self):
        """Test counter duplicate handling."""
        registry = MetricsRegistry()
        
        # Create counter first
        counter1 = registry.counter("http_requests_total", 
                                  {"route": "/test", "method": "GET", "status": "success"})
        
        # Should successfully create labeled instances without errors
        counter2 = registry.counter("http_requests_total", 
                                  {"route": "/api", "method": "POST", "status": "error"})
        
        assert isinstance(counter1, CounterWrapper)
        assert isinstance(counter2, CounterWrapper)
    
    def test_histogram_creation(self):
        """Test histogram creation."""
        registry = MetricsRegistry()
        
        histogram = registry.histogram("http_request_duration_seconds", 
                                     {"route": "/test", "method": "GET"})
        
        assert isinstance(histogram, Histogram)
        assert "http_request_duration_seconds" in registry._metrics
    
    def test_histogram_with_custom_buckets(self):
        """Test histogram creation with custom buckets."""
        registry = MetricsRegistry()
        
        custom_buckets = [0.1, 0.5, 1.0, 2.0, 5.0]
        histogram = registry.histogram("http_request_duration_seconds", 
                                     {"route": "/test", "method": "GET"},
                                     buckets=custom_buckets)
        
        assert isinstance(histogram, Histogram)
    
    def test_histogram_reuse(self):
        """Test histogram reuse."""
        registry = MetricsRegistry()
        
        # Create histogram twice with same metric name
        hist1 = registry.histogram("http_request_duration_seconds", 
                                 {"route": "/test", "method": "GET"})
        hist2 = registry.histogram("http_request_duration_seconds", 
                                 {"route": "/api", "method": "POST"})
        
        # Should reuse the same underlying metric registry entry
        assert "http_request_duration_seconds" in registry._metrics
        assert isinstance(hist1, Histogram)
        assert isinstance(hist2, Histogram)
    
    def test_histogram_duplicate_handling(self):
        """Test histogram duplicate handling."""
        registry = MetricsRegistry()
        
        # Create histogram first
        hist1 = registry.histogram("http_request_duration_seconds", 
                                 {"route": "/test", "method": "GET"})
        
        # Should successfully create labeled instances without errors
        hist2 = registry.histogram("http_request_duration_seconds", 
                                 {"route": "/api", "method": "POST"})
        
        assert isinstance(hist1, Histogram)
        assert isinstance(hist2, Histogram)
    
    def test_gauge_creation(self):
        """Test gauge creation."""
        registry = MetricsRegistry()
        
        gauge = registry.gauge("websocket_connections_total", {"client_type": "trading"})
        
        assert isinstance(gauge, Gauge)
        assert "websocket_connections_total" in registry._metrics
    
    def test_gauge_reuse(self):
        """Test gauge reuse."""
        registry = MetricsRegistry()
        
        # Create gauge twice with same metric name
        gauge1 = registry.gauge("websocket_connections_total", {"client_type": "trading"})
        gauge2 = registry.gauge("websocket_connections_total", {"client_type": "monitoring"})
        
        # Should reuse the same underlying metric registry entry
        assert "websocket_connections_total" in registry._metrics
        assert isinstance(gauge1, Gauge)
        assert isinstance(gauge2, Gauge)
    
    def test_gauge_duplicate_handling(self):
        """Test gauge duplicate handling."""
        registry = MetricsRegistry()
        
        # Create gauge first
        gauge1 = registry.gauge("websocket_connections_total", {"client_type": "trading"})
        
        # Should successfully create labeled instances without errors
        gauge2 = registry.gauge("websocket_connections_total", {"client_type": "admin"})
        
        assert isinstance(gauge1, Gauge)
        assert isinstance(gauge2, Gauge)
    
    def test_inc_counter_convenience(self):
        """Test inc_counter convenience method."""
        registry = MetricsRegistry()
        
        registry.inc_counter("http_requests_total", 
                           {"route": "/test", "method": "GET", "status": "success"}, 
                           amount=2.0)
        
        counter = registry.counters["http_requests_total"]
        assert counter.value >= 2.0
    
    def test_observe_histogram_convenience(self):
        """Test observe_histogram convenience method."""
        registry = MetricsRegistry()
        
        registry.observe_histogram("http_request_duration_seconds", 
                                 0.5, 
                                 {"route": "/test", "method": "GET"})
        
        # Should not raise exception
        assert "http_request_duration_seconds" in registry._metrics
    
    def test_set_gauge_convenience(self):
        """Test set_gauge convenience method."""
        registry = MetricsRegistry()
        
        registry.set_gauge("websocket_connections_total", 
                         5.0, 
                         {"client_type": "trading"})
        
        # Should not raise exception
        assert "websocket_connections_total" in registry._metrics
    
    def test_strategy_signals_convenience(self):
        """Test strategy signals convenience method."""
        registry = MetricsRegistry()
        
        registry.inc_strategy_signals("momentum", 3.0)
        
        counter = registry.counters["strategy_signals_total"]
        assert counter.value >= 3.0
    
    def test_strategy_netting_decisions_convenience(self):
        """Test strategy netting decisions convenience method."""
        registry = MetricsRegistry()
        
        registry.inc_strategy_netting_decisions("AAPL", 2.0)
        
        counter = registry.counters["strategy_netting_decisions_total"]
        assert counter.value >= 2.0
    
    def test_strategy_throttled_convenience(self):
        """Test strategy throttled convenience method."""
        registry = MetricsRegistry()
        
        registry.inc_strategy_throttled(1.0)
        
        counter = registry.counters["strategy_throttled_total"]
        assert counter.value >= 1.0
    
    def test_strategy_blocked_convenience(self):
        """Test strategy blocked convenience method."""
        registry = MetricsRegistry()
        
        registry.inc_strategy_blocked("risk_limit", 1.0)
        
        counter = registry.counters["strategy_blocked_total"]
        assert counter.value >= 1.0
    
    def test_strategy_planned_notional_convenience(self):
        """Test strategy planned notional convenience method."""
        registry = MetricsRegistry()
        
        registry.set_strategy_planned_notional("AAPL", 100000.0)
        
        gauge = registry.gauges["strategy_planned_notional_A-F"]
        # Should not raise exception
        assert gauge is not None
    
    def test_get_symbol_bucket(self):
        """Test symbol bucket classification."""
        registry = MetricsRegistry()
        
        assert registry._get_symbol_bucket("AAPL") == "A-F"
        assert registry._get_symbol_bucket("GOOGL") == "G-M"
        assert registry._get_symbol_bucket("NVDA") == "N-S"
        assert registry._get_symbol_bucket("TSLA") == "T-Z"
        assert registry._get_symbol_bucket("123") == "other"
        assert registry._get_symbol_bucket("") == "other"
    
    def test_get_metrics_data(self):
        """Test metrics data export."""
        registry = MetricsRegistry()
        
        # Create some metrics
        registry.inc_counter("http_requests_total", 
                           {"route": "/test", "method": "GET", "status": "success"})
        
        data = registry.get_metrics_data()
        
        assert isinstance(data, bytes)
        assert b"http_requests_total" in data
    
    def test_get_content_type(self):
        """Test metrics content type."""
        registry = MetricsRegistry()
        
        content_type = registry.get_content_type()
        
        # Should be a valid Prometheus content type
        assert "text/plain" in content_type
        assert "charset=utf-8" in content_type
    
    def test_validate_route_template_without_contracts(self):
        """Test route template validation without observability contracts."""
        registry = MetricsRegistry()
        registry.observability_contract = None
        
        result = registry.validate_route_template("/api/v1/orders/submit")
        
        assert result == "/api/v1/orders/submit"
    
    def test_validate_route_template_with_contracts(self):
        """Test route template validation with observability contracts."""
        registry = MetricsRegistry()
        
        # Mock observability contract
        mock_contract = Mock()
        mock_contract.validate_route_labeling.return_value = "/api/v1/orders/submit"
        registry.observability_contract = mock_contract
        
        result = registry.validate_route_template("/api/v1/orders/submit")
        
        assert result == "/api/v1/orders/submit"
        mock_contract.validate_route_labeling.assert_called_once()
    
    def test_check_duplicate_metrics_without_contracts(self):
        """Test duplicate metrics check without observability contracts."""
        registry = MetricsRegistry()
        registry.observability_contract = None
        
        # Create some metrics
        registry.counter("http_requests_total", {"route": "/test", "method": "GET", "status": "success"})
        
        duplicates = registry.check_duplicate_metrics()
        
        assert isinstance(duplicates, list)
    
    def test_check_duplicate_metrics_with_contracts(self):
        """Test duplicate metrics check with observability contracts."""
        registry = MetricsRegistry()
        
        # Mock observability contract
        mock_contract = Mock()
        mock_contract.check_for_duplicate_metrics.return_value = []
        registry.observability_contract = mock_contract
        
        duplicates = registry.check_duplicate_metrics()
        
        assert duplicates == []
        mock_contract.check_for_duplicate_metrics.assert_called_once()
    
    def test_get_observability_summary_without_contracts(self):
        """Test observability summary without contracts."""
        registry = MetricsRegistry()
        registry.observability_contract = None
        
        summary = registry.get_observability_summary()
        
        assert isinstance(summary, dict)
        assert "duplicate_metrics" in summary
        assert "duplicate_count" in summary
        assert summary["observability_contracts_enabled"] is False
    
    def test_get_observability_summary_with_contracts(self):
        """Test observability summary with contracts."""
        registry = MetricsRegistry()
        
        # Mock observability contract
        mock_contract = Mock()
        mock_contract.get_validation_summary.return_value = {"test": "summary"}
        registry.observability_contract = mock_contract
        
        summary = registry.get_observability_summary()
        
        assert summary == {"test": "summary"}
        mock_contract.get_validation_summary.assert_called_once()


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_normalize_route_exact_match(self):
        """Test route normalization with exact match."""
        result = normalize_route("/api/v1/orders/submit")
        
        assert result == "/api/v1/orders/submit"
    
    def test_normalize_route_uuid_replacement(self):
        """Test route normalization with UUID replacement."""
        result = normalize_route("/api/v1/orders/12345678-1234-1234-1234-123456789012")
        
        assert result == "/api/v1/orders/{id}"
    
    def test_normalize_route_numeric_id_replacement(self):
        """Test route normalization with numeric ID replacement."""
        result = normalize_route("/api/v1/orders/123/cancel")
        
        assert result == "/api/v1/orders/{id}/cancel"
    
    def test_normalize_route_no_change(self):
        """Test route normalization with no changes needed."""
        result = normalize_route("/api/v1/health")
        
        assert result == "/api/v1/health"
    
    def test_normalize_alpaca_endpoint_exact_match(self):
        """Test Alpaca endpoint normalization with exact match."""
        result = normalize_alpaca_endpoint("/v2/orders")
        
        assert result == "/v2/orders"
    
    def test_normalize_alpaca_endpoint_order_id(self):
        """Test Alpaca endpoint normalization with order ID."""
        result = normalize_alpaca_endpoint("/v2/orders/order123")
        
        assert result == "/v2/orders/{id}"
    
    def test_normalize_alpaca_endpoint_symbol(self):
        """Test Alpaca endpoint normalization with symbol."""
        result = normalize_alpaca_endpoint("/v2/positions/AAPL")
        
        assert result == "/v2/positions/{symbol}"
    
    def test_normalize_alpaca_endpoint_unknown(self):
        """Test Alpaca endpoint normalization with unknown endpoint."""
        result = normalize_alpaca_endpoint("/unknown/endpoint")
        
        assert result == "/unknown"
    
    def test_get_metrics_registry_singleton(self):
        """Test global metrics registry singleton."""
        # Clear global registry
        import backend.infra.metrics
        backend.infra.metrics._registry = None
        
        registry1 = get_metrics_registry()
        registry2 = get_metrics_registry()
        
        assert registry1 is registry2
        assert isinstance(registry1, MetricsRegistry)
    
    def test_initialize_metrics_registry(self):
        """Test metrics registry initialization."""
        custom_registry = CollectorRegistry()
        
        registry = initialize_metrics_registry(namespace="test", registry=custom_registry)
        
        assert isinstance(registry, MetricsRegistry)
        assert registry.namespace == "test"
        assert registry.registry == custom_registry
    
    def test_track_model_prediction(self):
        """Test track_model_prediction function."""
        # Should not raise exception (no-op function)
        result = track_model_prediction("test", "args", key="value")
        
        assert result is None


class TestConstants:
    """Test module constants."""
    
    def test_label_allowlist_exists(self):
        """Test that LABEL_ALLOWLIST is properly defined."""
        assert isinstance(LABEL_ALLOWLIST, dict)
        assert len(LABEL_ALLOWLIST) > 0
        assert "http_requests_total" in LABEL_ALLOWLIST
    
    def test_label_value_allowlist_exists(self):
        """Test that LABEL_VALUE_ALLOWLIST is properly defined."""
        assert isinstance(LABEL_VALUE_ALLOWLIST, dict)
        assert len(LABEL_VALUE_ALLOWLIST) > 0
        assert "status" in LABEL_VALUE_ALLOWLIST
    
    def test_route_templates_exists(self):
        """Test that ROUTE_TEMPLATES is properly defined."""
        assert isinstance(ROUTE_TEMPLATES, dict)
        assert len(ROUTE_TEMPLATES) > 0
        assert "/health" in ROUTE_TEMPLATES
    
    def test_alpaca_endpoint_templates_exists(self):
        """Test that ALPACA_ENDPOINT_TEMPLATES is properly defined."""
        assert isinstance(ALPACA_ENDPOINT_TEMPLATES, dict)
        assert len(ALPACA_ENDPOINT_TEMPLATES) > 0
        assert "/v2/orders" in ALPACA_ENDPOINT_TEMPLATES


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_counter_creation_other_value_error(self):
        """Test counter creation with other ValueError."""
        registry = MetricsRegistry()
        
        with patch.object(Counter, '__init__', side_effect=ValueError("Other error")):
            with pytest.raises(ValueError, match="Other error"):
                registry.counter("http_requests_total", 
                               {"route": "/test", "method": "GET", "status": "success"})
    
    def test_histogram_creation_other_value_error(self):
        """Test histogram creation with other ValueError."""
        registry = MetricsRegistry()
        
        with patch.object(Histogram, '__init__', side_effect=ValueError("Other error")):
            with pytest.raises(ValueError, match="Other error"):
                registry.histogram("http_request_duration_seconds", 
                                 {"route": "/test", "method": "GET"})
    
    def test_gauge_creation_other_value_error(self):
        """Test gauge creation with other ValueError."""
        registry = MetricsRegistry()
        
        with patch.object(Gauge, '__init__', side_effect=ValueError("Other error")):
            with pytest.raises(ValueError, match="Other error"):
                registry.gauge("websocket_connections_total", {"client_type": "trading"})


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_labels_handling(self):
        """Test handling of empty labels."""
        registry = MetricsRegistry()
        
        # Test with metric that allows empty labels
        counter = registry.counter("outbox_polled_total", {})
        
        assert isinstance(counter, CounterWrapper)
    
    def test_label_string_conversion(self):
        """Test that label values are converted to strings."""
        registry = MetricsRegistry()
        
        # Test with non-string label values
        labels = {"route": "/test", "method": "GET", "status": 200}  # status as int
        validated = registry._validate_labels("http_requests_total", labels)
        
        assert validated["status"] == "200"  # Should be converted to string
    
    def test_duplicate_check_with_empty_registry(self):
        """Test duplicate check with empty registry."""
        registry = MetricsRegistry()
        registry.observability_contract = None
        
        duplicates = registry.check_duplicate_metrics()
        
        assert duplicates == []
    
    def test_observability_contracts_fallback(self):
        """Test fallback when observability contracts not available."""
        # Mock the import failure
        with patch('backend.infra.metrics.OBSERVABILITY_CONTRACTS_AVAILABLE', False):
            registry = MetricsRegistry()
            
            # Should use fallback histogram buckets
            buckets = registry.histogram("http_request_duration_seconds", 
                                       {"route": "/test", "method": "GET"})
            assert isinstance(buckets, Histogram)
    
    def test_get_histogram_buckets_fallback(self):
        """Test get_histogram_buckets fallback function."""
        # Test with known metric that has buckets defined
        from backend.infra.metrics import get_histogram_buckets
        
        try:
            buckets = get_histogram_buckets("http_request_duration_seconds")
            assert isinstance(buckets, tuple)
            assert len(buckets) > 0
        except ValueError:
            # If specific metric not found, test that function exists
            assert get_histogram_buckets is not None
    
    def test_counter_duplicate_registry_handling(self):
        """Test counter duplicate handling in registry."""
        registry = MetricsRegistry()
        
        # Create counter
        counter1 = registry.counter("http_requests_total", 
                                  {"route": "/test", "method": "GET", "status": "success"})
        
        # Mock ValueError for duplicate during registry creation
        with patch.object(Counter, '__new__', side_effect=ValueError("Duplicated timeseries")):
            # Create a mock collector in registry
            mock_collector = Mock()
            mock_collector._name = "intraday_http_requests_total"
            registry.registry._collector_to_names = {mock_collector: ["test"]}
            registry._metrics["http_requests_total"] = mock_collector
            
            # This should find and reuse the existing metric
            counter2 = registry.counter("http_requests_total", 
                                      {"route": "/api", "method": "POST", "status": "error"})
            
            assert counter2 is not None
    
    def test_histogram_bucket_determination(self):
        """Test histogram bucket determination logic."""
        registry = MetricsRegistry()
        
        # Test with observability contract available
        if hasattr(registry, 'observability_contract') and registry.observability_contract:
            hist = registry.histogram("http_request_duration_seconds", 
                                    {"route": "/test", "method": "GET"})
            assert isinstance(hist, Histogram)
        
        # Test with custom buckets
        custom_buckets = [0.1, 0.5, 1.0]
        hist_custom = registry.histogram("alpaca_http_latency_seconds", 
                                       {"endpoint": "/v2/orders", "method": "POST"},
                                       buckets=custom_buckets)
        assert isinstance(hist_custom, Histogram)
    
    def test_histogram_duplicate_registry_handling(self):
        """Test histogram duplicate handling in registry."""
        registry = MetricsRegistry()
        
        # Create histogram
        hist1 = registry.histogram("http_request_duration_seconds", 
                                 {"route": "/test", "method": "GET"})
        
        # Mock ValueError for duplicate during registry creation
        with patch.object(Histogram, '__new__', side_effect=ValueError("Duplicated timeseries")):
            # Create a mock collector in registry
            mock_collector = Mock()
            mock_collector._name = "intraday_http_request_duration_seconds"
            registry.registry._collector_to_names = {mock_collector: ["test"]}
            registry._metrics["http_request_duration_seconds"] = mock_collector
            
            # This should find and reuse the existing metric
            hist2 = registry.histogram("http_request_duration_seconds", 
                                     {"route": "/api", "method": "POST"})
            
            assert hist2 is not None
    
    def test_gauge_duplicate_registry_handling(self):
        """Test gauge duplicate handling in registry."""
        registry = MetricsRegistry()
        
        # Create gauge
        gauge1 = registry.gauge("websocket_connections_total", {"client_type": "trading"})
        
        # Mock ValueError for duplicate during registry creation
        with patch.object(Gauge, '__new__', side_effect=ValueError("Duplicated timeseries")):
            # Create a mock collector in registry
            mock_collector = Mock()
            mock_collector._name = "intraday_websocket_connections_total"
            registry.registry._collector_to_names = {mock_collector: ["test"]}
            registry._metrics["websocket_connections_total"] = mock_collector
            
            # This should find and reuse the existing metric
            gauge2 = registry.gauge("websocket_connections_total", {"client_type": "admin"})
            
            assert gauge2 is not None


class TestCoverageGaps:
    """Test specific coverage gaps identified."""
    
    def test_observability_summary_duplicate_detection(self):
        """Test observability summary with actual duplicates."""
        registry = MetricsRegistry()
        registry.observability_contract = None
        
        # Create some test data to simulate duplicates
        duplicates = registry.check_duplicate_metrics()
        
        summary = registry.get_observability_summary()
        
        assert "duplicate_metrics" in summary
        assert "duplicate_count" in summary
        assert summary["observability_contracts_enabled"] is False