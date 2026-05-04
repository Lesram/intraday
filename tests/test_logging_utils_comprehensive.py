"""
Comprehensive tests for backend/utils/logging.py

Target: Increase coverage from 55% to 90%+
Tests cover:
- Logger stub class
- LogHandler stub class
- Formatter stub class
- Module-level functions
- Structured logging helpers
"""

import pytest
import logging
import sys
from unittest.mock import MagicMock


# Import the module under test
from backend.utils.logging import (
    Logger,
    LogHandler,
    Formatter,
    get_logger,
    setup_logging,
    configure_logger,
    create_console_handler,
    create_file_handler,
    create_formatter,
    log_trade_execution,
    log_risk_check,
    log_market_data_update,
    log_model_prediction,
    log_system_startup,
    log_system_shutdown,
    log_error_with_context,
    create_structured_logger,
    add_log_context,
    remove_log_context,
    logger,
    default_logger,
    log,
    trading_logger,
)


# =============================================================================
# Tests for Logger class
# =============================================================================

class TestLoggerClass:
    """Tests for Logger class."""
    
    def test_logger_init_default_name(self):
        """Test Logger initialization with default name."""
        lg = Logger()
        assert lg.name == "trading"
        
    def test_logger_init_custom_name(self):
        """Test Logger initialization with custom name."""
        lg = Logger("custom_logger")
        assert lg.name == "custom_logger"
        
    def test_logger_init_default_level(self):
        """Test Logger default level matches underlying logging.getLogger level."""
        lg = Logger("test_default_level_check")
        assert lg.level == logging.getLogger("test_default_level_check").level
        
    def test_logger_init_empty_handlers(self):
        """Test Logger starts with empty handlers."""
        lg = Logger()
        assert lg.handlers == []
        
    def test_logger_debug(self):
        """Test Logger.debug method."""
        lg = Logger()
        # Should not raise
        lg.debug("Debug message")
        lg.debug("Debug with args %s", "arg1")
        lg.debug("Debug with kwargs", extra={"key": "value"})
        
    def test_logger_info(self):
        """Test Logger.info method."""
        lg = Logger()
        lg.info("Info message")
        lg.info("Info with args %s %d", "test", 42)
        
    def test_logger_warning(self):
        """Test Logger.warning method."""
        lg = Logger()
        lg.warning("Warning message")
        lg.warning("Warning: %s", "something happened")
        
    def test_logger_error(self):
        """Test Logger.error method."""
        lg = Logger()
        lg.error("Error message")
        lg.error("Error: %s", "failed operation")
        
    def test_logger_critical(self):
        """Test Logger.critical method."""
        lg = Logger()
        lg.critical("Critical message")
        lg.critical("Critical: %s", "system failure")
        
    def test_logger_exception(self):
        """Test Logger.exception method."""
        lg = Logger()
        lg.exception("Exception message")
        lg.exception("Exception: %s", "error details")
        
    def test_logger_set_level(self):
        """Test Logger.setLevel method."""
        lg = Logger()
        lg.setLevel(logging.DEBUG)
        assert lg.level == logging.DEBUG
        
        lg.setLevel(logging.ERROR)
        assert lg.level == logging.ERROR
        
    def test_logger_add_handler(self):
        """Test Logger.addHandler method."""
        lg = Logger()
        handler = LogHandler()
        
        lg.addHandler(handler)
        
        assert handler in lg.handlers
        assert len(lg.handlers) == 1
        
    def test_logger_add_multiple_handlers(self):
        """Test adding multiple handlers."""
        lg = Logger("test_multi_handler_unique")
        handler1 = LogHandler()
        handler2 = LogHandler()

        lg.addHandler(handler1)
        lg.addHandler(handler2)

        assert handler1 in lg.handlers
        assert handler2 in lg.handlers
        assert len(lg.handlers) >= 2
        
    def test_logger_remove_handler(self):
        """Test Logger.removeHandler method."""
        lg = Logger()
        handler = LogHandler()
        lg.addHandler(handler)
        
        lg.removeHandler(handler)
        
        assert handler not in lg.handlers
        
    def test_logger_remove_nonexistent_handler(self):
        """Test removing handler that doesn't exist."""
        lg = Logger()
        handler = LogHandler()
        
        # Should not raise
        lg.removeHandler(handler)


# =============================================================================
# Tests for LogHandler class
# =============================================================================

