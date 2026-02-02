"""
Phase 7: Comprehensive tests for InstitutionalAnalytics (trade_analytics_service)
Coverage target: 85%+
Tests Sharpe ratio, max drawdown, profit factor, and other institutional metrics.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, UTC
from decimal import Decimal
import numpy as np


# ============================================================================
# INSTITUTIONAL ANALYTICS CLASS TESTS
# ============================================================================

class TestInstitutionalAnalyticsInit:
    """Test InstitutionalAnalytics initialization."""
    
    def test_init_with_db(self):
        """Test InstitutionalAnalytics initializes with database session."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        assert analytics.db is mock_db
    
    def test_module_imports(self):
        """Test module imports correctly."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        assert InstitutionalAnalytics is not None


# ============================================================================
# SHARPE RATIO TESTS
# ============================================================================

class TestCalculateSharpeRatio:
    """Test Sharpe Ratio calculation."""
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_empty_returns(self):
        """Test Sharpe ratio with no returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_sharpe_ratio([])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_single_return(self):
        """Test Sharpe ratio with single return (needs >= 2)."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_sharpe_ratio([0.05])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_zero_std_dev(self):
        """Test Sharpe ratio when all returns are the same."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # All identical returns = zero std deviation
        result = await analytics.calculate_sharpe_ratio([0.01, 0.01, 0.01])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_positive_returns(self):
        """Test Sharpe ratio with positive returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Good returns with low volatility should give positive Sharpe
        returns = [0.02, 0.03, 0.01, 0.02, 0.025]
        result = await analytics.calculate_sharpe_ratio(returns)
        
        assert result > 0  # Positive returns should give positive Sharpe
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_negative_returns(self):
        """Test Sharpe ratio with negative returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Negative returns should give negative Sharpe
        returns = [-0.02, -0.03, -0.01, -0.02, -0.025]
        result = await analytics.calculate_sharpe_ratio(returns)
        
        assert result < 0


# ============================================================================
# SORTINO RATIO TESTS
# ============================================================================

class TestCalculateSortinoRatio:
    """Test Sortino Ratio calculation."""
    
    @pytest.mark.asyncio
    async def test_sortino_ratio_empty_returns(self):
        """Test Sortino ratio with no returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_sortino_ratio([])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sortino_ratio_single_return(self):
        """Test Sortino ratio with single return."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_sortino_ratio([0.05])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sortino_ratio_no_negative_returns(self):
        """Test Sortino ratio when no negative returns exist."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # All positive returns = no downside deviation
        result = await analytics.calculate_sortino_ratio([0.01, 0.02, 0.03])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_sortino_ratio_mixed_returns(self):
        """Test Sortino ratio with mixed returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        returns = [0.05, -0.02, 0.03, -0.01, 0.04]
        result = await analytics.calculate_sortino_ratio(returns)
        
        # Should return a valid number
        assert isinstance(result, float)


# ============================================================================
# MAX DRAWDOWN TESTS
# ============================================================================

