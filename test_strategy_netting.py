"""
Unit tests for strategy engine netting logic
Tests signal aggregation, weighted averaging, and deterministic behavior
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.services.positions_service import Position, PositionsService
from backend.strategies.engine import StrategyEngine
from backend.strategies.types import Side, TradingSignal


class TestStrategyNetting:
    """Test strategy signal netting functionality"""

    @pytest.fixture
    def mock_risk_manager(self):
        """Mock risk manager that approves all trades"""
        mock = MagicMock()
        mock.before_order.return_value = (True, "approved", 100.0)
        return mock

    @pytest.fixture
    def mock_positions_service(self):
        """Mock positions service with zero positions"""
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

    @pytest.mark.asyncio
    async def test_single_signal_netting(self, strategy_engine):
        """Test netting a single signal creates correct execution plan"""
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        plans = await strategy_engine.generate_and_gate([signal])

        assert len(plans) == 1
        plan = plans[0]
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY
        assert plan.from_exposure == 0.0
        assert plan.to_exposure == 0.5
        assert plan.risk_allowed is True
        assert plan.qty > 0  # Should be positive for buy

    @pytest.mark.asyncio
    async def test_multiple_signals_same_symbol_netting(self, strategy_engine):
        """Test netting multiple signals for same symbol uses weighted average"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.8,
                confidence=0.9  # High confidence
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=datetime.now(),
                target_exposure=-0.4,
                confidence=0.5  # Lower confidence
            )
        ]

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        plans = await strategy_engine.generate_and_gate(signals)

        assert len(plans) == 1
        plan = plans[0]

        # Expected weighted average: (0.8 * 0.9 + (-0.4) * 0.5) / (0.9 + 0.5) = 0.371
        expected_exposure = (0.8 * 0.9 + (-0.4) * 0.5) / (0.9 + 0.5)
        assert abs(plan.to_exposure - expected_exposure) < 0.01
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY  # Positive net exposure

    @pytest.mark.asyncio
    async def test_netting_with_strategy_weights(self, strategy_engine):
        """Test that strategy weights are properly applied"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=1.0,
                confidence=1.0
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=datetime.now(),
                target_exposure=-1.0,
                confidence=1.0
            )
        ]

        # Set specific weights
        strategy_engine.strategy_weights = {
            "momentum": 0.7,
            "mean_reversion": 0.3
        }

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        plans = await strategy_engine.generate_and_gate(signals)

        assert len(plans) == 1
        plan = plans[0]

        # Expected weighted average with strategy weights:
        # (1.0 * 1.0 * 0.7 + (-1.0) * 1.0 * 0.3) / (1.0 * 0.7 + 1.0 * 0.3) = 0.4
        expected_exposure = (1.0 * 1.0 * 0.7 + (-1.0) * 1.0 * 0.3) / (1.0 * 0.7 + 1.0 * 0.3)
        assert abs(plan.to_exposure - expected_exposure) < 0.01
        assert plan.side == Side.BUY

    @pytest.mark.asyncio
    async def test_exposure_clamping(self, strategy_engine):
        """Test that exposure is clamped to [-1, 1] range"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.9,
                confidence=1.0
            ),
            TradingSignal(
                symbol="AAPL",
                source="ensemble",
                ts=datetime.now(),
                target_exposure=0.8,
                confidence=1.0
            )
        ]

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        plans = await strategy_engine.generate_and_gate(signals)

        assert len(plans) == 1
        plan = plans[0]

        # Should be clamped to 1.0 even though weighted average would be higher
        assert plan.to_exposure == 1.0
        assert plan.side == Side.BUY

    @pytest.mark.asyncio
    async def test_zero_confidence_signals_ignored(self, strategy_engine):
        """Test that zero confidence signals are ignored in netting"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.8,
                confidence=0.0  # Zero confidence - should be ignored
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=datetime.now(),
                target_exposure=-0.5,
                confidence=0.7  # Only this should count
            )
        ]

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0)
        })

        plans = await strategy_engine.generate_and_gate(signals)

        assert len(plans) == 1
        plan = plans[0]

        # Should use only the mean_reversion signal
        assert plan.to_exposure == -0.5 * 0.4  # mean_reversion weight = 0.4
        assert plan.side == Side.SELL

    @pytest.mark.asyncio
    async def test_multiple_symbols_processed_separately(self, strategy_engine):
        """Test that signals for different symbols are processed independently"""
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

        # Mock position lookup
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=0.0, price=150.0),
            "MSFT": Position("MSFT", qty=0.0, price=300.0)
        })

        plans = await strategy_engine.generate_and_gate(signals)

        assert len(plans) == 2

        # Find plans by symbol
        aapl_plan = next(p for p in plans if p.symbol == "AAPL")
        msft_plan = next(p for p in plans if p.symbol == "MSFT")

        assert aapl_plan.to_exposure == 0.5 * 0.6  # momentum weight = 0.6
        assert aapl_plan.side == Side.BUY

        assert msft_plan.to_exposure == -0.3 * 0.6  # momentum weight = 0.6
        assert msft_plan.side == Side.SELL

    @pytest.mark.asyncio
    async def test_no_change_no_plan(self, strategy_engine):
        """Test that no execution plan is created if target equals current exposure"""
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )

        # Mock current position with exposure that matches target
        current_qty = 10.0  # At price 150, with 3000 portfolio value = 0.5 exposure
        strategy_engine.positions_service.get_positions_by_symbols.return_value = asyncio.Future()
        strategy_engine.positions_service.get_positions_by_symbols.return_value.set_result({
            "AAPL": Position("AAPL", qty=current_qty, price=150.0)
        })

        # Mock portfolio value calculation
        with patch.object(strategy_engine, '_get_portfolio_value', return_value=3000.0):
            plans = await strategy_engine.generate_and_gate([signal])

        # Should have no plans since current exposure matches target
        assert len(plans) == 0

    def test_deterministic_netting(self, strategy_engine):
        """Test that netting produces deterministic results for same inputs"""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.6,
                confidence=0.8
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=datetime.now(),
                target_exposure=-0.2,
                confidence=0.4
            )
        ]

        # Run netting multiple times
        result1 = strategy_engine._net_signals_by_symbol([signals[0], signals[1]])
        result2 = strategy_engine._net_signals_by_symbol([signals[1], signals[0]])  # Different order
        result3 = strategy_engine._net_signals_by_symbol([signals[0], signals[1]])

        # All should produce identical results regardless of input order
        assert result1 == result2 == result3
        assert abs(result1["AAPL"] - result2["AAPL"]) < 1e-10
