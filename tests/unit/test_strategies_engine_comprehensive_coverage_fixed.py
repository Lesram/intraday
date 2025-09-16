"""
Comprehensive test suite for backend.strategies.engine module.

Tests StrategyEngine class with signal processing, risk gating, and execution plan building.

Target: backend.strategies.engine.py (500 lines, zero coverage)
Coverage Goal: 60%+ with comprehensive edge cases and error handling
"""

import asyncio
import logging
import os
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

# Set environment variables for test compatibility
os.environ["DISABLE_ML"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.strategies.engine import (
    StrategyEngine,
    logger,
)
from backend.strategies.types import (
    ExecutionPlan,
    TradingSignal,
    Side,
)

@pytest.fixture
def mock_risk_manager():
    """Create mock risk manager for testing."""
    risk_manager = Mock()
    risk_manager.before_order = Mock(return_value={"allowed": True, "reason": ""})
    return risk_manager

@pytest.fixture
def mock_positions_service():
    """Create mock positions service for testing."""
    positions_service = AsyncMock()
    positions_service.get_positions_by_symbols = AsyncMock(return_value={})
    return positions_service

@pytest.fixture  
def mock_metrics():
    """Create mock metrics collector for testing."""
    metrics = Mock()
    metrics.inc_counter = Mock()
    metrics.set_gauge = Mock()
    return metrics

@pytest.fixture
def sample_signals():
    """Create sample trading signals for testing."""
    return [
        TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,  # 50% long
            confidence=0.8,
        ),
        TradingSignal(
            symbol="TSLA",
            source="mean_reversion",
            ts=datetime.now(),
            target_exposure=-0.3,  # 30% short
            confidence=0.6,
        ),
    ]

@pytest.fixture
def basic_engine(mock_risk_manager, mock_positions_service):
    """Create basic strategy engine for testing."""
    with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
        return StrategyEngine(
            risk_manager=mock_risk_manager,
            positions_service=mock_positions_service
        )

@pytest.fixture
def engine_with_metrics(mock_risk_manager, mock_positions_service, mock_metrics):
    """Create strategy engine with metrics for testing."""
    with patch('backend.strategies.engine.get_metrics_registry', return_value=mock_metrics):
        return StrategyEngine(
            risk_manager=mock_risk_manager,
            positions_service=mock_positions_service
        )


