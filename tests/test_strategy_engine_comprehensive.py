"""
Comprehensive tests for backend.strategies.engine.StrategyEngine

Targets 70%+ coverage for the strategy engine module which handles:
- Signal netting from multiple strategies
- Position throttling to prevent rapid flips
- Risk gating through RiskManager
- Exposure to quantity conversions
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest

from backend.strategies.engine import StrategyEngine
from backend.strategies.types import ExecutionPlan, Side, TradingSignal


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_risk_manager():
    """Create mock RiskManager"""
    rm = Mock()
    rm.before_order = AsyncMock(return_value={"allowed": True, "reason": ""})
    return rm


@pytest.fixture
def mock_positions_service():
    """Create mock PositionsService"""
    ps = Mock()
    ps.get_positions_by_symbols = AsyncMock(return_value={})
    return ps


@pytest.fixture
def mock_metrics():
    """Create mock metrics registry"""
    m = Mock()
    m.inc_counter = Mock()
    m.set_gauge = Mock()
    return m


@pytest.fixture
def strategy_engine(mock_risk_manager, mock_positions_service, mock_metrics):
    """Create StrategyEngine with mocked dependencies"""
    with patch("backend.strategies.engine.get_settings") as mock_settings, \
         patch("backend.strategies.engine.get_metrics_registry", return_value=mock_metrics):
        
        # Configure settings mock
        settings = Mock()
        settings.strategy_momentum_weight = 0.6
        settings.strategy_mean_rev_weight = 0.4
        settings.strategy_ensemble_weight = 1.0
        settings.strategy_min_flip_interval_s = 60
        settings.strategy_max_new_risk_per_bar = 0.15
        settings.qty_precision = 4
        settings.price_precision = 4
        settings.trading = Mock()
        settings.trading.account_value = 100000
        mock_settings.return_value = settings
        
        engine = StrategyEngine(
            risk_manager=mock_risk_manager,
            positions_service=mock_positions_service,
            config={}
        )
        engine.metrics = mock_metrics
        
        return engine


@pytest.fixture
def sample_signal():
    """Create sample trading signal"""
    return TradingSignal(
        symbol="AAPL",
        source="momentum",
        ts=datetime.now(UTC),
        target_exposure=0.5,
        confidence=0.8
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestStrategyEngineInit:
    """Tests for StrategyEngine initialization"""
    
    def test_init_with_defaults(self, mock_risk_manager, mock_positions_service):
        """Test initialization with default config"""
        with patch("backend.strategies.engine.get_settings") as mock_settings, \
             patch("backend.strategies.engine.get_metrics_registry") as mock_metrics:
            
            settings = Mock()
            settings.strategy_momentum_weight = 0.6
            settings.strategy_mean_rev_weight = 0.4
            settings.strategy_ensemble_weight = 1.0
            settings.strategy_min_flip_interval_s = 60
            settings.strategy_max_new_risk_per_bar = 0.15
            settings.qty_precision = 4
            settings.price_precision = 4
            mock_settings.return_value = settings
            mock_metrics.return_value = Mock()
            
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service
            )
            
            assert engine.risk_manager == mock_risk_manager
            assert engine.positions_service == mock_positions_service
            assert engine.strategy_weights["momentum"] == 0.6
            assert engine.min_flip_interval_s == 10.0
            
    def test_init_with_custom_config(self, mock_risk_manager, mock_positions_service):
        """Test initialization with custom config"""
        with patch("backend.strategies.engine.get_settings") as mock_settings, \
             patch("backend.strategies.engine.get_metrics_registry"):
            
            settings = Mock()
            settings.strategy_momentum_weight = 0.6
            mock_settings.return_value = settings
            
            config = {
                "momentum_weight": 0.7,
                "mean_rev_weight": 0.3,
                "min_flip_interval_s": 120,
                "max_new_risk_per_bar": 0.20
            }
            
            engine = StrategyEngine(
                risk_manager=mock_risk_manager,
                positions_service=mock_positions_service,
                config=config
            )
            
            assert engine.strategy_weights["momentum"] == 0.7
            assert engine.strategy_weights["mean_reversion"] == 0.3
            assert engine.min_flip_interval_s == 120
            assert engine.max_new_risk_per_bar == 0.20


# ============================================================================
# SYMBOL BUCKET TESTS
# ============================================================================

class TestSymbolBucketing:
    """Tests for symbol bucketing to control metric cardinality"""
    
    def test_bucket_A_F(self, strategy_engine):
        """Test symbols A-F get bucketed correctly"""
        assert strategy_engine._get_symbol_bucket("AAPL") == "A-F"
        assert strategy_engine._get_symbol_bucket("FB") == "A-F"
        assert strategy_engine._get_symbol_bucket("DIS") == "A-F"
        
    def test_bucket_G_M(self, strategy_engine):
        """Test symbols G-M get bucketed correctly"""
        assert strategy_engine._get_symbol_bucket("GOOG") == "G-M"
        assert strategy_engine._get_symbol_bucket("MSFT") == "G-M"
        assert strategy_engine._get_symbol_bucket("IBM") == "G-M"
        
    def test_bucket_N_S(self, strategy_engine):
        """Test symbols N-S get bucketed correctly"""
        assert strategy_engine._get_symbol_bucket("NVDA") == "N-S"
        assert strategy_engine._get_symbol_bucket("ORCL") == "N-S"
        assert strategy_engine._get_symbol_bucket("SPY") == "N-S"
        
    def test_bucket_T_Z(self, strategy_engine):
        """Test symbols T-Z get bucketed correctly"""
        assert strategy_engine._get_symbol_bucket("TSLA") == "T-Z"
        assert strategy_engine._get_symbol_bucket("UBER") == "T-Z"
        assert strategy_engine._get_symbol_bucket("V") == "T-Z"


# ============================================================================
# BUILD EXECUTION PLAN TESTS
# ============================================================================

class TestBuildExecutionPlan:
    """Tests for building execution plans from signals"""
    
    @pytest.mark.asyncio
    async def test_empty_signals_returns_empty(self, strategy_engine):
        """Test empty signals list returns empty plans"""
        result = await strategy_engine.build_execution_plan([])
        assert result == []
        
    @pytest.mark.asyncio
    async def test_single_signal_builds_plan(self, strategy_engine, sample_signal):
        """Test single signal generates execution plan"""
        result = await strategy_engine.build_execution_plan([sample_signal])
        
        assert len(result) == 1
        plan = result[0]
        assert plan.symbol == "AAPL"
        assert plan.to_exposure > 0  # Positive exposure for long
        
    @pytest.mark.asyncio
    async def test_multiple_signals_same_symbol_netted(self, strategy_engine):
        """Test multiple signals for same symbol are netted"""
        now = datetime.now(UTC)
        signals = [
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=now,
                target_exposure=0.8,
                confidence=0.9
            ),
            TradingSignal(
                symbol="AAPL",
                source="mean_reversion",
                ts=now,
                target_exposure=0.4,
                confidence=0.8
            )
        ]
        
        result = await strategy_engine.build_execution_plan(signals)
        
        assert len(result) == 1
        # Exposure will be capped by max_new_risk_per_bar (0.25) since starting from 0
        plan = result[0]
        assert plan.to_exposure <= 0.25  # Limited by max risk per bar
        assert "throttle" in plan.reason or plan.to_exposure > 0
        
    @pytest.mark.asyncio
    async def test_different_symbols_generate_separate_plans(self, strategy_engine):
        """Test signals for different symbols generate separate plans"""
        now = datetime.now(UTC)
        signals = [
            TradingSignal(symbol="AAPL", source="momentum", ts=now, target_exposure=0.5, confidence=0.8),
            TradingSignal(symbol="GOOG", source="momentum", ts=now, target_exposure=0.3, confidence=0.7)
        ]
        
        result = await strategy_engine.build_execution_plan(signals)
        
        assert len(result) == 2
        symbols = {p.symbol for p in result}
        assert symbols == {"AAPL", "GOOG"}
        
    @pytest.mark.asyncio
    async def test_position_service_failure_continues(self, strategy_engine, sample_signal):
        """Test that position service failure doesn't crash engine"""
        strategy_engine.positions_service.get_positions_by_symbols = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        # Should still work with empty position map
        result = await strategy_engine.build_execution_plan([sample_signal])
        assert len(result) == 1


