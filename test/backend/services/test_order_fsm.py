"""
Test Module 92: backend.services.order_fsm
==========================================

Tests for the Order Finite State Machine module to achieve 100% coverage.

This module tests:
- OrderStateMachine class initialization with various parameters
- create_order method functionality
- Audit logger integration and default fallback
- Legacy positional/keyword argument handling

Module Under Test: backend/services/order_fsm.py (6 statements)
Coverage Goal: 100% (6/6 statements)
"""

import importlib.util
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Standard import approach for coverage tracking
from backend.services.order_fsm import OrderStateMachine


class TestModule92BackendServicesOrderFsm:
    """
    Test class for backend/services/order_fsm.py module.
    
    Tests the OrderStateMachine class and its methods to ensure 100% coverage.
    """
    
    def test_order_state_machine_initialization_with_audit_logger(self):
        """Test OrderStateMachine initialization with audit logger."""
        # Create a mock audit logger
        mock_logger = Mock()
        
        # Initialize with audit logger
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # Verify the audit logger is set
        assert fsm.audit_logger is mock_logger
        
    def test_order_state_machine_initialization_without_audit_logger(self):
        """Test OrderStateMachine initialization without audit logger (default fallback)."""
        # Initialize without audit logger
        fsm = OrderStateMachine()
        
        # Verify default audit logger is callable
        assert callable(fsm.audit_logger)
        
        # Test that default logger doesn't raise errors when called
        fsm.audit_logger("test", "message")  # Should not raise
        fsm.audit_logger("test", key="value")  # Should not raise
        
    def test_order_state_machine_initialization_with_positional_args(self):
        """Test OrderStateMachine initialization with legacy positional arguments."""
        # Initialize with positional arguments (legacy support)
        fsm = OrderStateMachine("arg1", "arg2", "arg3")
        
        # Should still work and create default audit logger
        assert callable(fsm.audit_logger)
        
    def test_order_state_machine_initialization_with_mixed_args(self):
        """Test OrderStateMachine initialization with mixed positional and keyword arguments."""
        mock_logger = Mock()
        
        # Initialize with both positional and keyword arguments
        fsm = OrderStateMachine("pos1", "pos2", audit_logger=mock_logger, extra_key="extra_value")
        
        # Verify audit logger is set correctly
        assert fsm.audit_logger is mock_logger
        
    def test_create_order_with_audit_logging(self):
        """Test create_order method with audit logging."""
        # Create a mock audit logger
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # Test order creation
        order_spec = {"symbol": "AAPL", "quantity": 100, "price": 150.0}
        result = fsm.create_order(order_spec)
        
        # Verify audit logger was called
        mock_logger.assert_called_once_with("create_order", order_spec)
        
        # Verify return value
        assert isinstance(result, dict)
        assert result["id"] == "test-order"
        assert result["status"] == "new"
        
    def test_create_order_with_default_audit_logger(self):
        """Test create_order method with default audit logger."""
        # Initialize without explicit audit logger
        fsm = OrderStateMachine()
        
        # Test order creation
        order_spec = {"symbol": "TSLA", "quantity": 50, "price": 800.0}
        result = fsm.create_order(order_spec)
        
        # Should not raise any errors despite default logger
        assert isinstance(result, dict)
        assert result["id"] == "test-order"
        assert result["status"] == "new"


