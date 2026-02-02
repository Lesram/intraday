"""
Extended comprehensive tests for backend.risk.risk_manager

Targets 70%+ coverage for:
- RiskMathUtils: Kelly fraction, EWMA volatility, VaR, CVaR
- AsyncRiskManager: Order risk checks, position limits, exposure
- Market hours utilities: is_market_hours, get_next_market_open
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from zoneinfo import ZoneInfo
import numpy as np

from backend.risk.risk_manager import (
    RiskMathUtils,
    AsyncRiskManager,
    is_market_hours,
    get_next_market_open,
    NYSE_HOLIDAYS,
    NYSE_EARLY_CLOSE,
    EPS,
    MIN_SAMPLES,
)
from backend.risk.types import OrderSpec, RiskDecision, RiskLimits
from backend.strategies.types import Side


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_returns():
    """Generate sample returns for VaR/CVaR calculations"""
    np.random.seed(42)
    return list(np.random.normal(0.001, 0.02, 100))


@pytest.fixture
def mock_order():
    """Create a mock order spec"""
    order = MagicMock(spec=OrderSpec)
    order.symbol = "AAPL"
    order.side = Side.BUY
    order.qty = Decimal("10")
    order.price = Decimal("150.00")
    return order


@pytest.fixture
def risk_manager():
    """Create an AsyncRiskManager with default settings"""
    with patch('backend.risk.risk_manager.get_settings') as mock_settings, \
         patch('backend.risk.risk_manager.get_risk_defaults') as mock_defaults, \
         patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics:
        
        mock_settings.return_value = MagicMock(TRADING_MODE="paper")
        mock_defaults.return_value = {
            "max_symbol_exposure": 0.15,
            "max_position_value": 1.0,
            "circuit_breaker_pct": 0.05
        }
        mock_metrics.return_value = MagicMock()
        
        return AsyncRiskManager()


# ============================================================================
# RISK MATH UTILS - KELLY FRACTION TESTS
# ============================================================================

class TestKellyFractionExtended:
    """Extended tests for Kelly fraction calculation"""
    
    def test_kelly_positive_mean_positive_variance(self):
        """Test Kelly with positive expected return"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=0.01,  # 1% mean return
            variance=0.04,     # 4% variance
        )
        
        assert result > 0
        # 0.01 / 0.04 = 0.25 capped at ceiling 0.2
        assert result == 0.2
        
    def test_kelly_negative_mean(self):
        """Test Kelly with negative expected return"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=-0.01,
            variance=0.04,
        )
        
        # Should return floor when mean is non-positive
        assert result == 0.0
        
    def test_kelly_zero_variance(self):
        """Test Kelly with near-zero variance"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=0.01,
            variance=1e-15,  # Below EPS
        )
        
        # Should return floor to avoid division by near-zero
        assert result == 0.0
        
    def test_kelly_ceiling(self):
        """Test Kelly ceiling is respected"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=0.10,  # High return
            variance=0.01,     # Low variance
            kelly_ceiling=0.2,
        )
        
        # 0.10 / 0.01 = 10, but should be clamped to ceiling
        assert result == 0.2
        
    def test_kelly_floor(self):
        """Test Kelly floor is respected"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=-0.01,
            variance=0.04,
            kelly_floor=0.05,
        )
        
        assert result == 0.05
        
    def test_kelly_within_bounds(self):
        """Test Kelly within floor and ceiling"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=0.005,  # 0.5% return
            variance=0.05,      # 5% variance
            kelly_floor=0.0,
            kelly_ceiling=0.5,
        )
        
        # 0.005 / 0.05 = 0.1
        assert abs(result - 0.1) < 0.0001


# ============================================================================
# RISK MATH UTILS - EWMA VOLATILITY TESTS
# ============================================================================

class TestEWMAVolatilityExtended:
    """Extended tests for EWMA volatility calculation"""
    
    def test_ewma_basic(self, sample_returns):
        """Test basic EWMA volatility calculation"""
        returns_array = np.array(sample_returns)
        result = RiskMathUtils.ewma_volatility(returns_array)
        
        assert result > 0
        assert isinstance(result, float)
        
    def test_ewma_insufficient_data(self):
        """Test EWMA with insufficient data"""
        result = RiskMathUtils.ewma_volatility(np.array([0.01]))
        
        # Should return fallback volatility
        assert result == 0.1
        
    def test_ewma_empty_data(self):
        """Test EWMA with empty data"""
        result = RiskMathUtils.ewma_volatility(np.array([]))
        
        assert result == 0.1
        
    def test_ewma_with_nan(self):
        """Test EWMA handles NaN values"""
        returns = np.array([0.01, np.nan, 0.02, 0.01, np.nan, 0.015, 0.01, 0.02, -0.01, 0.01])
        result = RiskMathUtils.ewma_volatility(returns)
        
        assert not np.isnan(result)
        assert result > 0
        
    def test_ewma_custom_lambda(self, sample_returns):
        """Test EWMA with custom lambda parameter"""
        returns_array = np.array(sample_returns)
        
        result_94 = RiskMathUtils.ewma_volatility(returns_array, lambda_param=0.94)
        result_97 = RiskMathUtils.ewma_volatility(returns_array, lambda_param=0.97)
        
        # Both should produce valid results
        assert result_94 > 0
        assert result_97 > 0


# ============================================================================
# RISK MATH UTILS - VAR TESTS
# ============================================================================

class TestParametricVaRExtended:
    """Extended tests for parametric VaR calculation"""
    
    def test_var_basic(self, sample_returns):
        """Test basic VaR calculation"""
        result = RiskMathUtils.parametric_var(sample_returns, confidence=0.05)
        
        assert isinstance(result, float)
        
    def test_var_insufficient_data(self):
        """Test VaR with insufficient data"""
        result = RiskMathUtils.parametric_var([0.01])
        
        assert result == 0.0
        
    def test_var_5_percent(self, sample_returns):
        """Test 5% VaR"""
        result = RiskMathUtils.parametric_var(sample_returns, confidence=0.05)
        assert isinstance(result, float)
        
    def test_var_1_percent(self, sample_returns):
        """Test 1% VaR"""
        result = RiskMathUtils.parametric_var(sample_returns, confidence=0.01)
        assert isinstance(result, float)
        
    def test_var_10_percent(self, sample_returns):
        """Test 10% VaR"""
        result = RiskMathUtils.parametric_var(sample_returns, confidence=0.10)
        assert isinstance(result, float)


# ============================================================================
# RISK MATH UTILS - CVAR TESTS
# ============================================================================

class TestHistoricalCVaRExtended:
    """Extended tests for historical CVaR calculation"""
    
    def test_cvar_basic(self, sample_returns):
        """Test basic CVaR calculation"""
        result = RiskMathUtils.historical_cvar(sample_returns, confidence=0.05)
        
        assert isinstance(result, float)
        
    def test_cvar_insufficient_data(self):
        """Test CVaR with insufficient data"""
        result = RiskMathUtils.historical_cvar([0.01] * 5)  # Less than 10
        
        assert result == 0.0
        
    def test_cvar_exactly_10_samples(self):
        """Test CVaR with exactly 10 samples"""
        returns = [0.01] * 8 + [-0.05, -0.03]
        result = RiskMathUtils.historical_cvar(returns, confidence=0.05)
        
        assert isinstance(result, float)
        
    def test_cvar_extreme_losses(self):
        """Test CVaR captures extreme tail losses"""
        returns = [0.01] * 45 + [-0.10] * 5  # 5 extreme losses
        result = RiskMathUtils.historical_cvar(returns, confidence=0.10)
        
        assert result > 0


# ============================================================================
# MARKET HOURS TESTS
# ============================================================================

class TestIsMarketHoursExtended:
    """Extended tests for is_market_hours function"""
    
    def test_market_open_930am(self):
        """Test exactly at market open"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 8, 9, 30, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is True
        
    def test_market_open_midday(self):
        """Test during midday trading"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 8, 12, 0, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is True
        
    def test_market_closed_929am(self):
        """Test one minute before open"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 8, 9, 29, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is False
        
    def test_market_closed_4pm(self):
        """Test exactly at market close"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 8, 16, 0, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is False
        
    def test_saturday(self):
        """Test Saturday"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 11, 11, 0, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is False
        
    def test_sunday(self):
        """Test Sunday"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 12, 11, 0, 0, tzinfo=et)
        
        result = is_market_hours(test_time)
        
        assert result is False
        
    def test_current_time_default(self):
        """Test with no argument uses current time"""
        # Just ensure it doesn't crash
        result = is_market_hours()
        
        assert isinstance(result, bool)


# ============================================================================
# GET NEXT MARKET OPEN TESTS
# ============================================================================

class TestGetNextMarketOpenExtended:
    """Extended tests for get_next_market_open function"""
    
    def test_next_open_before_930am(self):
        """Test before market open same day"""
        et = ZoneInfo("America/New_York")
        test_time = datetime(2025, 1, 8, 8, 0, 0, tzinfo=et)  # 8:00 AM
        
        result = get_next_market_open(test_time)
        
        result_et = result.astimezone(et)
        assert result_et.day == 8
        assert result_et.hour == 9
        assert result_et.minute == 30
        
    def test_next_open_default_time(self):
        """Test with no argument uses current time"""
        result = get_next_market_open()
        
        # Should return a future datetime
        assert result is not None
        assert isinstance(result, datetime)


# ============================================================================
# ASYNC RISK MANAGER TESTS
# ============================================================================

class TestAsyncRiskManagerExtended:
    """Extended tests for AsyncRiskManager"""
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters"""
        with patch('backend.risk.risk_manager.get_settings') as mock_settings, \
             patch('backend.risk.risk_manager.get_risk_defaults') as mock_defaults, \
             patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics:
            
            mock_settings.return_value = MagicMock(TRADING_MODE="paper")
            mock_defaults.return_value = {
                "max_symbol_exposure": 0.15,
                "max_position_value": 1.0,
                "circuit_breaker_pct": 0.05
            }
            mock_metrics.return_value = MagicMock()
            
            rm = AsyncRiskManager(
                max_position_per_symbol=5000,
                max_single_position_value=50000,
                max_portfolio_var=0.03,
            )
            
            assert rm.max_single_position_value == 50000
            
    def test_math_utils_attached(self, risk_manager):
        """Test RiskMathUtils is attached"""
        assert risk_manager.math_utils is not None
        assert isinstance(risk_manager.math_utils, RiskMathUtils)
        
    def test_halted_symbols_empty_initially(self, risk_manager):
        """Test halted symbols is empty on init"""
        assert risk_manager.halted_symbols == set()


