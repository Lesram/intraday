"""
Phase 7B.3 Extended: Order Service Module Testing - Advanced Coverage
Targeting remaining uncovered lines and advanced functionality
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from decimal import Decimal
from typing import Any

from backend.services.order_service import OrderService, OrderServiceExtensions, submit_order


class TestOrderModificationPhase7B3:
    """Test order modification functionality"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_modify_order_basic(self, service):
        """Test basic order modification"""
        modification_data = {
            "order_id": "order_123",
            "modification_id": "mod_456",
            "new_qty": 200,
            "new_price": 150.50
        }
        
        result = service.modify_order(modification_data)
        
        assert "order_id" in result
        assert result["order_id"] == "order_123"
        assert "status" in result
    
    def test_modify_order_with_generated_id(self, service):
        """Test order modification with generated modification_id"""
        modification_data = {
            "order_id": "order_789"
            # No modification_id provided
        }
        
        result = service.modify_order(modification_data)
        
        assert "order_id" in result
        assert result["order_id"] == "order_789"
        assert "modification_id" in result
    
    def test_modify_order_thread_safety(self, service):
        """Test order modification thread safety"""
        modification_data = {
            "order_id": "thread_safe_order",
            "modification_id": "thread_safe_mod"
        }
        
        # First modification
        result1 = service.modify_order(modification_data)
        
        # Second modification with same ID (should be idempotent)
        result2 = service.modify_order(modification_data)
        
        assert result1 == result2
        assert result1["order_id"] == "thread_safe_order"


class TestAdvancedValidationPhase7B3:
    """Test advanced validation scenarios"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_validate_order_valid_symbol_edge_cases(self, service):
        """Test validation with edge case valid symbols"""
        # Symbol with dot (like BRK.A)
        order = {"symbol": "BRK.A", "side": "buy", "qty": 10}
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Max length symbol
        order = {"symbol": "ABCDEFGHIJ", "side": "buy", "qty": 10}  # 10 chars
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Numeric symbol
        order = {"symbol": "123", "side": "buy", "qty": 10}
        result = service.validate_order(order)
        assert result["valid"] is True
    
    def test_validate_order_whitespace_symbol(self, service):
        """Test validation with whitespace-only symbol"""
        order = {"symbol": "   ", "side": "buy", "qty": 100}
        result = service.validate_order(order)
        
        assert not result["valid"]
        assert any("invalid_symbol: must be non-empty string" in error for error in result["errors"])
    
    def test_validate_order_boundary_quantities(self, service):
        """Test validation with boundary quantities"""
        # Very small positive quantity
        order = {"symbol": "AAPL", "side": "buy", "qty": 0.001}
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Maximum allowed quantity
        order = {"symbol": "AAPL", "side": "buy", "qty": 1000000}
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Just over maximum
        order = {"symbol": "AAPL", "side": "buy", "qty": 1000001}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_qty: too large" in result["errors"]
    
    def test_validate_order_boundary_prices(self, service):
        """Test validation with boundary prices for limit orders"""
        # Very small positive price
        order = {
            "symbol": "AAPL", 
            "side": "buy", 
            "qty": 100,
            "order_type": "limit",
            "price": 0.01
        }
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Maximum allowed price
        order = {
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 100,
            "order_type": "limit",
            "price": 1000000
        }
        result = service.validate_order(order)
        assert result["valid"] is True
        
        # Just over maximum
        order = {
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 100,
            "order_type": "limit",
            "price": 1000001
        }
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_price: too large" in result["errors"]
    
    def test_validate_order_price_for_stop_limit(self, service):
        """Test price validation for stop_limit orders"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "stop_limit",
            "price": 150.00
        }
        
        result = service.validate_order(order)
        assert result["valid"] is True
    
    def test_validate_order_all_valid_order_types(self, service):
        """Test validation with all valid order types"""
        valid_types = ['market', 'limit', 'stop', 'stop_limit']
        
        for order_type in valid_types:
            order = {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 100,
                "order_type": order_type
            }
            
            result = service.validate_order(order)
            assert result["valid"] is True, f"Order type {order_type} should be valid"
    
    def test_validate_order_price_not_required_for_market(self, service):
        """Test that price is not required for market orders"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "market"
            # No price provided
        }
        
        result = service.validate_order(order)
        assert result["valid"] is True


class TestAsyncLockingMechanismPhase7B3:
    """Test async locking and concurrency mechanisms"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    @pytest.mark.asyncio
    async def test_async_order_lock_initialization(self, service):
        """Test async order lock is created when needed"""
        assert service._async_order_lock is None
        
        order_data = {"symbol": "AAPL", "side": "buy", "qty": 100}
        
        await service.submit_order_async(order_data)
        
        assert service._async_order_lock is not None
        assert isinstance(service._async_order_lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_async_order_duplicate_detection(self, service):
        """Test async order duplicate detection"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_id": "duplicate_test_order"
        }
        
        # Submit first order
        result1 = await service.submit_order_async(order_data)
        assert result1["status"] == "submitted"
        
        # Submit same order again (should be detected as duplicate)
        result2 = await service.submit_order_async(order_data)
        assert result2["status"] == "duplicate"
        assert "duplicate request" in result2["reason"]
    
    @pytest.mark.asyncio
    async def test_async_order_exception_handling(self, service):
        """Test async order submission exception handling"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
            # No order_id provided to trigger uuid4 call
        }
        
        # Mock an internal exception during uuid4 generation
        with patch('backend.services.order_service.uuid4', side_effect=Exception("UUID generation failed")):
            try:
                result = await service.submit_order_async(order_data)
                # If it doesn't raise an exception, check the result
                assert result["status"] == "rejected"
                assert "UUID generation failed" in result["reason"]
            except Exception as e:
                # If it raises an exception, that's also valid behavior
                assert "UUID generation failed" in str(e)
    
    @pytest.mark.asyncio
    async def test_async_concurrent_submissions(self, service):
        """Test concurrent async order submissions"""
        # Submit multiple orders concurrently
        order_data_list = [
            {"symbol": "AAPL", "side": "buy", "qty": 100, "order_id": f"concurrent_{i}"}
            for i in range(5)
        ]
        
        tasks = [service.submit_order_async(order_data) for order_data in order_data_list]
        results = await asyncio.gather(*tasks)
        
        # All should succeed with unique order IDs
        assert len(results) == 5
        order_ids = [result["order_id"] for result in results]
        assert len(set(order_ids)) == 5  # All unique
        
        for result in results:
            assert result["status"] == "submitted"


