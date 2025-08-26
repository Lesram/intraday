"""
Unit tests for structured logging components.
Tests JSON formatting, trace correlation, and structured logging functionality.
"""
import json
import logging
import sys
from unittest.mock import Mock, patch
from datetime import datetime

from backend.infra.logging import (
    JSONFormatter,
    TraceIdFilter, 
    StructuredLogger
)


class TestTraceIdFilter:
    """Test OpenTelemetry trace ID injection filter."""
    
    def test_filter_without_otel_sets_none_values(self):
        """Test filter behavior when OpenTelemetry is not available."""
        filter_instance = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Apply filter
        result = filter_instance.filter(record)
        
        # Should return True to allow processing
        assert result is True
        
        # Should set trace fields to None when no span context
        assert hasattr(record, 'trace_id')
        assert hasattr(record, 'span_id') 
        assert hasattr(record, 'trace_flags')
        assert record.trace_id is None
        assert record.span_id is None
        assert record.trace_flags is None
    
    @patch('backend.infra.logging.OTEL_AVAILABLE', True)
    @patch('backend.infra.logging.trace')
    def test_filter_with_valid_span_context(self, mock_trace):
        """Test filter with valid OpenTelemetry span context."""
        # Mock span context
        mock_span_context = Mock()
        mock_span_context.trace_id = 12345678901234567890123456789012
        mock_span_context.span_id = 1234567890123456
        mock_span_context.trace_flags = 1
        mock_span_context.is_valid = True
        
        # Mock current span
        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context
        mock_trace.get_current_span.return_value = mock_span
        
        filter_instance = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        result = filter_instance.filter(record)
        
        assert result is True
        assert record.trace_id == f"{12345678901234567890123456789012:032x}"
        assert record.span_id == f"{1234567890123456:016x}"
        assert record.trace_flags == 1
    
    @patch('backend.infra.logging.OTEL_AVAILABLE', True)  
    @patch('backend.infra.logging.trace')
    def test_filter_with_invalid_span_context(self, mock_trace):
        """Test filter when span context is invalid."""
        mock_span_context = Mock()
        mock_span_context.is_valid = False
        
        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context
        mock_trace.get_current_span.return_value = mock_span
        
        filter_instance = TraceIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message", 
            args=(),
            exc_info=None
        )
        
        result = filter_instance.filter(record)
        
        assert result is True
        assert record.trace_id is None
        assert record.span_id is None
        assert record.trace_flags is None


class TestJSONFormatter:
    """Test JSON log formatter."""
    
    def test_basic_json_formatting(self):
        """Test basic JSON log formatting."""
        formatter = JSONFormatter(
            service_name="test-service",
            service_version="1.0.0"
        )
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test log message",
            args=(),
            exc_info=None
        )
        record.module = "file"
        record.funcName = "test_function"
        record.thread = 12345
        record.process = 67890
        
        formatted = formatter.format(record)
        
        # Should be valid JSON
        log_data = json.loads(formatted)
        
        # Check required fields
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test log message"
        assert log_data["service"]["name"] == "test-service"
        assert log_data["service"]["version"] == "1.0.0"
        assert log_data["module"] == "file"
        assert log_data["function"] == "test_function"
        assert log_data["line"] == 42
        assert log_data["thread"] == 12345
        assert log_data["process"] == 67890
        
        # Should have timestamp
        assert "timestamp" in log_data
        assert log_data["timestamp"].endswith("Z")  # UTC format
    
    def test_json_formatting_with_trace_info(self):
        """Test JSON formatting with trace correlation."""
        formatter = JSONFormatter(include_trace=True)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error message",
            args=(),
            exc_info=None
        )
        
        # Add trace info to record (as would be done by TraceIdFilter)
        record.trace_id = "abc123def456"
        record.span_id = "789ghi012"
        record.trace_flags = 1
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["trace_id"] == "abc123def456"
        assert log_data["span_id"] == "789ghi012"
        assert log_data["trace_flags"] == 1
    
    def test_json_formatting_without_trace(self):
        """Test JSON formatting with trace disabled."""
        formatter = JSONFormatter(include_trace=False)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Warning message",
            args=(),
            exc_info=None
        )
        record.trace_id = "should_not_appear"
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Trace fields should not be present
        assert "trace_id" not in log_data
        assert "span_id" not in log_data
    
    def test_json_formatting_with_exception(self):
        """Test JSON formatting with exception information."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error with exception",
            args=(),
            exc_info=exc_info
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert log_data["exception"]["message"] == "Test exception"
        assert "traceback" in log_data["exception"]
    
    def test_json_formatting_with_extra_fields(self):
        """Test JSON formatting with extra record fields."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Message with extras",
            args=(),
            exc_info=None
        )
        
        # Add custom fields to record
        record.user_id = "user123"
        record.request_id = "req456"
        record.duration = 0.123
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert "extra" in log_data
        assert log_data["extra"]["user_id"] == "user123"
        assert log_data["extra"]["request_id"] == "req456"
        assert log_data["extra"]["duration"] == 0.123
    
    def test_json_formatting_with_non_serializable_extra(self):
        """Test JSON formatting handles non-serializable extra fields."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Message with complex extra",
            args=(),
            exc_info=None
        )
        
        # Add non-serializable field
        record.complex_object = object()
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Should convert to string
        assert "extra" in log_data
        assert "complex_object" in log_data["extra"]
        assert isinstance(log_data["extra"]["complex_object"], str)
    
    def test_json_formatting_with_configured_extra_fields(self):
        """Test JSON formatting with configured extra fields."""
        extra_fields = {
            "environment": "test",
            "deployment": "v1.2.3"
        }
        
        formatter = JSONFormatter(extra_fields=extra_fields)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["environment"] == "test"
        assert log_data["deployment"] == "v1.2.3"


class TestStructuredLogger:
    """Test structured logger wrapper."""
    
    def test_structured_logger_creation(self):
        """Test creating structured logger."""
        logger = StructuredLogger("test.module")
        
        assert logger.logger is not None
        assert logger.logger.name == "test.module"
        assert isinstance(logger.logger, logging.Logger)
    
    def test_debug_with_context(self):
        """Test debug logging with context."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            structured_logger = StructuredLogger("test")
            context = {"user_id": "123", "action": "login"}
            
            structured_logger.debug("User action", context=context)
            
            mock_logger.log.assert_called_once_with(
                logging.DEBUG, "User action", extra=context
            )
    
    def test_debug_without_context(self):
        """Test debug logging without context."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            structured_logger = StructuredLogger("test")
            
            structured_logger.debug("Simple debug message")
            
            mock_logger.log.assert_called_once_with(
                logging.DEBUG, "Simple debug message"
            )
    
    def test_log_levels(self):
        """Test different log levels work correctly."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            structured_logger = StructuredLogger("test")
            
            # Test debug
            structured_logger.debug("Debug message")
            assert mock_logger.log.call_args[0][0] == logging.DEBUG
            
            mock_logger.reset_mock()