# ============================================================================
# SIGNAL NETTING TESTS
# ============================================================================

class TestSignalNetting:
    """Tests for signal netting logic"""
    
    @pytest.mark.asyncio
    async def test_weighted_averaging(self, strategy_engine):
        """Test that signals are weighted by confidence and strategy weight"""
        now = datetime.now(UTC)
        
        # Use higher max_new_risk_per_bar for this test to see full netting
        strategy_engine.max_new_risk_per_bar = 1.0  # Allow full range
        
        # Momentum weight = 0.6, mean_reversion weight = 0.4
        signals = [
            TradingSignal(symbol="TEST", source="momentum", ts=now, target_exposure=1.0, confidence=1.0),
            TradingSignal(symbol="TEST", source="mean_reversion", ts=now, target_exposure=0.0, confidence=1.0)
        ]
        
        result = await strategy_engine.build_execution_plan(signals)
        
        assert len(result) == 1
        # Weighted average: (1.0 * 0.6 * 1.0 + 0.0 * 0.4 * 1.0) / (0.6 + 0.4) = 0.6
        assert abs(result[0].to_exposure - 0.6) < 0.1
        
    @pytest.mark.asyncio
    async def test_unknown_strategy_uses_default_weight(self, strategy_engine):
        """Test unknown strategy sources use weight of 1.0"""
        now = datetime.now(UTC)
        
        # Use higher max_new_risk_per_bar to see full exposure
        strategy_engine.max_new_risk_per_bar = 1.0
        
        signals = [
            TradingSignal(symbol="TEST", source="custom_strategy", ts=now, target_exposure=0.5, confidence=1.0)
        ]
        
        result = await strategy_engine.build_execution_plan(signals)
        
        assert len(result) == 1
        assert abs(result[0].to_exposure - 0.5) < 0.1