# ============================================================================
# CONSTANTS TESTS
# ============================================================================

class TestConstantsExtended:
    """Extended tests for module constants"""
    
    def test_eps_value(self):
        """Test EPS specific value"""
        assert EPS == 1e-12
        
    def test_min_samples_value(self):
        """Test MIN_SAMPLES specific value"""
        assert MIN_SAMPLES == 30
        
    def test_holidays_2025(self):
        """Test 2025 holidays are included"""
        # New Year's 2025
        assert datetime(2025, 1, 1).date() in NYSE_HOLIDAYS
        
    def test_holidays_2026(self):
        """Test 2026 holidays are included"""
        # Christmas 2026
        assert datetime(2026, 12, 25).date() in NYSE_HOLIDAYS
        
    def test_early_close_2025(self):
        """Test 2025 early close days"""
        # Day before Independence Day 2025
        assert datetime(2025, 7, 3).date() in NYSE_EARLY_CLOSE


# ============================================================================
# EDGE CASES
# ============================================================================

class TestRiskMathEdgeCases:
    """Edge case tests for risk math"""
    
    def test_kelly_zero_mean_zero_variance(self):
        """Test Kelly with all zeros"""
        result = RiskMathUtils.kelly_fraction(
            mean_return=0.0,
            variance=0.0,
        )
        
        assert result == 0.0
        
    def test_ewma_two_values(self):
        """Test EWMA with exactly 2 values"""
        returns = np.array([0.01, 0.02])
        result = RiskMathUtils.ewma_volatility(returns)
        
        assert result > 0
        
    def test_var_empty_list(self):
        """Test VaR with empty list"""
        result = RiskMathUtils.parametric_var([])
        
        assert result == 0.0
        
    def test_cvar_empty_list(self):
        """Test CVaR with empty list"""
        result = RiskMathUtils.historical_cvar([])
        
        assert result == 0.0