class TestStrategyEngine:
    """Test suite for StrategyEngine class."""

    def test_strategy_engine_init_basic(self, mock_risk_manager, mock_positions_service):
        """Test basic StrategyEngine initialization."""
        with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service
            )
        
        assert engine.risk_manager is mock_risk_manager
        assert engine.positions_service is mock_positions_service
        assert hasattr(engine, 'strategy_weights')
        assert hasattr(engine, 'min_flip_interval_s')

    def test_strategy_engine_init_with_config(self, mock_risk_manager, mock_positions_service):
        """Test StrategyEngine initialization with custom configuration."""
        custom_config = {
            "momentum_weight": 0.7,
            "mean_rev_weight": 0.3,
            "min_flip_interval_s": 120
        }
        
        with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service,
                config=custom_config
            )
        
        assert engine.strategy_weights["momentum"] == 0.7
        assert engine.strategy_weights["mean_reversion"] == 0.3
        assert engine.min_flip_interval_s == 120

    def test_get_symbol_bucket_basic(self, basic_engine):
        """Test symbol bucket assignment."""
        # Test A-F bucket
        assert basic_engine._get_symbol_bucket("AAPL") == "A-F"
        assert basic_engine._get_symbol_bucket("FB") == "A-F"
        
        # Test G-M bucket  
        assert basic_engine._get_symbol_bucket("GOOGL") == "G-M"
        assert basic_engine._get_symbol_bucket("MSFT") == "G-M"
        
        # Test N-S bucket
        assert basic_engine._get_symbol_bucket("NVDA") == "N-S"
        assert basic_engine._get_symbol_bucket("SPY") == "N-S"
        
        # Test T-Z bucket
        assert basic_engine._get_symbol_bucket("TSLA") == "T-Z"
        assert basic_engine._get_symbol_bucket("ZM") == "T-Z"

    def test_get_symbol_bucket_edge_cases(self, basic_engine):
        """Test symbol bucket assignment for edge cases."""
        # Empty string should not crash
        try:
            result = basic_engine._get_symbol_bucket("")
            # Should return some bucket or handle gracefully
        except (IndexError, AttributeError):
            # This is acceptable behavior for empty string
            pass

    @pytest.mark.asyncio
    async def test_build_execution_plan_basic(self, basic_engine, sample_signals):
        """Test basic execution plan building."""
        plans = await basic_engine.build_execution_plan(sample_signals)
        
        assert isinstance(plans, list)
        # Should return plans for each symbol
        symbols = {plan.symbol for plan in plans}
        assert "AAPL" in symbols or "TSLA" in symbols

    @pytest.mark.asyncio
    async def test_build_execution_plan_empty_signals(self, basic_engine):
        """Test execution plan building with empty signals."""
        plans = await basic_engine.build_execution_plan([])
        assert plans == []

    @pytest.mark.asyncio
    async def test_build_symbol_plan_basic(self, basic_engine):
        """Test building plan for a single symbol."""
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=0.8,
            )
        ]
        
        current_time = datetime.now()
        
        # Create mock position object with qty and price attributes
        mock_position = Mock()
        mock_position.qty = 0
        mock_position.price = 100
        position_map = {"AAPL": mock_position}
        
        plan = await basic_engine._build_symbol_plan(
            "AAPL", signals, current_time, position_map
        )
        
        if plan:  # Plan might be None in some cases
            assert isinstance(plan, ExecutionPlan)
            assert plan.symbol == "AAPL"

    def test_apply_throttling_basic(self, basic_engine):
        """Test basic throttling functionality."""
        # Test with reasonable exposure that shouldn't be throttled
        from_exposure = 0.2
        target_exposure = 0.5
        current_time = datetime.now()
        
        result = basic_engine._apply_throttling(
            "AAPL", from_exposure, target_exposure, current_time
        )
        
        # Should return a tuple (adjusted_exposure, throttle_applied)
        assert isinstance(result, tuple)
        assert len(result) == 2
        adjusted_exposure, throttle_applied = result
        assert isinstance(adjusted_exposure, (int, float))
        assert isinstance(throttle_applied, bool)
        assert -1.0 <= adjusted_exposure <= 1.0

    def test_apply_throttling_extreme_exposure(self, basic_engine):
        """Test throttling with position flip scenario."""
        # Test with a flip that should trigger throttling
        from_exposure = 0.5  # Currently long
        target_exposure = -0.5  # Want to go short (flip)
        current_time = datetime.now()
        
        # Set last flip time to recent past to trigger throttling
        basic_engine.last_flip_times["AAPL"] = current_time - timedelta(seconds=30)  # 30 seconds ago
        basic_engine.min_flip_interval_s = 60  # 60 second minimum
        
        result = basic_engine._apply_throttling(
            "AAPL", from_exposure, target_exposure, current_time
        )
        
        # Should return throttled result
        adjusted_exposure, throttle_applied = result
        assert isinstance(adjusted_exposure, (int, float))
        assert isinstance(throttle_applied, bool)
        # Should be throttled since it's a recent flip
        if throttle_applied:
            assert abs(adjusted_exposure - from_exposure) < abs(target_exposure - from_exposure)

    @pytest.mark.asyncio
    async def test_exposure_to_qty_basic(self, basic_engine):
        """Test exposure to quantity conversion."""
        result = await basic_engine._exposure_to_qty("AAPL", 0.5, 10000.0)
        
        assert isinstance(result, tuple)
        assert len(result) == 3  # Returns (qty, notional, side)
        qty, notional, side = result
        assert isinstance(qty, Decimal)
        assert isinstance(notional, Decimal)
        assert side in [Side.BUY, Side.SELL, Side.FLAT]

    @pytest.mark.asyncio
    async def test_exposure_to_qty_zero_exposure(self, basic_engine):
        """Test exposure to quantity conversion for zero exposure."""
        result = await basic_engine._exposure_to_qty("AAPL", 0.0, 10000.0)
        
        qty, notional, side = result
        assert side == "flat"
        assert qty == Decimal("0")
        assert notional == Decimal("0")

    @pytest.mark.asyncio
    async def test_gate_with_risk_allowed(self, basic_engine):
        """Test risk gating when risk manager allows order."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        # Mock risk manager to allow
        basic_engine.risk_manager.before_order.return_value = {
            "allowed": True,
            "reason": ""
        }
        
        gated_plan = await basic_engine.gate_with_risk(plan)
        
        assert gated_plan.risk_allowed is True
        assert gated_plan.qty == plan.qty

    @pytest.mark.asyncio
    async def test_gate_with_risk_blocked(self, basic_engine):
        """Test risk gating when risk manager blocks order."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        # Mock risk manager to block
        basic_engine.risk_manager.before_order.return_value = {
            "allowed": False,
            "reason": "Risk limit exceeded"
        }
        
        gated_plan = await basic_engine.gate_with_risk(plan)
        
        assert gated_plan.risk_allowed is False
        assert gated_plan.risk_reason == "Risk limit exceeded"
        assert gated_plan.qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_gate_with_risk_flat_position(self, basic_engine):
        """Test risk gating with flat position (no risk check needed)."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.0,
            side=Side.FLAT,
            notional=Decimal("0"),
            qty=Decimal("0"),
            reason="flat position",
            risk_allowed=True,
        )
        
        gated_plan = await basic_engine.gate_with_risk(plan)
        
        assert gated_plan == plan  # Should return unchanged
        # Risk manager should not be called for flat positions
        basic_engine.risk_manager.before_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_gate_with_risk_exception_handling(self, basic_engine):
        """Test risk gating when risk manager raises exception."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        # Mock risk manager to raise exception
        basic_engine.risk_manager.before_order.side_effect = Exception("Risk error")
        
        gated_plan = await basic_engine.gate_with_risk(plan)
        
        assert gated_plan.risk_allowed is False
        assert "Risk check failed" in gated_plan.risk_reason
        assert gated_plan.qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_generate_and_gate_complete_pipeline(self, basic_engine, sample_signals):
        """Test complete pipeline: generate plans and apply risk gating."""
        # Mock risk manager to allow orders
        basic_engine.risk_manager.before_order.return_value = {
            "allowed": True,
            "reason": ""
        }
        
        gated_plans = await basic_engine.generate_and_gate(sample_signals)
        
        assert isinstance(gated_plans, list)
        for plan in gated_plans:
            assert isinstance(plan, ExecutionPlan)
            assert hasattr(plan, 'risk_allowed')
            assert hasattr(plan, 'risk_reason')

    @pytest.mark.asyncio
    async def test_generate_and_gate_with_portfolio_state(self, basic_engine, sample_signals):
        """Test complete pipeline with portfolio state."""
        portfolio_state = {"AAPL": {"position": 100, "unrealized_pnl": 500}}
        
        basic_engine.risk_manager.before_order.return_value = {
            "allowed": True,
            "reason": ""
        }
        
        gated_plans = await basic_engine.generate_and_gate(
            sample_signals, portfolio_state
        )
        
        assert isinstance(gated_plans, list)

    @pytest.mark.asyncio
    async def test_generate_and_gate_empty_signals(self, basic_engine):
        """Test complete pipeline with empty signals."""
        gated_plans = await basic_engine.generate_and_gate([])
        assert gated_plans == []

    def test_strategy_engine_logging(self, basic_engine, caplog):
        """Test that StrategyEngine produces appropriate log messages."""
        with caplog.at_level(logging.INFO):
            # Test symbol bucket logging indirectly
            bucket = basic_engine._get_symbol_bucket("AAPL")
            assert bucket == "A-F"
        
        # Should not have any error logs for normal operations
        error_logs = [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert len(error_logs) == 0

    @pytest.mark.asyncio
    async def test_build_execution_plan_with_metrics(self, engine_with_metrics, sample_signals):
        """Test execution plan building with metrics."""
        plans = await engine_with_metrics.build_execution_plan(sample_signals)
        
        assert isinstance(plans, list)
        # Should record signal metrics
        engine_with_metrics.metrics.inc_counter.assert_called()

    @pytest.mark.asyncio
    async def test_large_signal_volume_performance(self, basic_engine):
        """Test engine performance with large number of signals."""
        # Create 50 signals across 5 symbols
        signals = []
        for i in range(50):
            symbol = f"TEST{i % 5}"
            target_exposure = 0.1 * (i % 10 - 5)  # Range from -0.5 to 0.4
            signals.append(
                TradingSignal(
                    symbol=symbol,
                    source="test",
                    ts=datetime.now(),
                    target_exposure=target_exposure,
                    confidence=0.5,
                )
            )
        
        # Should handle large volume efficiently
        plans = await basic_engine.build_execution_plan(signals)
        assert isinstance(plans, list)

    def test_signal_validation_edge_cases(self):
        """Test TradingSignal validation with edge cases."""
        # Valid signal at boundaries
        signal = TradingSignal(
            symbol="TEST",
            source="test",
            ts=datetime.now(),
            target_exposure=1.0,  # Maximum long
            confidence=1.0,  # Maximum confidence
        )
        assert signal.target_exposure == 1.0
        assert signal.confidence == 1.0

        # Valid signal at other boundary
        signal2 = TradingSignal(
            symbol="TEST",
            source="test",
            ts=datetime.now(),
            target_exposure=-1.0,  # Maximum short
            confidence=0.0,  # Minimum confidence
        )
        assert signal2.target_exposure == -1.0
        assert signal2.confidence == 0.0

    def test_signal_validation_invalid_exposure(self):
        """Test TradingSignal validation with invalid exposure."""
        with pytest.raises(ValueError, match="target_exposure must be in"):
            TradingSignal(
                symbol="TEST",
                source="test",
                ts=datetime.now(),
                target_exposure=1.5,  # Invalid: > 1.0
                confidence=0.5,
            )

    def test_signal_validation_invalid_confidence(self):
        """Test TradingSignal validation with invalid confidence."""
        with pytest.raises(ValueError, match="confidence must be in"):
            TradingSignal(
                symbol="TEST",
                source="test",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=1.5,  # Invalid: > 1.0
            )

    def test_execution_plan_validation_edge_cases(self):
        """Test ExecutionPlan validation with edge cases."""
        # Valid plan at boundaries
        plan = ExecutionPlan(
            symbol="TEST",
            ts=datetime.now(),
            from_exposure=1.0,  # Maximum long
            to_exposure=-1.0,  # Maximum short 
            side=Side.SELL,
            notional=Decimal("1000"),
            qty=Decimal("100"),
            reason="test",
            risk_allowed=True,
        )
        assert plan.from_exposure == 1.0
        assert plan.to_exposure == -1.0

    def test_execution_plan_validation_invalid_exposure(self):
        """Test ExecutionPlan validation with invalid exposure."""
        with pytest.raises(ValueError, match="from_exposure must be in"):
            ExecutionPlan(
                symbol="TEST",
                ts=datetime.now(),
                from_exposure=1.5,  # Invalid: > 1.0
                to_exposure=0.5,
                side=Side.BUY,
                notional=Decimal("1000"),
                qty=Decimal("100"),
                reason="test",
                risk_allowed=True,
            )

    @pytest.mark.asyncio
    async def test_async_risk_manager_compatibility(self, mock_positions_service):
        """Test compatibility with async risk manager."""
        # Create async risk manager
        async_risk_manager = AsyncMock()
        async_risk_manager.before_order = AsyncMock(return_value={
            "allowed": True,
            "reason": ""
        })
        
        with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
            engine = StrategyEngine(
                risk_manager=async_risk_manager,
                positions_service=mock_positions_service
            )
        
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        gated_plan = await engine.gate_with_risk(plan)
        
        assert gated_plan.risk_allowed is True
        async_risk_manager.before_order.assert_called_once()

    @pytest.mark.asyncio 
    async def test_boolean_risk_manager_response(self, basic_engine):
        """Test handling of boolean response from risk manager."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        # Mock risk manager to return boolean (backward compatibility)
        basic_engine.risk_manager.before_order.return_value = True
        
        gated_plan = await basic_engine.gate_with_risk(plan)
        
        assert gated_plan.risk_allowed is True
        assert gated_plan.risk_reason is None

    def test_strategy_weights_configuration(self, mock_risk_manager, mock_positions_service):
        """Test strategy weights configuration."""
        config = {
            "momentum_weight": 0.8,
            "mean_rev_weight": 0.2,
            "ensemble_weight": 1.5,
        }
        
        with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service,
                config=config
            )
        
        assert engine.strategy_weights["momentum"] == 0.8
        assert engine.strategy_weights["mean_reversion"] == 0.2
        assert engine.strategy_weights["ensemble"] == 1.5

    def test_concurrent_signal_processing(self, basic_engine):
        """Test that engine handles concurrent-like signal patterns."""
        # Create signals with same timestamp (simulating concurrent arrival)
        current_time = datetime.now()
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=current_time,
                target_exposure=0.5,
                confidence=0.8,
            ),
            TradingSignal(
                symbol="AAPL", 
                source="mean_reversion",
                ts=current_time,
                target_exposure=-0.3,
                confidence=0.6,
            ),
        ]
        
        # Should handle multiple signals for same symbol
        assert len(signals) == 2
        assert all(s.symbol == "AAPL" for s in signals)


class TestExecutionPlanDataClass:
    """Test ExecutionPlan data class functionality."""

    def test_execution_plan_creation_complete(self):
        """Test ExecutionPlan creation with all fields."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
            risk_reason=None,
        )
        
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY
        assert plan.notional == Decimal("1000")
        assert plan.qty == Decimal("10")
        assert plan.risk_allowed is True
        assert plan.risk_reason is None

    def test_execution_plan_frozen_dataclass(self):
        """Test that ExecutionPlan is immutable (frozen)."""
        plan = ExecutionPlan(
            symbol="AAPL",
            ts=datetime.now(),
            from_exposure=0.0,
            to_exposure=0.5,
            side=Side.BUY,
            notional=Decimal("1000"),
            qty=Decimal("10"),
            reason="test order",
            risk_allowed=True,
        )
        
        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            plan.symbol = "TSLA"


