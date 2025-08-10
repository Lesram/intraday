"""
Comprehensive test suite for Branch 2.5 observability infrastructure.
Tests OpenTelemetry tracing, Prometheus metrics, structured logging, and integration.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from prometheus_client.core import CollectorRegistry

# Test imports
from backend.config import get_settings
from backend.infra.observability import (
    initialize_observability,
    ObservabilityConfig,
    trace_span,
    record_latency,
    record_alpaca_request,
    record_database_operation,
    record_outbox_metrics,
    get_tracer,
    get_meter
)
from backend.infra.metrics import (
    MetricsRegistry,
    initialize_metrics_registry,
    get_metrics_registry,
    normalize_route,
    normalize_alpaca_endpoint,
    LABEL_ALLOWLIST,
    LABEL_VALUE_ALLOWLIST
)
from backend.infra.logging import (
    configure_structured_logging,
    get_logger,
    JSONFormatter,
    TraceIdFilter,
    StructuredLogger
)


class TestObservabilityConfig:
    """Test observability configuration functionality."""
    
    def test_observability_config_defaults(self):
        """Test observability configuration with default values."""
        config = ObservabilityConfig()
        
        assert config.service_name == "intraday-trading"
        assert config.service_version == "2.0.0"
        assert config.otel_enabled is True
        assert config.prometheus_enabled is True
        assert config.otel_sampler == "traceidratio"
        assert config.otel_sampler_arg == 0.1
    
    def test_observability_config_custom_values(self):
        """Test observability configuration with custom values."""
        config = ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            otel_enabled=False,
            prometheus_enabled=False,
            otel_sampler="always_on",
            otel_sampler_arg=1.0,
            latency_buckets_ms="5,10,25,50,100"
        )
        
        assert config.service_name == "test-service"
        assert config.service_version == "1.0.0"
        assert config.otel_enabled is False
        assert config.prometheus_enabled is False
        assert config.otel_sampler == "always_on"
        assert config.otel_sampler_arg == 1.0
    
    def test_latency_buckets_parsing(self):
        """Test latency buckets parsing from string to float list."""
        config = ObservabilityConfig(latency_buckets_ms="1,5,10,25,50")
        buckets = config.latency_buckets
        
        expected = [0.001, 0.005, 0.010, 0.025, 0.050]  # Converted to seconds
        assert buckets == expected


class TestMetricsRegistry:
    """Test metrics registry functionality."""
    
    @pytest.fixture
    def metrics_registry(self):
        """Create a test metrics registry."""
        # Use a separate registry for testing
        test_registry = CollectorRegistry()
        return MetricsRegistry(namespace="test", registry=test_registry)
    
    def test_counter_creation_and_validation(self, metrics_registry):
        """Test counter creation with label validation."""
        # Valid metric with correct labels
        counter = metrics_registry.counter(
            "http_requests_total",
            {"route": "/test", "method": "GET", "status": "success"}
        )
        assert counter is not None
        
        # Test increment
        metrics_registry.inc_counter(
            "http_requests_total",
            {"route": "/test", "method": "GET", "status": "success"}
        )
    
    def test_histogram_creation_and_validation(self, metrics_registry):
        """Test histogram creation with label validation."""
        histogram = metrics_registry.histogram(
            "http_request_duration_seconds",
            {"route": "/test", "method": "GET"}
        )
        assert histogram is not None
        
        # Test observation
        metrics_registry.observe_histogram(
            "http_request_duration_seconds",
            0.5,
            {"route": "/test", "method": "GET"}
        )
    
    def test_gauge_creation_and_validation(self, metrics_registry):
        """Test gauge creation with label validation."""
        gauge = metrics_registry.gauge(
            "outbox_queue_gauge",
            {"status": "pending"}
        )
        assert gauge is not None
        
        # Test setting value
        metrics_registry.set_gauge(
            "outbox_queue_gauge",
            10.0,
            {"status": "pending"}
        )
    
    def test_invalid_metric_name_raises_error(self, metrics_registry):
        """Test that invalid metric names raise validation errors."""
        with pytest.raises(ValueError, match="not found in LABEL_ALLOWLIST"):
            metrics_registry.counter("invalid_metric_name", {})
    
    def test_invalid_labels_raise_error(self, metrics_registry):
        """Test that invalid labels raise validation errors."""
        with pytest.raises(ValueError, match="Unexpected labels"):
            metrics_registry.counter(
                "http_requests_total",
                {"invalid_label": "value"}
            )
    
    def test_missing_required_labels_raise_error(self, metrics_registry):
        """Test that missing required labels raise validation errors."""
        with pytest.raises(ValueError, match="Missing required labels"):
            metrics_registry.counter("http_requests_total", {"route": "/test"})
    
    def test_route_normalization(self):
        """Test route path normalization for cardinality control."""
        # Test UUID replacement
        assert normalize_route("/orders/123e4567-e89b-12d3-a456-426614174000") == "/orders/{id}"
        
        # Test numeric ID replacement
        assert normalize_route("/orders/12345") == "/orders/{id}"
        
        # Test known routes
        assert normalize_route("/api/v1/orders/submit") == "/api/v1/orders/submit"
        
        # Test unknown routes
        assert normalize_route("/unknown/path") == "/unknown/path"
    
    def test_alpaca_endpoint_normalization(self):
        """Test Alpaca endpoint normalization."""
        assert normalize_alpaca_endpoint("/v2/orders/abc123") == "/v2/orders/{id}"
        assert normalize_alpaca_endpoint("/v2/positions/AAPL") == "/v2/positions/{symbol}"
        assert normalize_alpaca_endpoint("/v2/account") == "/v2/account"


class TestStructuredLogging:
    """Test structured logging functionality."""
    
    @pytest.fixture
    def log_formatter(self):
        """Create a test JSON formatter."""
        return JSONFormatter(
            service_name="test-service",
            service_version="1.0.0",
            include_trace=True
        )
    
    def test_json_formatter_basic_message(self, log_formatter):
        """Test JSON formatter with basic log message."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=100,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Mock trace attributes
        record.trace_id = "trace123"
        record.span_id = "span456"
        
        formatted = log_formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["message"] == "Test message"
        assert log_data["level"] == "INFO"
        assert log_data["trace_id"] == "trace123"
        assert log_data["span_id"] == "span456"
        assert log_data["service"]["name"] == "test-service"
        assert log_data["service"]["version"] == "1.0.0"
        assert "timestamp" in log_data
    
    def test_structured_logger_domain_methods(self):
        """Test structured logger domain-specific methods."""
        logger = get_logger("test.logger")
        
        # Mock the underlying logger to capture calls
        with patch.object(logger, '_log_with_context') as mock_log:
            # Test HTTP request logging
            logger.log_http_request(
                method="GET",
                path="/test",
                status_code=200,
                duration_ms=50.0,
                user_id="user123"
            )
            
            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            assert args[0] == logging.INFO  # log level
            assert "GET /test - 200" in args[1]  # message
            assert "http" in args[2]  # context
            assert args[2]["user_id"] == "user123"
    
    def test_structured_logger_database_operation(self):
        """Test database operation logging."""
        logger = get_logger("test.logger")
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_database_operation(
                operation="select",
                table="orders",
                duration_ms=25.5,
                rows_affected=5
            )
            
            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            context = args[2]
            assert context["database"]["operation"] == "select"
            assert context["database"]["table"] == "orders"
            assert context["database"]["duration_ms"] == 25.5
            assert context["database"]["rows_affected"] == 5
    
    def test_structured_logger_order_event(self):
        """Test order event logging."""
        logger = get_logger("test.logger")
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_order_event(
                event="order_submitted",
                order_id="order123",
                symbol="AAPL",
                side="buy",
                quantity=100.0,
                price=150.50
            )
            
            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            context = args[2]
            assert context["order"]["event"] == "order_submitted"
            assert context["order"]["order_id"] == "order123"
            assert context["order"]["symbol"] == "AAPL"
            assert context["order"]["side"] == "buy"


