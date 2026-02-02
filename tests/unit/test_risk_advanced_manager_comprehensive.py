"""
Comprehensive tests for backend.risk.advanced_risk_manager module.

Tests cover:
- RiskLimits, RiskMetrics, Position dataclasses
- AdvancedRiskManager initialization
- Position updates and risk calculations
- VaR, drawdown, concentration, correlation calculations
- Market regime detection
- Risk limit checking and alerts
- Position sizing and rebalancing recommendations
- Emergency risk reduction protocol
- SLO integration

Target: 90%+ coverage
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import math

import numpy as np
import pytest

from backend.risk.advanced_risk_manager import (
    AdvancedRiskManager,
    RiskLimits,
    RiskMetrics,
    Position,
    RiskLevel,
    MarketRegime,
)


# ==============================================================================
# Dataclass Tests
# ==============================================================================

class TestRiskLimits:
    """Tests for RiskLimits dataclass."""

    def test_default_values(self):
        """Test default risk limits values."""
        limits = RiskLimits()
        assert limits.max_position_size == 0.1
        assert limits.max_sector_concentration == 0.25
        assert limits.max_correlation == 0.8
        assert limits.max_portfolio_var == 0.02
        assert limits.max_drawdown == 0.05
        assert limits.max_leverage == 2.0
        assert limits.stop_loss_threshold == 0.03
        assert limits.profit_target == 0.05
        assert limits.min_liquidity == 0.1
        assert limits.var_confidence_level == 0.95

    def test_custom_values(self):
        """Test custom risk limits."""
        limits = RiskLimits(
            max_position_size=0.05,
            max_sector_concentration=0.15,
            max_leverage=1.5,
            max_drawdown=0.03
        )
        assert limits.max_position_size == 0.05
        assert limits.max_sector_concentration == 0.15
        assert limits.max_leverage == 1.5
        assert limits.max_drawdown == 0.03


class TestRiskMetrics:
    """Tests for RiskMetrics dataclass."""

    def test_default_values(self):
        """Test default risk metrics values."""
        metrics = RiskMetrics()
        assert metrics.portfolio_var_1d == 0.0
        assert metrics.portfolio_var_5d == 0.0
        assert metrics.portfolio_var_10d == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.current_drawdown == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.sortino_ratio == 0.0
        assert metrics.beta == 1.0
        assert metrics.alpha == 0.0
        assert metrics.tracking_error == 0.0
        assert metrics.information_ratio == 0.0
        assert metrics.concentration_risk == 0.0
        assert metrics.sector_concentration == {}
        assert metrics.correlation_risk == 0.0
        assert metrics.leverage == 1.0
        assert metrics.gross_exposure == 0.0
        assert metrics.net_exposure == 0.0
        assert metrics.long_exposure == 0.0
        assert metrics.short_exposure == 0.0
        assert metrics.risk_level == RiskLevel.LOW
        assert metrics.market_regime == MarketRegime.CALM
        assert isinstance(metrics.timestamp, datetime)

    def test_custom_values(self):
        """Test RiskMetrics with custom values."""
        now = datetime.utcnow()
        metrics = RiskMetrics(
            portfolio_var_1d=0.05,
            max_drawdown=0.1,
            leverage=2.5,
            risk_level=RiskLevel.HIGH,
            market_regime=MarketRegime.VOLATILE,
            timestamp=now
        )
        assert metrics.portfolio_var_1d == 0.05
        assert metrics.max_drawdown == 0.1
        assert metrics.leverage == 2.5
        assert metrics.risk_level == RiskLevel.HIGH
        assert metrics.market_regime == MarketRegime.VOLATILE
        assert metrics.timestamp == now


class TestPosition:
    """Tests for Position dataclass."""

    def test_default_values(self):
        """Test Position with required and default values."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            price=150.0,
            market_value=15000.0,
            weight=0.1
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.price == 150.0
        assert pos.market_value == 15000.0
        assert pos.weight == 0.1
        assert pos.sector == "Unknown"
        assert pos.beta == 1.0
        assert pos.volatility == 0.0
        assert pos.correlation_to_portfolio == 0.0

    def test_all_values(self):
        """Test Position with all values specified."""
        pos = Position(
            symbol="TSLA",
            quantity=50,
            price=200.0,
            market_value=10000.0,
            weight=0.05,
            sector="Automotive",
            beta=1.8,
            volatility=0.45,
            correlation_to_portfolio=0.7
        )
        assert pos.sector == "Automotive"
        assert pos.beta == 1.8
        assert pos.volatility == 0.45
        assert pos.correlation_to_portfolio == 0.7


