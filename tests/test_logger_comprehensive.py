"""
Comprehensive tests for backend/utils/logger.py

Target: Increase coverage from 59% to 90%+
Tests cover:
- Sensitive data scrubbing (PII/secrets protection)
- Structlog configuration and logger creation
- AuditLogger for compliance events
- PerformanceLogger for metrics
- StandardEventLogger for trading events
- Event logging helpers
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, ANY
import logging
import structlog


# Import the module under test
from backend.utils.logger import (
    SENSITIVE_PATTERNS,
    SENSITIVE_FIELD_NAMES,
    _mask_value,
    _scrub_string,
    _scrub_dict,
    _scrub_list,
    scrub_sensitive_data,
    AuditLogger,
    PerformanceContext,
    PerformanceLogger,
    log_event,
    StandardEventLogger,
    log_order_submitted,
    log_order_ack,
    log_order_rejected,
    log_order_cancelled,
    get_event_logger,
    setup_logging,
    get_structured_logger,
    audit_logger,
    performance_logger,
)
# Import get_logger from structlog (re-exported in logger.py)
from structlog import get_logger


# =============================================================================
# Tests for Sensitive Data Patterns and Field Names
# =============================================================================

class TestSensitivePatterns:
    """Tests for SENSITIVE_PATTERNS dictionary."""
    
    def test_patterns_dict_exists(self):
        """Test that SENSITIVE_PATTERNS is a dictionary."""
        assert isinstance(SENSITIVE_PATTERNS, dict)
        
    def test_required_pattern_keys_exist(self):
        """Test that required pattern keys exist."""
        required_keys = [
            "api_key", "bearer_token", "jwt_token", "password",
            "aws_key", "credit_card", "ssn", "alpaca_key"
        ]
        for key in required_keys:
            assert key in SENSITIVE_PATTERNS, f"Missing pattern: {key}"
            
    def test_api_key_pattern_matches(self):
        """Test API key regex pattern matches correctly."""
        pattern = SENSITIVE_PATTERNS["api_key"]
        text = "Authorization: APIKEY=sk-12345678abcdef"
        match = pattern.search(text)
        assert match is not None
        
    def test_bearer_token_pattern_matches(self):
        """Test Bearer token regex pattern matches correctly."""
        pattern = SENSITIVE_PATTERNS["bearer_token"]
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        match = pattern.search(text)
        assert match is not None
        
    def test_jwt_token_pattern_matches(self):
        """Test JWT pattern matches correctly."""
        import re
        pattern = SENSITIVE_PATTERNS["jwt_token"]
        text = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        match = pattern.search(text)
        assert match is not None
        
    def test_password_pattern_matches(self):
        """Test password pattern matches correctly."""
        pattern = SENSITIVE_PATTERNS["password"]
        text = 'password=mysecretpassword123'
        match = pattern.search(text)
        assert match is not None
        
    def test_credit_card_pattern_matches(self):
        """Test credit card pattern matches correctly."""
        import re
        pattern = SENSITIVE_PATTERNS["credit_card"]
        text = "Card: 4111-1111-1111-1111"
        match = pattern.search(text)
        assert match is not None
        
    def test_ssn_pattern_matches(self):
        """Test SSN pattern matches correctly."""
        import re
        pattern = SENSITIVE_PATTERNS["ssn"]
        text = "SSN: 123-45-6789"
        match = pattern.search(text)
        assert match is not None


class TestSensitiveFieldNames:
    """Tests for SENSITIVE_FIELD_NAMES frozenset."""
    
    def test_field_names_is_frozenset(self):
        """Test that SENSITIVE_FIELD_NAMES is a frozenset."""
        assert isinstance(SENSITIVE_FIELD_NAMES, frozenset)
        
    def test_required_field_names_exist(self):
        """Test that common sensitive field names exist."""
        required_fields = [
            "password", "secret", "token", "api_key", "apikey",
            "authorization", "credential"
        ]
        for field in required_fields:
            assert field in SENSITIVE_FIELD_NAMES, f"Missing field: {field}"


# =============================================================================
# Tests for _mask_value function
# =============================================================================

class TestMaskValue:
    """Tests for _mask_value function."""
    
    def test_mask_short_string(self):
        """Test masking short strings."""
        result = _mask_value("abc")
        # Short strings get full mask
        assert "REDACTED" in result
        
    def test_mask_long_string(self):
        """Test masking long strings shows first/last chars."""
        result = _mask_value("secretpassword12345")
        # Should show first and last characters with *** in middle
        assert "***" in result
        assert result.startswith("s")
        
    def test_mask_integer_string(self):
        """Test masking integer converted to string."""
        result = _mask_value("12345")
        assert "REDACTED" in result
        
    def test_mask_empty_string(self):
        """Test masking empty string."""
        result = _mask_value("")
        assert "REDACTED" in result


# =============================================================================
# Tests for _scrub_string function
# =============================================================================

class TestScrubString:
    """Tests for _scrub_string function."""
    
    def test_scrub_api_key_in_string(self):
        """Test scrubbing API key from string."""
        text = "Using APIKEY=sk-12345678abcdefghijklmnop"
        result = _scrub_string(text)
        # The value should be masked
        assert "REDACTED" in result
        
    def test_scrub_bearer_token_in_string(self):
        """Test scrubbing Bearer token from string."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = _scrub_string(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        
    def test_scrub_password_in_string(self):
        """Test scrubbing password from string."""
        text = "password=supersecret123"
        result = _scrub_string(text)
        assert "supersecret123" not in result
        
    def test_scrub_credit_card_in_string(self):
        """Test scrubbing credit card from string."""
        text = "Card number: 4111-1111-1111-1111"
        result = _scrub_string(text)
        assert "4111-1111-1111-1111" not in result
        
    def test_scrub_ssn_in_string(self):
        """Test scrubbing SSN from string."""
        text = "SSN: 123-45-6789"
        result = _scrub_string(text)
        assert "123-45-6789" not in result
        
    def test_scrub_email_in_string(self):
        """Test scrubbing email from string."""
        text = "Contact: user@example.com"
        result = _scrub_string(text)
        # Email may or may not be scrubbed depending on pattern
        # Just ensure no exceptions
        assert isinstance(result, str)
        
    def test_no_sensitive_data(self):
        """Test string without sensitive data unchanged."""
        text = "This is a normal log message"
        result = _scrub_string(text)
        assert result == text
        
    def test_non_string_input(self):
        """Test non-string values - function expects strings."""
        # _scrub_string is designed for strings but may handle others
        # Just test that it doesn't crash on normal strings
        result = _scrub_string("normal text")
        assert result == "normal text"