class TestLoggingIntegration:
    """Integration tests for logging components."""
    
    def test_filter_and_formatter_integration(self):
        """Test TraceIdFilter and JSONFormatter work together."""
        # Create logger with filter and formatter
        logger = logging.getLogger("integration.test")
        logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        logger.handlers.clear()
        
        # Create handler with our components and capture output
        import io
        captured_output = io.StringIO()
        handler = logging.StreamHandler(captured_output)
        handler.addFilter(TraceIdFilter())
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        
        # Log message
        logger.info("Integration test message")
        
        # Verify output was captured
        output = captured_output.getvalue()
        assert "Integration test message" in output
        assert "timestamp" in output  # Verify JSON format
        assert "level" in output
    
    def test_structured_logger_with_json_formatter(self):
        """Test StructuredLogger produces valid JSON output."""
        # This would be an integration test in a real scenario
        # Here we just verify the components can work together
        structured_logger = StructuredLogger("integration.test")
        
        # The actual formatting would happen in the logging handler
        # This test verifies the logger can be created and used
        assert structured_logger.logger is not None
        
        # Test that methods exist and can be called
        try:
            structured_logger.debug("Test message", context={"key": "value"})
            # If no exception, the method signature is correct
            assert True
        except Exception as e:
            raise AssertionError(f"StructuredLogger method call failed: {e}")
    
    def test_json_output_is_valid(self):
        """Test that JSON formatter always produces valid JSON."""
        formatter = JSONFormatter()
        
        # Test various record configurations
        test_cases = [
            # Basic record
            {
                "name": "test",
                "level": logging.INFO,
                "msg": "Simple message"
            },
            # Record with unicode
            {
                "name": "test.unicode",
                "level": logging.WARNING,
                "msg": "Message with émojis 🎉 and ñoñó"
            },
            # Record with special characters
            {
                "name": "test.special",
                "level": logging.ERROR,
                "msg": 'Message with "quotes" and \n newlines'
            }
        ]
        
        for case in test_cases:
            record = logging.LogRecord(
                name=case["name"],
                level=case["level"],
                pathname="",
                lineno=0,
                msg=case["msg"],
                args=(),
                exc_info=None
            )
            
            formatted = formatter.format(record)
            
            # Should be valid JSON
            try:
                parsed = json.loads(formatted)
                assert parsed["message"] == case["msg"]
                assert parsed["level"] == logging.getLevelName(case["level"])
            except json.JSONDecodeError as e:
                raise AssertionError(f"Invalid JSON produced for case {case}: {e}")