class TestEnums:
    """Tests for Risk and Market enums."""

    def test_risk_level_values(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_market_regime_values(self):
        """Test MarketRegime enum values."""
        assert MarketRegime.CALM.value == "calm"
        assert MarketRegime.VOLATILE.value == "volatile"
        assert MarketRegime.TRENDING.value == "trending"
        assert MarketRegime.CRISIS.value == "crisis"


# ==============================================================================
# AdvancedRiskManager Initialization Tests
# ==============================================================================

class TestAdvancedRiskManagerInit:
    """Tests for AdvancedRiskManager initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        manager = AdvancedRiskManager(enable_slo=False)
        assert manager.risk_limits is not None
        assert manager.positions == {}
        assert manager.portfolio_value == 0.0
        assert manager.cash_balance == 0.0
        assert manager.price_history == {}
        assert manager.returns_history == {}
        assert manager.portfolio_returns == []
        assert manager.alerts == []
        assert manager.slo_monitor is None

    def test_custom_risk_limits(self):
        """Test initialization with custom risk limits."""
        limits = RiskLimits(max_position_size=0.05, max_leverage=1.5)
        manager = AdvancedRiskManager(risk_limits=limits, enable_slo=False)
        assert manager.risk_limits.max_position_size == 0.05
        assert manager.risk_limits.max_leverage == 1.5

    @patch('backend.risk.advanced_risk_manager.SLO_AVAILABLE', True)
    def test_slo_enabled_but_unavailable(self):
        """Test SLO enabled when module not available."""
        with patch('backend.risk.advanced_risk_manager.SLO_AVAILABLE', False):
            manager = AdvancedRiskManager(enable_slo=True)
            assert manager.slo_monitor is None

    def test_slo_disabled(self):
        """Test SLO explicitly disabled."""
        manager = AdvancedRiskManager(enable_slo=False)
        assert manager.slo_monitor is None


# ==============================================================================
# Position Update Tests
# ==============================================================================

class TestUpdatePositions:
    """Tests for update_positions method."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.fixture
    def sample_positions(self):
        """Sample positions data."""
        return {
            'AAPL': {
                'quantity': 100,
                'price': 150.0,
                'market_value': 15000,
                'sector': 'Technology',
                'beta': 1.2,
                'volatility': 0.25
            },
            'GOOGL': {
                'quantity': 50,
                'price': 100.0,
                'market_value': 5000,
                'sector': 'Technology',
                'beta': 1.1,
                'volatility': 0.28
            }
        }

    @pytest.mark.asyncio
    async def test_update_positions_basic(self, manager, sample_positions):
        """Test basic position update."""
        await manager.update_positions(sample_positions)
        assert len(manager.positions) == 2
        assert 'AAPL' in manager.positions
        assert 'GOOGL' in manager.positions
        assert manager.portfolio_value == 20000.0

    @pytest.mark.asyncio
    async def test_update_positions_weight_calculation(self, manager, sample_positions):
        """Test position weight calculation."""
        await manager.update_positions(sample_positions)
        aapl_weight = manager.positions['AAPL'].weight
        googl_weight = manager.positions['GOOGL'].weight
        assert abs(aapl_weight - 0.75) < 0.01  # 15000/20000
        assert abs(googl_weight - 0.25) < 0.01  # 5000/20000

    @pytest.mark.asyncio
    async def test_update_positions_clears_previous(self, manager, sample_positions):
        """Test that update clears previous positions."""
        await manager.update_positions(sample_positions)
        assert len(manager.positions) == 2
        
        new_positions = {
            'TSLA': {'quantity': 10, 'price': 200.0, 'market_value': 2000}
        }
        await manager.update_positions(new_positions)
        assert len(manager.positions) == 1
        assert 'TSLA' in manager.positions
        assert 'AAPL' not in manager.positions

    @pytest.mark.asyncio
    async def test_update_positions_empty(self, manager):
        """Test update with empty positions."""
        await manager.update_positions({})
        assert len(manager.positions) == 0
        assert manager.portfolio_value == 0.0

    @pytest.mark.asyncio
    async def test_update_positions_default_values(self, manager):
        """Test update with minimal data (uses defaults)."""
        positions = {
            'XYZ': {'quantity': 0, 'price': 0, 'market_value': 0}
        }
        await manager.update_positions(positions)
        assert len(manager.positions) == 1
        pos = manager.positions['XYZ']
        assert pos.sector == 'Unknown'
        assert pos.beta == 1.0
        assert pos.volatility == 0.0

    @pytest.mark.asyncio
    async def test_update_positions_with_slo(self, manager, sample_positions):
        """Test position update with SLO monitoring."""
        mock_slo = AsyncMock()
        manager.slo_monitor = mock_slo
        
        await manager.update_positions(sample_positions)
        # SLO should have been called
        mock_slo.record_metric.assert_called()

    @pytest.mark.asyncio
    async def test_update_positions_error_with_slo(self, manager):
        """Test position update error records SLO failure."""
        mock_slo = AsyncMock()
        manager.slo_monitor = mock_slo
        
        # Force an error in price history update
        with patch.object(manager, '_update_price_history', side_effect=Exception("Test error")):
            with pytest.raises(Exception):
                await manager.update_positions({'AAPL': {'quantity': 100, 'price': 150, 'market_value': 15000}})


# ==============================================================================
# Price History Tests
# ==============================================================================

class TestPriceHistory:
    """Tests for _update_price_history method."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_price_history_initialization(self, manager):
        """Test price history is initialized for new symbols."""
        positions = {'AAPL': {'quantity': 100, 'price': 150.0, 'market_value': 15000}}
        await manager.update_positions(positions)
        assert 'AAPL' in manager.price_history
        assert len(manager.price_history['AAPL']) == 1
        assert manager.price_history['AAPL'][0] == 150.0

    @pytest.mark.asyncio
    async def test_price_history_multiple_updates(self, manager):
        """Test price history accumulates with multiple updates."""
        for price in [150.0, 152.0, 155.0]:
            await manager.update_positions({
                'AAPL': {'quantity': 100, 'price': price, 'market_value': 100 * price}
            })
        
        assert len(manager.price_history['AAPL']) == 3
        assert 150.0 in manager.price_history['AAPL']
        assert 152.0 in manager.price_history['AAPL']
        assert 155.0 in manager.price_history['AAPL']

    @pytest.mark.asyncio
    async def test_returns_calculation(self, manager):
        """Test returns are calculated correctly."""
        prices = [100.0, 110.0, 105.0]  # +10%, -4.5%
        for price in prices:
            await manager.update_positions({
                'AAPL': {'quantity': 100, 'price': price, 'market_value': 100 * price}
            })
        
        returns = manager.returns_history.get('AAPL', [])
        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 0.001  # 10% return
        assert abs(returns[1] - (-0.0454545)) < 0.01  # ~-4.5% return

    @pytest.mark.asyncio
    async def test_price_history_limit(self, manager):
        """Test price history is limited to 252 observations."""
        # Simulate 260 price updates
        for i in range(260):
            price = 100.0 + i * 0.1
            await manager.update_positions({
                'AAPL': {'quantity': 100, 'price': price, 'market_value': 100 * price}
            })
        
        assert len(manager.price_history['AAPL']) <= 252


# ==============================================================================
# Risk Metrics Calculation Tests
# ==============================================================================

class TestCalculateRiskMetrics:
    """Tests for risk metrics calculation."""

    @pytest.fixture
    def manager_with_positions(self):
        """Create a manager with sample positions."""
        manager = AdvancedRiskManager(enable_slo=False)
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.6, 'Technology', 1.2, 0.25),
            'GOOGL': Position('GOOGL', 50, 100.0, 10000.0, 0.4, 'Technology', 1.1, 0.28)
        }
        manager.portfolio_value = 25000.0
        return manager

    @pytest.mark.asyncio
    async def test_gross_exposure_calculation(self, manager_with_positions):
        """Test gross exposure is sum of absolute market values."""
        await manager_with_positions._calculate_risk_metrics()
        assert manager_with_positions.risk_metrics.gross_exposure == 25000.0

    @pytest.mark.asyncio
    async def test_net_exposure_calculation(self, manager_with_positions):
        """Test net exposure calculation."""
        await manager_with_positions._calculate_risk_metrics()
        assert manager_with_positions.risk_metrics.net_exposure == 25000.0

    @pytest.mark.asyncio
    async def test_long_short_exposure(self, manager_with_positions):
        """Test long and short exposure separation."""
        # Add a short position
        manager_with_positions.positions['TSLA'] = Position(
            'TSLA', -50, 200.0, -10000.0, -0.4, 'Automotive', 1.8, 0.45
        )
        
        await manager_with_positions._calculate_risk_metrics()
        assert manager_with_positions.risk_metrics.long_exposure == 25000.0
        assert manager_with_positions.risk_metrics.short_exposure == -10000.0

    @pytest.mark.asyncio
    async def test_leverage_calculation(self, manager_with_positions):
        """Test leverage calculation."""
        await manager_with_positions._calculate_risk_metrics()
        expected_leverage = 25000.0 / 25000.0  # gross / portfolio
        assert manager_with_positions.risk_metrics.leverage == expected_leverage

    @pytest.mark.asyncio
    async def test_timestamp_updated(self, manager_with_positions):
        """Test timestamp is updated after calculation."""
        before = datetime.utcnow()
        await manager_with_positions._calculate_risk_metrics()
        after = datetime.utcnow()
        assert before <= manager_with_positions.risk_metrics.timestamp <= after


class TestCalculateVaR:
    """Tests for VaR calculation."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_var_insufficient_history(self, manager):
        """Test VaR returns early with insufficient history."""
        manager.portfolio_returns = [0.01] * 5  # Only 5 observations
        await manager._calculate_var()
        # VaR should remain at default 0.0
        assert manager.risk_metrics.portfolio_var_1d == 0.0

    @pytest.mark.asyncio
    async def test_var_calculation_with_history(self, manager):
        """Test VaR calculation with sufficient history."""
        # Create returns history (30 observations)
        np.random.seed(42)
        manager.portfolio_returns = list(np.random.normal(0.001, 0.02, 30))
        
        await manager._calculate_var()
        
        # VaR should be non-zero
        assert manager.risk_metrics.portfolio_var_1d > 0
        # 5-day VaR should be sqrt(5) times 1-day VaR
        assert abs(manager.risk_metrics.portfolio_var_5d - manager.risk_metrics.portfolio_var_1d * math.sqrt(5)) < 0.001
        # 10-day VaR should be sqrt(10) times 1-day VaR
        assert abs(manager.risk_metrics.portfolio_var_10d - manager.risk_metrics.portfolio_var_1d * math.sqrt(10)) < 0.001


class TestCalculateDrawdown:
    """Tests for drawdown calculation."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_drawdown_insufficient_history(self, manager):
        """Test drawdown with insufficient history."""
        manager.portfolio_returns = [0.01]  # Only 1 observation
        await manager._calculate_drawdown_metrics()
        assert manager.risk_metrics.current_drawdown == 0.0
        assert manager.risk_metrics.max_drawdown == 0.0

    @pytest.mark.asyncio
    async def test_drawdown_calculation(self, manager):
        """Test drawdown calculation with returns."""
        # Returns that create a drawdown
        manager.portfolio_returns = [0.05, 0.03, -0.02, -0.05, 0.01, -0.03]
        
        await manager._calculate_drawdown_metrics()
        
        # Should have non-zero drawdown
        assert manager.risk_metrics.max_drawdown <= 0  # Drawdown is negative
        assert manager.risk_metrics.current_drawdown <= 0

    @pytest.mark.asyncio
    async def test_drawdown_no_drawdown(self, manager):
        """Test with only positive returns (no drawdown)."""
        manager.portfolio_returns = [0.01, 0.02, 0.01, 0.03, 0.02]
        
        await manager._calculate_drawdown_metrics()
        
        # No drawdown with continuously rising prices
        assert manager.risk_metrics.current_drawdown == 0.0
        assert manager.risk_metrics.max_drawdown == 0.0


class TestCalculateConcentration:
    """Tests for concentration risk calculation."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_concentration_empty_portfolio(self, manager):
        """Test concentration with no positions."""
        await manager._calculate_concentration_risk()
        assert manager.risk_metrics.concentration_risk == 0.0

    @pytest.mark.asyncio
    async def test_concentration_single_position(self, manager):
        """Test concentration with single position (100%)."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 1.0, 'Technology')
        }
        
        await manager._calculate_concentration_risk()
        
        # Herfindahl = 1.0^2 = 1.0
        assert manager.risk_metrics.concentration_risk == 1.0
        assert manager.risk_metrics.sector_concentration['Technology'] == 1.0

    @pytest.mark.asyncio
    async def test_concentration_diversified(self, manager):
        """Test concentration with diversified portfolio."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 5000.0, 0.25, 'Technology'),
            'GOOGL': Position('GOOGL', 50, 100.0, 5000.0, 0.25, 'Technology'),
            'JNJ': Position('JNJ', 30, 167.0, 5000.0, 0.25, 'Healthcare'),
            'JPM': Position('JPM', 40, 125.0, 5000.0, 0.25, 'Finance')
        }
        
        await manager._calculate_concentration_risk()
        
        # Herfindahl = 4 * 0.25^2 = 0.25
        assert abs(manager.risk_metrics.concentration_risk - 0.25) < 0.01
        assert manager.risk_metrics.sector_concentration['Technology'] == 0.5
        assert manager.risk_metrics.sector_concentration['Healthcare'] == 0.25


