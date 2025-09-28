#!/usr/bin/env python3
"""
Comprehensive test suite for backend/utils/logger.py - 100% coverage target.

This test file enhances coverage for the AuditLogger and related logging functionality.
Current coverage: 46% → Target: 100%
Missing lines: 49 lines
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime, UTC
from unittest.mock import Mock, patch, MagicMock
import logging
import json

# Set test environment
os.environ['DISABLE_ML'] = '1'
os.environ['DISABLE_TENSORFLOW'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

from backend.utils.logger import AuditLogger, get_logger


class TestAuditLogger:
    """Test AuditLogger functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_audit.log")
        self.audit_logger = AuditLogger(self.log_file)

    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_audit_logger_initialization(self):
        """Test AuditLogger initialization."""
        logger = AuditLogger(self.log_file)
        assert logger.log_file == Path(self.log_file)
        assert logger.logger is not None
        assert os.path.exists(self.log_file)

    def test_audit_logger_default_file(self):
        """Test AuditLogger with default log file."""
        with patch('backend.utils.logger.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.parent.mkdir = MagicMock()
            
            logger = AuditLogger()
            assert logger.log_file == mock_path_instance

    def test_info_logging(self):
        """Test info level logging."""
        event_type = "test_event"
        additional_data = {"user_id": 123, "action": "test"}
        
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.info(event_type, **additional_data)
            
            # Verify logger.info was called
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            # Check the message
            assert call_args[0][0] == f"Event: {event_type}"
            
            # Check the structured data
            assert call_args[1]["event_type"] == event_type
            assert "timestamp" in call_args[1]
            assert call_args[1]["user_id"] == 123
            assert call_args[1]["action"] == "test"

    def test_warning_logging(self):
        """Test warning level logging."""
        event_type = "warning_event"
        additional_data = {"severity": "medium", "details": "test warning"}
        
        with patch.object(self.audit_logger.logger, 'warning') as mock_warning:
            self.audit_logger.warning(event_type, **additional_data)
            
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            
            assert call_args[0][0] == f"Event: {event_type}"
            assert call_args[1]["event_type"] == event_type
            assert call_args[1]["severity"] == "medium"
            assert call_args[1]["details"] == "test warning"

    def test_error_logging(self):
        """Test error level logging."""
        event_type = "error_event"
        additional_data = {"error_code": 500, "message": "Internal error"}
        
        with patch.object(self.audit_logger.logger, 'error') as mock_error:
            self.audit_logger.error(event_type, **additional_data)
            
            mock_error.assert_called_once()
            call_args = mock_error.call_args
            
            assert call_args[0][0] == f"Event: {event_type}"
            assert call_args[1]["event_type"] == event_type
            assert call_args[1]["error_code"] == 500
            assert call_args[1]["message"] == "Internal error"

    def test_log_trade_execution(self):
        """Test trade execution logging."""
        trade_data = {
            "strategy": "momentum",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100.0,
            "price": 150.50,
            "order_id": "ORD123456"
        }
        
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_trade_execution(**trade_data)
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[0][0] == "Trade executed"
            assert call_args[1]["event_type"] == "trade_execution"
            assert call_args[1]["strategy"] == "momentum"
            assert call_args[1]["symbol"] == "AAPL"
            assert call_args[1]["side"] == "buy"
            assert call_args[1]["quantity"] == 100.0
            assert call_args[1]["price"] == 150.50
            assert call_args[1]["order_id"] == "ORD123456"
            assert "event_id" in call_args[1]
            assert call_args[1]["event_id"].startswith("trade_ORD123456_")

    def test_log_trade_execution_with_timestamp(self):
        """Test trade execution logging with custom timestamp."""
        timestamp = datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC)
        
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_trade_execution(
                strategy="test_strategy",
                symbol="TEST",
                side="sell", 
                quantity=50.0,
                price=100.0,
                order_id="TEST123",
                timestamp=timestamp
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[1]["timestamp"] == timestamp.isoformat()

    def test_log_risk_event_info(self):
        """Test risk event logging with INFO severity."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_risk_event(
                event_type="position_limit",
                description="Position size within limits",
                severity="INFO",
                data={"position_size": 1000}
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[0][0] == "Risk event"
            assert call_args[1]["event_type"] == "risk_position_limit"
            assert call_args[1]["description"] == "Position size within limits"
            assert call_args[1]["severity"] == "INFO"
            assert call_args[1]["data"]["position_size"] == 1000

    def test_log_risk_event_warning(self):
        """Test risk event logging with WARNING severity."""
        with patch.object(self.audit_logger.logger, 'warning') as mock_warning:
            self.audit_logger.log_risk_event(
                event_type="drawdown",
                description="Approaching max drawdown",
                severity="WARNING"
            )
            
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            
            assert call_args[1]["event_type"] == "risk_drawdown"
            assert call_args[1]["severity"] == "WARNING"

    def test_log_risk_event_error(self):
        """Test risk event logging with ERROR severity."""
        with patch.object(self.audit_logger.logger, 'error') as mock_error:
            self.audit_logger.log_risk_event(
                event_type="limit_breach",
                description="Position limit exceeded",
                severity="ERROR",
                data={"limit": 5000, "actual": 6000}
            )
            
            mock_error.assert_called_once()
            call_args = mock_error.call_args
            
            assert call_args[1]["event_type"] == "risk_limit_breach"
            assert call_args[1]["severity"] == "ERROR"
            assert call_args[1]["data"]["limit"] == 5000
            assert call_args[1]["data"]["actual"] == 6000

    def test_log_risk_event_default_severity(self):
        """Test risk event logging with default severity."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_risk_event(
                event_type="check",
                description="Routine risk check"
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[1]["severity"] == "INFO"

    def test_log_risk_event_no_data(self):
        """Test risk event logging without data parameter."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_risk_event(
                event_type="check",
                description="Test without data"
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[1]["data"] == {}

    def test_log_strategy_signal(self):
        """Test strategy signal logging."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_strategy_signal(
                strategy="moving_average",
                symbol="MSFT",
                signal="buy",
                confidence=0.85,
                data={"ma_short": 50.0, "ma_long": 200.0}
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[0][0] == "Strategy signal"
            assert call_args[1]["event_type"] == "strategy_signal"
            assert call_args[1]["strategy"] == "moving_average"
            assert call_args[1]["symbol"] == "MSFT"
            assert call_args[1]["signal"] == "buy"
            assert call_args[1]["confidence"] == 0.85
            assert call_args[1]["data"]["ma_short"] == 50.0
            assert call_args[1]["data"]["ma_long"] == 200.0
            assert "event_id" in call_args[1]
            assert call_args[1]["event_id"].startswith("signal_moving_average_")

    def test_log_strategy_signal_minimal(self):
        """Test strategy signal logging with minimal parameters."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_strategy_signal(
                strategy="simple",
                symbol="SPY",
                signal="hold"
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert call_args[1]["confidence"] is None
            assert call_args[1]["data"] == {}


class TestLoggerIntegration:
    """Test integration aspects of the logger module."""
    
    def test_get_logger_function(self):
        """Test the get_logger function."""
        logger = get_logger("test_logger")
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'error')

    def test_structlog_configuration(self):
        """Test that structlog is properly configured."""
        # This tests that the module-level configuration is applied
        logger = get_logger("config_test")
        
        # Test that we can log without errors
        logger.info("Test configuration", test_key="test_value")

    def test_audit_logger_file_creation(self):
        """Test that audit logger creates log files properly."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_path = os.path.join(temp_dir, "nested", "audit.log")
            
            # This should create the directory structure
            logger = AuditLogger(log_path)
            
            # Verify the file was created
            assert os.path.exists(log_path)
            
            # Test actual logging to file
            logger.info("test_event", key="value")
            
            # Verify log file has content
            assert os.path.getsize(log_path) > 0
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


class TestLoggerEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_audit_logger_with_existing_file(self):
        """Test AuditLogger with pre-existing log file."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file = os.path.join(temp_dir, "existing.log")
            
            # Create file first
            with open(log_file, 'w') as f:
                f.write("existing content\n")
                
            # Initialize logger
            logger = AuditLogger(log_file)
            logger.info("new_event", data="test")
            
            # File should still exist and have new content
            assert os.path.exists(log_file)
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_empty_event_data(self):
        """Test logging with empty event data."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file = os.path.join(temp_dir, "empty.log")
            logger = AuditLogger(log_file)
            
            # These should not fail
            logger.info("empty_event")
            logger.warning("empty_warning")
            logger.error("empty_error")
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_large_event_data(self):
        """Test logging with large event data."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file = os.path.join(temp_dir, "large.log")
            logger = AuditLogger(log_file)
            
            # Create large data structure
            large_data = {"data": ["item"] * 1000, "metadata": {"key": "value"}}
            
            logger.info("large_event", **large_data)
            
            # Should complete without error
            assert os.path.exists(log_file)
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("🚀 Comprehensive Utils Logger Test")
    print("=" * 50)
    
    # Run the tests
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--cov=backend.utils.logger",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov_logger"
    ])
    
    print(f"\n✅ Test execution completed with exit code: {exit_code}")