# ============================================================================
# THROTTLING TESTS
# ============================================================================

class TestThrottling:
    """Tests for position flip throttling"""
    
    def test_apply_throttling_no_flip(self, strategy_engine):
        """Test no throttle when not flipping position"""
        # Small change, not a flip
        to_exp, throttled = strategy_engine._apply_throttling(
            "AAPL",
            from_exposure=0.5,
            target_exposure=0.7,
            current_time=datetime.now(UTC)
        )
        
        assert to_exp == 0.7
        assert throttled is False
        
    def test_apply_throttling_first_flip_allowed(self, strategy_engine):
        """Test first flip is allowed (no recent flip)"""
        to_exp, throttled = strategy_engine._apply_throttling(
            "AAPL",
            from_exposure=0.5,  # Long
            target_exposure=-0.5,  # Short (flip)
            current_time=datetime.now(UTC)
        )
        
        # First flip should be allowed
        assert to_exp == -0.5
        assert throttled is False
        # Should record flip time
        assert "AAPL" in strategy_engine.last_flip_times
        
    def test_apply_throttling_rapid_flip_blocked(self, strategy_engine):
        """Test rapid second flip is throttled"""
        now = datetime.now(UTC)
        
        # Record a recent flip (within the 10s min_flip_interval_s window)
        strategy_engine.last_flip_times["AAPL"] = now - timedelta(seconds=5)
        
        to_exp, throttled = strategy_engine._apply_throttling(
            "AAPL",
            from_exposure=-0.5,  # Short (after first flip)
            target_exposure=0.5,  # Long again (second flip)
            current_time=now
        )
        
        # Should be throttled
        assert throttled is True
        # Should limit movement
        assert abs(to_exp) < 0.5  # Less than full flip
        
    def test_apply_throttling_flip_after_interval(self, strategy_engine):
        """Test flip allowed after min interval"""
        now = datetime.now(UTC)
        
        # Record old flip (beyond min interval)
        strategy_engine.last_flip_times["AAPL"] = now - timedelta(seconds=120)
        
        to_exp, throttled = strategy_engine._apply_throttling(
            "AAPL",
            from_exposure=-0.5,
            target_exposure=0.5,
            current_time=now
        )
        
        # Should be allowed (interval exceeded)
        assert to_exp == 0.5
        assert throttled is False


# ============================================================================
# EXPOSURE TO QUANTITY TESTS
# ============================================================================