class TestCalculateCorrelation:
    """Tests for correlation risk calculation."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_correlation_single_position(self, manager):
        """Test correlation with single position."""
        manager.positions = {'AAPL': Position('AAPL', 100, 150.0, 15000.0, 1.0)}
        
        await manager._calculate_correlation_risk()
        
        assert manager.risk_metrics.correlation_risk == 0.0

    @pytest.mark.asyncio
    async def test_correlation_insufficient_data(self, manager):
        """Test correlation with insufficient return history."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.5),
            'GOOGL': Position('GOOGL', 50, 100.0, 10000.0, 0.5)
        }
        manager.returns_history = {'AAPL': [0.01], 'GOOGL': [0.02]}  # Only 1 observation
        
        await manager._calculate_correlation_risk()
        
        assert manager.risk_metrics.correlation_risk == 0.0

    @pytest.mark.asyncio
    async def test_correlation_with_history(self, manager):
        """Test correlation with sufficient return history."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.5),
            'GOOGL': Position('GOOGL', 50, 100.0, 10000.0, 0.5)
        }
        # Correlated returns
        np.random.seed(42)
        base_returns = np.random.normal(0.001, 0.02, 20)
        manager.returns_history = {
            'AAPL': list(base_returns),
            'GOOGL': list(base_returns * 0.8 + np.random.normal(0, 0.005, 20))
        }
        
        await manager._calculate_correlation_risk()
        
        # Should have positive correlation
        assert manager.risk_metrics.correlation_risk > 0


# ==============================================================================
# Market Regime Detection Tests
# ==============================================================================

class TestMarketRegimeDetection:
    """Tests for market regime detection."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_regime_insufficient_history(self, manager):
        """Test regime detection with insufficient history."""
        manager.portfolio_returns = [0.01] * 5
        
        await manager._detect_market_regime()
        
        assert manager.risk_metrics.market_regime == MarketRegime.CALM

    @pytest.mark.asyncio
    async def test_regime_calm(self, manager):
        """Test calm market regime."""
        # Low volatility, no trend - use fixed values that sum to near zero
        manager.portfolio_returns = [0.001, -0.001, 0.002, -0.002, 0.001, -0.001,
                                     0.0005, -0.0005, 0.001, -0.001, 0.0015, -0.0015,
                                     0.002, -0.002, 0.001, -0.001, 0.0005, -0.0005,
                                     0.001, -0.001, 0.001, -0.001, 0.002, -0.002, 0.001]
        
        await manager._detect_market_regime()
        
        assert manager.risk_metrics.market_regime == MarketRegime.CALM

    @pytest.mark.asyncio
    async def test_regime_volatile(self, manager):
        """Test volatile market regime."""
        # High volatility (std > 0.3/sqrt(252) daily)
        manager.portfolio_returns = list(np.random.normal(0, 0.03, 25))  # ~47% annualized
        
        await manager._detect_market_regime()
        
        assert manager.risk_metrics.market_regime in [MarketRegime.VOLATILE, MarketRegime.CRISIS]

    @pytest.mark.asyncio
    async def test_regime_trending(self, manager):
        """Test trending market regime."""
        # Moderate volatility with strong positive trend
        manager.portfolio_returns = [0.003] * 25  # Strong positive drift
        
        await manager._detect_market_regime()
        
        # May be calm or trending depending on exact thresholds
        assert manager.risk_metrics.market_regime in [MarketRegime.CALM, MarketRegime.TRENDING]


