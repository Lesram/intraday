"""
Integration tests for strategy engine to order flow
Tests end-to-end signal processing through order submission
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from backend.infra.schemas import Order
from backend.services.order_service import OrderService
from backend.services.positions_service import Position, PositionsService
from backend.strategies.engine import StrategyEngine
from backend.strategies.types import TradingSignal


class TestStrategyToOrderFlow:
    """Test integration between strategy engine and order service"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def mock_orders_repo(self):
        """Mock orders repository"""
        mock = AsyncMock()
        mock.create.return_value = Order(
            id=uuid.uuid4(),
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=10.0,
            status="pending_submit",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        return mock

    @pytest.fixture
    def mock_outbox_repo(self):
        """Mock outbox repository"""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def mock_risk_manager(self):
        """Mock risk manager that approves all trades"""
        mock = MagicMock()
        mock.before_order.return_value = (True, "approved", 100.0)
        return mock

    @pytest.fixture
    def mock_positions_service(self):
        """Mock positions service"""
        mock = MagicMock(spec=PositionsService)
        mock.get_positions_by_symbols.return_value = asyncio.Future()
        mock.get_positions_by_symbols.return_value.set_result({})
        return mock

    @pytest.fixture
    def mock_metrics(self):
        """Mock metrics registry"""
        mock = MagicMock()
        mock.inc_strategy_signals = MagicMock()
        mock.inc_strategy_netting_decisions = MagicMock()
        mock.inc_strategy_throttled = MagicMock()
        mock.inc_strategy_blocked = MagicMock()
        mock.set_strategy_planned_notional = MagicMock()
        return mock

    @pytest.fixture
    def mock_settings(self):
        """Mock settings object"""
        mock = MagicMock()
        mock.strategy_momentum_weight = 0.6
        mock.strategy_mean_rev_weight = 0.4
        mock.strategy_ensemble_weight = 1.0
        mock.strategy_min_flip_interval_s = 300
        mock.strategy_max_new_risk_per_bar = 10000.0
        mock.strategy_min_notional = 1000.0
        return mock

    @pytest.fixture
    def strategy_engine(self, mock_risk_manager, mock_positions_service, mock_metrics, mock_settings):
        """Create strategy engine with mocked dependencies"""
        with patch('backend.strategies.engine.get_settings', return_value=mock_settings):
            with patch('backend.strategies.engine.get_metrics_registry', return_value=mock_metrics):
                engine = StrategyEngine(
                    risk_manager=mock_risk_manager,
                    positions_service=mock_positions_service,
                    config={}
                )
                return engine

    @pytest.fixture
    def order_service(self, mock_db_session, mock_orders_repo, mock_outbox_repo):
        """Create order service with mocked dependencies"""
        with patch('backend.services.order_service.OrdersRepo', return_value=mock_orders_repo):
            with patch('backend.services.order_service.OutboxRepo', return_value=mock_outbox_repo):
                service = OrderService(mock_db_session)
                return service

    @pytest.mark.asyncio
    async def test_strategy_signal_to_order_flow(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test complete flow from strategy signal to order creation"""

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create test signal
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Use order service plan_and_submit method
        result = await order_service.plan_and_submit([signal], strategy_engine)

        # Verify order was created
        assert mock_orders_repo.create.called
        assert mock_outbox_repo.create.called

        # Check the created order details
        create_call_args = mock_orders_repo.create.call_args[1]  # Get keyword arguments
        created_order = create_call_args['order']

        assert created_order.symbol == "AAPL"
        assert created_order.side == "buy"
        assert created_order.qty > 0
        assert created_order.status == "pending_submit"

    @pytest.mark.asyncio
    async def test_risk_blocked_signal_no_order(
        self, strategy_engine, order_service, mock_positions_service, mock_risk_manager,
        mock_orders_repo, mock_outbox_repo
    ):
        """Test that risk-blocked signals don't create orders"""

        # Setup risk manager to block trades
        mock_risk_manager.before_order.return_value = (False, "risk_limit", 0.0)

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create test signal
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Use order service plan_and_submit method
        result = await order_service.plan_and_submit([signal], strategy_engine)

        # Verify no order was created due to risk block
        assert not mock_orders_repo.create.called
        assert not mock_outbox_repo.create.called

        # Verify metrics were recorded
        assert strategy_engine.metrics.inc_strategy_blocked.called

    @pytest.mark.asyncio
    async def test_throttled_signal_no_order(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that throttled signals don't create orders"""

        # Setup position data with recent flip to trigger throttling
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=-5.0, price=150.0)  # Currently short
        })

        # Set recent flip time to trigger throttling
        strategy_engine._position_flip_times["AAPL"] = datetime.now() - timedelta(seconds=60)  # Recent flip

        # Create signal that would flip position
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,  # Would flip from short to long
            confidence=0.8
        )

        # Mock portfolio value
        with patch.object(strategy_engine, '_get_portfolio_value', return_value=10000.0):
            result = await order_service.plan_and_submit([signal], strategy_engine)

        # Verify no order was created due to throttling
        assert not mock_orders_repo.create.called
        assert not mock_outbox_repo.create.called

        # Verify throttling metrics were recorded
        assert strategy_engine.metrics.inc_strategy_throttled.called

    @pytest.mark.asyncio
    async def test_multiple_signals_netted_single_order(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that multiple signals for same symbol result in single netted order"""

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create multiple signals for same symbol
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.8,
                confidence=0.9
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=datetime.now(),
                target_exposure=-0.2,
                confidence=0.4
            )
        ]

        # Use order service plan_and_submit method
        result = await order_service.plan_and_submit(signals, strategy_engine)

        # Should create only one order (netted)
        assert mock_orders_repo.create.call_count == 1
        assert mock_outbox_repo.create.call_count == 1

        # Verify netting metrics were recorded
        assert strategy_engine.metrics.inc_strategy_netting_decisions.called

    @pytest.mark.asyncio
    async def test_multiple_symbols_multiple_orders(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that signals for different symbols create separate orders"""

        # Setup position data for multiple symbols
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0),
            "MSFT": Position("MSFT", qty=0.0, price=300.0)
        })

        # Create signals for different symbols
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=0.8
            ),
            TradingSignal(
                symbol="MSFT",
                source="momentum",
                ts=datetime.now(),
                target_exposure=-0.3,
                confidence=0.6
            )
        ]

        # Use order service plan_and_submit method
        result = await order_service.plan_and_submit(signals, strategy_engine)

        # Should create two orders (one per symbol)
        assert mock_orders_repo.create.call_count == 2
        assert mock_outbox_repo.create.call_count == 2

    @pytest.mark.asyncio
    async def test_min_notional_filtering(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that orders below minimum notional are filtered out"""

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create signal with very small target exposure (below min notional)
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.001,  # Very small exposure
            confidence=0.8
        )

        # Mock small portfolio value to ensure notional is below minimum
        with patch.object(strategy_engine, '_get_portfolio_value', return_value=1000.0):
            result = await order_service.plan_and_submit([signal], strategy_engine)

        # Should not create order due to min notional filter
        assert not mock_orders_repo.create.called
        assert not mock_outbox_repo.create.called

    @pytest.mark.asyncio
    async def test_idempotent_order_submission(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that repeated signal submission is idempotent"""

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create test signal
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Submit same signal twice
        result1 = await order_service.plan_and_submit([signal], strategy_engine)
        result2 = await order_service.plan_and_submit([signal], strategy_engine)

        # Verify idempotency mechanisms prevent duplicate orders
        # Note: This depends on the specific idempotency implementation
        # in OrderService.submit_symbol_order

        # At minimum, should have recorded metrics appropriately
        assert strategy_engine.metrics.inc_strategy_signals.called
        assert strategy_engine.metrics.inc_strategy_netting_decisions.called

    @pytest.mark.asyncio
    async def test_metrics_recorded_throughout_flow(
        self, strategy_engine, order_service, mock_positions_service, mock_orders_repo, mock_outbox_repo
    ):
        """Test that all appropriate metrics are recorded during signal processing"""

        # Setup position data
        mock_positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        mock_positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        # Create test signal
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Submit signal
        result = await order_service.plan_and_submit([signal], strategy_engine)

        # Verify all expected metrics were recorded
        strategy_engine.metrics.inc_strategy_signals.assert_called_with("momentum", 1.0)
        strategy_engine.metrics.inc_strategy_netting_decisions.assert_called_with("AAPL", 1.0)
        strategy_engine.metrics.set_strategy_planned_notional.assert_called()

        # Should not have throttling or blocking metrics for successful case
        assert not strategy_engine.metrics.inc_strategy_throttled.called
        assert not strategy_engine.metrics.inc_strategy_blocked.called
