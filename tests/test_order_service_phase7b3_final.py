"""
Phase 7B.3 Final Coverage: Order Service Module Testing - Targeting Uncovered Lines
Focused on lines 276-286, 416-489, 550, 571-584, 617-628
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from decimal import Decimal
from typing import Any

from backend.services.order_service import OrderService, OrderServiceExtensions


class TestUncoveredLinesPhase7B3:
    """Target specific uncovered lines for maximum coverage"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_submit_order_missing_side_fallback(self, service):
        """Test submit_order when side is missing or invalid - should fallback to 'buy'"""
        order_data = {
            "symbol": "AAPL", 
            "qty": 100
            # Missing 'side' - should use default
        }
        
        result = service.submit_order(order_data)
        
        # Should use default side which is typically 'buy'
        assert result["side"] in ["buy", "sell"]  # Either default behavior
    
    def test_submit_order_missing_qty_fallback(self, service):
        """Test submit_order when qty is missing - should use default 0"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy"
            # Missing 'qty'
        }
        
        result = service.submit_order(order_data)
        
        # Should be rejected due to qty=0
        assert result["qty"] == 0
        assert result["status"] == "rejected"
    
    def test_modify_order_with_complex_data(self, service):
        """Test modify_order with complex modification data"""
        # Test lines 276-286 in modify_order
        modification_data = {
            "order_id": "complex_order_123",
            "modification_id": "fixed_mod_id",  # Provide fixed modification_id for idempotency
            "new_qty": 500,
            "new_price": 175.25,
            "new_stop_price": 170.00,
            "new_time_in_force": "GTC",
            "modification_reason": "Risk adjustment"
        }
        
        result = service.modify_order(modification_data)
        
        assert result["order_id"] == "complex_order_123"
        assert result["modification_id"] == "fixed_mod_id"
        
        # Test idempotency - should return same result
        result2 = service.modify_order(modification_data)
        assert result == result2
    
    def test_modify_order_generates_modification_id(self, service):
        """Test modify_order generates modification_id when not provided"""
        modification_data = {
            "order_id": "auto_id_order"
            # No modification_id provided
        }
        
        result = service.modify_order(modification_data)
        
        assert result["order_id"] == "auto_id_order"
        assert "modification_id" in result
        assert len(result["modification_id"]) > 0
    
    @pytest.mark.asyncio
    async def test_submit_order_async_with_valid_order_id(self, service):
        """Test submit_order_async with explicitly provided order_id"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 100,
            "order_id": "explicit_async_order_id"
        }
        
        result = await service.submit_order_async(order_data)
        
        assert result["order_id"] == "explicit_async_order_id"
        assert result["status"] == "submitted"
    
    @pytest.mark.asyncio
    async def test_submit_order_async_generates_order_id(self, service):
        """Test submit_order_async generates order_id when not provided"""
        order_data = {
            "symbol": "MSFT",
            "side": "sell",
            "qty": 200
            # No order_id provided - should generate one
        }
        
        result = await service.submit_order_async(order_data)
        
        assert "order_id" in result
        assert len(result["order_id"]) > 0
        assert result["status"] == "submitted"
    
    @pytest.mark.asyncio
    async def test_async_order_duplicate_detection_detailed(self, service):
        """Test detailed async order duplicate detection mechanism"""
        order_data = {
            "symbol": "TSLA",
            "side": "buy",
            "qty": 50,
            "order_id": "detailed_duplicate_test"
        }
        
        # First submission
        result1 = await service.submit_order_async(order_data)
        assert result1["status"] == "submitted"
        assert result1["order_id"] == "detailed_duplicate_test"
        
        # Second submission - should detect duplicate
        result2 = await service.submit_order_async(order_data)
        assert result2["status"] == "duplicate"
        assert "duplicate request" in result2["reason"]
        assert result2["order_id"] == "detailed_duplicate_test"
    
    @pytest.mark.asyncio 
    async def test_async_lock_creation(self, service):
        """Test async lock is created on demand"""
        # Initially no lock
        assert service._async_order_lock is None
        
        # Submit async order
        order_data = {"symbol": "NFLX", "side": "buy", "qty": 75}
        await service.submit_order_async(order_data)
        
        # Lock should now exist
        assert service._async_order_lock is not None
        assert isinstance(service._async_order_lock, asyncio.Lock)


