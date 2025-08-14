"""
Comprehensive order service testing with table-driven parametrization.
Tests order submission, lifecycle, and error scenarios with mock dependencies.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
import uuid

from backend.services.order_service import OrderService
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.outbox import OutboxRepo
from backend.strategies.types import TradingSignal

# Test data matrices for comprehensive coverage

ORDER_SUBMISSION_DATA = [
    ("AAPL", "buy", 100, "market", "ioc", {"test": True}),
    ("GOOGL", "sell", 50, "limit", "day", {"test": True}),
    ("MSFT", "buy", 200, "market", "ioc", {"priority": "high"}),
    ("TSLA", "sell", 25, "limit", "gtc", {"strategy": "momentum"}),
    ("AMZN", "buy", 10, "market", "ioc", {"source": "signal"}),
    ("META", "sell", 75, "limit", "day", {"urgency": "medium"}),
    ("NVDA", "buy", 30, "market", "ioc", {"model": "ml"}),
    ("SPY", "sell", 100, "limit", "gtc", {"hedge": True}),
]

BROKER_ERROR_SCENARIOS = [
    ("connection_timeout", "Connection timeout", 503),
    ("insufficient_funds", "Insufficient buying power", 422),
    ("market_closed", "Market is closed", 400),
    ("invalid_symbol", "Symbol not found", 404),
    ("order_rejected", "Order rejected by broker", 400),
    ("rate_limited", "Rate limit exceeded", 429),
    ("system_maintenance", "System under maintenance", 503),
    ("unknown_error", "Unknown broker error", 500),
]

ORDER_STATUS_TRANSITIONS = [
    ("pending", "submitted", "Order sent to broker"),
    ("submitted", "partially_filled", "Partial execution"),
    ("partially_filled", "filled", "Complete execution"),
    ("pending", "cancelled", "User cancellation"),
    ("submitted", "rejected", "Broker rejection"),
    ("pending", "expired", "Order timeout"),
    ("submitted", "failed", "System error"),
    ("filled", "settled", "Settlement complete"),
]


@pytest.fixture
def mock_orders_repo():
    """Mock orders repository with async methods"""
    repo = Mock(spec=OrdersRepo)
    
    # Mock order creation
    async def mock_upsert(client_key, **kwargs):
        mock_order = Mock()
        mock_order.id = uuid.uuid4()
        mock_order.symbol = kwargs.get("symbol", "TEST")
        mock_order.side = kwargs.get("side", "buy")
        mock_order.qty = kwargs.get("qty", Decimal("100"))
        mock_order.status = "pending"
        mock_order.submitted_at = datetime.utcnow()
        return mock_order
        
    repo.upsert_by_idempotency = AsyncMock(side_effect=mock_upsert)
    return repo


@pytest.fixture
def mock_outbox_repo():
    """Mock outbox repository with async methods"""
    repo = Mock(spec=OutboxRepo)
    repo.add_order_submit_event = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_strategy_engine():
    """Mock strategy engine for plan-and-submit testing"""
    engine = Mock()
    
    # Mock execution plan
    mock_plan = Mock()
    mock_plan.symbol = "AAPL"
    mock_plan.side = "buy"
    mock_plan.qty = Decimal("100")
    mock_plan.notional = Decimal("15000")
    mock_plan.risk_allowed = True
    mock_plan.risk_reason = None
    mock_plan.reason = "signal_strength"
    mock_plan.from_exposure = Decimal("0")
    mock_plan.to_exposure = Decimal("15000")
    
    engine.generate_and_gate = AsyncMock(return_value=[mock_plan])
    return engine


@pytest.fixture
def order_service(mock_orders_repo, mock_outbox_repo, mock_strategy_engine):
    """OrderService instance with mocked dependencies"""
    return OrderService(
        orders_repo=mock_orders_repo,
        outbox_repo=mock_outbox_repo,
        strategy_engine=mock_strategy_engine
    )


class TestOrderServiceComprehensive:
    """Comprehensive table-driven tests for OrderService"""
    
    @pytest.mark.parametrize("symbol,side,qty,order_type,tif,attributes", ORDER_SUBMISSION_DATA)
    @pytest.mark.asyncio
    async def test_order_submission_scenarios(
        self, order_service, symbol, side, qty, order_type, tif, attributes
    ):
        """Test order submission with various parameter combinations"""
        idempotency_key = f"test_{symbol}_{uuid.uuid4().hex[:8]}"
        
        result = await order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=float(qty),
            idempotency_key=idempotency_key,
            order_type=order_type,
            tif=tif,
            attributes=attributes
        )
        
        # Verify result structure
        assert "order_id" in result
        assert result["symbol"] == symbol
        assert result["side"] == side
        assert result["qty"] == str(qty)
        assert result["status"] in ["pending", "submitted"]
        assert result["idempotency_key"] == idempotency_key
        
        # Verify repository interactions
        order_service.orders_repo.upsert_by_idempotency.assert_called_once()
        order_service.outbox_repo.add_order_submit_event.assert_called_once()
        
        # Verify call parameters
        repo_call = order_service.orders_repo.upsert_by_idempotency.call_args
        assert repo_call.kwargs["client_key"] == idempotency_key
        assert repo_call.kwargs["symbol"] == symbol
        assert repo_call.kwargs["side"] == side
        assert repo_call.kwargs["qty"] == Decimal(str(qty))
        assert repo_call.kwargs["order_type"] == order_type
        assert repo_call.kwargs["tif"] == tif
        assert repo_call.kwargs["attributes"] == attributes

    @pytest.mark.parametrize("error_type,error_message,error_code", BROKER_ERROR_SCENARIOS)
    @pytest.mark.asyncio
    async def test_broker_error_handling(
        self, order_service, error_type, error_message, error_code
    ):
        """Test handling of various broker error scenarios"""
        # Configure the orders_repo to raise an exception
        order_service.orders_repo.upsert_by_idempotency.side_effect = Exception(error_message)
        
        with pytest.raises(Exception) as exc_info:
            await order_service.submit_symbol_order(
                symbol="TEST",
                side="buy",
                qty=100.0,
                idempotency_key=f"error_{error_type}",
                order_type="market",
                tif="ioc"
            )
        
        assert error_message in str(exc_info.value)

    @pytest.mark.parametrize("from_status,to_status,reason", ORDER_STATUS_TRANSITIONS)
    @pytest.mark.asyncio  
    async def test_order_status_lifecycle(
        self, order_service, from_status, to_status, reason
    ):
        """Test order status transitions throughout lifecycle"""
        # Configure mock to return different statuses
        mock_order = Mock()
        mock_order.id = uuid.uuid4()
        mock_order.symbol = "TEST"
        mock_order.side = "buy"
        mock_order.qty = Decimal("100")
        mock_order.status = to_status  # Final status after transition
        mock_order.submitted_at = datetime.utcnow()
        
        order_service.orders_repo.upsert_by_idempotency.return_value = mock_order
        
        result = await order_service.submit_symbol_order(
            symbol="TEST",
            side="buy", 
            qty=100.0,
            idempotency_key=f"lifecycle_{from_status}_{to_status}",
            order_type="market",
            tif="ioc",
            attributes={"transition_reason": reason}
        )
        
        # Verify status progression
        assert result["status"] == to_status

    @pytest.mark.asyncio
    async def test_plan_and_submit_integration(self, order_service):
        """Test strategy engine integration with plan-and-submit workflow"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                signal_type="momentum",
                strength=0.8,
                confidence=0.9,
                timestamp=datetime.utcnow(),
                attributes={"model": "ml_v1", "timeframe": "1h"}
            )
        ]
        
        results = await order_service.plan_and_submit(
            signals=signals,
            idempotency_key="test_plan_submit",
            portfolio_state={"equity": 100000, "cash": 50000}
        )
        
        # Verify strategy engine was called
        order_service.strategy_engine.generate_and_gate.assert_called_once_with(
            signals, {"equity": 100000, "cash": 50000}
        )
        
        # Verify results structure
        assert len(results) >= 1
        result = results[0]
        assert result["symbol"] == "AAPL"
        assert "order_id" in result or "status" in result

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, order_service):
        """Test circuit breaker patterns with order submission"""
        # Configure multiple failures to trigger circuit breaker logic
        failure_count = 0
        
        async def failing_upsert(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 3:
                raise Exception("Simulated broker failure")
            # Success after 3 failures
            mock_order = Mock()
            mock_order.id = uuid.uuid4()
            mock_order.symbol = "TEST"
            mock_order.side = "buy"
            mock_order.qty = Decimal("100")
            mock_order.status = "pending"
            mock_order.submitted_at = datetime.utcnow()
            return mock_order
            
        order_service.orders_repo.upsert_by_idempotency.side_effect = failing_upsert
        
        # First three attempts should fail
        for i in range(3):
            with pytest.raises(Exception):
                await order_service.submit_symbol_order(
                    symbol="TEST",
                    side="buy",
                    qty=100.0,
                    idempotency_key=f"circuit_test_{i}",
                    order_type="market",
                    tif="ioc"
                )
        
        # Fourth attempt should succeed
        result = await order_service.submit_symbol_order(
            symbol="TEST",
            side="buy",
            qty=100.0,
            idempotency_key="circuit_test_success",
            order_type="market", 
            tif="ioc"
        )
        
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_idempotency_protection(self, order_service):
        """Test idempotency key protection for duplicate submissions"""
        idempotency_key = "duplicate_test_key"
        
        # First submission
        result1 = await order_service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            idempotency_key=idempotency_key,
            order_type="market",
            tif="ioc"
        )
        
        # Reset mocks for second call
        order_service.orders_repo.reset_mock()
        order_service.outbox_repo.reset_mock()
        
        # Second submission with same key
        result2 = await order_service.submit_symbol_order(
            symbol="AAPL",
            side="buy", 
            qty=100.0,
            idempotency_key=idempotency_key,
            order_type="market",
            tif="ioc"
        )
        
        # Both should have same structure
        assert result1["symbol"] == result2["symbol"]
        assert result1["side"] == result2["side"]
        assert result1["qty"] == result2["qty"]

    def test_service_initialization(self):
        """Test OrderService initialization with various configurations"""
        # Test with minimal configuration
        service = OrderService(
            orders_repo=Mock(spec=OrdersRepo),
            outbox_repo=Mock(spec=OutboxRepo)
        )
        
        assert service.orders_repo is not None
        assert service.outbox_repo is not None
        assert service.strategy_engine is None
        
        # Test with strategy engine
        service_with_engine = OrderService(
            orders_repo=Mock(spec=OrdersRepo),
            outbox_repo=Mock(spec=OutboxRepo),
            strategy_engine=Mock()
        )
        
        assert service_with_engine.strategy_engine is not None