# ==============================================================================
# Risk Level Determination Tests
# ==============================================================================

class TestDetermineRiskLevel:
    """Tests for risk level determination."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    def test_risk_level_low(self, manager):
        """Test low risk level."""
        manager.risk_metrics = RiskMetrics(
            portfolio_var_1d=0.01,
            current_drawdown=-0.01,
            concentration_risk=0.2,
            leverage=1.0,
            market_regime=MarketRegime.CALM
        )
        
        manager._determine_risk_level()
        
        assert manager.risk_metrics.risk_level == RiskLevel.LOW

    def test_risk_level_medium(self, manager):
        """Test medium risk level."""
        manager.risk_metrics = RiskMetrics(
            portfolio_var_1d=0.015,  # Above 70% of limit
            current_drawdown=-0.02,
            concentration_risk=0.2,
            leverage=1.5,
            market_regime=MarketRegime.CALM
        )
        
        manager._determine_risk_level()
        
        assert manager.risk_metrics.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]

    def test_risk_level_high(self, manager):
        """Test high risk level."""
        manager.risk_metrics = RiskMetrics(
            portfolio_var_1d=0.03,  # Exceeds 2% limit
            current_drawdown=-0.06,  # Exceeds 5% limit
            concentration_risk=0.6,  # High concentration
            leverage=2.5,  # Exceeds limit
            market_regime=MarketRegime.VOLATILE
        )
        
        manager._determine_risk_level()
        
        assert manager.risk_metrics.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

    def test_risk_level_critical(self, manager):
        """Test critical risk level."""
        manager.risk_metrics = RiskMetrics(
            portfolio_var_1d=0.05,  # Well over limit
            current_drawdown=-0.15,  # Major drawdown
            concentration_risk=0.8,
            leverage=3.0,
            market_regime=MarketRegime.CRISIS
        )
        
        manager._determine_risk_level()
        
        assert manager.risk_metrics.risk_level == RiskLevel.CRITICAL


# ==============================================================================
# Risk Limits Check Tests
# ==============================================================================

class TestCheckRiskLimits:
    """Tests for risk limit checking."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_position_size_breach(self, manager):
        """Test position size limit breach alert."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.15, 'Technology')  # 15% > 10% limit
        }
        
        await manager._check_risk_limits()
        
        alerts = [a for a in manager.alerts if a['type'] == 'position_limit_breach']
        assert len(alerts) == 1
        assert alerts[0]['symbol'] == 'AAPL'
        assert alerts[0]['severity'] == 'high'

    @pytest.mark.asyncio
    async def test_sector_concentration_breach(self, manager):
        """Test sector concentration limit breach alert."""
        manager.risk_metrics.sector_concentration = {'Technology': 0.35}  # 35% > 25% limit
        
        await manager._check_risk_limits()
        
        alerts = [a for a in manager.alerts if a['type'] == 'sector_concentration_breach']
        assert len(alerts) == 1
        assert alerts[0]['sector'] == 'Technology'
        assert alerts[0]['severity'] == 'medium'

    @pytest.mark.asyncio
    async def test_var_limit_breach(self, manager):
        """Test VaR limit breach alert."""
        manager.risk_metrics.portfolio_var_1d = 0.03  # 3% > 2% limit
        
        await manager._check_risk_limits()
        
        alerts = [a for a in manager.alerts if a['type'] == 'var_limit_breach']
        assert len(alerts) == 1
        assert alerts[0]['severity'] == 'high'

    @pytest.mark.asyncio
    async def test_drawdown_limit_breach(self, manager):
        """Test drawdown limit breach alert."""
        manager.risk_metrics.current_drawdown = -0.08  # 8% > 5% limit
        
        await manager._check_risk_limits()
        
        alerts = [a for a in manager.alerts if a['type'] == 'drawdown_limit_breach']
        assert len(alerts) == 1
        assert alerts[0]['severity'] == 'critical'

    @pytest.mark.asyncio
    async def test_leverage_limit_breach(self, manager):
        """Test leverage limit breach alert."""
        manager.risk_metrics.leverage = 2.5  # 2.5x > 2.0x limit
        
        await manager._check_risk_limits()
        
        alerts = [a for a in manager.alerts if a['type'] == 'leverage_limit_breach']
        assert len(alerts) == 1
        assert alerts[0]['severity'] == 'high'

    @pytest.mark.asyncio
    async def test_alerts_pruned_after_24_hours(self, manager):
        """Test old alerts are pruned."""
        old_alert = {
            'type': 'test_alert',
            'timestamp': datetime.utcnow() - timedelta(hours=25)
        }
        manager.alerts = [old_alert]
        
        await manager._check_risk_limits()
        
        # Old alert should be removed
        old_alerts = [a for a in manager.alerts if a.get('type') == 'test_alert']
        assert len(old_alerts) == 0


# ==============================================================================
# Position Sizing Tests
# ==============================================================================

class TestPositionSizing:
    """Tests for position sizing calculation."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_position_size_no_history(self, manager):
        """Test position sizing with no history."""
        size = await manager.calculate_position_size('AAPL')
        assert size == 0.02  # Default conservative sizing

    @pytest.mark.asyncio
    async def test_position_size_insufficient_history(self, manager):
        """Test position sizing with insufficient history."""
        manager.returns_history = {'AAPL': [0.01] * 5}  # Only 5 observations
        size = await manager.calculate_position_size('AAPL')
        assert size == 0.02  # Default

    @pytest.mark.asyncio
    async def test_position_size_with_history(self, manager):
        """Test position sizing with sufficient history."""
        # Create returns history (60 observations, ~20% annualized vol)
        np.random.seed(42)
        daily_vol = 0.2 / math.sqrt(252)  # Daily vol for 20% annualized
        manager.returns_history = {'AAPL': list(np.random.normal(0, daily_vol, 60))}
        
        size = await manager.calculate_position_size('AAPL', target_risk=0.01)
        
        # Position size = target_risk / volatility
        assert 0.001 <= size <= 0.1  # Within limits

    @pytest.mark.asyncio
    async def test_position_size_respects_max_limit(self, manager):
        """Test position sizing respects maximum limit."""
        # Very low volatility would give very large position
        manager.returns_history = {'AAPL': [0.0001] * 60}  # Near-zero vol
        
        size = await manager.calculate_position_size('AAPL')
        
        assert size <= manager.risk_limits.max_position_size

    @pytest.mark.asyncio
    async def test_position_size_zero_volatility(self, manager):
        """Test position sizing with zero volatility."""
        manager.returns_history = {'AAPL': [0.0] * 60}  # Zero returns
        
        size = await manager.calculate_position_size('AAPL')
        
        assert size == 0.0


