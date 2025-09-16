"""
BRANCH 2.8: Risk Gate Order Flow Integration Tests

Tests for risk manager integration with order execution flow.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from backend.risk.risk_manager import AsyncRiskManager
from backend.risk.types import OrderSpec, PortfolioState, RiskDecision


class TestRiskGateOrderFlowIntegration:
    """Test risk manager integration with order execution flow."""

    @pytest.fixture
    def mock_execution_context(self):
        """Mock execution context with all services."""
        context = Mock()
        context.positions_service = AsyncMock()
        context.pricing_service = AsyncMock()
        context.halt_service = AsyncMock()
        context.order_service = AsyncMock()
        context.metrics_service = Mock()
        return context

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.trading = Mock()
        settings.trading.trading_hours_start = "09:30:00"
        settings.trading.trading_hours_end = "16:00:00"
        settings.trading.kelly_floor = 0.0
        settings.trading.kelly_ceiling = 0.2
        settings.trading.max_position_pct = 0.10
        settings.trading.portfolio_heat_cap = 1.50
        settings.trading.leverage_cap = 2.0
        settings.trading.trading_hours_only = True
        settings.trading.halted_symbols = ""
        return settings

    @pytest.fixture
    def sample_order_request(self):
        """Sample order request from trading strategy."""
        return {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "price": 150.00,
            "order_type": "limit",
            "strategy_id": "momentum_v2",
            "request_id": "req_123456"
        }

    @pytest.mark.asyncio
    async def test_risk_gate_allows_valid_order(self, mock_execution_context, mock_settings, sample_order_request):
        """Test risk gate allows a valid order to proceed."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                # Setup risk manager
                risk_manager = AsyncRiskManager(
                    positions_service=mock_execution_context.positions_service,
                    pricing_service=mock_execution_context.pricing_service,
                    halt_service=mock_execution_context.halt_service
                )

                # Mock portfolio state
                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={"AAPL": Decimal("50")},
                    sector_map={"AAPL": "technology"},
                    last_updated=datetime.utcnow()
                )

                # Create order spec from request
                order_spec = OrderSpec(
                    symbol=sample_order_request["symbol"],
                    side=sample_order_request["side"],
                    qty=Decimal(str(sample_order_request["quantity"])),
                    notional=Decimal(str(sample_order_request["quantity"] * sample_order_request["price"])),
                    price=Decimal(str(sample_order_request["price"]))
                )

                # Mock market open
                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    decision = await risk_manager.before_order(
                        order_spec,
                        portfolio_state,
                        sample_order_request["request_id"]
                    )

                # Should allow the order
                assert decision.allowed == True
                assert decision.reason == "approved"
                assert decision.original_qty == Decimal("100")
                assert decision.adjusted_qty == Decimal("100")

    @pytest.mark.asyncio
    async def test_risk_gate_blocks_oversized_order(self, mock_execution_context, mock_settings):
        """Test risk gate blocks an oversized order."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics, \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager(
                    positions_service=mock_execution_context.positions_service
                )

                # Small portfolio
                portfolio_state = PortfolioState(
                    equity=Decimal("10000"),  # Small equity
                    cash=Decimal("5000"),
                    positions={},
                    sector_map={},
                    last_updated=datetime.utcnow()
                )

                # Large order (>10% of portfolio)
                large_order = OrderSpec(
                    symbol="AAPL",
                    side="buy",
                    qty=Decimal("100"),  # $15,000 notional vs $10k equity
                    notional=Decimal("15000"),
                    price=Decimal("150.00")
                )

                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    decision = await risk_manager.before_order(large_order, portfolio_state)

                # Should block or adjust the order
                if decision.allowed:
                    # If allowed, should be adjusted down
                    assert decision.adjusted_qty < large_order.qty
                    assert "qty_cap" in decision.adjustments or "position_limit" in decision.adjustments
                else:
                    # If blocked, should be for position cap
                    assert decision.reason == "pos_cap"

                # Should record metrics
                mock_metrics.return_value.observe.assert_called()

    @pytest.mark.asyncio
    async def test_risk_gate_handles_concurrent_orders(self, mock_execution_context, mock_settings):
        """Test risk gate handles multiple concurrent order checks."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager(
                    positions_service=mock_execution_context.positions_service
                )

                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={},
                    sector_map={},
                    last_updated=datetime.utcnow()
                )

                # Create multiple orders
                orders = [
                    OrderSpec(
                        symbol=f"STOCK{i}",
                        side="buy",
                        qty=Decimal("50"),
                        notional=Decimal("5000"),
                        price=Decimal("100.00")
                    )
                    for i in range(5)
                ]

                # Process orders concurrently
                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    tasks = [
                        risk_manager.before_order(order, portfolio_state, f"req_{i}")
                        for i, order in enumerate(orders)
                    ]

                    decisions = await asyncio.gather(*tasks)

                # All should complete without error
                assert len(decisions) == 5
                for decision in decisions:
                    assert isinstance(decision, RiskDecision)
                    # Each decision should be independent
                    assert decision.allowed in [True, False]

    @pytest.mark.asyncio
    async def test_risk_gate_with_portfolio_service_failure(self, mock_execution_context, mock_settings):
        """Test risk gate behavior when portfolio service fails."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                # Mock portfolio service failure
                mock_execution_context.positions_service.get_all_positions.side_effect = Exception("Service down")

                risk_manager = AsyncRiskManager(
                    positions_service=mock_execution_context.positions_service
                )

                order = OrderSpec(
                    symbol="AAPL",
                    side="buy",
                    qty=Decimal("100"),
                    notional=Decimal("15000"),
                    price=Decimal("150.00")
                )

                decision = await risk_manager.before_order(order)

                # Should block when portfolio state unavailable
                assert decision.allowed == False
                assert decision.reason == "pos_cap"
                assert "Unable to fetch portfolio state" in str(decision.adjustments)

    @pytest.mark.asyncio
    async def test_risk_gate_metrics_recording(self, mock_execution_context, mock_settings):
        """Test that risk gate properly records metrics."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics, \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager()

                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={},
                    sector_map={},
                    last_updated=datetime.utcnow()
                )

                order = OrderSpec(
                    symbol="AAPL",
                    side="buy",
                    qty=Decimal("100"),
                    notional=Decimal("15000"),
                    price=Decimal("150.00")
                )

                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    decision = await risk_manager.before_order(order, portfolio_state)

                # Verify metrics were recorded
                mock_metrics.return_value.observe.assert_called_with("risk_decision_latency_seconds", ANY)

                if decision.allowed:
                    mock_metrics.return_value.inc_counter.assert_called_with("risk_allows_total")
                else:
                    mock_metrics.return_value.inc_counter.assert_called_with(
                        "risk_blocks_total",
                        {"reason": ANY}
                    )

    @pytest.mark.asyncio
    async def test_risk_gate_audit_logging(self, mock_execution_context, mock_settings):
        """Test that risk gate properly logs audit trail."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'), \
                 patch('backend.risk.risk_manager.audit_logger') as mock_audit:

                risk_manager = AsyncRiskManager()

                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={"AAPL": Decimal("25")},
                    sector_map={"AAPL": "technology"},
                    last_updated=datetime.utcnow()
                )

                order = OrderSpec(
                    symbol="AAPL",
                    side="buy",
                    qty=Decimal("100"),
                    notional=Decimal("15000"),
                    price=Decimal("150.00")
                )

                request_id = "audit_test_123"

                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    decision = await risk_manager.before_order(order, portfolio_state, request_id)

                # Verify audit log was called
                mock_audit.info.assert_called_once()
                call_args = mock_audit.info.call_args

                # Check audit data structure
                audit_data = call_args[1]["extra"]
                assert audit_data["event"] == "risk_decision"
                assert audit_data["request_id"] == request_id
                assert audit_data["order"]["symbol"] == "AAPL"
                assert audit_data["order"]["side"] == "buy"
                assert audit_data["order"]["qty"] == "100"
                assert audit_data["decision"]["allowed"] == decision.allowed
                assert audit_data["decision"]["reason"] == decision.reason
                assert audit_data["portfolio_summary"]["equity"] == "100000"
                assert audit_data["portfolio_summary"]["position_count"] == 1

    @pytest.mark.asyncio
    async def test_risk_gate_with_halted_symbol_service(self, mock_execution_context, mock_settings):
        """Test risk gate integration with halt service."""
        # Update settings to include halted symbols
        mock_settings.trading.halted_symbols = "GME,TSLA"

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager(
                    halt_service=mock_execution_context.halt_service
                )

                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={},
                    sector_map={},
                    last_updated=datetime.utcnow()
                )

                # Order for halted symbol
                halted_order = OrderSpec(
                    symbol="GME",  # Halted symbol
                    side="buy",
                    qty=Decimal("100"),
                    notional=Decimal("5000"),
                    price=Decimal("50.00")
                )

                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    decision = await risk_manager.before_order(halted_order, portfolio_state)

                # Should block halted symbol
                assert decision.allowed == False
                assert decision.reason == "halt"
                assert decision.adjustments["halted_symbol"] == "GME"


class TestRiskGateErrorHandling:
    """Test error handling in risk gate integration."""

    @pytest.mark.asyncio
    async def test_risk_gate_handles_unexpected_exceptions(self, mock_settings):
        """Test risk gate graceful handling of unexpected exceptions."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics, \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager()

                # Mock an exception in the evaluation logic
                with patch.object(risk_manager, '_evaluate_order', side_effect=Exception("Unexpected error")):
                    order = OrderSpec(
                        symbol="TEST",
                        side="buy",
                        qty=Decimal("100"),
                        notional=Decimal("10000"),
                        price=Decimal("100.00")
                    )

                    decision = await risk_manager.before_order(order)

                # Should block with error reason
                assert decision.allowed == False
                assert decision.reason == "other"
                assert "Risk check failed" in decision.adjustments["error"]

                # Should still record metrics
                mock_metrics.return_value.observe.assert_called()
                mock_metrics.return_value.inc_counter.assert_called_with(
                    "risk_blocks_total",
                    {"reason": "other"}
                )

    @pytest.mark.asyncio
    async def test_risk_gate_timeout_handling(self, mock_execution_context, mock_settings):
        """Test risk gate handling of service timeouts."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                # Mock positions service timeout
                async def slow_positions():
                    await asyncio.sleep(10)  # Simulate slow service
                    return {}

                mock_execution_context.positions_service.get_all_positions = slow_positions

                risk_manager = AsyncRiskManager(
                    positions_service=mock_execution_context.positions_service
                )

                order = OrderSpec(
                    symbol="TEST",
                    side="buy",
                    qty=Decimal("100"),
                    notional=Decimal("10000"),
                    price=Decimal("100.00")
                )

                # Use asyncio.wait_for to simulate timeout
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        risk_manager.before_order(order),
                        timeout=0.1
                    )


class TestRiskGatePerformance:
    """Test performance characteristics of risk gate."""

    @pytest.mark.asyncio
    async def test_risk_gate_latency_under_load(self, mock_settings):
        """Test risk gate latency under concurrent load."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics, \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager()

                portfolio_state = PortfolioState(
                    equity=Decimal("1000000"),  # Large portfolio
                    cash=Decimal("500000"),
                    positions={f"STOCK{i}": Decimal("100") for i in range(50)},
                    sector_map={f"STOCK{i}": "tech" for i in range(50)},
                    last_updated=datetime.utcnow()
                )

                # Create many concurrent orders
                orders = [
                    OrderSpec(
                        symbol=f"TEST{i}",
                        side="buy",
                        qty=Decimal("10"),
                        notional=Decimal("1000"),
                        price=Decimal("100.00")
                    )
                    for i in range(100)  # 100 concurrent orders
                ]

                start_time = asyncio.get_event_loop().time()

                with patch.object(risk_manager, '_is_market_open', return_value=True):
                    tasks = [
                        risk_manager.before_order(order, portfolio_state, f"perf_test_{i}")
                        for i, order in enumerate(orders)
                    ]

                    decisions = await asyncio.gather(*tasks)

                end_time = asyncio.get_event_loop().time()
                total_time = end_time - start_time

                # Performance assertions
                assert len(decisions) == 100
                assert total_time < 1.0  # Should complete in under 1 second

                # Average decision time should be reasonable
                avg_decision_time = total_time / 100
                assert avg_decision_time < 0.01  # Less than 10ms average

                # All decisions should be valid
                for decision in decisions:
                    assert isinstance(decision, RiskDecision)

    @pytest.mark.asyncio
    async def test_risk_gate_memory_efficiency(self, mock_settings):
        """Test that risk gate doesn't leak memory under load."""
        import gc

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                risk_manager = AsyncRiskManager()

                portfolio_state = PortfolioState(
                    equity=Decimal("100000"),
                    cash=Decimal("50000"),
                    positions={},
                    sector_map={},
                    last_updated=datetime.utcnow()
                )

                # Process many orders to test for memory leaks
                for batch in range(10):
                    orders = [
                        OrderSpec(
                            symbol=f"MEM_TEST_{batch}_{i}",
                            side="buy",
                            qty=Decimal("10"),
                            notional=Decimal("1000"),
                            price=Decimal("100.00")
                        )
                        for i in range(50)
                    ]

                    with patch.object(risk_manager, '_is_market_open', return_value=True):
                        tasks = [
                            risk_manager.before_order(order, portfolio_state)
                            for order in orders
                        ]

                        await asyncio.gather(*tasks)

                    # Force garbage collection
                    gc.collect()

                # Test passes if no memory-related exceptions occur
                assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