class TestLogHandlerClass:
    """Tests for LogHandler class."""
    
    def test_handler_init_default_stream(self):
        """Test LogHandler initialization with default stream."""
        handler = LogHandler()
        assert handler.stream == sys.stdout
        
    def test_handler_init_custom_stream(self):
        """Test LogHandler initialization with custom stream."""
        custom_stream = MagicMock()
        handler = LogHandler(stream=custom_stream)
        assert handler.stream == custom_stream
        
    def test_handler_init_no_formatter(self):
        """Test LogHandler starts with no formatter."""
        handler = LogHandler()
        assert handler.formatter is None
        
    def test_handler_set_formatter(self):
        """Test LogHandler.setFormatter method."""
        handler = LogHandler()
        formatter = Formatter()
        
        handler.setFormatter(formatter)
        
        assert handler.formatter == formatter
        
    def test_handler_emit(self):
        """Test LogHandler.emit method."""
        handler = LogHandler()
        record = MagicMock()
        
        # Should not raise
        handler.emit(record)


# =============================================================================
# Tests for Formatter class
# =============================================================================

class TestFormatterClass:
    """Tests for Formatter class."""
    
    def test_formatter_init_default_format(self):
        """Test Formatter initialization with default format."""
        formatter = Formatter()
        assert "asctime" in formatter.fmt
        assert "name" in formatter.fmt
        assert "levelname" in formatter.fmt
        
    def test_formatter_init_custom_format(self):
        """Test Formatter initialization with custom format."""
        custom_fmt = "%(levelname)s: %(message)s"
        formatter = Formatter(fmt=custom_fmt)
        assert formatter.fmt == custom_fmt
        
    def test_formatter_init_datefmt(self):
        """Test Formatter initialization with date format."""
        formatter = Formatter(datefmt="%Y-%m-%d")
        assert formatter.datefmt == "%Y-%m-%d"
        
    def test_formatter_format(self):
        """Test Formatter.format method."""
        formatter = Formatter()

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="Test message", args=(), exc_info=None,
        )

        result = formatter.format(record)

        assert "INFO" in result
        assert "Test message" in result


# =============================================================================
# Tests for module-level functions
# =============================================================================

class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_default_name(self):
        """Test get_logger with default name."""
        lg = get_logger()
        assert isinstance(lg, Logger)
        assert lg.name == "trading"
        
    def test_get_logger_custom_name(self):
        """Test get_logger with custom name."""
        lg = get_logger("my_module")
        assert lg.name == "my_module"


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging_no_config(self):
        """Test setup_logging with no config."""
        # Should not raise
        result = setup_logging()
        assert result is None
        
    def test_setup_logging_with_config(self):
        """Test setup_logging with config dict."""
        config = {"level": "DEBUG", "format": "simple"}
        result = setup_logging(config)
        assert result is None


class TestConfigureLogger:
    """Tests for configure_logger function."""
    
    def test_configure_logger_default_level(self):
        """Test configure_logger with default INFO level."""
        lg = configure_logger("test_logger")
        assert lg.level == logging.INFO
        
    def test_configure_logger_debug_level(self):
        """Test configure_logger with DEBUG level."""
        lg = configure_logger("debug_logger", level="DEBUG")
        assert lg.level == logging.DEBUG
        
    def test_configure_logger_error_level(self):
        """Test configure_logger with ERROR level."""
        lg = configure_logger("error_logger", level="ERROR")
        assert lg.level == logging.ERROR
        
    def test_configure_logger_warning_level(self):
        """Test configure_logger with WARNING level."""
        lg = configure_logger("warn_logger", level="WARNING")
        assert lg.level == logging.WARNING
        
    def test_configure_logger_critical_level(self):
        """Test configure_logger with CRITICAL level."""
        lg = configure_logger("critical_logger", level="CRITICAL")
        assert lg.level == logging.CRITICAL
        
    def test_configure_logger_unknown_level(self):
        """Test configure_logger with unknown level defaults to INFO."""
        lg = configure_logger("unknown_logger", level="UNKNOWN")
        assert lg.level == logging.INFO


class TestCreateConsoleHandler:
    """Tests for create_console_handler function."""
    
    def test_create_console_handler_default(self):
        """Test create_console_handler with default level."""
        handler = create_console_handler()
        assert isinstance(handler, LogHandler)
        assert handler.stream == sys.stdout
        
    def test_create_console_handler_custom_level(self):
        """Test create_console_handler with custom level."""
        handler = create_console_handler(level="DEBUG")
        assert isinstance(handler, LogHandler)


class TestCreateFileHandler:
    """Tests for create_file_handler function."""
    
    def test_create_file_handler(self):
        """Test create_file_handler."""
        handler = create_file_handler("test.log")
        assert isinstance(handler, LogHandler)
        
    def test_create_file_handler_custom_level(self):
        """Test create_file_handler with custom level."""
        handler = create_file_handler("test.log", level="ERROR")
        assert isinstance(handler, LogHandler)