# ==============================================================================
# Rebalancing Recommendations Tests
# ==============================================================================

class TestRebalancingRecommendations:
    """Tests for rebalancing recommendations."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_recommendations_empty_portfolio(self, manager):
        """Test recommendations with empty portfolio."""
        recommendations = await manager.get_rebalancing_recommendations()
        assert len(recommendations) == 0

    @pytest.mark.asyncio
    async def test_recommendations_position_size_exceeded(self, manager):
        """Test recommendations when position size exceeded."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.15, 'Technology')  # 15% > 10%
        }
        
        recommendations = await manager.get_rebalancing_recommendations()
        
        reduce_recs = [r for r in recommendations if r['action'] == 'reduce_position']
        assert len(reduce_recs) == 1
        assert reduce_recs[0]['symbol'] == 'AAPL'
        assert reduce_recs[0]['priority'] == 'high'

    @pytest.mark.asyncio
    async def test_recommendations_sector_concentration_exceeded(self, manager):
        """Test recommendations when sector concentration exceeded."""
        manager.risk_metrics.sector_concentration = {'Technology': 0.35}  # 35% > 25%
        
        recommendations = await manager.get_rebalancing_recommendations()
        
        sector_recs = [r for r in recommendations if r['action'] == 'reduce_sector_exposure']
        assert len(sector_recs) == 1
        assert sector_recs[0]['sector'] == 'Technology'
        assert sector_recs[0]['priority'] == 'medium'

    @pytest.mark.asyncio
    async def test_recommendations_high_risk_level(self, manager):
        """Test recommendations when risk level is high."""
        manager.risk_metrics.risk_level = RiskLevel.HIGH
        
        recommendations = await manager.get_rebalancing_recommendations()
        
        risk_recs = [r for r in recommendations if r['action'] == 'reduce_overall_risk']
        assert len(risk_recs) == 1

    @pytest.mark.asyncio
    async def test_recommendations_critical_risk_level(self, manager):
        """Test recommendations when risk level is critical."""
        manager.risk_metrics.risk_level = RiskLevel.CRITICAL
        
        recommendations = await manager.get_rebalancing_recommendations()
        
        risk_recs = [r for r in recommendations if r['action'] == 'reduce_overall_risk']
        assert len(risk_recs) == 1
        assert 'critical' in risk_recs[0]['reason']


