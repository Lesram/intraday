"""
Comprehensive test suite for backend.infra.observability module to achieve 100% coverage.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock, call
from contextlib import contextmanager
import time
from typing import Any

# Import the module under test
from backend.infra.observability import (
    ObservabilityConfig,
    initialize_observability,
    get_tracer,
    get_meter,
    trace_span,
    record_latency,
    record_operation,
    record_alpaca_request,
    record_database_operation,
    record_outbox_metrics,
    record_auth_metrics,
    record_websocket_metrics,
    _setup_tracing,
    _setup_prometheus_metrics,
    _setup_otel_metrics,
    _setup_instrumentation,
)


class TestObservabilityConfig:
    """Test ObservabilityConfig class."""
    
    def test_observability_config_default_values(self):
        """Test ObservabilityConfig with default values."""
        config = ObservabilityConfig()
        
        assert config.service_name == "intraday-trading"
        assert config.service_version == "2.0.0"
        assert config.otel_enabled is True
        assert config.otel_exporter_otlp_endpoint is None
        assert config.otel_exporter_protocol == "grpc"
        assert config.otel_sampler == "traceidratio"
        assert config.otel_sampler_arg == 0.1
        assert config.prometheus_enabled is True
        assert config.prometheus_path == "/metrics"
        assert config.metric_namespace == "intraday"
        assert config.latency_buckets_ms == "1,5,10,25,50,100,250,500,1000,2500,5000,10000"

    def test_observability_config_custom_values(self):
        """Test ObservabilityConfig with custom values."""
        config = ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            otel_enabled=False,
            otel_exporter_otlp_endpoint="http://localhost:4317",
            otel_exporter_protocol="http",
            otel_sampler="always_on",
            otel_sampler_arg=1.0,
            prometheus_enabled=False,
            prometheus_path="/custom-metrics",
            metric_namespace="test",
            latency_buckets_ms="1,10,100,1000"
        )
        
        assert config.service_name == "test-service"
        assert config.service_version == "1.0.0"
        assert config.otel_enabled is False
        assert config.otel_exporter_otlp_endpoint == "http://localhost:4317"
        assert config.otel_exporter_protocol == "http"
        assert config.otel_sampler == "always_on"
        assert config.otel_sampler_arg == 1.0
        assert config.prometheus_enabled is False
        assert config.prometheus_path == "/custom-metrics"
        assert config.metric_namespace == "test"
        assert config.latency_buckets_ms == "1,10,100,1000"

    def test_latency_buckets_property(self):
        """Test latency_buckets property conversion from ms to seconds."""
        config = ObservabilityConfig(latency_buckets_ms="100,500,1000")
        buckets = config.latency_buckets
        
        assert buckets == [0.1, 0.5, 1.0]  # Converted to seconds


class TestObservabilityInitialization:
    """Test observability initialization functions."""
    
    @patch('backend.infra.observability._setup_tracing')
    @patch('backend.infra.observability._setup_prometheus_metrics')
    @patch('backend.infra.observability._setup_otel_metrics')
    @patch('backend.infra.observability._setup_instrumentation')
    @patch('backend.infra.observability.get_metrics_registry')
    def test_initialize_observability_full_setup(self, mock_get_registry, mock_setup_instr, 
                                                 mock_setup_otel, mock_setup_prom, mock_setup_trace):
        """Test full observability initialization."""
        config = ObservabilityConfig(
            otel_enabled=True,
            prometheus_enabled=True,
            otel_exporter_otlp_endpoint="http://localhost:4317"
        )
        
        initialize_observability(config)
        
        mock_setup_trace.assert_called_once()
        mock_setup_prom.assert_called_once()
        mock_setup_otel.assert_called_once()
        mock_setup_instr.assert_called_once()
        mock_get_registry.assert_called_once()

    @patch('backend.infra.observability._setup_tracing')
    @patch('backend.infra.observability._setup_prometheus_metrics')
    @patch('backend.infra.observability._setup_otel_metrics')
    @patch('backend.infra.observability._setup_instrumentation')
    @patch('backend.infra.observability.get_metrics_registry')
    def test_initialize_observability_partial_setup(self, mock_get_registry, mock_setup_instr, 
                                                   mock_setup_otel, mock_setup_prom, mock_setup_trace):
        """Test partial observability initialization."""
        config = ObservabilityConfig(
            otel_enabled=False,
            prometheus_enabled=True,
            otel_exporter_otlp_endpoint=None
        )
        
        initialize_observability(config)
        
        mock_setup_trace.assert_not_called()
        mock_setup_prom.assert_called_once()
        mock_setup_otel.assert_not_called()
        mock_setup_instr.assert_called_once()

    @patch('backend.infra.observability.logger')
    def test_setup_tracing_always_on_sampler(self, mock_logger):
        """Test tracing setup with always_on sampler."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(
            otel_sampler="always_on",
            otel_exporter_otlp_endpoint="http://localhost:4317"
        )
        resource = Resource.create({})
        
        # This should not raise an exception
        _setup_tracing(config, resource)
        
        # Verify logger was called for initialization
        assert mock_logger.info.call_count >= 1

    @patch('backend.infra.observability.logger')
    def test_setup_tracing_always_off_sampler(self, mock_logger):
        """Test tracing setup with always_off sampler."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_sampler="always_off")
        resource = Resource.create({})
        
        # This should not raise an exception  
        _setup_tracing(config, resource)
        
        # Verify logger was called
        assert mock_logger.info.call_count >= 1

    @patch('backend.infra.observability.logger')
    def test_setup_tracing_unknown_sampler(self, mock_logger):
        """Test tracing setup with unknown sampler falls back to traceidratio."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_sampler="unknown_sampler")
        resource = Resource.create({})
        
        # This should not raise an exception
        _setup_tracing(config, resource)
        
        # Verify warning was logged for unknown sampler
        mock_logger.warning.assert_called_once()
        mock_logger.info.assert_called()

    @patch('backend.infra.observability.logger')
    def test_setup_prometheus_metrics(self, mock_logger):
        """Test Prometheus metrics setup."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig()
        resource = Resource.create({})
        
        # This should not raise an exception
        _setup_prometheus_metrics(config, resource)
        
        # Verify logger was called
        assert mock_logger.info.call_count >= 1

    @patch('backend.infra.observability.logger')
    def test_setup_otel_metrics_success(self, mock_logger):
        """Test OTEL metrics setup success case."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_exporter_otlp_endpoint="http://localhost:4317")
        resource = Resource.create({})
        
        # This should not raise an exception
        _setup_otel_metrics(config, resource)
        
        # Verify logger was used (either info or warning)
        assert mock_logger.info.call_count >= 1 or mock_logger.warning.call_count >= 1

    def test_setup_otel_metrics_no_endpoint(self):
        """Test OTEL metrics setup with no endpoint returns early."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_exporter_otlp_endpoint=None)
        resource = Resource.create({})
        
        # Should return early without doing anything
        _setup_otel_metrics(config, resource)

    @patch('opentelemetry.metrics.get_meter_provider')
    def test_setup_otel_metrics_exception_handling(self, mock_get_provider):
        """Test OTEL metrics setup exception handling."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_exporter_otlp_endpoint="http://localhost:4317")
        resource = Resource.create({})
        
        # Mock to raise exception
        mock_get_provider.side_effect = Exception("Test error")
        
        # Should not raise exception, just log warning
        _setup_otel_metrics(config, resource)

    @patch('backend.infra.observability.logger')
    def test_setup_instrumentation(self, mock_logger):
        """Test auto-instrumentation setup."""
        # This should not raise an exception
        _setup_instrumentation()
        
        # Verify logger was called
        assert mock_logger.info.call_count >= 1