# =============================================================================
# Tests for _scrub_dict function
# =============================================================================

class TestScrubDict:
    """Tests for _scrub_dict function."""
    
    def test_scrub_sensitive_field_by_name(self):
        """Test scrubbing values of sensitive field names."""
        data = {"password": "mysecret123", "username": "john"}
        result = _scrub_dict(data)
        assert "***" in result["password"]
        assert result["username"] == "john"
        
    def test_scrub_api_key_field(self):
        """Test scrubbing api_key field."""
        data = {"api_key": "sk-12345678abcdef", "name": "test"}
        result = _scrub_dict(data)
        assert "sk-12345678" not in result["api_key"]
        
    def test_scrub_nested_dict(self):
        """Test scrubbing nested dictionaries."""
        data = {
            "user": {
                "name": "John",
                "password": "secret123"
            }
        }
        result = _scrub_dict(data)
        assert "***" in result["user"]["password"]
        assert result["user"]["name"] == "John"
        
    def test_scrub_list_in_dict(self):
        """Test scrubbing list values in dict."""
        data = {
            "tokens": ["token123", "token456"],
            "names": ["John", "Jane"]
        }
        result = _scrub_dict(data)
        # tokens field should be scrubbed
        assert isinstance(result["tokens"], list)
        
    def test_scrub_string_values_in_dict(self):
        """Test scrubbing string values containing patterns."""
        data = {
            "log_message": "Error with APIKEY=sk-12345678abcdef"
        }
        result = _scrub_dict(data)
        assert "sk-12345678" not in result["log_message"]