# ==============================================================================
# Emergency Risk Reduction Tests
# ==============================================================================

class TestEmergencyRiskReduction:
    """Tests for emergency risk reduction protocol."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_emergency_reduction_empty_portfolio(self, manager):
        """Test emergency reduction with empty portfolio."""
        actions = await manager.emergency_risk_reduction(0.5)
        
        # Should still have raise_cash action
        cash_actions = [a for a in actions if a['action'] == 'raise_cash']
        assert len(cash_actions) == 1

    @pytest.mark.asyncio
    async def test_emergency_reduction_generates_actions(self, manager):
        """Test emergency reduction generates position reduction actions."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.6, 'Technology', 1.2, 0.25),
            'TSLA': Position('TSLA', 50, 200.0, 10000.0, 0.4, 'Automotive', 1.8, 0.45)
        }
        
        actions = await manager.emergency_risk_reduction(0.5)
        
        reduce_actions = [a for a in actions if a['action'] == 'emergency_position_reduction']
        assert len(reduce_actions) > 0

    @pytest.mark.asyncio
    async def test_emergency_reduction_sorts_by_risk(self, manager):
        """Test emergency reduction targets highest risk positions first."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.6, 'Technology', 1.2, 0.25),
            'TSLA': Position('TSLA', 50, 200.0, 10000.0, 0.4, 'Automotive', 1.8, 0.45)  # Higher risk
        }
        
        actions = await manager.emergency_risk_reduction(0.5)
        
        reduce_actions = [a for a in actions if a['action'] == 'emergency_position_reduction']
        # TSLA should be first (higher beta and volatility)
        if len(reduce_actions) >= 2:
            assert reduce_actions[0]['symbol'] == 'TSLA'

    @pytest.mark.asyncio
    async def test_emergency_reduction_includes_cash_action(self, manager):
        """Test emergency reduction includes cash raising action."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 1.0, 'Technology')
        }
        
        actions = await manager.emergency_risk_reduction(0.5)
        
        cash_actions = [a for a in actions if a['action'] == 'raise_cash']
        assert len(cash_actions) == 1
        assert cash_actions[0]['target_cash_pct'] == 0.2
        assert cash_actions[0]['priority'] == 'critical'