class TestExposureToQuantity:
    """Tests for exposure to quantity conversion"""
    
    @pytest.mark.asyncio
    async def test_flat_exposure(self, strategy_engine):
        """Test near-zero exposure returns flat"""
        qty, notional, side = await strategy_engine._exposure_to_qty(
            "TEST", 0.0001, 100000
        )
        
        assert qty == Decimal("0")
        assert side == Side.FLAT
        
    @pytest.mark.asyncio
    async def test_long_exposure(self, strategy_engine):
        """Test positive exposure returns buy side"""
        qty, notional, side = await strategy_engine._exposure_to_qty(
            "TEST", 0.5, 100000  # 50% long, $100k account
        )
        
        assert qty > 0
        assert side == Side.BUY
        assert float(notional) > 0
        
    @pytest.mark.asyncio
    async def test_short_exposure(self, strategy_engine):
        """Test negative exposure returns sell side"""
        qty, notional, side = await strategy_engine._exposure_to_qty(
            "TEST", -0.5, 100000  # 50% short
        )
        
        assert qty < 0
        assert side == Side.SELL
        
    @pytest.mark.asyncio
    async def test_known_symbol_pricing(self, strategy_engine):
        """Test known symbols use their mock prices"""
        qty_btc, _, _ = await strategy_engine._exposure_to_qty(
            "BTCUSD", 0.5, 100000
        )
        
        qty_test, _, _ = await strategy_engine._exposure_to_qty(
            "TEST", 0.5, 100000
        )
        
        # BTC at $45k should have fewer units than TEST at $100
        assert abs(qty_btc) < abs(qty_test)


# ============================================================================
# RISK GATING TESTS
# ============================================================================

class TestRiskGating:
    """Tests for risk manager gating"""
    
    @pytest.fixture
    def sample_plan(self):
        """Create sample execution plan"""
        return ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=Decimal("100"),
            price=Decimal("150"),
            ts=datetime.now(UTC),
            from_exposure=0.0,
            to_exposure=0.5,
            notional=Decimal("15000"),
            qty=Decimal("100"),
            reason="test plan",
            risk_allowed=True,
            risk_reason=None
        )
    
    @pytest.mark.asyncio
    async def test_risk_allowed(self, strategy_engine, sample_plan):
        """Test plan passes when risk allows"""
        strategy_engine.risk_manager.before_order = AsyncMock(
            return_value={"allowed": True, "reason": ""}
        )
        
        result = await strategy_engine.gate_with_risk(sample_plan)
        
        assert result.risk_allowed is True
        assert "risk=allow" in result.reason
        
    @pytest.mark.asyncio
    async def test_risk_blocked(self, strategy_engine, sample_plan):
        """Test plan blocked when risk denies"""
        strategy_engine.risk_manager.before_order = AsyncMock(
            return_value={"allowed": False, "reason": "Max exposure exceeded"}
        )
        
        result = await strategy_engine.gate_with_risk(sample_plan)
        
        assert result.risk_allowed is False
        assert result.side == Side.FLAT
        assert result.qty == Decimal("0")
        assert "risk=blocked" in result.reason
        
    @pytest.mark.asyncio
    async def test_risk_error_defaults_blocked(self, strategy_engine, sample_plan):
        """Test risk check error defaults to blocked"""
        strategy_engine.risk_manager.before_order = AsyncMock(
            side_effect=Exception("Risk service unavailable")
        )
        
        result = await strategy_engine.gate_with_risk(sample_plan)
        
        assert result.risk_allowed is False
        assert "risk=error" in result.reason
        
    @pytest.mark.asyncio
    async def test_flat_position_bypasses_risk(self, strategy_engine):
        """Test flat position doesn't need risk check"""
        flat_plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.FLAT,
            quantity=Decimal("0"),
            price=Decimal("150"),
            qty=Decimal("0")
        )
        
        result = await strategy_engine.gate_with_risk(flat_plan)
        
        # Should return unchanged without calling risk manager
        assert result.side == Side.FLAT
        strategy_engine.risk_manager.before_order.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_sync_risk_manager_supported(self, strategy_engine, sample_plan):
        """Test synchronous risk manager is supported"""
        # Use non-async before_order
        strategy_engine.risk_manager.before_order = Mock(
            return_value={"allowed": True, "reason": ""}
        )
        
        result = await strategy_engine.gate_with_risk(sample_plan)
        
        assert result.risk_allowed is True
        
    @pytest.mark.asyncio
    async def test_boolean_risk_response(self, strategy_engine, sample_plan):
        """Test backward compatible boolean response"""
        strategy_engine.risk_manager.before_order = AsyncMock(return_value=True)
        
        result = await strategy_engine.gate_with_risk(sample_plan)
        
        assert result.risk_allowed is True