class TestOrderServiceExtensionsPhase7B3:
    """Test OrderServiceExtensions functionality"""
    
    @pytest.fixture
    def extensions(self):
        return OrderServiceExtensions()
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_no_strategy_engine(self, extensions):
        """Test plan_and_submit raises error when no strategy engine configured"""
        # Don't set strategy_engine (it should be None by default)
        mock_signals = [Mock(symbol="AAPL")]
        
        with pytest.raises(AttributeError, match="'OrderServiceExtensions' object has no attribute 'strategy_engine'"):
            await extensions.plan_and_submit(signals=mock_signals)
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_basic(self, extensions):
        """Test basic plan_and_submit functionality"""
        # Mock trading signals
        mock_signals = [Mock(symbol="AAPL", confidence=0.8, signal_type="buy")]
        
        # Mock strategy engine and bind to extensions
        extensions.strategy_engine = AsyncMock()
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(
                symbol="AAPL",
                side="buy",
                qty=100,
                risk_allowed=True,
                from_exposure=0,
                to_exposure=100,
                reason="Test trade",
                notional=15000
            )
        ]
        
        # Mock submit_symbol_order method
        extensions.submit_symbol_order = AsyncMock()
        extensions.submit_symbol_order.return_value = {
            "order_id": "planned_order_1",
            "status": "submitted",
            "symbol": "AAPL"
        }
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="test_key",
            portfolio_state={"max_position": 1000}
        )
        
        assert len(result) > 0
        assert result[0]["status"] == "submitted"
        
        # Verify strategy engine was called
        extensions.strategy_engine.generate_and_gate.assert_called_once_with(
            mock_signals, {"max_position": 1000}
        )
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_no_trades(self, extensions):
        """Test plan_and_submit when strategy engine returns no trades"""
        mock_signals = []  # No signals
        
        # Mock strategy engine and bind to extensions
        extensions.strategy_engine = AsyncMock()
        extensions.strategy_engine.generate_and_gate.return_value = []  # No plans
        
        # Mock submit_symbol_order method
        extensions.submit_symbol_order = AsyncMock()
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="test_key"
        )
        
        assert result == []
        
        # Order service should not be called
        extensions.submit_symbol_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_multiple_trades(self, extensions):
        """Test plan_and_submit with multiple trades"""
        mock_signals = [
            Mock(symbol="AAPL", confidence=0.8),
            Mock(symbol="MSFT", confidence=0.7),
            Mock(symbol="GOOGL", confidence=0.9)
        ]
        
        # Mock strategy engine and bind to extensions
        extensions.strategy_engine = AsyncMock()
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(symbol="AAPL", side="buy", qty=100, risk_allowed=True, 
                 from_exposure=0, to_exposure=100, reason="Buy signal", notional=15000),
            Mock(symbol="MSFT", side="sell", qty=50, risk_allowed=True,
                 from_exposure=100, to_exposure=50, reason="Sell signal", notional=7500),
            Mock(symbol="GOOGL", side="buy", qty=25, risk_allowed=True,
                 from_exposure=0, to_exposure=25, reason="Strong buy", notional=12500)
        ]
        
        # Mock submit_symbol_order method
        extensions.submit_symbol_order = AsyncMock()
        extensions.submit_symbol_order.side_effect = [
            {"order_id": "order_1", "status": "submitted", "symbol": "AAPL"},
            {"order_id": "order_2", "status": "submitted", "symbol": "MSFT"},
            {"order_id": "order_3", "status": "submitted", "symbol": "GOOGL"}
        ]
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="multi_test"
        )
        
        assert len(result) == 3
        
        # All orders should be submitted
        for order in result:
            assert order["status"] == "submitted"
        
        # Order service should be called 3 times
        assert extensions.submit_symbol_order.call_count == 3
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_exception_handling(self, extensions):
        """Test plan_and_submit exception handling"""
        mock_signals = [Mock(symbol="AAPL")]
        
        # Mock strategy engine and bind to extensions - but make it raise an exception
        extensions.strategy_engine = AsyncMock()
        extensions.strategy_engine.generate_and_gate.side_effect = Exception("Strategy engine failed")
        
        # Should raise the exception from strategy engine
        with pytest.raises(Exception, match="Strategy engine failed"):
            await extensions.plan_and_submit(
                signals=mock_signals,
                idempotency_key="error_test"
            )