class TestCreateFormatter:
    """Tests for create_formatter function."""
    
    def test_create_formatter_default(self):
        """Test create_formatter with no format string."""
        formatter = create_formatter()
        assert isinstance(formatter, Formatter)
        
    def test_create_formatter_custom(self):
        """Test create_formatter with custom format string."""
        formatter = create_formatter("%(message)s")
        assert isinstance(formatter, Formatter)


# =============================================================================
# Tests for logging utility functions
# =============================================================================

class TestLoggingUtilityFunctions:
    """Tests for logging utility functions."""
    
    def test_log_trade_execution(self):
        """Test log_trade_execution function."""
        # Should not raise
        log_trade_execution("order123", "AAPL", 100.0, 150.50)
        
    def test_log_risk_check_approved(self):
        """Test log_risk_check with approved=True."""
        log_risk_check("AAPL", 0.3, approved=True)
        
    def test_log_risk_check_rejected(self):
        """Test log_risk_check with approved=False."""
        log_risk_check("TSLA", 0.9, approved=False)
        
    def test_log_market_data_update(self):
        """Test log_market_data_update function."""
        log_market_data_update("AAPL", 150.25, 1000000)
        
    def test_log_model_prediction(self):
        """Test log_model_prediction function."""
        log_model_prediction("MSFT", 1, 0.85)
        
    def test_log_system_startup(self):
        """Test log_system_startup function."""
        log_system_startup()
        
    def test_log_system_shutdown(self):
        """Test log_system_shutdown function."""
        log_system_shutdown()
        
    def test_log_error_with_context(self):
        """Test log_error_with_context function."""
        error = ValueError("Test error")
        context = {"user_id": "123", "action": "trade"}
        log_error_with_context(error, context)


# =============================================================================
# Tests for structured logging helpers
# =============================================================================

class TestStructuredLoggingHelpers:
    """Tests for structured logging helpers."""
    
    def test_create_structured_logger(self):
        """Test create_structured_logger function."""
        result = create_structured_logger("test_module")
        
        assert isinstance(result, dict)
        assert "logger" in result
        assert "context" in result
        assert "handlers" in result
        assert isinstance(result["logger"], Logger)
        
    def test_add_log_context(self):
        """Test add_log_context function."""
        # Should not raise
        add_log_context({"user": "test_user", "session": "abc123"})
        
    def test_remove_log_context(self):
        """Test remove_log_context function."""
        # Should not raise
        remove_log_context(["user", "session"])


# =============================================================================
# Tests for module-level instances
# =============================================================================

class TestModuleLevelInstances:
    """Tests for module-level logger instances."""
    
    def test_logger_instance_exists(self):
        """Test that logger instance exists."""
        assert logger is not None
        assert isinstance(logger, Logger)
        
    def test_default_logger_instance_exists(self):
        """Test that default_logger instance exists."""
        assert default_logger is not None
        assert isinstance(default_logger, Logger)
        
    def test_log_alias_exists(self):
        """Test that log alias exists."""
        assert log is not None
        assert isinstance(log, Logger)
        
    def test_trading_logger_exists(self):
        """Test that trading_logger exists."""
        assert trading_logger is not None
        assert isinstance(trading_logger, Logger)
        
    def test_all_instances_same_logger(self):
        """Test that all instances are the same."""
        assert logger is default_logger
        assert logger is log
        assert logger is trading_logger


# =============================================================================
# Integration tests
# =============================================================================

class TestLoggingIntegration:
    """Integration tests for logging module."""
    
    def test_full_logging_setup(self):
        """Test complete logging setup flow."""
        # Get logger
        lg = get_logger("integration_test")
        
        # Configure it
        lg = configure_logger("integration_test", level="DEBUG")
        
        # Create and add handlers
        console_handler = create_console_handler()
        lg.addHandler(console_handler)
        
        # Set formatter
        formatter = create_formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(formatter)
        
        # Log messages
        lg.debug("Debug message")
        lg.info("Info message")
        lg.warning("Warning message")
        lg.error("Error message")
        
    def test_structured_logging_workflow(self):
        """Test structured logging workflow."""
        struct_logger = create_structured_logger("my_service")
        
        # Add context
        add_log_context({"request_id": "req123"})
        
        # Use logger
        struct_logger["logger"].info("Processing request")
        
        # Remove context
        remove_log_context(["request_id"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