class TestTracerAndMeterGetters:
    """Test tracer and meter getter functions."""
    
    @patch('backend.infra.observability._tracer', None)
    @patch('opentelemetry.trace.get_tracer')
    def test_get_tracer_fallback(self, mock_get_tracer):
        """Test get_tracer fallback when _tracer is None."""
        mock_tracer = Mock()
        mock_get_tracer.return_value = mock_tracer
        
        tracer = get_tracer()
        
        assert tracer == mock_tracer
        mock_get_tracer.assert_called_once()

    @patch('backend.infra.observability._meter', None)
    @patch('opentelemetry.metrics.get_meter')
    def test_get_meter_fallback(self, mock_get_meter):
        """Test get_meter fallback when _meter is None."""
        mock_meter = Mock()
        mock_get_meter.return_value = mock_meter
        
        meter = get_meter()
        
        assert meter == mock_meter
        mock_get_meter.assert_called_once()


class TestTraceSpan:
    """Test trace_span context manager."""
    
    @patch('backend.infra.observability.get_tracer')
    def test_trace_span_success(self, mock_get_tracer):
        """Test trace_span success case."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer
        
        attributes = {"key": "value", "number": 42}
        
        with trace_span("test_operation", attributes) as span:
            assert span == mock_span
            span.set_attribute.assert_any_call("key", "value")
            span.set_attribute.assert_any_call("number", 42)

    @patch('backend.infra.observability.get_tracer')
    def test_trace_span_exception(self, mock_get_tracer):
        """Test trace_span exception handling."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer
        
        test_exception = ValueError("Test error")
        
        with pytest.raises(ValueError):
            with trace_span("test_operation") as span:
                span.record_exception.assert_not_called()  # Not called yet
                raise test_exception
        
        mock_span.record_exception.assert_called_once_with(test_exception)
        mock_span.set_status.assert_called_once()

    @patch('backend.infra.observability.get_tracer')
    def test_trace_span_no_attributes(self, mock_get_tracer):
        """Test trace_span without attributes."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer
        
        with trace_span("test_operation") as span:
            assert span == mock_span
            # Should not call set_attribute when no attributes provided
            span.set_attribute.assert_not_called()


class TestRecordLatency:
    """Test record_latency decorator."""
    
    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('backend.infra.observability.normalize_route')
    @patch('time.time')
    def test_record_latency_async_success(self, mock_time, mock_normalize, mock_get_registry, mock_trace_span):
        """Test record_latency decorator with async function success."""
        mock_time.side_effect = [1000.0, 1001.5]  # 1.5 second duration
        mock_normalize.return_value = "/normalized/route"
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(return_value=None)
        
        @record_latency("test_metric", route="/test/route", method="POST", extra_labels={"env": "test"})
        async def test_async_func():
            return "success"
        
        result = asyncio.run(test_async_func())
        
        assert result == "success"
        mock_registry.observe_histogram.assert_called_once_with(
            "test_metric", 1.5, {"env": "test", "route": "/normalized/route", "method": "POST"}
        )
        mock_span.set_attribute.assert_any_call("duration_seconds", 1.5)
        mock_span.set_attribute.assert_any_call("success", True)

    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('time.time')
    def test_record_latency_async_exception(self, mock_time, mock_get_registry, mock_trace_span):
        """Test record_latency decorator with async function exception."""
        mock_time.side_effect = [1000.0, 1001.0]  # 1 second duration
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(side_effect=ValueError("Test error"))
        
        @record_latency("test_metric")
        async def test_async_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            asyncio.run(test_async_func())
        
        mock_registry.observe_histogram.assert_called_once_with("test_metric", 1.0, {})
        mock_span.set_attribute.assert_any_call("duration_seconds", 1.0)
        mock_span.set_attribute.assert_any_call("success", False)
        mock_span.set_attribute.assert_any_call("error_type", "ValueError")

    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('time.time')
    def test_record_latency_sync_success(self, mock_time, mock_get_registry, mock_trace_span):
        """Test record_latency decorator with sync function success."""
        mock_time.side_effect = [1000.0, 1002.0]  # 2 second duration
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(return_value=None)
        
        @record_latency("test_metric")
        def test_sync_func():
            return "success"
        
        result = test_sync_func()
        
        assert result == "success"
        mock_registry.observe_histogram.assert_called_once_with("test_metric", 2.0, {})
        mock_span.set_attribute.assert_any_call("duration_seconds", 2.0)
        mock_span.set_attribute.assert_any_call("success", True)

    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('time.time')
    def test_record_latency_sync_exception(self, mock_time, mock_get_registry, mock_trace_span):
        """Test record_latency decorator with sync function exception."""
        mock_time.side_effect = [1000.0, 1000.5]  # 0.5 second duration
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(side_effect=RuntimeError("Test error"))
        
        @record_latency("test_metric")
        def test_sync_func():
            raise RuntimeError("Test error")
        
        with pytest.raises(RuntimeError):
            test_sync_func()
        
        mock_registry.observe_histogram.assert_called_once_with("test_metric", 0.5, {})
        mock_span.set_attribute.assert_any_call("duration_seconds", 0.5)
        mock_span.set_attribute.assert_any_call("success", False)
        mock_span.set_attribute.assert_any_call("error_type", "RuntimeError")

    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('time.time')
    def test_record_latency_with_label_allowlist(self, mock_time, mock_get_registry, mock_trace_span):
        """Test record_latency decorator exception handling without LABEL_ALLOWLIST."""
        mock_time.side_effect = [1000.0, 1001.0]
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(side_effect=ValueError("Test error"))
        
        @record_latency("test_metric")
        async def test_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            asyncio.run(test_func())
        
        # Should call observe_histogram with base labels (no status since allowlist unavailable)
        mock_registry.observe_histogram.assert_called_with("test_metric", 1.0, {})


class TestRecordOperation:
    """Test record_operation function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('opentelemetry.trace.get_current_span')
    def test_record_operation_success(self, mock_get_span, mock_get_registry):
        """Test record_operation with success."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_get_span.return_value = mock_span
        
        # Mock the metrics module import
        mock_metrics_module = Mock()
        mock_metrics_module.LABEL_ALLOWLIST = {"order_submit_total": ["result"]}
        
        with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
            record_operation("order_submit", True, {"symbol": "AAPL"})
            
            mock_registry.inc_counter.assert_called_once_with(
                "order_submit_total", {"symbol": "AAPL", "result": "success"}
            )
            mock_span.add_event.assert_called_once()

    @patch('backend.infra.observability.get_metrics_registry')
    @patch('opentelemetry.trace.get_current_span')
    def test_record_operation_failure(self, mock_get_span, mock_get_registry):
        """Test record_operation with failure."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_get_span.return_value = mock_span
        
        # Mock the metrics module import
        mock_metrics_module = Mock()
        mock_metrics_module.LABEL_ALLOWLIST = {"signal_generate_total": ["result"]}
        
        with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
            record_operation("signal_generate", False)
            
            mock_registry.inc_counter.assert_called_once_with(
                "signal_generate_total", {"result": "error"}
            )

    @patch('backend.infra.observability.get_metrics_registry')
    @patch('opentelemetry.trace.get_current_span')
    def test_record_operation_no_span(self, mock_get_span, mock_get_registry):
        """Test record_operation when no current span."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_get_span.return_value = None
        
        # Mock the metrics module import
        mock_metrics_module = Mock()
        mock_metrics_module.LABEL_ALLOWLIST = {"test_total": ["result"]}
        
        with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
            record_operation("test", True)
            
            mock_registry.inc_counter.assert_called_once()


class TestRecordAlpacaRequest:
    """Test record_alpaca_request function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('backend.infra.observability.normalize_alpaca_endpoint')
    def test_record_alpaca_request_success(self, mock_normalize, mock_get_registry):
        """Test record_alpaca_request with success status."""
        mock_normalize.return_value = "/orders"
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_alpaca_request("/v2/orders/123", "GET", 200, 0.5)
        
        mock_registry.inc_counter.assert_called_once_with(
            "alpaca_http_requests_total",
            {"endpoint": "/orders", "method": "GET", "status": "success"}
        )
        mock_registry.observe_histogram.assert_called_once_with(
            "alpaca_http_latency_seconds",
            0.5,
            {"endpoint": "/orders", "method": "GET"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    @patch('backend.infra.observability.normalize_alpaca_endpoint')
    def test_record_alpaca_request_client_error(self, mock_normalize, mock_get_registry):
        """Test record_alpaca_request with client error."""
        mock_normalize.return_value = "/orders"
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_alpaca_request("/v2/orders/123", "POST", 400, 0.2)
        
        mock_registry.inc_counter.assert_called_once_with(
            "alpaca_http_requests_total",
            {"endpoint": "/orders", "method": "POST", "status": "error"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    @patch('backend.infra.observability.normalize_alpaca_endpoint')
    def test_record_alpaca_request_server_error(self, mock_normalize, mock_get_registry):
        """Test record_alpaca_request with server error."""
        mock_normalize.return_value = "/positions"
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_alpaca_request("/v2/positions", "GET", 500, 1.0)
        
        mock_registry.inc_counter.assert_called_once_with(
            "alpaca_http_requests_total",
            {"endpoint": "/positions", "method": "GET", "status": "error"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    @patch('backend.infra.observability.normalize_alpaca_endpoint')
    def test_record_alpaca_request_other_status(self, mock_normalize, mock_get_registry):
        """Test record_alpaca_request with other status code."""
        mock_normalize.return_value = "/account"
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_alpaca_request("/v2/account", "GET", 100, 0.1)
        
        mock_registry.inc_counter.assert_called_once_with(
            "alpaca_http_requests_total",
            {"endpoint": "/account", "method": "GET", "status": "error"}
        )


class TestRecordDatabaseOperation:
    """Test record_database_operation function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_database_operation_select(self, mock_get_registry):
        """Test record_database_operation for select operation."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_database_operation("select", 0.1, True)
        
        mock_registry.observe_histogram.assert_called_once_with(
            "db_query_duration_seconds", 0.1, {"operation": "select"}
        )
        mock_registry.inc_counter.assert_not_called()

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_database_operation_health_check_success(self, mock_get_registry):
        """Test record_database_operation for health_check success."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_database_operation("health_check", 0.05, True)
        
        mock_registry.observe_histogram.assert_called_once_with(
            "db_query_duration_seconds", 0.05, {"operation": "health_check"}
        )
        mock_registry.inc_counter.assert_called_once_with(
            "db_health_checks_total", {"result": "success"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_database_operation_health_check_failure(self, mock_get_registry):
        """Test record_database_operation for health_check failure."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_database_operation("health_check", 0.2, False)
        
        mock_registry.observe_histogram.assert_called_once_with(
            "db_query_duration_seconds", 0.2, {"operation": "health_check"}
        )
        mock_registry.inc_counter.assert_called_once_with(
            "db_health_checks_total", {"result": "error"}
        )


class TestRecordOutboxMetrics:
    """Test record_outbox_metrics function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_outbox_metrics_all_values(self, mock_get_registry):
        """Test record_outbox_metrics with all values provided."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_outbox_metrics(
            polled_count=5,
            dispatched_count=3,
            failed_count=1,
            queue_size=10,
            dispatch_duration_seconds=0.5
        )
        
        # Check all expected calls
        mock_registry.inc_counter.assert_any_call("outbox_polled_total", amount=5)
        mock_registry.inc_counter.assert_any_call(
            "outbox_dispatched_total",
            {"topic": "orders", "status": "success"},
            amount=3
        )
        mock_registry.inc_counter.assert_any_call(
            "outbox_dispatched_total",
            {"topic": "orders", "status": "failed"},
            amount=1
        )
        mock_registry.set_gauge.assert_called_once_with(
            "outbox_queue_gauge", 10, {"status": "pending"}
        )
        mock_registry.observe_histogram.assert_called_once_with(
            "outbox_dispatch_latency_seconds",
            0.5,
            {"topic": "orders"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_outbox_metrics_partial_values(self, mock_get_registry):
        """Test record_outbox_metrics with partial values."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_outbox_metrics(
            polled_count=0,
            dispatched_count=2,
            failed_count=0,
            queue_size=5
        )
        
        # Only dispatched_count and queue_size should be recorded
        mock_registry.inc_counter.assert_called_once_with(
            "outbox_dispatched_total",
            {"topic": "orders", "status": "success"},
            amount=2
        )
        mock_registry.set_gauge.assert_called_once_with(
            "outbox_queue_gauge", 5, {"status": "pending"}
        )
        mock_registry.observe_histogram.assert_not_called()


class TestRecordAuthMetrics:
    """Test record_auth_metrics function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_auth_metrics_attempt_success(self, mock_get_registry):
        """Test record_auth_metrics for successful attempt."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_auth_metrics("attempt", True)
        
        mock_registry.inc_counter.assert_called_once_with(
            "auth_attempts_total", {"result": "success"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_auth_metrics_attempt_failure(self, mock_get_registry):
        """Test record_auth_metrics for failed attempt."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_auth_metrics("attempt", False)
        
        mock_registry.inc_counter.assert_called_once_with(
            "auth_attempts_total", {"result": "error"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_auth_metrics_token_validation(self, mock_get_registry):
        """Test record_auth_metrics for token validation."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_auth_metrics("token_validation", True)
        
        mock_registry.inc_counter.assert_called_once_with(
            "auth_token_validations_total", {"result": "success"}
        )

    def test_record_auth_metrics_custom_registry(self):
        """Test record_auth_metrics with custom registry."""
        mock_registry = Mock()
        
        record_auth_metrics("attempt", True, mock_registry)
        
        mock_registry.inc_counter.assert_called_once_with(
            "auth_attempts_total", {"result": "success"}
        )


class TestRecordWebSocketMetrics:
    """Test record_websocket_metrics function."""
    
    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_websocket_metrics_connection(self, mock_get_registry):
        """Test record_websocket_metrics for connection event."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_websocket_metrics("connection", "trading")
        
        mock_registry.inc_counter.assert_called_once_with(
            "websocket_connections_total", {"client_type": "trading"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_websocket_metrics_message(self, mock_get_registry):
        """Test record_websocket_metrics for message event."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_websocket_metrics("message", "api", "order_update", "outbound")
        
        mock_registry.inc_counter.assert_called_once_with(
            "websocket_messages_total",
            {"message_type": "order_update", "direction": "outbound"}
        )

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_websocket_metrics_message_incomplete(self, mock_get_registry):
        """Test record_websocket_metrics for message event with missing params."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_websocket_metrics("message", "api", message_type="order_update")
        
        # Should not call inc_counter since direction is missing
        mock_registry.inc_counter.assert_not_called()

    @patch('backend.infra.observability.get_metrics_registry')
    def test_record_websocket_metrics_unknown_event(self, mock_get_registry):
        """Test record_websocket_metrics for unknown event."""
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        
        record_websocket_metrics("unknown_event", "trading")
        
        # Should not call inc_counter for unknown event
        mock_registry.inc_counter.assert_not_called()


class TestAdditionalCoverage:
    """Additional tests to cover remaining lines."""
    
    def test_setup_tracing_with_otlp_endpoint(self):
        """Test _setup_tracing with OTLP endpoint configuration."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(
            otel_sampler="traceidratio",
            otel_exporter_otlp_endpoint="http://localhost:4317"
        )
        resource = Resource.create({})
        
        # This should execute without errors and cover the OTLP endpoint branch
        _setup_tracing(config, resource)

    def test_record_operation_metric_in_allowlist(self):
        """Test record_operation when counter is in LABEL_ALLOWLIST."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry:
            with patch('opentelemetry.trace.get_current_span') as mock_get_span:
                mock_registry = Mock()
                mock_get_registry.return_value = mock_registry
                mock_span = Mock()
                mock_get_span.return_value = mock_span
                
                # Mock the metrics module import
                mock_metrics_module = Mock()
                mock_metrics_module.LABEL_ALLOWLIST = {"test_operation_total": ["result"]}
                
                with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
                    record_operation("test_operation", True, {"extra": "label"})
                    
                    # Should call inc_counter since metric is in allowlist
                    mock_registry.inc_counter.assert_called_once_with(
                        "test_operation_total", {"extra": "label", "result": "success"}
                    )
                    mock_span.add_event.assert_called_once()

    def test_record_operation_metric_not_in_allowlist(self):
        """Test record_operation when counter is NOT in LABEL_ALLOWLIST.""" 
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry:
            with patch('opentelemetry.trace.get_current_span') as mock_get_span:
                mock_registry = Mock()
                mock_get_registry.return_value = mock_registry
                mock_span = Mock()
                mock_get_span.return_value = mock_span
                
                # Mock the metrics module import with empty allowlist
                mock_metrics_module = Mock()
                mock_metrics_module.LABEL_ALLOWLIST = {}
                
                with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
                    record_operation("unknown_operation", True)
                    
                    # Should NOT call inc_counter since metric is not in allowlist
                    mock_registry.inc_counter.assert_not_called()
                    # Should still add span event
                    mock_span.add_event.assert_called_once()

    @patch('backend.infra.observability.trace_span')
    @patch('backend.infra.observability.get_metrics_registry')
    @patch('time.time')
    def test_record_latency_with_metrics_allowlist_status(self, mock_time, mock_get_registry, mock_trace_span):
        """Test record_latency when status is in LABEL_ALLOWLIST."""
        mock_time.side_effect = [1000.0, 1001.0]
        mock_registry = Mock()
        mock_get_registry.return_value = mock_registry
        mock_span = Mock()
        mock_trace_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace_span.return_value.__exit__ = Mock(side_effect=ValueError("Test error"))
        
        # Mock the metrics module to have status in allowlist
        mock_metrics_module = Mock()
        mock_metrics_module.LABEL_ALLOWLIST = {"test_metric": ["status"]}
        
        with patch.dict('sys.modules', {'backend.infra.metrics': mock_metrics_module}):
            @record_latency("test_metric")
            async def test_func():
                raise ValueError("Test error")
            
            with pytest.raises(ValueError):
                asyncio.run(test_func())
            
            # Should call observe_histogram with status=error since it's in allowlist
            mock_registry.observe_histogram.assert_called_with("test_metric", 1.0, {"status": "error"})

    def test_setup_otel_metrics_meter_provider_without_attribute(self):
        """Test _setup_otel_metrics when meter provider lacks _metric_readers."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_exporter_otlp_endpoint="http://localhost:4317")
        resource = Resource.create({})
        
        with patch('opentelemetry.metrics.get_meter_provider') as mock_get_provider:
            # Mock meter provider without _metric_readers attribute
            mock_provider = Mock(spec=[])  # No _metric_readers attribute
            mock_get_provider.return_value = mock_provider
            
            # Should handle the exception gracefully
            _setup_otel_metrics(config, resource)

    def test_setup_otel_metrics_success_path(self):
        """Test _setup_otel_metrics success path when provider has _metric_readers."""
        from opentelemetry.sdk.resources import Resource
        
        config = ObservabilityConfig(otel_exporter_otlp_endpoint="http://localhost:4317")
        resource = Resource.create({})
        
        with patch('opentelemetry.metrics.get_meter_provider') as mock_get_provider:
            with patch('backend.infra.observability.logger') as mock_logger:
                # Mock meter provider with _metric_readers attribute
                mock_provider = Mock()
                mock_provider._metric_readers = []
                mock_get_provider.return_value = mock_provider
                
                # Should execute the success path and log info message
                _setup_otel_metrics(config, resource)
                
                # Check that the info log was called
                mock_logger.info.assert_called()

    def test_global_tracer_meter_access(self):
        """Test global _tracer and _meter variables are accessed correctly."""
        # Test when global variables are already set
        from backend.infra.observability import get_tracer, get_meter
        
        # These should not raise exceptions
        tracer = get_tracer()
        meter = get_meter()
        
        assert tracer is not None
        assert meter is not None
    
    def test_record_latency_async_exception_import_error(self):
        """Test async record_latency exception handling when LABEL_ALLOWLIST import fails."""
        import asyncio
        
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            # Create a function that will cause ImportError only for metrics module
            original_import = __builtins__['__import__']
            def selective_import_error(name, *args, **kwargs):
                if name == 'backend.infra.metrics':
                    raise ImportError("Cannot import backend.infra.metrics")
                return original_import(name, *args, **kwargs)
            
            with patch('builtins.__import__', side_effect=selective_import_error):
                @record_latency("test_metric", extra_labels={"key": "value"})
                async def failing_async_func():
                    raise ValueError("Test async error")
                
                with pytest.raises(ValueError, match="Test async error"):
                    asyncio.run(failing_async_func())
                
                # Verify metrics were recorded without status label (due to import error)
                mock_registry.observe_histogram.assert_called_once()
                call_args = mock_registry.observe_histogram.call_args[0]
                labels = call_args[2]  # Third argument is labels
                assert "status" not in labels  # Should not have status due to import error
                assert "key" in labels  # Should have original label
    
    def test_record_latency_sync_exception_import_error(self):
        """Test sync record_latency exception handling when LABEL_ALLOWLIST import fails."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            # Force ImportError when trying to import LABEL_ALLOWLIST
            with patch('builtins.__import__', side_effect=ImportError("Module not found")):
                @record_latency("test_metric", extra_labels={"key": "value"})
                def failing_sync_func():
                    raise ValueError("Test sync error")
                
                with pytest.raises(ValueError, match="Test sync error"):
                    failing_sync_func()
                
                # Verify metrics were recorded without status label (due to import error)
                mock_registry.observe_histogram.assert_called_once()
                call_args = mock_registry.observe_histogram.call_args[0]
                labels = call_args[2]  # Third argument is labels
                assert "status" not in labels  # Should not have status due to import error
                assert "key" in labels  # Should have original label
    
    def test_record_latency_async_exception_attribute_error(self):
        """Test async record_latency when LABEL_ALLOWLIST.get() raises AttributeError."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            # Mock LABEL_ALLOWLIST to raise AttributeError on .get()
            mock_allowlist = MagicMock()
            mock_allowlist.get.side_effect = AttributeError("get method not found")
            
            with patch.dict('backend.infra.metrics.__dict__', {'LABEL_ALLOWLIST': mock_allowlist}, clear=False):
                @record_latency("test_metric")
                async def failing_async_func():
                    raise ValueError("Test async attr error")
                
                import asyncio
                with pytest.raises(ValueError, match="Test async attr error"):
                    asyncio.run(failing_async_func())
                
                # Verify exception handling path was taken
                mock_registry.observe_histogram.assert_called_once()
    
    def test_record_latency_sync_exception_attribute_error(self):
        """Test sync record_latency when LABEL_ALLOWLIST.get() raises AttributeError."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            # Mock LABEL_ALLOWLIST to raise AttributeError on .get()
            mock_allowlist = MagicMock()
            mock_allowlist.get.side_effect = AttributeError("get method not found")
            
            with patch.dict('backend.infra.metrics.__dict__', {'LABEL_ALLOWLIST': mock_allowlist}, clear=False):
                @record_latency("test_metric")
                def failing_sync_func():
                    raise ValueError("Test sync attr error")
                
                with pytest.raises(ValueError, match="Test sync attr error"):
                    failing_sync_func()
                
                # Verify exception handling path was taken
                mock_registry.observe_histogram.assert_called_once()
    
    def test_record_latency_with_route_and_method_sync(self):
        """Test sync record_latency with route and method parameters to cover lines 368, 370."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span, \
             patch('backend.infra.observability.normalize_route') as mock_normalize:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            mock_normalize.return_value = "normalized_route"
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            @record_latency("test_metric", route="/api/test", method="GET")
            def test_func():
                return "success"
            
            result = test_func()
            
            # Verify the function executed successfully
            assert result == "success"
            
            # Verify trace_span was called with correct labels (including route and method)
            mock_trace_span.assert_called_once()
            call_args = mock_trace_span.call_args[0]
            labels = call_args[1]  # Second argument is labels
            assert "route" in labels
            assert "method" in labels
            assert labels["method"] == "GET"
            
            # Verify normalize_route was called
            mock_normalize.assert_called_once_with("/api/test")
    
    def test_record_latency_sync_exception_with_status_in_allowlist(self):
        """Test sync record_latency exception with status in LABEL_ALLOWLIST to cover line 400."""
        with patch('backend.infra.observability.get_metrics_registry') as mock_get_registry, \
             patch('backend.infra.observability.trace_span') as mock_trace_span:
            
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry
            
            # Mock trace_span context manager
            mock_span = MagicMock()
            mock_trace_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_span.return_value.__exit__ = MagicMock(return_value=None)
            
            # Mock LABEL_ALLOWLIST to include 'status' for the test metric
            mock_allowlist = {"test_metric": ("status", "other_label")}
            
            with patch.dict('backend.infra.metrics.__dict__', {'LABEL_ALLOWLIST': mock_allowlist}, clear=False):
                @record_latency("test_metric")
                def failing_func():
                    raise ValueError("Test error for status line")
                
                with pytest.raises(ValueError, match="Test error for status line"):
                    failing_func()
                
                # Verify metrics were recorded with status label
                mock_registry.observe_histogram.assert_called_once()
                call_args = mock_registry.observe_histogram.call_args[0]
                labels = call_args[2]  # Third argument is labels
                assert "status" in labels  # Should have status due to allowlist
                assert labels["status"] == "error"  # This covers line 400