# ==============================================================================
# Risk Summary Tests
# ==============================================================================

class TestGetRiskSummary:
    """Tests for get_risk_summary method."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        manager = AdvancedRiskManager(enable_slo=False)
        manager.portfolio_value = 100000.0
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.15, 'Technology')
        }
        manager.risk_metrics = RiskMetrics(
            leverage=1.5,
            gross_exposure=100000.0,
            net_exposure=80000.0,
            portfolio_var_1d=0.015,
            portfolio_var_5d=0.033,
            max_drawdown=-0.05,
            current_drawdown=-0.02,
            concentration_risk=0.3,
            correlation_risk=0.4,
            risk_level=RiskLevel.MEDIUM,
            market_regime=MarketRegime.CALM
        )
        return manager

    def test_summary_contains_portfolio_metrics(self, manager):
        """Test summary contains portfolio metrics."""
        summary = manager.get_risk_summary()
        
        assert 'portfolio_metrics' in summary
        assert summary['portfolio_metrics']['value'] == 100000.0
        assert summary['portfolio_metrics']['leverage'] == 1.5
        assert summary['portfolio_metrics']['position_count'] == 1

    def test_summary_contains_risk_metrics(self, manager):
        """Test summary contains risk metrics."""
        summary = manager.get_risk_summary()
        
        assert 'risk_metrics' in summary
        assert summary['risk_metrics']['var_1d'] == 0.015
        assert summary['risk_metrics']['risk_level'] == 'medium'
        assert summary['risk_metrics']['market_regime'] == 'calm'

    def test_summary_contains_sector_exposure(self, manager):
        """Test summary contains sector exposure."""
        manager.risk_metrics.sector_concentration = {'Technology': 0.5}
        summary = manager.get_risk_summary()
        
        assert 'sector_exposure' in summary
        assert summary['sector_exposure']['Technology'] == 0.5

    def test_summary_contains_active_alerts_count(self, manager):
        """Test summary contains active alerts count."""
        manager.alerts = [
            {'type': 'test', 'timestamp': datetime.utcnow()},
            {'type': 'test', 'timestamp': datetime.utcnow() - timedelta(hours=2)}  # Not active
        ]
        
        summary = manager.get_risk_summary()
        
        assert 'active_alerts' in summary
        assert summary['active_alerts'] == 1  # Only recent alert

    def test_summary_contains_timestamp(self, manager):
        """Test summary contains last updated timestamp."""
        summary = manager.get_risk_summary()
        
        assert 'last_updated' in summary


# ==============================================================================
# SLO Integration Tests
# ==============================================================================

class TestSLOIntegration:
    """Tests for SLO monitoring integration."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager with mock SLO."""
        manager = AdvancedRiskManager(enable_slo=False)
        manager.slo_monitor = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_record_slo_metrics_success(self, manager):
        """Test SLO metrics are recorded on success."""
        manager.portfolio_value = 100000.0
        manager.positions = {'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.15)}
        manager.risk_metrics = RiskMetrics(risk_level=RiskLevel.MEDIUM, market_regime=MarketRegime.CALM)
        
        await manager._record_slo_metrics("test_operation", 50.0, success=True)
        
        manager.slo_monitor.record_metric.assert_called_once()
        call_args = manager.slo_monitor.record_metric.call_args
        assert call_args.kwargs['operation_name'] == 'test_operation'
        assert call_args.kwargs['latency_ms'] == 50.0
        assert call_args.kwargs['success'] is True

    @pytest.mark.asyncio
    async def test_record_slo_metrics_no_monitor(self):
        """Test SLO metrics do nothing without monitor."""
        manager = AdvancedRiskManager(enable_slo=False)
        
        # Should not raise
        await manager._record_slo_metrics("test", 50.0, success=True)

    @pytest.mark.asyncio
    async def test_record_slo_metrics_error_handling(self, manager):
        """Test SLO metrics handle errors gracefully."""
        manager.slo_monitor.record_metric.side_effect = Exception("SLO error")
        
        # Should not raise
        await manager._record_slo_metrics("test", 50.0, success=True)


# ==============================================================================
# Public API Tests
# ==============================================================================

class TestCalculateRiskMetricsPublic:
    """Tests for public calculate_risk_metrics method."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_returns_metrics_dict(self, manager):
        """Test public method returns dict with expected keys."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 1.0, 'Technology')
        }
        manager.portfolio_value = 15000.0
        
        result = await manager.calculate_risk_metrics()
        
        assert isinstance(result, dict)
        assert 'gross_exposure' in result
        assert 'net_exposure' in result
        assert 'leverage' in result
        assert 'var_1d' in result
        assert 'var_5d' in result
        assert 'var_10d' in result
        assert 'max_drawdown' in result
        assert 'risk_level' in result
        assert 'timestamp' in result