class TestModuleLevelFunctionsPhase7B3:
    """Test module-level functions"""
    
    @pytest.mark.asyncio
    async def test_submit_order_function(self):
        """Test module-level submit_order function"""
        # Test that the function raises NotImplementedError as expected
        order_data = {"symbol": "AAPL", "side": "buy", "qty": 100}
        
        with pytest.raises(NotImplementedError, match="submit_order is a test patch point"):
            await submit_order(order_data)


class TestThreadSafetyPhase7B3:
    """Test thread safety mechanisms"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_thread_safe_order_submission(self, service):
        """Test thread-safe order submission"""
        import threading
        
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_id": "thread_safe_order"
        }
        
        results = []
        
        def submit_order_thread():
            result = service.submit_order(order_data)
            results.append(result)
        
        # Submit the same order from multiple threads
        threads = [threading.Thread(target=submit_order_thread) for _ in range(3)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All results should be the same due to idempotency
        assert len(results) == 3
        assert all(result == results[0] for result in results)
        assert results[0]["order_id"] == "thread_safe_order"
    
    def test_thread_safe_order_modification(self, service):
        """Test thread-safe order modification"""
        import threading
        
        modification_data = {
            "order_id": "thread_safe_mod_order",
            "modification_id": "thread_safe_mod"
        }
        
        results = []
        
        def modify_order_thread():
            result = service.modify_order(modification_data)
            results.append(result)
        
        # Modify the same order from multiple threads
        threads = [threading.Thread(target=modify_order_thread) for _ in range(3)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All results should be the same due to idempotency
        assert len(results) == 3
        assert all(result == results[0] for result in results)
        assert results[0]["order_id"] == "thread_safe_mod_order"
    
    def test_thread_safe_order_cancellation(self, service):
        """Test thread-safe order cancellation"""
        import threading
        
        order_id = "thread_safe_cancel_order"
        results = []
        
        def cancel_order_thread():
            result = service.cancel_order(order_id)
            results.append(result)
        
        # Cancel the same order from multiple threads
        threads = [threading.Thread(target=cancel_order_thread) for _ in range(3)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # First should be cancelled, others should be already_cancelled
        assert len(results) == 3
        cancelled_count = sum(1 for result in results if result["status"] == "cancelled")
        already_cancelled_count = sum(1 for result in results if result["status"] == "already_cancelled")
        
        assert cancelled_count == 1
        assert already_cancelled_count == 2


class TestEdgeCasesAndErrorHandlingPhase7B3:
    """Test edge cases and comprehensive error handling"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_submit_order_with_none_values(self, service):
        """Test order submission with None values"""
        order_data = {
            "symbol": None,
            "side": None,
            "qty": None,
            "order_id": "none_values_order"
        }
        
        result = service.submit_order(order_data)
        
        # Should be rejected due to None values
        assert result["status"] == "rejected"
        assert "Invalid order parameters" in result["reason"]
    
    def test_submit_order_empty_dict(self, service):
        """Test order submission with empty dictionary"""
        result = service.submit_order({})
        
        # Should use defaults and be rejected due to qty=0
        assert result["status"] == "rejected"
        assert result["symbol"] == "UNKNOWN"
        assert result["qty"] == 0
    
    def test_validate_order_stress_test(self, service):
        """Test order validation with stress scenarios"""
        # Very large order dictionary
        large_order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            # Add many extra fields
            **{f"extra_field_{i}": f"value_{i}" for i in range(100)}
        }
        
        result = service.validate_order(large_order)
        assert result["valid"] is True  # Should handle extra fields gracefully
        
        # Order with unicode characters
        unicode_order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "note": "测试订单"  # Chinese characters
        }
        
        result = service.validate_order(unicode_order)
        assert result["valid"] is True  # Should handle unicode gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