class TestObservabilityInitialization:
    """Test observability initialization and integration."""
    
    def test_observability_initialization_called(self):
        """Test that observability initialization works correctly."""
        config = ObservabilityConfig(
            service_name="test-service",
            otel_enabled=True,
            prometheus_enabled=True
        )
        
        # Test that initialization doesn't raise an exception
        try:
            initialize_observability(config)
            success = True
        except Exception:
            success = False
        
        assert success, "Observability initialization should succeed"
    
    def test_metrics_registry_initialization(self):
        """Test metrics registry initialization."""
        registry = initialize_metrics_registry(namespace="test_init")
        assert registry.namespace == "test_init"
        
        # Test global registry access
        global_registry = get_metrics_registry()
        assert global_registry is not None
    
    def test_structured_logging_configuration(self):
        """Test structured logging configuration."""
        # Test that configuration doesn't raise an exception
        try:
            configure_structured_logging(
                level="INFO",
                service_name="test-service",
                json_format=True,
                enable_trace_correlation=True
            )
            success = True
        except Exception:
            success = False
        
        assert success, "Structured logging configuration should succeed"


class TestObservabilityDecorators:
    """Test observability decorators and context managers."""
    
    @pytest.mark.asyncio
    async def test_record_latency_decorator_async(self):
        """Test record_latency decorator with async functions."""
        
        @record_latency("http_request_duration_seconds", method="GET")
        async def test_async_function():
            await asyncio.sleep(0.1)
            return "success"
        
        # Mock the metrics registry to avoid dependencies
        with patch('backend.infra.observability.get_metrics_registry') as mock_registry:
            mock_registry.return_value.observe_histogram = MagicMock()
            
            result = await test_async_function()
            assert result == "success"
            mock_registry.return_value.observe_histogram.assert_called_once()
    
    def test_record_latency_decorator_sync(self):
        """Test record_latency decorator with sync functions."""
        
        @record_latency("db_query_duration_seconds", extra_labels={"operation": "select"})
        def test_sync_function():
            time.sleep(0.1)
            return "success"
        
        with patch('backend.infra.observability.get_metrics_registry') as mock_registry:
            mock_registry.return_value.observe_histogram = MagicMock()
            
            result = test_sync_function()
            assert result == "success"
            mock_registry.return_value.observe_histogram.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_trace_span_context_manager(self):
        """Test trace_span context manager."""
        with patch('backend.infra.observability.get_tracer') as mock_tracer:
            mock_span = MagicMock()
            mock_tracer.return_value.start_as_current_span.return_value.__enter__ = lambda self: mock_span
            mock_tracer.return_value.start_as_current_span.return_value.__exit__ = lambda self, *args: None
            
            with trace_span("test_operation", {"test.attribute": "value"}):
                pass
            
            mock_tracer.return_value.start_as_current_span.assert_called_once_with("test_operation")
    
    def test_record_alpaca_request_metrics(self):
        """Test Alpaca request metrics recording."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_registry:
            mock_registry.return_value.inc_counter = MagicMock()
            mock_registry.return_value.observe_histogram = MagicMock()
            
            record_alpaca_request(
                endpoint="/v2/orders",
                method="POST",
                status_code=201,
                duration_seconds=0.5
            )
            
            # Verify counter was incremented
            mock_registry.return_value.inc_counter.assert_called_once_with(
                "alpaca_http_requests_total",
                {"endpoint": "/v2/orders", "method": "POST", "status": "success"}
            )
            
            # Verify histogram was observed
            mock_registry.return_value.observe_histogram.assert_called_once_with(
                "alpaca_http_latency_seconds",
                0.5,
                {"endpoint": "/v2/orders", "method": "POST"}
            )
    
    def test_record_database_operation_metrics(self):
        """Test database operation metrics recording."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_registry:
            mock_registry.return_value.observe_histogram = MagicMock()
            mock_registry.return_value.inc_counter = MagicMock()
            
            record_database_operation(
                operation="select",
                duration_seconds=0.025,
                success=True
            )
            
            # Verify histogram was observed
            mock_registry.return_value.observe_histogram.assert_called_once_with(
                "db_query_duration_seconds",
                0.025,
                {"operation": "select"}
            )
            
            # Since this is a successful operation, health check counter should not be called
            # (health check counter is only called for health_check operations)
    
    def test_record_outbox_metrics_comprehensive(self):
        """Test comprehensive outbox metrics recording."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_registry:
            mock_registry.return_value.inc_counter = MagicMock()
            mock_registry.return_value.set_gauge = MagicMock()
            mock_registry.return_value.observe_histogram = MagicMock()
            
            record_outbox_metrics(
                polled_count=1,
                dispatched_count=5,
                failed_count=2,
                queue_size=10,
                dispatch_duration_seconds=1.5
            )
            
            # Verify multiple metrics were recorded
            assert mock_registry.return_value.inc_counter.call_count >= 2
            assert mock_registry.return_value.set_gauge.called
            assert mock_registry.return_value.observe_histogram.called


class TestObservabilityIntegration:
    """Test observability integration with application components."""
    
    @pytest.mark.asyncio
    async def test_database_health_check_observability(self):
        """Test database health check with observability."""
        from backend.infra.db import db_health_check
        
        with patch('backend.infra.db._engine') as mock_engine:
            mock_conn = AsyncMock()
            mock_result = MagicMock()  # Regular mock for synchronous result
            mock_result.fetchone.return_value = (1,)
            mock_conn.execute.return_value = mock_result
            mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
            
            with patch('backend.infra.db.record_database_operation') as mock_record:
                with patch('backend.infra.db.get_structured_logger'):
                    result = await db_health_check()
                    
                    assert result is True
                    mock_record.assert_called_once()
                    args, kwargs = mock_record.call_args
                    assert kwargs['operation'] == 'health_check'
                    assert kwargs['success'] is True
    
    @pytest.mark.asyncio 
    async def test_alpaca_client_observability_integration(self):
        """Test Alpaca client observability integration."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Mock the dependencies to avoid actual API calls
        with patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True):
            with patch('backend.data.alpaca_client.TradingClient') as mock_trading_client:
                with patch('backend.data.alpaca_client.record_alpaca_request') as mock_record:
                    with patch('backend.data.alpaca_client.get_structured_logger'):
                        # Create mock order response
                        mock_order = MagicMock()
                        mock_order.id = "order123"
                        mock_order.symbol = "AAPL"
                        mock_order.side.value = "buy"
                        mock_order.qty = 100
                        mock_order.filled_qty = 0
                        mock_order.filled_avg_price = None
                        mock_order.status.value = "pending"
                        mock_order.created_at = "2024-01-01T10:00:00Z"
                        
                        mock_trading_client.return_value.submit_order.return_value = mock_order
                        
                        # Create Alpaca client in test mode
                        client = AlpacaClient("test_key", "test_secret", test_mode=True)
                        
                        # Mock rate limiting
                        client._rate_limit = MagicMock()
                        
                        # Submit order
                        result = client.submit_order("AAPL", 100, "buy")
                        
                        # Verify observability was recorded
                        assert mock_record.called
                        assert result.order_id == "order123"
                        assert result.symbol == "AAPL"