class TestModule92Coverage:
    """
    Coverage-focused tests to ensure every line in order_fsm.py is executed.
    """
    
    def test_class_definition_coverage(self):
        """Test that the OrderStateMachine class is properly defined."""
        # This covers the class definition line
        assert OrderStateMachine is not None
        assert OrderStateMachine.__name__ == "OrderStateMachine"
        assert "State machine for managing order lifecycle transitions" in OrderStateMachine.__doc__
        
    def test_init_method_with_audit_logger_or_fallback(self):
        """Test both branches of the audit_logger assignment."""
        # Test with audit logger provided (covers: self.audit_logger = audit_logger)
        mock_logger = Mock()
        fsm1 = OrderStateMachine(audit_logger=mock_logger)
        assert fsm1.audit_logger is mock_logger
        
        # Test without audit logger (covers: or (lambda *x, **y: None))
        fsm2 = OrderStateMachine()
        assert callable(fsm2.audit_logger)
        
        # Verify the default lambda works
        result = fsm2.audit_logger("test", "data", key="value")
        assert result is None
        
    def test_create_order_audit_logging_line(self):
        """Test the audit logging line in create_order method."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # This covers: self.audit_logger("create_order", spec)
        spec = {"test": "data"}
        fsm.create_order(spec)
        
        # Verify the audit log call
        mock_logger.assert_called_once_with("create_order", spec)
        
    def test_create_order_return_statement(self):
        """Test the return statement in create_order method."""
        fsm = OrderStateMachine()
        
        # This covers: return {"id": "test-order", "status": "new"}
        result = fsm.create_order({"any": "spec"})
        
        # Verify exact return value structure
        expected = {"id": "test-order", "status": "new"}
        assert result == expected


class TestModule92Standalone:
    """
    Standalone tests using importlib to ensure independent coverage.
    """
    
    def test_standalone_module_loading(self):
        """Test loading the module independently to ensure all lines execute."""
        # Get the module path
        module_path = Path(__file__).parent.parent.parent / 'backend' / 'services' / 'order_fsm.py'
        
        # Load module using importlib
        spec = importlib.util.spec_from_file_location('test_order_fsm', module_path)
        test_module = importlib.util.module_from_spec(spec)
        
        # Execute the module (this covers all lines)
        spec.loader.exec_module(test_module)
        
        # Verify module loaded correctly
        assert hasattr(test_module, 'OrderStateMachine')
        
        # Test the loaded class
        loaded_class = test_module.OrderStateMachine
        fsm = loaded_class()
        assert callable(fsm.audit_logger)
        
        result = fsm.create_order({"test": "spec"})
        assert result == {"id": "test-order", "status": "new"}


class TestModule92Integration:
    """
    Integration tests to verify the order FSM works with different scenarios.
    """
    
    def test_multiple_order_creation(self):
        """Test creating multiple orders with the same FSM instance."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # Create multiple orders
        specs = [
            {"symbol": "AAPL", "quantity": 100},
            {"symbol": "GOOGL", "quantity": 50},
            {"symbol": "MSFT", "quantity": 75}
        ]
        
        results = []
        for spec in specs:
            result = fsm.create_order(spec)
            results.append(result)
            
        # Verify all orders were created identically
        for result in results:
            assert result == {"id": "test-order", "status": "new"}
            
        # Verify all audit logs were made
        assert mock_logger.call_count == 3
        expected_calls = [("create_order", spec) for spec in specs]
        actual_calls = [call.args for call in mock_logger.call_args_list]
        assert actual_calls == expected_calls
        
    def test_fsm_with_complex_audit_logger(self):
        """Test FSM with a more complex audit logger implementation."""
        audit_log = []
        
        def complex_logger(action, spec, **kwargs):
            audit_log.append({
                "action": action,
                "spec": spec,
                "timestamp": "mock_time",
                "kwargs": kwargs
            })
            
        fsm = OrderStateMachine(audit_logger=complex_logger)
        
        # Create an order
        spec = {"symbol": "NVDA", "quantity": 25, "price": 500.0}
        result = fsm.create_order(spec)
        
        # Verify audit log was populated
        assert len(audit_log) == 1
        assert audit_log[0]["action"] == "create_order"
        assert audit_log[0]["spec"] is spec
        
        # Verify order creation result
        assert result == {"id": "test-order", "status": "new"}


class TestModule92EdgeCases:
    """
    Edge case tests for comprehensive coverage.
    """
    
    def test_initialization_with_none_audit_logger(self):
        """Test initialization with None as audit logger."""
        # Initialize with None - should use default lambda
        fsm = OrderStateMachine(audit_logger=None)
        
        # Should use the default lambda (or clause)
        assert callable(fsm.audit_logger)
        
        # Should not raise errors when called
        fsm.audit_logger("test")
        fsm.audit_logger("test", "data", key="value")
        
    def test_create_order_with_empty_spec(self):
        """Test create_order with empty specification."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # Test with empty dict
        result = fsm.create_order({})
        
        # Should still work
        assert result == {"id": "test-order", "status": "new"}
        mock_logger.assert_called_once_with("create_order", {})
        
    def test_create_order_with_none_spec(self):
        """Test create_order with None specification."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        # Test with None
        result = fsm.create_order(None)
        
        # Should still work
        assert result == {"id": "test-order", "status": "new"}
        mock_logger.assert_called_once_with("create_order", None)
        
    def test_audit_logger_with_various_argument_patterns(self):
        """Test that default audit logger handles various argument patterns."""
        fsm = OrderStateMachine()  # Uses default lambda
        
        # Test various calling patterns
        fsm.audit_logger()  # No args
        fsm.audit_logger("single_arg")  # Single positional
        fsm.audit_logger("pos1", "pos2", "pos3")  # Multiple positional
        fsm.audit_logger(key="value")  # Keyword only
        fsm.audit_logger("pos", key="value")  # Mixed
        fsm.audit_logger("pos1", "pos2", key1="val1", key2="val2")  # Complex mixed
        
        # All should complete without error
        assert True  # If we get here, no exceptions were raised