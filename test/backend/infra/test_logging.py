"""
Comprehensive test suite for Module 37: backend.infra.logging
Tests logging functionality including structured logging, JSON formatting, and OpenTelemetry integration.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from unittest.mock import Mock, patch, MagicMock
import pytest

from backend.infra.logging import (
    TraceIdFilter,
    JSONFormatter,
    StructuredLogger,
    configure_structured_logging,
    get_logger,
    OTEL_AVAILABLE,
)


class TestOtelAvailability:
    """Test OpenTelemetry availability detection."""

    def test_otel_import_error_handling(self):
        """Test OTEL_AVAILABLE flag when OpenTelemetry import fails."""
        # This test verifies the ImportError handling in the module initialization
        # We can't easily mock the import at module level, so this is more of a 
        # documentation test. The actual import error path would be hit if 
        # opentelemetry.trace package was not installed.
        
        # Test that the module loads and has the expected attributes
        import backend.infra.logging as logging_module
        assert hasattr(logging_module, 'OTEL_AVAILABLE')
        assert hasattr(logging_module, 'ReadableSpan')
        
        # If OTEL is not available, ReadableSpan should be None (line 22)
        if not logging_module.OTEL_AVAILABLE:
            assert logging_module.ReadableSpan is None


class TestTraceIdFilter:
    """Test TraceIdFilter functionality."""

    def test_filter_with_otel_available_and_valid_span(self):
        """Test filter when OpenTelemetry is available with valid span."""
        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not available")
            
        trace_filter = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock current span with valid context
        mock_span_context = Mock()
        mock_span_context.trace_id = 123456789012345678901234567890123456
        mock_span_context.span_id = 1234567890123456
        mock_span_context.trace_flags = 1
        mock_span_context.is_valid = True

        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        with patch('backend.infra.logging.trace.get_current_span', return_value=mock_span):
            result = trace_filter.filter(record)

        assert result is True
        assert record.trace_id == f"{123456789012345678901234567890123456:032x}"
        assert record.span_id == f"{1234567890123456:016x}"
        assert record.trace_flags == 1

    def test_filter_with_otel_available_and_invalid_span(self):
        """Test filter when OpenTelemetry is available with invalid span."""
        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not available")
            
        trace_filter = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock current span with invalid context
        mock_span_context = Mock()
        mock_span_context.is_valid = False

        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        with patch('backend.infra.logging.trace.get_current_span', return_value=mock_span):
            result = trace_filter.filter(record)

        assert result is True
        assert record.trace_id is None
        assert record.span_id is None
        assert record.trace_flags is None

    def test_filter_with_no_current_span(self):
        """Test filter when no current span is available."""
        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not available")
            
        trace_filter = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        with patch('backend.infra.logging.trace.get_current_span', return_value=None):
            result = trace_filter.filter(record)

        assert result is True
        assert record.trace_id is None
        assert record.span_id is None
        assert record.trace_flags is None

    def test_filter_without_otel_available(self):
        """Test filter when OpenTelemetry is not available."""
        trace_filter = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock OTEL_AVAILABLE as False
        with patch('backend.infra.logging.OTEL_AVAILABLE', False):
            result = trace_filter.filter(record)

        assert result is True
        assert record.trace_id is None
        assert record.span_id is None
        assert record.trace_flags is None


class TestJSONFormatter:
    """Test JSONFormatter functionality."""

    def test_json_formatter_initialization(self):
        """Test JSONFormatter initialization with default parameters."""
        formatter = JSONFormatter()
        assert formatter.service_name == "intraday-trading"
        assert formatter.service_version == "2.0.0"
        assert formatter.include_trace is True
        assert formatter.extra_fields == {}

    def test_json_formatter_initialization_with_custom_params(self):
        """Test JSONFormatter initialization with custom parameters."""
        extra_fields = {"env": "test", "region": "us-west"}
        formatter = JSONFormatter(
            service_name="test-service",
            service_version="1.0.0",
            include_trace=False,
            extra_fields=extra_fields,
        )
        assert formatter.service_name == "test-service"
        assert formatter.service_version == "1.0.0"
        assert formatter.include_trace is False
        assert formatter.extra_fields == extra_fields

    def test_format_basic_log_record(self):
        """Test formatting basic log record."""
        formatter = JSONFormatter(include_trace=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        # Mock datetime.now to get consistent timestamp
        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert log_entry["timestamp"] == "2023-01-01T12:00:00Z"
        assert log_entry["level"] == "INFO"
        assert log_entry["logger"] == "test.module"
        assert log_entry["message"] == "Test message"
        assert log_entry["service"]["name"] == "intraday-trading"
        assert log_entry["service"]["version"] == "2.0.0"
        assert log_entry["module"] == "test"
        assert log_entry["line"] == 42

    def test_format_with_trace_information(self):
        """Test formatting log record with trace information."""
        formatter = JSONFormatter(include_trace=True)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        # Add trace information to record
        record.trace_id = "abc123def456"
        record.span_id = "789xyz012"
        record.trace_flags = 1

        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert log_entry["trace_id"] == "abc123def456"
        assert log_entry["span_id"] == "789xyz012"
        assert log_entry["trace_flags"] == 1

    def test_format_with_exception_information(self):
        """Test formatting log record with exception information."""
        formatter = JSONFormatter(include_trace=False)
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert "exception" in log_entry
        assert log_entry["exception"]["type"] == "ValueError"
        assert log_entry["exception"]["message"] == "Test exception"
        assert "traceback" in log_entry["exception"]

    def test_format_with_extra_fields_in_record(self):
        """Test formatting log record with extra fields."""
        formatter = JSONFormatter(include_trace=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        # Add extra fields to record
        record.user_id = "user123"
        record.request_id = "req456"
        record.custom_field = {"nested": "value"}

        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert "extra" in log_entry
        assert log_entry["extra"]["user_id"] == "user123"
        assert log_entry["extra"]["request_id"] == "req456"
        assert log_entry["extra"]["custom_field"] == {"nested": "value"}

    def test_format_with_non_json_serializable_extra_field(self):
        """Test formatting log record with non-JSON-serializable extra field."""
        formatter = JSONFormatter(include_trace=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        # Add non-serializable extra field
        record.complex_object = Mock()

        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert "extra" in log_entry
        assert isinstance(log_entry["extra"]["complex_object"], str)

    def test_format_with_configured_extra_fields(self):
        """Test formatting with extra fields configured in formatter."""
        extra_fields = {"environment": "production", "service_type": "api"}
        formatter = JSONFormatter(include_trace=False, extra_fields=extra_fields)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        fixed_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch('backend.infra.logging.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_time
            formatted = formatter.format(record)

        log_entry = json.loads(formatted)
        assert log_entry["environment"] == "production"
        assert log_entry["service_type"] == "api"


class TestStructuredLogger:
    """Test StructuredLogger functionality."""

    def test_structured_logger_initialization(self):
        """Test StructuredLogger initialization."""
        logger = StructuredLogger("test.module")
        assert logger.logger.name == "test.module"

    def test_debug_logging(self):
        """Test debug level logging."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.debug("Debug message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.DEBUG, "Debug message", extra={"key": "value"}
            )

    def test_info_logging(self):
        """Test info level logging."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.info("Info message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.INFO, "Info message", extra={"key": "value"}
            )

    def test_warning_logging(self):
        """Test warning level logging."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.warning("Warning message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.WARNING, "Warning message", extra={"key": "value"}
            )

    def test_error_logging(self):
        """Test error level logging."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.error("Error message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.ERROR, "Error message", extra={"key": "value"}
            )

    def test_critical_logging(self):
        """Test critical level logging."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.critical("Critical message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.CRITICAL, "Critical message", extra={"key": "value"}
            )

    def test_exception_logging(self):
        """Test exception logging with traceback."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.exception("Exception message", context={"key": "value"})
            mock_log.assert_called_once_with(
                logging.ERROR, "Exception message", extra={"key": "value"}, exc_info=True
            )

    def test_logging_without_context(self):
        """Test logging without context."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            logger.info("Simple message")
            mock_log.assert_called_once_with(logging.INFO, "Simple message")

    def test_log_with_context_method(self):
        """Test the private _log_with_context method."""
        logger = StructuredLogger("test.module")
        with patch.object(logger.logger, 'log') as mock_log:
            context = {"key": "value", "nested": {"data": 123}}
            logger._log_with_context(logging.INFO, "Test message", context)
            mock_log.assert_called_once_with(
                logging.INFO, "Test message", extra=context
            )

    def test_log_http_request_success(self):
        """Test HTTP request logging for successful request."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_http_request(
                method="GET",
                path="/api/users",
                status_code=200,
                duration_ms=150.5,
                user_id="user123",
                request_id="req456"
            )

            expected_context = {
                "http": {
                    "method": "GET",
                    "path": "/api/users",
                    "status_code": 200,
                    "duration_ms": 150.5,
                },
                "user_id": "user123",
                "request_id": "req456"
            }
            expected_message = "GET /api/users - 200 (150.5ms)"
            
            mock_log.assert_called_once_with(logging.INFO, expected_message, expected_context)

    def test_log_http_request_client_error(self):
        """Test HTTP request logging for client error."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_http_request(
                method="POST",
                path="/api/orders",
                status_code=400,
                duration_ms=50.0
            )

            expected_context = {
                "http": {
                    "method": "POST",
                    "path": "/api/orders",
                    "status_code": 400,
                    "duration_ms": 50.0,
                }
            }
            expected_message = "POST /api/orders - 400 (50.0ms)"
            
            mock_log.assert_called_once_with(logging.WARNING, expected_message, expected_context)

    def test_log_http_request_server_error(self):
        """Test HTTP request logging for server error."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_http_request(
                method="GET",
                path="/api/data",
                status_code=500,
                duration_ms=1000.0
            )

            expected_context = {
                "http": {
                    "method": "GET",
                    "path": "/api/data",
                    "status_code": 500,
                    "duration_ms": 1000.0,
                }
            }
            expected_message = "GET /api/data - 500 (1000.0ms)"
            
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_database_operation_success(self):
        """Test database operation logging for successful operation."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_database_operation(
                operation="SELECT",
                table="users",
                duration_ms=25.5,
                rows_affected=10
            )

            expected_context = {
                "database": {
                    "operation": "SELECT",
                    "table": "users",
                    "duration_ms": 25.5,
                    "rows_affected": 10
                }
            }
            expected_message = "Database SELECT on users"
            
            mock_log.assert_called_once_with(logging.DEBUG, expected_message, expected_context)

    def test_log_database_operation_with_error(self):
        """Test database operation logging with error."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_database_operation(
                operation="INSERT",
                table="orders",
                error="Connection timeout"
            )

            expected_context = {
                "database": {
                    "operation": "INSERT",
                    "table": "orders",
                    "error": "Connection timeout"
                }
            }
            expected_message = "Database INSERT on orders failed: Connection timeout"
            
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_alpaca_request_success(self):
        """Test Alpaca API request logging for successful request."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_alpaca_request(
                endpoint="/orders",
                method="POST",
                status_code=201,
                duration_ms=300.0,
                request_id="alpaca-123"
            )

            expected_context = {
                "alpaca": {
                    "endpoint": "/orders",
                    "method": "POST",
                    "status_code": 201,
                    "duration_ms": 300.0,
                    "request_id": "alpaca-123"
                }
            }
            expected_message = "Alpaca POST /orders - 201 (300.0ms)"
            
            mock_log.assert_called_once_with(logging.INFO, expected_message, expected_context)

    def test_log_alpaca_request_with_error(self):
        """Test Alpaca API request logging with error."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_alpaca_request(
                endpoint="/positions",
                method="GET",
                status_code=500,
                duration_ms=5000.0,
                error="Internal server error"
            )

            expected_context = {
                "alpaca": {
                    "endpoint": "/positions",
                    "method": "GET",
                    "status_code": 500,
                    "duration_ms": 5000.0,
                    "error": "Internal server error"
                }
            }
            expected_message = "Alpaca GET /positions - 500 (5000.0ms) - Internal server error"
            
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_alpaca_request_successful_with_error_parameter(self):
        """Test Alpaca API request logging - successful status but with error parameter."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            # Test case where status_code < 400 but error is provided (covers line 325)
            logger.log_alpaca_request(
                endpoint="/accounts",
                method="GET", 
                status_code=200,
                duration_ms=100.0,
                error="Warning: Rate limit approaching"
            )

            expected_context = {
                "alpaca": {
                    "endpoint": "/accounts",
                    "method": "GET",
                    "status_code": 200,
                    "duration_ms": 100.0,
                    "error": "Warning: Rate limit approaching"
                }
            }
            expected_message = "Alpaca GET /accounts - 200 (100.0ms) - Warning: Rate limit approaching"
            
            # Should log as ERROR because error is present (level logic: if error: level = ERROR)
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_order_event_success(self):
        """Test order event logging for successful event."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_order_event(
                event="created",
                order_id="order123",
                symbol="AAPL",
                side="buy",
                quantity=100.0,
                price=150.50,
                status="pending"
            )

            expected_context = {
                "order": {
                    "event": "created",
                    "order_id": "order123",
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 100.0,
                    "price": 150.50,
                    "status": "pending"
                }
            }
            expected_message = "Order created: order123 (AAPL)"
            
            mock_log.assert_called_once_with(logging.INFO, expected_message, expected_context)

    def test_log_order_event_with_error(self):
        """Test order event logging with error."""
        logger = StructuredLogger("test.module")
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_order_event(
                event="rejected",
                order_id="order456",
                symbol="TSLA",
                error="Insufficient funds"
            )

            expected_context = {
                "order": {
                    "event": "rejected",
                    "order_id": "order456",
                    "symbol": "TSLA",
                    "error": "Insufficient funds"
                }
            }
            expected_message = "Order rejected: order456 (TSLA) - Insufficient funds"
            
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_outbox_event_success(self):
        """Test outbox event logging for successful event."""
        logger = StructuredLogger("test.module")
        next_retry = datetime(2023, 1, 1, 13, 0, 0, tzinfo=UTC)
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_outbox_event(
                event="sent",
                message_id="msg123",
                topic="order.events",
                attempt=1,
                max_attempts=3,
                next_retry=next_retry
            )

            expected_context = {
                "outbox": {
                    "event": "sent",
                    "message_id": "msg123",
                    "topic": "order.events",
                    "attempt": 1,
                    "max_attempts": 3,
                    "next_retry": "2023-01-01T13:00:00+00:00"
                }
            }
            expected_message = "Outbox sent: msg123 (order.events)"
            
            mock_log.assert_called_once_with(logging.INFO, expected_message, expected_context)

    def test_log_outbox_event_with_error(self):
        """Test outbox event logging with error."""
        logger = StructuredLogger("test.module")
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_outbox_event(
                event="failed",
                message_id="msg456",
                topic="position.events",
                error="Broker unavailable"
            )

            expected_context = {
                "outbox": {
                    "event": "failed",
                    "message_id": "msg456",
                    "topic": "position.events",
                    "error": "Broker unavailable"
                }
            }
            expected_message = "Outbox failed: msg456 (position.events) - Broker unavailable"
            
            mock_log.assert_called_once_with(logging.ERROR, expected_message, expected_context)

    def test_log_auth_event_success(self):
        """Test authentication event logging for successful event."""
        logger = StructuredLogger("test.module")
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_auth_event(
                event="login",
                user_id="user123",
                method="jwt",
                success=True
            )

            expected_context = {
                "auth": {
                    "event": "login",
                    "user_id": "user123",
                    "method": "jwt",
                    "success": True
                }
            }
            expected_message = "Auth login for user user123"
            
            mock_log.assert_called_once_with(logging.INFO, expected_message, expected_context)

    def test_log_auth_event_failure(self):
        """Test authentication event logging for failed event."""
        logger = StructuredLogger("test.module")
        
        with patch.object(logger, '_log_with_context') as mock_log:
            logger.log_auth_event(
                event="login",
                user_id="user456",
                method="password",
                success=False,
                reason="Invalid credentials"
            )

            expected_context = {
                "auth": {
                    "event": "login",
                    "user_id": "user456",
                    "method": "password",
                    "success": False,
                    "reason": "Invalid credentials"
                }
            }
            expected_message = "Auth login for user user456 - Invalid credentials"
            
            mock_log.assert_called_once_with(logging.WARNING, expected_message, expected_context)


class TestConfigureStructuredLogging:
    """Test configure_structured_logging function."""

    def setUp(self):
        """Set up test environment."""
        # Clear existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_configure_structured_logging_defaults(self):
        """Test configuration with default parameters."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_get_logger.return_value = mock_root_logger
            
            configure_structured_logging()
            
            # Verify logger configuration calls - setLevel called for root + 4 third-party loggers
            assert mock_root_logger.setLevel.call_count == 5
            # Verify first call was for root logger with INFO level
            mock_root_logger.setLevel.assert_any_call(logging.INFO)
            assert mock_root_logger.addHandler.called
            
    def test_configure_structured_logging_custom_level_string(self):
        """Test configuration with custom string level."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_get_logger.return_value = mock_root_logger
            
            configure_structured_logging(level="DEBUG")
            
            # Verify first call was for root logger with DEBUG level
            mock_root_logger.setLevel.assert_any_call(logging.DEBUG)

    def test_configure_structured_logging_custom_level_int(self):
        """Test configuration with custom integer level."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_get_logger.return_value = mock_root_logger
            
            configure_structured_logging(level=logging.WARNING)
            
            # Verify first call was for root logger with WARNING level
            mock_root_logger.setLevel.assert_any_call(logging.WARNING)

    def test_configure_structured_logging_plain_format(self):
        """Test configuration with plain text formatting."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger, \
             patch('logging.StreamHandler') as mock_handler_class:
            
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_handler = Mock()
            mock_get_logger.return_value = mock_root_logger
            mock_handler_class.return_value = mock_handler
            
            configure_structured_logging(json_format=False)
            
            # Verify plain formatter is used
            mock_handler.setFormatter.assert_called_once()
            formatter_arg = mock_handler.setFormatter.call_args[0][0]
            assert isinstance(formatter_arg, logging.Formatter)
            assert not isinstance(formatter_arg, JSONFormatter)

    def test_configure_structured_logging_json_format_with_trace(self):
        """Test configuration with JSON format and trace correlation."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger, \
             patch('logging.StreamHandler') as mock_handler_class:
            
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_handler = Mock()
            mock_get_logger.return_value = mock_root_logger
            mock_handler_class.return_value = mock_handler
            
            configure_structured_logging(
                json_format=True,
                enable_trace_correlation=True,
                service_name="test-service",
                service_version="1.0.0"
            )
            
            # Verify JSON formatter is used
            mock_handler.setFormatter.assert_called_once()
            # Verify trace filter is added
            mock_handler.addFilter.assert_called_once()

    def test_configure_structured_logging_with_extra_fields(self):
        """Test configuration with extra fields."""
        self.setUp()
        extra_fields = {"environment": "test", "region": "us-west"}
        
        with patch('logging.getLogger') as mock_get_logger, \
             patch('logging.StreamHandler') as mock_handler_class:
            
            mock_root_logger = Mock()
            mock_root_logger.handlers = []  # Mock handlers as empty list
            mock_handler = Mock()
            mock_get_logger.return_value = mock_root_logger
            mock_handler_class.return_value = mock_handler
            
            configure_structured_logging(extra_fields=extra_fields)
            
            mock_handler.setFormatter.assert_called_once()
            formatter_arg = mock_handler.setFormatter.call_args[0][0]
            # Check if formatter has expected properties (JSON formatter behavior)
            assert hasattr(formatter_arg, 'extra_fields')
            assert formatter_arg.extra_fields == extra_fields

    def test_configure_structured_logging_removes_existing_handlers(self):
        """Test that configuration removes existing handlers."""
        self.setUp()
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = Mock()
            existing_handler = Mock()
            mock_root_logger.handlers = [existing_handler]
            mock_get_logger.return_value = mock_root_logger
            
            configure_structured_logging()
            
            mock_root_logger.removeHandler.assert_called_once_with(existing_handler)

    def test_configure_structured_logging_third_party_loggers(self):
        """Test that third-party logger levels are configured."""
        self.setUp()
        
        third_party_loggers = {}
        
        def mock_get_logger(name=""):
            if name == "":  # Root logger
                mock_root = Mock()
                mock_root.handlers = []  # Mock handlers as empty list
                return mock_root
            if name not in third_party_loggers:
                third_party_loggers[name] = Mock()
            return third_party_loggers[name]
        
        with patch('logging.getLogger', side_effect=mock_get_logger):
            configure_structured_logging()
            
            # Verify third-party loggers are configured
            assert "uvicorn.access" in third_party_loggers
            assert "urllib3.connectionpool" in third_party_loggers
            assert "sqlalchemy.engine" in third_party_loggers
            assert "asyncpg" in third_party_loggers
            
            third_party_loggers["uvicorn.access"].setLevel.assert_called_with(logging.WARNING)
            third_party_loggers["urllib3.connectionpool"].setLevel.assert_called_with(logging.WARNING)
            third_party_loggers["sqlalchemy.engine"].setLevel.assert_called_with(logging.WARNING)
            third_party_loggers["asyncpg"].setLevel.assert_called_with(logging.WARNING)


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_returns_structured_logger(self):
        """Test that get_logger returns a StructuredLogger instance."""
        logger = get_logger("test.module")
        # Check if logger has StructuredLogger characteristics
        assert hasattr(logger, 'logger')
        assert hasattr(logger, '_log_with_context')
        assert hasattr(logger, 'log_http_request')
        assert logger.logger.name == "test.module"

    def test_get_logger_different_names(self):
        """Test that get_logger creates different loggers for different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1.logger.name == "module1"
        assert logger2.logger.name == "module2"
        assert logger1.logger != logger2.logger