@pytest.mark.integration
class TestObservabilityEndToEnd:
    """End-to-end tests for observability infrastructure."""
    
    def test_metrics_endpoint_returns_prometheus_format(self):
        """Test that metrics endpoint returns Prometheus format data."""
        # This would require running the actual FastAPI app
        # For now, test that metrics registry produces correct format
        registry = MetricsRegistry(namespace="test")
        
        # Add some metrics
        registry.inc_counter("http_requests_total", {
            "route": "/test", 
            "method": "GET", 
            "status": "success"
        })
        
        # Get metrics data
        metrics_data = registry.get_metrics_data()
        content_type = registry.get_content_type()
        
        assert isinstance(metrics_data, bytes)
        # Prometheus client returns text/plain by default, not openmetrics
        assert "text/plain" in content_type
        
        # Decode and check content
        metrics_text = metrics_data.decode('utf-8')
        assert "test_http_requests_total" in metrics_text
    
    def test_structured_logging_with_trace_correlation(self):
        """Test structured logging with trace correlation."""
        # Configure logging for test
        configure_structured_logging(
            level="INFO",
            service_name="test-service",
            json_format=True,
            enable_trace_correlation=True
        )
        
        # Use a custom stream to capture output
        import io
        test_stream = io.StringIO()
        
        # Get the underlying Python logger and add our handler
        logger = get_logger("test.integration")
        python_logger = logger.logger  # Get the underlying logger
        
        # Add handler to capture the output
        handler = logging.StreamHandler(test_stream)
        handler.setFormatter(JSONFormatter())
        python_logger.addHandler(handler)
        
        logger.info("Test message", {"test_context": "value"})
        
        # Get the output and verify it contains structured data
        output = test_stream.getvalue()
        assert "Test message" in output
        assert "test_context" in output
        
        # Clean up
        python_logger.removeHandler(handler)


if __name__ == "__main__":
    # Run specific test categories
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-k", "not integration"  # Skip integration tests by default
    ])