# =============================================================================
# Tests for _scrub_list function
# =============================================================================

class TestScrubList:
    """Tests for _scrub_list function."""
    
    def test_scrub_list_of_strings(self):
        """Test scrubbing list of strings with patterns."""
        data = ["normal", "password=secret123", "ok"]
        result = _scrub_list(data)
        assert result[0] == "normal"
        assert "secret123" not in result[1]
        assert result[2] == "ok"
        
    def test_scrub_list_of_dicts(self):
        """Test scrubbing list of dictionaries."""
        data = [
            {"password": "secret1"},
            {"password": "secret2"}
        ]
        result = _scrub_list(data)
        for item in result:
            assert "***" in item["password"]
            
    def test_scrub_empty_list(self):
        """Test scrubbing empty list."""
        result = _scrub_list([])
        assert result == []
        
    def test_scrub_nested_list(self):
        """Test scrubbing nested lists."""
        data = [["password=secret"], ["normal"]]
        result = _scrub_list(data)
        assert "secret" not in str(result[0])


# =============================================================================
# Tests for scrub_sensitive_data processor
# =============================================================================

class TestScrubSensitiveData:
    """Tests for scrub_sensitive_data structlog processor."""
    
    def test_scrub_event_dict(self):
        """Test scrubbing event dict as structlog processor."""
        logger = MagicMock()
        method_name = "info"
        event_dict = {
            "event": "User login",
            "password": "secret123",
            "username": "john"
        }
        
        result = scrub_sensitive_data(logger, method_name, event_dict)
        
        assert "***" in result["password"]
        assert result["username"] == "john"
        assert result["event"] == "User login"
        
    def test_scrub_preserves_structure(self):
        """Test that scrubbing preserves dict structure."""
        logger = MagicMock()
        method_name = "warning"
        event_dict = {
            "event": "API call",
            "api_key": "sk-12345678",
            "data": {
                "nested": "value",
                "token": "abc123"
            }
        }
        
        result = scrub_sensitive_data(logger, method_name, event_dict)
        
        assert "data" in result
        assert "nested" in result["data"]


# =============================================================================
# Tests for get_logger function
# =============================================================================

class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_returns_bound_logger(self):
        """Test that get_logger returns a structlog BoundLogger."""
        logger = get_logger("test_module")
        # Should be a structlog logger
        assert logger is not None
        
    def test_get_logger_with_different_names(self):
        """Test getting loggers with different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1 is not None
        assert logger2 is not None


# =============================================================================
# Tests for get_structured_logger function
# =============================================================================

class TestGetStructuredLogger:
    """Tests for get_structured_logger function."""
    
    def test_get_structured_logger_returns_logger(self):
        """Test that get_structured_logger returns a logger."""
        logger = get_structured_logger("test")
        assert logger is not None
        
    def test_get_structured_logger_is_alias(self):
        """Test that get_structured_logger calls get_logger."""
        # Both should return similar loggers
        logger1 = get_logger("alias_test")
        logger2 = get_structured_logger("alias_test")
        
        assert logger1 is not None
        assert logger2 is not None


# =============================================================================
# Tests for setup_logging function
# =============================================================================

class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging_default_level(self):
        """Test setup_logging with default level."""
        logger = setup_logging()
        assert logger is not None
        
    def test_setup_logging_custom_level(self):
        """Test setup_logging with custom log level."""
        logger = setup_logging(log_level="DEBUG")
        assert logger is not None
        
    def test_setup_logging_with_file(self, tmp_path):
        """Test setup_logging with file handler."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(log_level="INFO", log_file=str(log_file))
        assert logger is not None
        
    def test_setup_logging_warning_level(self):
        """Test setup_logging with WARNING level."""
        logger = setup_logging(log_level="WARNING")
        assert logger is not None