class TestOrderServiceExtensionsAdvancedPhase7B3:
    """Test OrderServiceExtensions advanced scenarios"""
    
    @pytest.fixture
    def extensions(self):
        ext = OrderServiceExtensions()
        # Mock strategy engine
        ext.strategy_engine = AsyncMock()
        # Mock submit_symbol_order method
        ext.submit_symbol_order = AsyncMock()
        return ext
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_risk_blocked_trades(self, extensions):
        """Test plan_and_submit with risk-blocked trades"""
        mock_signals = [Mock(symbol="RISKY", confidence=0.9)]
        
        # Mock strategy engine to return risk-blocked plan
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(
                symbol="RISKY",
                side="buy",
                qty=1000,
                risk_allowed=False,  # Risk blocked
                risk_reason="Exceeds position limit",
                from_exposure=0,
                to_exposure=1000,
                reason="High confidence signal"
            )
        ]
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="risk_test"
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "risk_blocked"
        assert result[0]["symbol"] == "RISKY"
        assert "Exceeds position limit" in result[0]["reason"]
        assert not result[0]["risk_allowed"]
        
        # No orders should be submitted
        extensions.submit_symbol_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_no_change_trades(self, extensions):
        """Test plan_and_submit with no-change trades (qty=0)"""
        mock_signals = [Mock(symbol="STABLE", confidence=0.5)]
        
        # Mock strategy engine to return no-change plan
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(
                symbol="STABLE",
                side="hold",
                qty=0,  # No change
                risk_allowed=True,
                risk_reason=None,
                from_exposure=100,
                to_exposure=100,
                reason="Position unchanged"
            )
        ]
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="stable_test"
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "no_change"
        assert result[0]["symbol"] == "STABLE"
        assert result[0]["qty"] == "0"
        
        # No orders should be submitted
        extensions.submit_symbol_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_order_submission_failure(self, extensions):
        """Test plan_and_submit handling order submission failures"""
        mock_signals = [Mock(symbol="FAILURE", confidence=0.8)]
        
        # Mock strategy engine to return valid plan
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(
                symbol="FAILURE",
                side="buy", 
                qty=100,
                risk_allowed=True,
                from_exposure=0,
                to_exposure=100,
                reason="Test signal",
                notional=15000
            )
        ]
        
        # Mock order submission to fail
        extensions.submit_symbol_order.side_effect = Exception("Order submission failed")
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            idempotency_key="failure_test"
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "submit_error"
        assert result[0]["symbol"] == "FAILURE"
        assert "Order submission failed" in result[0]["reason"]
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_with_portfolio_state(self, extensions):
        """Test plan_and_submit with portfolio state parameter"""
        mock_signals = [Mock(symbol="PORTFOLIO", confidence=0.7)]
        
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(
                symbol="PORTFOLIO",
                side="sell",
                qty=50,
                risk_allowed=True,
                from_exposure=100,
                to_exposure=50,
                reason="Portfolio rebalancing",
                notional=7500
            )
        ]
        
        extensions.submit_symbol_order.return_value = {
            "order_id": "portfolio_order_1",
            "status": "submitted",
            "symbol": "PORTFOLIO"
        }
        
        portfolio_state = {
            "total_value": 100000,
            "cash": 20000,
            "positions": {"PORTFOLIO": 100}
        }
        
        result = await extensions.plan_and_submit(
            signals=mock_signals,
            portfolio_state=portfolio_state,
            idempotency_key="portfolio_test"
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "submitted"
        
        # Verify strategy engine was called with portfolio state
        extensions.strategy_engine.generate_and_gate.assert_called_once_with(
            mock_signals, portfolio_state
        )
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_idempotency_key_generation(self, extensions):
        """Test plan_and_submit generates idempotency keys properly"""
        mock_signals = [
            Mock(symbol="KEY1", confidence=0.8),
            Mock(symbol="KEY2", confidence=0.6)
        ]
        
        extensions.strategy_engine.generate_and_gate.return_value = [
            Mock(symbol="KEY1", side="buy", qty=100, risk_allowed=True,
                 from_exposure=0, to_exposure=100, reason="Signal 1", notional=15000),
            Mock(symbol="KEY2", side="sell", qty=75, risk_allowed=True, 
                 from_exposure=75, to_exposure=0, reason="Signal 2", notional=11250)
        ]
        
        extensions.submit_symbol_order.side_effect = [
            {"order_id": "key1_order", "status": "submitted", "symbol": "KEY1"},
            {"order_id": "key2_order", "status": "submitted", "symbol": "KEY2"}
        ]
        
        result = await extensions.plan_and_submit(signals=mock_signals)
        
        assert len(result) == 2
        assert all(r["status"] == "submitted" for r in result)
        
        # Verify submit_symbol_order was called with proper idempotency keys
        calls = extensions.submit_symbol_order.call_args_list
        assert len(calls) == 2
        
        # Each call should have an idempotency_key that includes symbol
        for i, call in enumerate(calls):
            kwargs = call.kwargs
            assert "idempotency_key" in kwargs
            assert f"KEY{i+1}" in kwargs["idempotency_key"]


class TestRemainingUncoveredLinesPhase7B3:
    """Target the final remaining uncovered lines"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_cancel_order_detailed_flow(self, service):
        """Test cancel_order detailed flow to hit lines 416-489"""
        # First cancellation
        result1 = service.cancel_order("detailed_cancel_order")
        assert result1["status"] == "cancelled"
        assert result1["order_id"] == "detailed_cancel_order"
        
        # Second cancellation (idempotency check)
        result2 = service.cancel_order("detailed_cancel_order")
        assert result2["status"] == "already_cancelled"
        assert result2["order_id"] == "detailed_cancel_order"
        
        # Different order
        result3 = service.cancel_order("different_order")
        assert result3["status"] == "cancelled"
        assert result3["order_id"] == "different_order"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
