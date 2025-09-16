"""
Tests for backend/services/order_fsm.py - Order Finite State Machine.
Tests the state machine that manages order lifecycle transitions.
"""

import pytest
from unittest.mock import MagicMock, Mock
from backend.services.order_fsm import OrderStateMachine


class TestOrderStateMachine:
    """Test the OrderStateMachine class."""
    
    def test_initialization_with_defaults(self):
        """Test basic initialization without parameters."""
        fsm = OrderStateMachine()
        
        assert fsm.audit_logger is not None
        # Should have a default no-op audit logger
        assert callable(fsm.audit_logger)
    
    def test_initialization_with_audit_logger(self):
        """Test initialization with custom audit logger."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        assert fsm.audit_logger is mock_logger
    
    def test_initialization_with_positional_args(self):
        """Test backward compatibility with legacy positional arguments."""
        # Should accept arbitrary positional args for backward compatibility
        fsm = OrderStateMachine("arg1", "arg2", audit_logger=Mock())
        
        assert fsm.audit_logger is not None
        assert callable(fsm.audit_logger)
    
    def test_initialization_with_keyword_args(self):
        """Test backward compatibility with arbitrary keyword arguments."""
        mock_logger = Mock()
        fsm = OrderStateMachine(
            some_legacy_param="value",
            another_param=123,
            audit_logger=mock_logger
        )
        
        assert fsm.audit_logger is mock_logger
    
    def test_create_order_basic_functionality(self):
        """Test basic order creation functionality."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        test_spec = {"symbol": "AAPL", "quantity": 100, "side": "buy"}
        result = fsm.create_order(test_spec)
        
        # Should return order with basic structure
        assert isinstance(result, dict)
        assert "id" in result
        assert "status" in result
        assert result["status"] == "new"
        assert result["id"] == "test-order"
        
        # Should have called audit logger
        mock_logger.assert_called_once_with("create_order", test_spec)
    
    def test_create_order_with_different_specs(self):
        """Test order creation with various order specifications."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        test_cases = [
            {"symbol": "AAPL", "qty": 100, "side": "buy"},
            {"symbol": "TSLA", "qty": 50, "side": "sell", "order_type": "limit"},
            {"symbol": "SPY", "qty": 200, "side": "buy", "time_in_force": "day"},
            {},  # Empty spec should still work
            {"complex": {"nested": "data"}},  # Complex spec
        ]
        
        for i, spec in enumerate(test_cases):
            mock_logger.reset_mock()
            result = fsm.create_order(spec)
            
            assert isinstance(result, dict)
            assert result["status"] == "new"
            assert result["id"] == "test-order"
            mock_logger.assert_called_once_with("create_order", spec)
    
    def test_audit_logger_called_correctly(self):
        """Test that audit logger is called with correct parameters."""
        mock_logger = Mock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        test_spec = {"symbol": "MSFT", "quantity": 75}
        fsm.create_order(test_spec)
        
        # Verify logger was called with correct action and spec
        args, kwargs = mock_logger.call_args
        assert args == ("create_order", test_spec)
    
    def test_default_audit_logger_no_op(self):
        """Test that default audit logger doesn't raise exceptions."""
        fsm = OrderStateMachine()
        
        # Should not raise any exceptions with default logger
        result = fsm.create_order({"symbol": "NVDA", "qty": 25})
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_order_id_consistency(self):
        """Test that order creation returns consistent test ID."""
        fsm = OrderStateMachine()
        
        # Multiple calls should return same test ID (as per current implementation)
        result1 = fsm.create_order({"symbol": "AAPL"})
        result2 = fsm.create_order({"symbol": "TSLA"})
        
        assert result1["id"] == result2["id"] == "test-order"
        assert result1["status"] == result2["status"] == "new"
    
    def test_backward_compatibility_mixed_args(self):
        """Test full backward compatibility with mixed argument styles."""
        mock_logger = Mock()
        
        # Should handle positional args, keyword args, and audit_logger together
        fsm = OrderStateMachine(
            "legacy_arg1",
            123,
            legacy_param="old_value",
            new_param={"modern": "value"},
            audit_logger=mock_logger
        )
        
        # Should still function normally
        result = fsm.create_order({"test": "order"})
        assert result["status"] == "new"
        mock_logger.assert_called_once()


class TestOrderStateMachineIntegration:
    """Integration tests for OrderStateMachine."""
    
    def test_fsm_with_real_logging_scenario(self):
        """Test FSM with a more realistic logging scenario."""
        log_calls = []
        
        def audit_logger(action, data):
            log_calls.append({"action": action, "data": data, "timestamp": "mock_time"})
        
        fsm = OrderStateMachine(audit_logger=audit_logger)
        
        # Create multiple orders
        orders = [
            {"symbol": "AAPL", "qty": 100, "side": "buy"},
            {"symbol": "TSLA", "qty": 50, "side": "sell"},
            {"symbol": "MSFT", "qty": 200, "side": "buy"},
        ]
        
        results = []
        for order_spec in orders:
            result = fsm.create_order(order_spec)
            results.append(result)
        
        # Verify all orders were logged
        assert len(log_calls) == len(orders)
        for i, (order_spec, log_call) in enumerate(zip(orders, log_calls)):
            assert log_call["action"] == "create_order"
            assert log_call["data"] == order_spec
        
        # Verify all orders have consistent structure
        for result in results:
            assert result["status"] == "new"
            assert result["id"] == "test-order"
    
    def test_fsm_error_handling(self):
        """Test FSM behavior when audit logger raises exceptions."""
        def failing_logger(action, data):
            raise ValueError("Logger error")
        
        fsm = OrderStateMachine(audit_logger=failing_logger)
        
        # Should propagate logger exceptions (current implementation)
        with pytest.raises(ValueError, match="Logger error"):
            fsm.create_order({"symbol": "AAPL"})
    
    def test_fsm_with_none_audit_logger(self):
        """Test FSM when audit_logger is explicitly set to None."""
        fsm = OrderStateMachine(audit_logger=None)
        
        # Should fall back to default no-op logger
        result = fsm.create_order({"symbol": "AAPL"})
        assert result is not None
        assert result["status"] == "new"


@pytest.mark.integration
class TestOrderStateMachineRealWorld:
    """Real-world integration tests for OrderStateMachine."""
    
    def test_integration_with_order_specs(self):
        """Test integration with realistic order specifications."""
        audit_log = []
        fsm = OrderStateMachine(audit_logger=lambda action, data: audit_log.append((action, data)))
        
        # Test various realistic order specs
        realistic_orders = [
            {
                "symbol": "AAPL",
                "qty": 100,
                "side": "buy",
                "order_type": "market",
                "time_in_force": "day"
            },
            {
                "symbol": "TSLA",
                "qty": 50,
                "side": "sell",
                "order_type": "limit",
                "limit_price": 250.00,
                "time_in_force": "gtc"
            },
            {
                "symbol": "SPY",
                "qty": 1000,
                "side": "buy",
                "order_type": "stop",
                "stop_price": 400.00
            }
        ]
        
        for order_spec in realistic_orders:
            result = fsm.create_order(order_spec)
            
            # All orders should be created successfully
            assert result["status"] == "new"
            assert result["id"] == "test-order"
        
        # All orders should be audited
        assert len(audit_log) == len(realistic_orders)
        for i, (action, data) in enumerate(audit_log):
            assert action == "create_order"
            assert data == realistic_orders[i]