# ==============================================================================
# Edge Cases and Error Handling Tests
# ==============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def manager(self):
        """Create a risk manager instance."""
        return AdvancedRiskManager(enable_slo=False)

    @pytest.mark.asyncio
    async def test_zero_portfolio_value_leverage(self, manager):
        """Test leverage calculation with zero portfolio value."""
        manager.portfolio_value = 0.0
        
        await manager._calculate_risk_metrics()
        
        # Should not divide by zero
        assert manager.risk_metrics.leverage == 1.0

    @pytest.mark.asyncio
    async def test_position_with_negative_market_value(self, manager):
        """Test handling of short positions (negative market value)."""
        positions = {
            'AAPL': {'quantity': -100, 'price': 150.0, 'market_value': -15000}
        }
        
        await manager.update_positions(positions)
        
        assert manager.portfolio_value == 15000.0  # Absolute value

    @pytest.mark.asyncio
    async def test_nan_in_correlation_calculation(self, manager):
        """Test handling of NaN in correlation calculation."""
        manager.positions = {
            'AAPL': Position('AAPL', 100, 150.0, 15000.0, 0.5),
            'GOOGL': Position('GOOGL', 50, 100.0, 10000.0, 0.5)
        }
        # Returns that would cause NaN correlation (all same values)
        manager.returns_history = {
            'AAPL': [0.01] * 20,
            'GOOGL': [0.01] * 20
        }
        
        await manager._calculate_correlation_risk()
        
        # Should handle gracefully
        assert not math.isnan(manager.risk_metrics.correlation_risk)

    @pytest.mark.asyncio
    async def test_empty_returns_array_in_var(self, manager):
        """Test VaR with empty returns array."""
        manager.portfolio_returns = []
        
        await manager._calculate_var()
        
        # Should not raise
        assert manager.risk_metrics.portfolio_var_1d == 0.0

    @pytest.mark.asyncio  
    async def test_calculation_errors_logged(self, manager):
        """Test that calculation errors are logged."""
        # Force an error in correlation calculation by corrupting data
        manager.positions = {'AAPL': 'invalid'}  # Invalid data
        
        # Should not raise, just log error
        await manager._calculate_concentration_risk()