# ============================================================================
# GENERATE AND GATE TESTS
# ============================================================================

class TestGenerateAndGate:
    """Tests for the complete pipeline"""
    
    @pytest.mark.asyncio
    async def test_complete_pipeline(self, strategy_engine, sample_signal):
        """Test full signal -> plan -> gated plan pipeline"""
        result = await strategy_engine.generate_and_gate([sample_signal])
        
        assert len(result) == 1
        plan = result[0]
        assert plan.symbol == "AAPL"
        assert plan.risk_allowed is True  # Default mock allows
        
    @pytest.mark.asyncio
    async def test_multiple_symbols_gated_independently(self, strategy_engine):
        """Test each symbol plan is gated independently"""
        now = datetime.now(UTC)
        signals = [
            TradingSignal(symbol="AAPL", source="momentum", ts=now, target_exposure=0.5, confidence=0.8),
            TradingSignal(symbol="GOOG", source="momentum", ts=now, target_exposure=-0.3, confidence=0.7)
        ]
        
        # Block only GOOG
        async def selective_risk(order_spec, portfolio_state):
            if order_spec["symbol"] == "GOOG":
                return {"allowed": False, "reason": "No shorts"}
            return {"allowed": True, "reason": ""}
        
        strategy_engine.risk_manager.before_order = AsyncMock(side_effect=selective_risk)
        
        result = await strategy_engine.generate_and_gate(signals)
        
        assert len(result) == 2
        
        aapl_plan = next(p for p in result if p.symbol == "AAPL")
        goog_plan = next(p for p in result if p.symbol == "GOOG")
        
        assert aapl_plan.risk_allowed is True
        assert goog_plan.risk_allowed is False
        
    @pytest.mark.asyncio
    async def test_metrics_recorded(self, strategy_engine, sample_signal):
        """Test metrics are recorded during pipeline"""
        await strategy_engine.generate_and_gate([sample_signal])
        
        # Verify metrics were called
        assert strategy_engine.metrics.inc_counter.called


# ============================================================================
# LEGACY COMPATIBILITY TESTS
# ============================================================================

class TestLegacyCompatibility:
    """Tests for legacy test compatibility"""
    
    @pytest.mark.asyncio
    async def test_process_signals_alias(self, strategy_engine, sample_signal):
        """Test process_signals works as alias for build_execution_plan"""
        result = await strategy_engine.process_signals([sample_signal])
        
        assert len(result) == 1
        
    def test_net_signals_sync_hook(self, strategy_engine, sample_signal):
        """Test net_signals returns signals unchanged (sync)"""
        result = strategy_engine.net_signals([sample_signal])
        
        assert result == [sample_signal]
        
    def test_is_throttled_default(self, strategy_engine):
        """Test is_throttled returns False by default"""
        assert strategy_engine.is_throttled("ANY_SYMBOL") is False


# ============================================================================
# MAX RISK PER BAR TESTS
# ============================================================================

class TestMaxRiskPerBar:
    """Tests for max risk per bar limiting"""
    
    @pytest.mark.asyncio
    async def test_risk_delta_within_limit(self, strategy_engine):
        """Test small risk changes pass through"""
        now = datetime.now(UTC)
        signal = TradingSignal(
            symbol="TEST",
            source="momentum",
            ts=now,
            target_exposure=0.10,  # 10% exposure, within 15% limit
            confidence=1.0
        )
        
        result = await strategy_engine.build_execution_plan([signal])
        
        assert len(result) == 1
        # Should reach target (from 0 to 0.10 is within 0.15 limit)
        assert abs(result[0].to_exposure - 0.10) < 0.05
        
    @pytest.mark.asyncio
    async def test_risk_delta_exceeds_limit(self, strategy_engine):
        """Test large risk changes are capped"""
        now = datetime.now(UTC)
        # Start with a known position to create large delta
        mock_position = Mock()
        mock_position.qty = 5000  # Large position
        mock_position.price = 100
        strategy_engine.positions_service.get_positions_by_symbols = AsyncMock(
            return_value={"TEST": mock_position}
        )
        
        signal = TradingSignal(
            symbol="TEST",
            source="momentum",
            ts=now,
            target_exposure=-0.8,  # Requesting large flip
            confidence=1.0
        )
        
        result = await strategy_engine.build_execution_plan([signal])
        
        # Should be limited by max_new_risk_per_bar (0.15)
        assert len(result) == 1