class TestCalculateMaxDrawdown:
    """Test Maximum Drawdown calculation."""
    
    @pytest.mark.asyncio
    async def test_max_drawdown_empty_curve(self):
        """Test max drawdown with empty equity curve."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_max_drawdown([])
        
        assert result['max_dd'] == 0.0
        assert result['max_dd_dollars'] == 0.0
    
    @pytest.mark.asyncio
    async def test_max_drawdown_single_point(self):
        """Test max drawdown with single point."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_max_drawdown([100000])
        
        assert result['max_dd'] == 0.0
    
    @pytest.mark.asyncio
    async def test_max_drawdown_always_increasing(self):
        """Test max drawdown when equity always increases."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Perfect equity curve - never goes down
        equity = [100000, 105000, 110000, 115000, 120000]
        result = await analytics.calculate_max_drawdown(equity)
        
        assert result['max_dd'] == 0.0
    
    @pytest.mark.asyncio
    async def test_max_drawdown_with_decline(self):
        """Test max drawdown with a decline in equity."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Equity curve with 10% drawdown
        equity = [100000, 110000, 99000, 105000]  # Peak 110k, trough 99k
        result = await analytics.calculate_max_drawdown(equity)
        
        # Max DD = (110000 - 99000) / 110000 = 10%
        assert result['max_dd'] == pytest.approx(10.0, rel=0.1)
        assert result['max_dd_dollars'] == pytest.approx(11000, rel=0.1)
    
    @pytest.mark.asyncio
    async def test_max_drawdown_duration(self):
        """Test max drawdown calculates duration."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        equity = [100000, 110000, 100000, 95000, 105000]
        result = await analytics.calculate_max_drawdown(equity)
        
        assert 'duration_days' in result
        assert result['duration_days'] >= 0


# ============================================================================
# PROFIT FACTOR TESTS
# ============================================================================

class TestCalculateProfitFactor:
    """Test Profit Factor calculation."""
    
    @pytest.mark.asyncio
    async def test_profit_factor_no_trades(self):
        """Test profit factor with no trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_profit_factor([], [])
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_profit_factor_only_winners(self):
        """Test profit factor with only winning trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_profit_factor([100, 200, 150], [])
        
        # No losses = capped at 999.99
        assert result == 999.99
    
    @pytest.mark.asyncio
    async def test_profit_factor_only_losers(self):
        """Test profit factor with only losing trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_profit_factor([], [-100, -200])
        
        # No profits = 0 / losses = 0
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_profit_factor_mixed_trades(self):
        """Test profit factor with mixed wins and losses."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Gross profit = 450, gross loss = 150
        result = await analytics.calculate_profit_factor([100, 200, 150], [-50, -100])
        
        # Profit factor = 450 / 150 = 3.0
        assert result == pytest.approx(3.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_profit_factor_equal_wins_losses(self):
        """Test profit factor when wins equal losses."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_profit_factor([100], [-100])
        
        # Profit factor = 100 / 100 = 1.0
        assert result == pytest.approx(1.0, rel=0.01)


# ============================================================================
# EXPECTANCY TESTS
# ============================================================================