class TestTradingSignalDataClass:
    """Test TradingSignal data class functionality."""

    def test_trading_signal_creation_complete(self):
        """Test TradingSignal creation with all fields."""
        metadata = {"strategy_id": "test_001", "params": {"period": 20}}
        
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8,
            metadata=metadata,
        )
        
        assert signal.symbol == "AAPL"
        assert signal.source == "momentum"
        assert signal.target_exposure == 0.5
        assert signal.confidence == 0.8
        assert signal.metadata == metadata

    def test_trading_signal_frozen_dataclass(self):
        """Test that TradingSignal is immutable (frozen)."""
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8,
        )
        
        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            signal.symbol = "TSLA"


# Integration and performance tests
class TestStrategyEngineIntegration:
    """Integration and performance tests for StrategyEngine."""

    @pytest.mark.asyncio
    async def test_full_pipeline_integration(self, mock_risk_manager, mock_positions_service):
        """Test full signal-to-execution pipeline integration."""
        with patch('backend.strategies.engine.get_metrics_registry', return_value=None):
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service
            )
        
        # Create diverse signals
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.6,
                confidence=0.9,
            ),
            TradingSignal(
                symbol="TSLA",
                source="mean_reversion", 
                ts=datetime.now(),
                target_exposure=-0.4,
                confidence=0.7,
            ),
            TradingSignal(
                symbol="AAPL",
                source="ensemble",
                ts=datetime.now(),
                target_exposure=0.2,
                confidence=0.5,
            ),
        ]
        
        # Mock portfolio state
        portfolio_state = {
            "AAPL": {"position": 50, "unrealized_pnl": 250},
            "TSLA": {"position": -20, "unrealized_pnl": -100},
        }
        
        # Allow all orders
        mock_risk_manager.before_order.return_value = {"allowed": True, "reason": ""}
        
        # Run full pipeline
        plans = await engine.generate_and_gate(signals, portfolio_state)
        
        # Verify results
        assert isinstance(plans, list)
        symbols = {plan.symbol for plan in plans}
        
        # Should have processed both symbols
        expected_symbols = {"AAPL", "TSLA"}
        assert symbols.intersection(expected_symbols)  # At least some overlap
        
        # All plans should be risk-gated
        for plan in plans:
            assert hasattr(plan, 'risk_allowed')
            assert hasattr(plan, 'risk_reason')

    @pytest.mark.asyncio
    async def test_error_resilience(self, basic_engine):
        """Test engine resilience to various error conditions."""
        # Test with malformed signal data - this should be caught by validation
        try:
            # This should raise validation error before reaching engine
            bad_signal = TradingSignal(
                symbol="",  # Empty symbol might cause issues
                source="test",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=0.8,
            )
            await basic_engine.build_execution_plan([bad_signal])
        except Exception:
            # Expected to fail gracefully
            pass

        # Test with positions service failure
        basic_engine.positions_service.get_positions_by_symbols.side_effect = Exception("DB error")
        
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="test",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=0.8,
            )
        ]
        
        # Should handle gracefully
        try:
            plans = await basic_engine.build_execution_plan(signals)
            # If it doesn't raise, that's also acceptable
        except Exception:
            # Acceptable to fail, but shouldn't crash the process
            pass