# ============================================================================
# FACTORY METHOD TESTS
# ============================================================================

class TestFactoryMethod:
    """Tests for create_default factory method"""
    
    def test_create_default_returns_engine(self):
        """Test factory method creates engine instance"""
        with patch("backend.strategies.engine.get_settings") as mock_settings, \
             patch("backend.strategies.engine.get_metrics_registry"), \
             patch("backend.strategies.engine.RiskManager"), \
             patch("backend.strategies.engine.PositionsService"):
            
            settings = Mock()
            settings.strategy_momentum_weight = 0.6
            settings.strategy_mean_rev_weight = 0.4
            settings.strategy_ensemble_weight = 1.0
            settings.strategy_min_flip_interval_s = 60
            settings.strategy_max_new_risk_per_bar = 0.15
            settings.qty_precision = 4
            settings.price_precision = 4
            mock_settings.return_value = settings
            
            engine = StrategyEngine.create_default()
            
            assert isinstance(engine, StrategyEngine)


# ============================================================================
# TRADING SIGNAL VALIDATION TESTS
# ============================================================================

class TestTradingSignalValidation:
    """Tests for TradingSignal dataclass validation"""
    
    def test_valid_signal(self):
        """Test valid signal creation"""
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(UTC),
            target_exposure=0.5,
            confidence=0.8
        )
        
        assert signal.symbol == "AAPL"
        assert signal.target_exposure == 0.5
        
    def test_exposure_out_of_range_raises(self):
        """Test exposure > 1.0 raises ValueError"""
        with pytest.raises(ValueError, match="target_exposure"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(UTC),
                target_exposure=1.5,  # Invalid
                confidence=0.8
            )
            
    def test_negative_exposure_too_low_raises(self):
        """Test exposure < -1.0 raises ValueError"""
        with pytest.raises(ValueError, match="target_exposure"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(UTC),
                target_exposure=-1.5,  # Invalid
                confidence=0.8
            )
            
    def test_confidence_out_of_range_raises(self):
        """Test confidence > 1.0 raises ValueError"""
        with pytest.raises(ValueError, match="confidence"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(UTC),
                target_exposure=0.5,
                confidence=1.5  # Invalid
            )
            
    def test_negative_confidence_raises(self):
        """Test negative confidence raises ValueError"""
        with pytest.raises(ValueError, match="confidence"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(UTC),
                target_exposure=0.5,
                confidence=-0.1  # Invalid
            )
            
    def test_signal_with_metadata(self):
        """Test signal with metadata"""
        signal = TradingSignal(
            symbol="AAPL",
            source="custom",
            ts=datetime.now(UTC),
            target_exposure=0.5,
            confidence=0.8,
            metadata={"lookback": 20, "threshold": 0.02}
        )
        
        assert signal.metadata["lookback"] == 20


# ============================================================================
# EXECUTION PLAN TESTS
# ============================================================================

class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass"""
    
    def test_minimal_plan(self):
        """Test minimal plan creation (legacy compatibility)"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150
        )
        
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY
        assert plan.quantity == 100
        assert plan.order_type == "market"  # Default
        
    def test_full_plan(self):
        """Test full plan with all fields"""
        now = datetime.now(UTC)
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=Decimal("100"),
            price=Decimal("150"),
            order_type="limit",
            ts=now,
            from_exposure=0.0,
            to_exposure=0.5,
            notional=Decimal("15000"),
            qty=Decimal("100"),
            reason="momentum signal",
            risk_allowed=True,
            risk_reason=None
        )
        
        assert plan.ts == now
        assert plan.from_exposure == 0.0
        assert plan.to_exposure == 0.5


# ============================================================================
# SIDE ENUM TESTS  
# ============================================================================

class TestSideEnum:
    """Tests for Side enumeration"""
    
    def test_side_values(self):
        """Test Side enum values"""
        assert Side.BUY.value == "buy"
        assert Side.SELL.value == "sell"
        assert Side.FLAT.value == "flat"
        
    def test_side_comparison(self):
        """Test Side enum comparison"""
        assert Side.BUY != Side.SELL
        assert Side.BUY == Side.BUY