class TestCalculateExpectancy:
    """Test Expectancy calculation."""
    
    @pytest.mark.asyncio
    async def test_expectancy_zero_win_rate(self):
        """Test expectancy with 0% win rate."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_expectancy(0.0, 0.0, -100.0)
        
        # 0% wins, 100% losses of -$100 each = -$100 expectancy
        assert result == pytest.approx(-100.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_expectancy_100_win_rate(self):
        """Test expectancy with 100% win rate."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_expectancy(100.0, 200.0, 0.0)
        
        # 100% wins of $200 each = $200 expectancy
        assert result == pytest.approx(200.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_expectancy_50_win_rate(self):
        """Test expectancy with 50% win rate."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # 50% win rate, $200 avg win, -$100 avg loss
        result = await analytics.calculate_expectancy(50.0, 200.0, -100.0)
        
        # (0.5 * 200) + (0.5 * -100) = 100 - 50 = 50
        assert result == pytest.approx(50.0, rel=0.01)


# ============================================================================
# CALMAR RATIO TESTS
# ============================================================================

class TestCalculateCalmarRatio:
    """Test Calmar Ratio calculation."""
    
    @pytest.mark.asyncio
    async def test_calmar_ratio_no_returns(self):
        """Test Calmar ratio with no returns."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_calmar_ratio([], 10.0)
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_calmar_ratio_zero_drawdown(self):
        """Test Calmar ratio with zero drawdown."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_calmar_ratio([0.01, 0.02], 0.0)
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_calmar_ratio_with_values(self):
        """Test Calmar ratio with valid values."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        returns = [0.01] * 252  # 1% daily for a year
        result = await analytics.calculate_calmar_ratio(returns, 10.0)
        
        assert isinstance(result, float)


# ============================================================================
# RECOVERY FACTOR TESTS
# ============================================================================

class TestCalculateRecoveryFactor:
    """Test Recovery Factor calculation."""
    
    @pytest.mark.asyncio
    async def test_recovery_factor_zero_drawdown(self):
        """Test recovery factor with zero drawdown."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_recovery_factor(10000.0, 0.0)
        
        # Capped at 999.99 when no drawdown
        assert result == 999.99
    
    @pytest.mark.asyncio
    async def test_recovery_factor_zero_profit_zero_drawdown(self):
        """Test recovery factor with zero profit and zero drawdown."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_recovery_factor(0.0, 0.0)
        
        assert result == 0.0
    
    @pytest.mark.asyncio
    async def test_recovery_factor_positive(self):
        """Test recovery factor with positive profit."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # $20,000 profit with $5,000 max drawdown = 4.0 recovery factor
        result = await analytics.calculate_recovery_factor(20000.0, 5000.0)
        
        assert result == pytest.approx(4.0, rel=0.01)


# ============================================================================
# STREAKS TESTS
# ============================================================================

class TestCalculateStreaks:
    """Test win/loss streak calculation."""
    
    @pytest.mark.asyncio
    async def test_streaks_empty_trades(self):
        """Test streaks with no trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_streaks([])
        
        assert result['max_win_streak'] == 0
        assert result['max_loss_streak'] == 0
        assert result['current_streak'] == 0
        assert result['current_streak_type'] == 'none'
    
    @pytest.mark.asyncio
    async def test_streaks_all_wins(self):
        """Test streaks with all winning trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_streaks([100, 200, 150, 50, 75])
        
        assert result['max_win_streak'] == 5
        assert result['max_loss_streak'] == 0
        assert result['current_streak'] == 5
        assert result['current_streak_type'] == 'win'
    
    @pytest.mark.asyncio
    async def test_streaks_all_losses(self):
        """Test streaks with all losing trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_streaks([-100, -200, -150, -50])
        
        assert result['max_win_streak'] == 0
        assert result['max_loss_streak'] == 4
        assert result['current_streak'] == 4
        assert result['current_streak_type'] == 'loss'
    
    @pytest.mark.asyncio
    async def test_streaks_alternating(self):
        """Test streaks with alternating wins and losses."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_streaks([100, -50, 75, -25, 200])
        
        # Each streak is 1
        assert result['max_win_streak'] == 1
        assert result['max_loss_streak'] == 1
        assert result['current_streak'] == 1
    
    @pytest.mark.asyncio
    async def test_streaks_with_breakeven(self):
        """Test streaks with break-even trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Break-even resets streak
        result = await analytics.calculate_streaks([100, 100, 0, 100])
        
        assert result['max_win_streak'] == 2  # First two wins
        assert result['current_streak'] == 1  # After break-even


# ============================================================================
# COMPREHENSIVE METRICS TESTS
# ============================================================================

class TestCalculateComprehensiveMetrics:
    """Test the main calculate_comprehensive_metrics method."""
    
    @pytest.mark.asyncio
    async def test_comprehensive_metrics_no_trades(self):
        """Test comprehensive metrics with no trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_comprehensive_metrics()
        
        # Should return empty metrics
        assert result['totalTrades'] == 0
        assert result['sharpeRatio'] == 0
        assert result['profitFactor'] == 0
    
    @pytest.mark.asyncio
    async def test_comprehensive_metrics_with_trades(self):
        """Test comprehensive metrics with realized trades."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = AsyncMock()
        
        # Create mock realized trades
        mock_trade1 = MagicMock()
        mock_trade1.realized_pnl = Decimal("100.00")
        mock_trade1.realized_pnl_percent = Decimal("5.0")
        mock_trade1.close_date = datetime.now(UTC)
        mock_trade1.open_date = datetime.now(UTC)
        mock_trade1.qty = Decimal("10")
        mock_trade1.open_price = Decimal("100")
        mock_trade1.close_price = Decimal("110")
        mock_trade1.symbol = "AAPL"
        
        mock_trade2 = MagicMock()
        mock_trade2.realized_pnl = Decimal("-50.00")
        mock_trade2.realized_pnl_percent = Decimal("-2.5")
        mock_trade2.close_date = datetime.now(UTC)
        mock_trade2.open_date = datetime.now(UTC)
        mock_trade2.qty = Decimal("10")
        mock_trade2.open_price = Decimal("100")
        mock_trade2.close_price = Decimal("95")
        mock_trade2.symbol = "MSFT"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_trade1, mock_trade2]
        mock_db.execute.return_value = mock_result
        
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_comprehensive_metrics()
        
        assert result['totalTrades'] == 2
        assert result['winningTrades'] == 1
        assert result['losingTrades'] == 1
        assert result['winRate'] == 50.0
    
    @pytest.mark.asyncio
    async def test_comprehensive_metrics_with_filters(self):
        """Test comprehensive metrics with date and symbol filters."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        analytics = InstitutionalAnalytics(mock_db)
        
        result = await analytics.calculate_comprehensive_metrics(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            symbol="AAPL",
            user_id="admin"
        )
        
        assert result['totalTrades'] == 0


class TestEmptyMetrics:
    """Test empty metrics response."""
    
    def test_empty_metrics_structure(self):
        """Test empty metrics has all required fields."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        result = analytics._empty_metrics()
        
        expected_keys = [
            'sharpeRatio', 'sortinoRatio', 'calmarRatio',
            'maxDrawdown', 'maxDrawdownDollars', 'maxDrawdownDuration',
            'profitFactor', 'expectancy', 'recoveryFactor',
            'maxWinStreak', 'maxLossStreak', 'currentStreak',
            'monthlyReturns', 'rMultiples', 'avgTradeDurationHours',
            'totalTrades', 'winningTrades', 'losingTrades', 'winRate'
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


class TestEquityCurveBuilder:
    """Test equity curve building."""
    
    def test_build_equity_curve(self):
        """Test _build_equity_curve helper."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        pnls = [100, -50, 75, -25, 200]
        curve = analytics._build_equity_curve(pnls, initial_capital=100000)
        
        assert curve[0] == 100000
        assert curve[1] == 100100  # +100
        assert curve[2] == 100050  # -50
        assert len(curve) == 6  # Initial + 5 trades


class TestHelperMethods:
    """Test helper methods in analytics service."""
    
    @pytest.mark.asyncio
    async def test_calculate_monthly_returns(self):
        """Test monthly returns calculation."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        # Create trades with dates
        mock_trade1 = MagicMock()
        mock_trade1.close_date = datetime(2024, 1, 15)
        mock_trade1.realized_pnl = Decimal("100")
        mock_trade1.open_price = Decimal("100")
        
        mock_trade2 = MagicMock()
        mock_trade2.close_date = datetime(2024, 1, 20)
        mock_trade2.realized_pnl = Decimal("50")
        mock_trade2.open_price = Decimal("100")
        
        mock_trade3 = MagicMock()
        mock_trade3.close_date = datetime(2024, 2, 10)
        mock_trade3.realized_pnl = Decimal("-75")
        mock_trade3.open_price = Decimal("100")
        
        result = await analytics.calculate_monthly_returns([mock_trade1, mock_trade2, mock_trade3])
        
        # Should have returns for January and February
        assert isinstance(result, list)
    
    @pytest.mark.asyncio
    async def test_calculate_r_multiples(self):
        """Test R-multiple calculation."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        mock_trade = MagicMock()
        mock_trade.realized_pnl = Decimal("100")
        mock_trade.open_price = Decimal("100")
        mock_trade.qty = Decimal("10")
        
        result = await analytics.calculate_r_multiples([mock_trade])
        
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_calculate_avg_trade_duration(self):
        """Test average trade duration calculation."""
        from backend.services.trade_analytics_service import InstitutionalAnalytics
        
        mock_db = MagicMock()
        analytics = InstitutionalAnalytics(mock_db)
        
        mock_trade = MagicMock()
        mock_trade.open_date = datetime(2024, 1, 1, 10, 0, 0)
        mock_trade.close_date = datetime(2024, 1, 1, 14, 0, 0)  # 4 hours later
        
        result = await analytics.calculate_avg_trade_duration([mock_trade])
        
        assert result >= 0