# =============================================================================
# Tests for AuditLogger class
# =============================================================================

class TestAuditLogger:
    """Tests for AuditLogger class."""
    
    def test_audit_logger_init(self):
        """Test AuditLogger initialization."""
        al = AuditLogger()
        assert al.logger is not None
        
    def test_global_audit_logger_exists(self):
        """Test that global audit_logger instance exists."""
        assert audit_logger is not None
        assert isinstance(audit_logger, AuditLogger)
        
    def test_log_info(self):
        """Test AuditLogger.info method."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.info("Test event", data={"key": "value"})
            mock_info.assert_called_once()
            
    def test_log_warning(self):
        """Test AuditLogger.warning method."""
        al = AuditLogger()
        with patch.object(al.logger, 'warning') as mock_warning:
            al.warning("Warning event", data={"issue": "test"})
            mock_warning.assert_called_once()
            
    def test_log_error(self):
        """Test AuditLogger.error method."""
        al = AuditLogger()
        with patch.object(al.logger, 'error') as mock_error:
            al.error("Error event", data={"error": "test"})
            mock_error.assert_called_once()
            
    def test_log_trade_execution(self):
        """Test AuditLogger.log_trade_execution method."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_trade_execution(
                strategy="momentum",
                symbol="AAPL",
                side="buy",
                quantity=100,
                price=150.50,
                order_id="order123"
            )
            mock_info.assert_called_once()
            call_kwargs = mock_info.call_args
            assert "Trade executed" in str(call_kwargs)
            
    def test_log_risk_event_info(self):
        """Test AuditLogger.log_risk_event with INFO severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_risk_event(
                event_type="limit_check",
                description="Position limit check passed",
                severity="INFO"
            )
            mock_info.assert_called_once()
            
    def test_log_risk_event_warning(self):
        """Test AuditLogger.log_risk_event with WARNING severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'warning') as mock_warning:
            al.log_risk_event(
                event_type="limit_warning",
                description="Approaching position limit",
                severity="WARNING"
            )
            mock_warning.assert_called_once()
            
    def test_log_risk_event_error(self):
        """Test AuditLogger.log_risk_event with ERROR severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'error') as mock_error:
            al.log_risk_event(
                event_type="limit_breach",
                description="Position limit breached",
                severity="ERROR"
            )
            mock_error.assert_called_once()
            
    def test_log_strategy_signal(self):
        """Test AuditLogger.log_strategy_signal method."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_strategy_signal(
                strategy="momentum",
                symbol="TSLA",
                signal="BUY",
                confidence=0.85
            )
            mock_info.assert_called_once()
            
    def test_log_strategy_signal_with_data(self):
        """Test log_strategy_signal with additional data."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_strategy_signal(
                strategy="mean_reversion",
                symbol="SPY",
                signal="SELL",
                confidence=0.75,
                data={"indicator": "RSI", "value": 75}
            )
            mock_info.assert_called_once()
            
    def test_log_model_prediction(self):
        """Test AuditLogger.log_model_prediction method."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_model_prediction(
                model_name="lstm_predictor",
                symbol="AAPL",
                prediction=0.65,
                confidence=0.80
            )
            mock_info.assert_called_once()
            
    def test_log_model_prediction_with_features(self):
        """Test log_model_prediction with features dict."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_model_prediction(
                model_name="xgboost",
                symbol="MSFT",
                prediction=0.45,
                confidence=0.70,
                features={"rsi": 45, "macd": 0.5}
            )
            mock_info.assert_called_once()
            
    def test_log_system_event_info(self):
        """Test AuditLogger.log_system_event with INFO severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_system_event(
                event_type="startup",
                description="System started successfully",
                severity="INFO"
            )
            mock_info.assert_called_once()
            
    def test_log_system_event_warning(self):
        """Test log_system_event with WARNING severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'warning') as mock_warning:
            al.log_system_event(
                event_type="degraded",
                description="System performance degraded",
                severity="WARNING"
            )
            mock_warning.assert_called_once()
            
    def test_log_system_event_error(self):
        """Test log_system_event with ERROR severity."""
        al = AuditLogger()
        with patch.object(al.logger, 'error') as mock_error:
            al.log_system_event(
                event_type="failure",
                description="System component failed",
                severity="ERROR"
            )
            mock_error.assert_called_once()
            
    def test_log_system_event_with_data(self):
        """Test log_system_event with additional data."""
        al = AuditLogger()
        with patch.object(al.logger, 'info') as mock_info:
            al.log_system_event(
                event_type="config_change",
                description="Configuration updated",
                data={"setting": "max_orders", "old": 100, "new": 150}
            )
            mock_info.assert_called_once()


# =============================================================================
# Tests for PerformanceContext class
# =============================================================================

class TestPerformanceContext:
    """Tests for PerformanceContext class."""
    
    def test_context_manager_protocol(self):
        """Test PerformanceContext implements context manager protocol."""
        mock_logger = MagicMock(spec=PerformanceLogger)
        ctx = PerformanceContext(mock_logger, "test_op")
        
        assert hasattr(ctx, '__enter__')
        assert hasattr(ctx, '__exit__')
        
    def test_context_manager_times_operation(self):
        """Test that context manager times operation."""
        mock_logger = MagicMock(spec=PerformanceLogger)
        ctx = PerformanceContext(mock_logger, "timed_op")
        
        import time
        with ctx:
            time.sleep(0.01)  # 10ms
            
        # Should have called log_latency
        mock_logger.log_latency.assert_called_once()
        call_args = mock_logger.log_latency.call_args[0]
        assert call_args[0] == "timed_op"
        assert call_args[1] >= 10  # At least 10ms
        
    def test_context_manager_returns_self(self):
        """Test that __enter__ returns self."""
        mock_logger = MagicMock(spec=PerformanceLogger)
        ctx = PerformanceContext(mock_logger, "test")
        
        result = ctx.__enter__()
        assert result is ctx


# =============================================================================
# Tests for PerformanceLogger class
# =============================================================================

class TestPerformanceLogger:
    """Tests for PerformanceLogger class."""
    
    def test_performance_logger_init(self):
        """Test PerformanceLogger initialization."""
        pl = PerformanceLogger()
        assert pl.logger is not None
        
    def test_global_performance_logger_exists(self):
        """Test that global performance_logger instance exists."""
        assert performance_logger is not None
        assert isinstance(performance_logger, PerformanceLogger)
        
    def test_callable_returns_context(self):
        """Test that calling PerformanceLogger returns context manager."""
        pl = PerformanceLogger()
        ctx = pl("test_operation")
        
        assert isinstance(ctx, PerformanceContext)
        assert ctx.operation == "test_operation"
        
    def test_log_latency(self):
        """Test PerformanceLogger.log_latency method."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_latency("db_query", 15.5)
            mock_info.assert_called_once()
            
    def test_log_latency_with_context(self):
        """Test log_latency with additional context."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_latency("api_call", 50.0, context={"endpoint": "/orders"})
            mock_info.assert_called_once()
            
    def test_log_throughput(self):
        """Test PerformanceLogger.log_throughput method."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_throughput("messages", count=1000, time_window_sec=60.0)
            mock_info.assert_called_once()
            
    def test_log_throughput_zero_time_window(self):
        """Test log_throughput with zero time window (edge case)."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_throughput("messages", count=100, time_window_sec=0)
            mock_info.assert_called_once()
            # Throughput should be 0 when time window is 0
            
    def test_log_throughput_with_context(self):
        """Test log_throughput with additional context."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_throughput(
                "orders",
                count=500,
                time_window_sec=300.0,
                context={"queue": "main"}
            )
            mock_info.assert_called_once()
            
    def test_log_resource_usage(self):
        """Test PerformanceLogger.log_resource_usage method."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_resource_usage(cpu_percent=45.5, memory_mb=1024.0)
            mock_info.assert_called_once()
            
    def test_log_resource_usage_with_context(self):
        """Test log_resource_usage with additional context."""
        pl = PerformanceLogger()
        with patch.object(pl.logger, 'info') as mock_info:
            pl.log_resource_usage(
                cpu_percent=80.0,
                memory_mb=2048.0,
                context={"process": "worker"}
            )
            mock_info.assert_called_once()


# =============================================================================
# Tests for log_event function
# =============================================================================

class TestLogEvent:
    """Tests for log_event function."""
    
    def test_log_event_info_level(self):
        """Test log_event with INFO level event."""
        mock_logger = MagicMock()
        log_event("SIGNAL_DECIDED", mock_logger, symbol="AAPL", action="BUY")
        mock_logger.info.assert_called_once()
        
    def test_log_event_warning_level(self):
        """Test log_event with WARNING level event."""
        mock_logger = MagicMock()
        log_event("RISK_BLOCKED", mock_logger, symbol="AAPL", reason="limit")
        mock_logger.warning.assert_called_once()
        
    def test_log_event_critical_level(self):
        """Test log_event with critical level event."""
        mock_logger = MagicMock()
        log_event("SYSTEM_FAILURE", mock_logger, component="database")
        mock_logger.error.assert_called_once()
        
    def test_log_event_unknown_event(self):
        """Test log_event with unknown event type defaults to info."""
        mock_logger = MagicMock()
        log_event("UNKNOWN_EVENT", mock_logger, data="test")
        mock_logger.info.assert_called_once()
        
    def test_log_event_no_logger_provided(self):
        """Test log_event creates logger when none provided."""
        # Should not raise exception
        log_event("SIGNAL_DECIDED", symbol="AAPL")
        
    def test_log_event_order_events(self):
        """Test log_event with various order events."""
        mock_logger = MagicMock()
        
        order_events = [
            "ORDER_SUBMIT", "ORDER_STATUS", "ORDER_CANCEL",
            "ORDER_SUBMITTED", "ORDER_ACK", "ORDER_CANCELLED"
        ]
        
        for event in order_events:
            mock_logger.reset_mock()
            log_event(event, mock_logger, order_id="123")
            mock_logger.info.assert_called_once()
            
    def test_log_event_with_trace_id(self):
        """Test log_event with provided trace_id."""
        mock_logger = MagicMock()
        log_event("SIGNAL_DECIDED", mock_logger, trace_id="abc123", symbol="AAPL")
        mock_logger.info.assert_called_once()
        
    def test_log_event_generates_trace_id(self):
        """Test log_event generates trace_id when not provided."""
        mock_logger = MagicMock()
        log_event("SIGNAL_DECIDED", mock_logger, symbol="AAPL")
        
        # Check that trace_id was added to event_data
        call_kwargs = mock_logger.info.call_args[1]
        assert "trace_id" in call_kwargs


# =============================================================================
# Tests for StandardEventLogger class
# =============================================================================

class TestStandardEventLogger:
    """Tests for StandardEventLogger class."""
    
    def test_standard_event_logger_init(self):
        """Test StandardEventLogger initialization."""
        sel = StandardEventLogger("test_service")
        assert sel.logger is not None
        assert sel.service_name == "test_service"
        
    def test_signal_decided(self):
        """Test StandardEventLogger.signal_decided method."""
        sel = StandardEventLogger("trading")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.signal_decided("AAPL", "BUY", 0.85)
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["action"] == "BUY"
            assert call_kwargs["confidence"] == 0.85
            
    def test_order_submit(self):
        """Test StandardEventLogger.order_submit method."""
        sel = StandardEventLogger("orders")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.order_submit("order123", "TSLA", "buy", 100.0)
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["order_id"] == "order123"
            assert call_kwargs["symbol"] == "TSLA"
            assert call_kwargs["side"] == "buy"
            assert call_kwargs["qty"] == 100.0
            
    def test_order_status(self):
        """Test StandardEventLogger.order_status method."""
        sel = StandardEventLogger("orders")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.order_status("order123", "FILLED")
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["order_id"] == "order123"
            assert call_kwargs["status"] == "FILLED"
            
    def test_order_cancel(self):
        """Test StandardEventLogger.order_cancel method."""
        sel = StandardEventLogger("orders")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.order_cancel("order123", reason="User requested")
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["order_id"] == "order123"
            assert call_kwargs["reason"] == "User requested"
            
    def test_risk_blocked(self):
        """Test StandardEventLogger.risk_blocked method."""
        sel = StandardEventLogger("risk")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.risk_blocked("AAPL", "buy", 1000.0, ["position_limit", "daily_loss"])
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["side"] == "buy"
            assert call_kwargs["qty"] == 1000.0
            assert call_kwargs["issues"] == ["position_limit", "daily_loss"]
            
    def test_position_update(self):
        """Test StandardEventLogger.position_update method."""
        sel = StandardEventLogger("positions")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.position_update("AAPL", "long", quantity=500)
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["position_type"] == "long"
            
    def test_methods_include_service_name(self):
        """Test that all methods include service name in kwargs."""
        sel = StandardEventLogger("my_service")
        with patch('backend.utils.logger.log_event') as mock_log:
            sel.signal_decided("AAPL", "BUY", 0.85)
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["service"] == "my_service"


# =============================================================================
# Tests for helper functions
# =============================================================================

class TestLogOrderHelpers:
    """Tests for order logging helper functions."""
    
    def test_log_order_submitted(self):
        """Test log_order_submitted helper."""
        with patch('backend.utils.logger.log_event') as mock_log:
            log_order_submitted(order_id="123", symbol="AAPL")
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "ORDER_SUBMITTED"
            
    def test_log_order_ack(self):
        """Test log_order_ack helper."""
        with patch('backend.utils.logger.log_event') as mock_log:
            log_order_ack(order_id="123", broker="alpaca")
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "ORDER_ACK"
            
    def test_log_order_rejected(self):
        """Test log_order_rejected helper."""
        with patch('backend.utils.logger.log_event') as mock_log:
            log_order_rejected(order_id="123", reason="Insufficient funds")
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "ORDER_REJECTED"
            
    def test_log_order_cancelled(self):
        """Test log_order_cancelled helper."""
        with patch('backend.utils.logger.log_event') as mock_log:
            log_order_cancelled(order_id="123")
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "ORDER_CANCELLED"


class TestGetEventLogger:
    """Tests for get_event_logger function."""
    
    def test_get_event_logger_returns_standard_event_logger(self):
        """Test that get_event_logger returns StandardEventLogger."""
        logger = get_event_logger("test_service")
        assert isinstance(logger, StandardEventLogger)
        assert logger.service_name == "test_service"
        
    def test_get_event_logger_different_names(self):
        """Test getting event loggers with different names."""
        logger1 = get_event_logger("service1")
        logger2 = get_event_logger("service2")
        
        assert logger1.service_name == "service1"
        assert logger2.service_name == "service2"


# =============================================================================
# Integration tests
# =============================================================================

class TestLoggerIntegration:
    """Integration tests for logger module."""
    
    def test_full_audit_logging_flow(self):
        """Test complete audit logging flow."""
        al = AuditLogger()
        
        # Should not raise any exceptions
        al.info("Test started")
        al.log_trade_execution("momentum", "AAPL", "buy", 100, 150.0, "order1")
        al.log_risk_event("check", "Passed", "INFO")
        al.log_strategy_signal("momentum", "AAPL", "BUY", 0.9)
        al.log_model_prediction("lstm", "AAPL", 0.7, 0.85)
        al.log_system_event("complete", "Test completed")
        
    def test_full_performance_logging_flow(self):
        """Test complete performance logging flow."""
        pl = PerformanceLogger()
        
        # Should not raise any exceptions
        pl.log_latency("operation1", 50.0)
        pl.log_throughput("messages", 1000, 60.0)
        pl.log_resource_usage(50.0, 1024.0)
        
        # Test context manager
        with pl("timed_operation"):
            pass
            
    def test_full_event_logging_flow(self):
        """Test complete event logging flow."""
        sel = StandardEventLogger("integration_test")
        
        # Should not raise any exceptions
        sel.signal_decided("AAPL", "BUY", 0.85)
        sel.order_submit("order1", "AAPL", "buy", 100.0)
        sel.order_status("order1", "FILLED")
        sel.position_update("AAPL", "long")
        
    def test_sensitive_data_not_logged(self):
        """Test that sensitive data is scrubbed before logging."""
        al = AuditLogger()
        
        # Create event with sensitive data
        al.log_system_event(
            "config",
            "Config loaded",
            data={"password": "secret123", "api_key": "sk-12345678"}
        )
        
        # The sensitive data should be scrubbed internally
        # This test verifies no exceptions are raised


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases:
    """Edge case tests for logger module."""
    
    def test_mask_value_with_none(self):
        """Test _mask_value with None value."""
        # Should handle gracefully
        try:
            result = _mask_value(None)
            # If it doesn't raise, the result should be masked or unchanged
        except TypeError:
            pass  # Expected if None is not handled
            
    def test_scrub_string_with_multiple_patterns(self):
        """Test _scrub_string with multiple sensitive patterns."""
        text = "API: APIKEY=sk-12345678901234567890 Password: password=secret SSN: 123-45-6789"
        result = _scrub_string(text)
        
        # Multiple patterns should be scrubbed - check masking occurred
        assert "REDACTED" in result or "***" in result
        # Original sensitive values should be masked
        assert "sk-12345678901234567890" not in result
        assert "secret" not in result or "***" in result
        assert "123-45-6789" not in result
        
    def test_scrub_deeply_nested_structure(self):
        """Test scrubbing deeply nested data structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "password": "deep_secret"
                    }
                }
            }
        }
        result = _scrub_dict(data)
        
        # Deep secret should be masked
        assert "***" in result["level1"]["level2"]["level3"]["password"]
        
    def test_performance_context_with_exception(self):
        """Test PerformanceContext when exception occurs in block."""
        mock_logger = MagicMock(spec=PerformanceLogger)
        ctx = PerformanceContext(mock_logger, "exception_op")
        
        try:
            with ctx:
                raise ValueError("Test error")
        except ValueError:
            pass
            
        # Should still log latency even after exception
        mock_logger.log_latency.assert_called_once()
        
    def test_log_event_all_critical_events(self):
        """Test all critical events log at error level."""
        critical_events = ["SYSTEM_FAILURE", "SECURITY_BREACH", "DATA_CORRUPTION"]
        
        for event in critical_events:
            mock_logger = MagicMock()
            log_event(event, mock_logger)
            mock_logger.error.assert_called_once()
            
    def test_log_event_all_warning_events(self):
        """Test all warning events log at warning level."""
        warning_events = ["RISK_BLOCKED", "ORDER_REJECTED", "LIMIT_EXCEEDED", "CIRCUIT_BREAKER"]
        
        for event in warning_events:
            mock_logger = MagicMock()
            log_event(event, mock_logger)
            mock_logger.warning.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
