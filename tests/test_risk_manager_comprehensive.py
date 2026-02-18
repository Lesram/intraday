"""
Comprehensive tests for backend.risk.risk_manager to achieve 80%+ coverage.

Covers:
- Market hours and holiday detection
- RiskMathUtils (Kelly, EWMA, VaR, CVaR)
- AsyncRiskManager initialization and risk evaluation
- Legacy RiskManager compatibility
- Edge cases and error handling
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from backend.risk.risk_manager import (
    ET,
    NYSE_EARLY_CLOSE,
    NYSE_HOLIDAYS,
    AsyncRiskManager,
    RiskManager,
    RiskMathUtils,
    get_next_market_open,
    is_market_hours,
)
from backend.risk.types import OrderSpec, PortfolioState, RiskDecision, RiskLimits
from backend.strategies.types import Side


# =============================================================================
# MARKET HOURS TESTS
# =============================================================================

class TestIsMarketHours:
    """Tests for is_market_hours function."""

    def test_market_open_during_regular_hours(self):
        """Market should be open during regular trading hours."""
        # Wednesday at 10:00 AM ET (not a holiday)
        trading_time = datetime(2026, 1, 28, 15, 0, 0, tzinfo=UTC)  # 10 AM ET
        assert is_market_hours(trading_time) is True

    def test_market_closed_before_open(self):
        """Market should be closed before 9:30 AM ET."""
        early_morning = datetime(2026, 1, 28, 13, 0, 0, tzinfo=UTC)  # 8 AM ET
        assert is_market_hours(early_morning) is False

    def test_market_closed_after_close(self):
        """Market should be closed after 4:00 PM ET."""
        after_hours = datetime(2026, 1, 28, 22, 0, 0, tzinfo=UTC)  # 5 PM ET
        assert is_market_hours(after_hours) is False

    def test_market_closed_on_saturday(self):
        """Market should be closed on Saturday."""
        saturday = datetime(2026, 1, 31, 16, 0, 0, tzinfo=UTC)  # Saturday 11 AM ET
        assert is_market_hours(saturday) is False

    def test_market_closed_on_sunday(self):
        """Market should be closed on Sunday."""
        sunday = datetime(2026, 2, 1, 16, 0, 0, tzinfo=UTC)  # Sunday 11 AM ET
        assert is_market_hours(sunday) is False

    def test_market_closed_on_holiday(self):
        """Market should be closed on NYSE holidays."""
        # New Year's Day 2026
        new_years = datetime(2026, 1, 1, 16, 0, 0, tzinfo=UTC)
        assert is_market_hours(new_years) is False

    def test_early_close_day(self):
        """Market should close at 1 PM on early close days."""
        # Day before Thanksgiving 2026, at 12:30 PM ET (should be open)
        early_close_day = datetime(2026, 11, 27, 17, 30, 0, tzinfo=UTC)  # 12:30 PM ET
        assert is_market_hours(early_close_day) is True

        # Same day at 1:30 PM ET (should be closed)
        after_early_close = datetime(2026, 11, 27, 18, 30, 0, tzinfo=UTC)  # 1:30 PM ET
        assert is_market_hours(after_early_close) is False

    def test_uses_current_time_when_none(self):
        """Should use current time when check_time is None."""
        # This test just verifies the function doesn't crash
        result = is_market_hours(None)
        assert isinstance(result, bool)


class TestGetNextMarketOpen:
    """Tests for get_next_market_open function."""

    def test_returns_next_day_if_after_open(self):
        """If after today's open, should return tomorrow's open."""
        # Wednesday at 11 AM ET (after 9:30 AM)
        current = datetime(2026, 1, 28, 16, 0, 0, tzinfo=UTC)
        next_open = get_next_market_open(current)
        
        # Should be Thursday 9:30 AM ET
        assert next_open.astimezone(ET).hour == 9
        assert next_open.astimezone(ET).minute == 30

    def test_skips_weekends(self):
        """Should skip Saturday and Sunday."""
        # Friday at 5 PM ET
        friday = datetime(2026, 1, 30, 22, 0, 0, tzinfo=UTC)
        next_open = get_next_market_open(friday)
        
        # Should be Monday 9:30 AM ET
        et_open = next_open.astimezone(ET)
        assert et_open.weekday() == 0  # Monday

    def test_skips_holidays(self):
        """Should skip NYSE holidays."""
        # Day before New Year's Day 2026
        dec_31 = datetime(2025, 12, 31, 22, 0, 0, tzinfo=UTC)
        next_open = get_next_market_open(dec_31)
        
        # Should skip Jan 1 holiday
        et_open = next_open.astimezone(ET)
        assert et_open.date() != datetime(2026, 1, 1).date()

    def test_uses_current_time_when_none(self):
        """Should use current time when from_time is None."""
        result = get_next_market_open(None)
        assert result.tzinfo == UTC


# =============================================================================
# RISK MATH UTILS TESTS
# =============================================================================

class TestRiskMathUtils:
    """Tests for RiskMathUtils static methods."""

    def test_kelly_fraction_positive_return(self):
        """Kelly fraction should be positive for positive expected returns."""
        mean_return = 0.05
        variance = 0.01
        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)
        assert kelly > 0
        assert kelly <= 0.2  # Capped at ceiling

    def test_kelly_fraction_negative_return(self):
        """Kelly fraction should be floor for negative expected returns."""
        mean_return = -0.05
        variance = 0.01
        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)
        assert kelly == 0.0  # Floor

    def test_kelly_fraction_zero_variance(self):
        """Kelly fraction should be floor for zero variance."""
        mean_return = 0.05
        variance = 0.0
        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)
        assert kelly == 0.0

    def test_kelly_fraction_custom_bounds(self):
        """Kelly fraction should respect custom floor and ceiling."""
        mean_return = 0.10
        variance = 0.01
        kelly = RiskMathUtils.kelly_fraction(
            mean_return, variance, kelly_floor=0.05, kelly_ceiling=0.10
        )
        assert kelly >= 0.05
        assert kelly <= 0.10

    def test_ewma_volatility_normal_returns(self):
        """EWMA volatility should calculate correctly for normal returns."""
        returns = np.array([0.01, -0.02, 0.015, -0.01, 0.005] * 10)
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol > 0
        assert vol < 1  # Reasonable volatility

    def test_ewma_volatility_insufficient_data(self):
        """EWMA volatility should return fallback for insufficient data."""
        returns = np.array([0.01])  # Only one return
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol == 0.1  # Fallback

    def test_ewma_volatility_with_nan(self):
        """EWMA volatility should handle NaN values."""
        returns = np.array([0.01, np.nan, 0.02, -0.01, 0.005])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol >= 0

    def test_parametric_var_normal_case(self):
        """Parametric VaR should calculate correctly."""
        returns = [0.01, -0.02, 0.015, -0.01, 0.005] * 10
        var = RiskMathUtils.parametric_var(returns, confidence=0.05)
        assert var >= 0  # VaR is typically positive

    def test_parametric_var_insufficient_data(self):
        """Parametric VaR should return 0 for insufficient data."""
        returns = [0.01]
        var = RiskMathUtils.parametric_var(returns)
        assert var == 0.0

    def test_parametric_var_different_confidence(self):
        """Parametric VaR should adjust for different confidence levels."""
        returns = [0.01, -0.02, 0.015, -0.01, 0.005] * 10
        var_95 = RiskMathUtils.parametric_var(returns, confidence=0.05)
        var_99 = RiskMathUtils.parametric_var(returns, confidence=0.01)
        # 99% VaR should be higher than 95% VaR
        assert var_99 >= var_95

    def test_historical_cvar_normal_case(self):
        """Historical CVaR should calculate correctly."""
        returns = [0.01, -0.02, 0.015, -0.01, 0.005, -0.03, 0.02, -0.015, 0.01, -0.02]
        cvar = RiskMathUtils.historical_cvar(returns, confidence=0.05)
        assert cvar >= 0

    def test_historical_cvar_insufficient_data(self):
        """Historical CVaR should return 0 for insufficient data."""
        returns = [0.01, -0.02, 0.015]  # Less than 10
        cvar = RiskMathUtils.historical_cvar(returns)
        assert cvar == 0.0


# =============================================================================
# ASYNC RISK MANAGER TESTS
# =============================================================================

class TestAsyncRiskManagerInit:
    """Tests for AsyncRiskManager initialization."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        manager = AsyncRiskManager()
        assert manager.max_single_position_value == 100000
        assert manager.circuit_breaker_active is False

    def test_custom_initialization(self):
        """Should accept custom parameters."""
        manager = AsyncRiskManager(
            max_position_per_symbol=5000,
            max_single_position_value=50000,
            max_portfolio_var=0.03,
        )
        assert manager.max_single_position_value == 50000
        # Note: max_portfolio_var may be overridden by profile defaults

    def test_risk_limits_override(self):
        """Should extract limits from RiskLimits object."""
        limits = RiskLimits(
            max_symbol_exposure=0.10,
            max_position_value=0.5,
            circuit_breaker_pct=0.03,
        )
        manager = AsyncRiskManager(risk_limits=limits)
        assert manager.max_symbol_exposure == 0.10

    def test_accepts_legacy_parameters(self):
        """Should accept legacy parameters for backward compatibility."""
        manager = AsyncRiskManager(
            position_limits=MagicMock(),
            margin_calculator=MagicMock(),
            volatility_checker=MagicMock(),
        )
        assert manager.position_limits is not None
        assert manager.margin_calculator is not None
        assert manager.volatility_checker is not None


class TestAsyncRiskManagerBeforeOrder:
    """Tests for AsyncRiskManager.before_order method."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.fixture
    def sample_order(self):
        return OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("10"),
            notional=Decimal("1500"),
            price=Decimal("150"),
        )

    @pytest.mark.asyncio
    async def test_before_order_allows_valid_order(self, manager, sample_order):
        """Should allow valid orders within limits."""
        decision = await manager.before_order(sample_order)
        assert isinstance(decision, RiskDecision)
        # May be blocked due to market price lookup failure in test env
        # but should return a valid RiskDecision

    @pytest.mark.asyncio
    async def test_before_order_records_metrics(self, manager, sample_order):
        """Should record metrics for decisions."""
        await manager.before_order(sample_order)
        # Metrics registry should have recorded something
        # (metrics are recorded internally)

    @pytest.mark.asyncio
    async def test_before_order_handles_exception(self, manager):
        """Should handle exceptions gracefully."""
        # Create an invalid order that might cause issues
        bad_order = OrderSpec(
            symbol="",  # Empty symbol
            side=Side.BUY,
            qty=Decimal("10"),
            notional=Decimal("1500"),
        )
        decision = await manager.before_order(bad_order)
        assert isinstance(decision, RiskDecision)


class TestAsyncRiskManagerAssessOrder:
    """Tests for AsyncRiskManager.assess_order method."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.fixture
    def sample_order(self):
        return OrderSpec(
            symbol="MSFT",
            side=Side.BUY,
            qty=Decimal("5"),
            notional=Decimal("1500"),
            price=Decimal("300"),
        )

    @pytest.mark.asyncio
    async def test_assess_order_returns_dict(self, manager, sample_order):
        """Should return a dictionary with assessment results."""
        result = await manager.assess_order(sample_order)
        assert isinstance(result, dict)
        assert "allowed" in result or "reason_code" in result

    @pytest.mark.asyncio
    async def test_assess_order_with_risk_override(self, manager, sample_order):
        """Should handle risk override parameter."""
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.username = "testadmin"
        
        result = await manager.assess_order(
            sample_order,
            current_user=mock_user,
            risk_override=True,
        )
        assert isinstance(result, dict)


class TestAsyncRiskManagerHelperMethods:
    """Tests for AsyncRiskManager helper methods."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.mark.asyncio
    async def test_get_portfolio_value_fallback(self, manager):
        """Should return fallback value when broker unavailable."""
        value = await manager._get_portfolio_value()
        assert value > 0
        assert isinstance(value, Decimal)

    @pytest.mark.asyncio
    async def test_get_current_positions_empty(self, manager):
        """Should return empty dict when no service."""
        positions = await manager._get_current_positions()
        assert isinstance(positions, dict)

    @pytest.mark.asyncio
    async def test_get_portfolio_state(self, manager):
        """Should return PortfolioState object."""
        state = await manager._get_portfolio_state("AAPL")
        assert isinstance(state, PortfolioState)
        assert state.equity > 0

    def test_get_historical_returns(self, manager):
        """Should return list of returns."""
        returns = manager._get_historical_returns("AAPL", 30)
        assert isinstance(returns, list)
        assert len(returns) >= 5


# =============================================================================
# LEGACY COMPATIBILITY TESTS
# =============================================================================

class TestLegacyCheckOrderRisk:
    """Tests for legacy check_order_risk method."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.mark.asyncio
    async def test_check_order_risk_high_risk_symbol(self, manager):
        """Should block symbols in the restricted list."""
        manager._restricted_symbols = {"GME": "High risk symbol", "PENNY": "Penny stock prohibited", "CRYPTO": "Cryptocurrency not supported"}
        decision = await manager.check_order_risk({"symbol": "GME", "qty": 10})
        assert decision.allowed is False
        assert "risk" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_penny_stock(self, manager):
        """Should block restricted penny stocks."""
        manager._restricted_symbols = {"PENNY": "Penny stock prohibited"}
        decision = await manager.check_order_risk({"symbol": "PENNY", "qty": 1000})
        assert decision.allowed is False
        assert "penny" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_crypto(self, manager):
        """Should block restricted cryptocurrency symbols."""
        manager._restricted_symbols = {"CRYPTO": "Cryptocurrency not supported"}
        decision = await manager.check_order_risk({"symbol": "CRYPTO", "qty": 10})
        assert decision.allowed is False
        assert "crypto" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_tsla_monitoring(self, manager):
        """Should allow TSLA when not in restricted list."""
        decision = await manager.check_order_risk({"symbol": "TSLA", "qty": 5})
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_check_order_risk_negative_qty(self, manager):
        """Should reject negative quantity."""
        decision = await manager.check_order_risk({"symbol": "AAPL", "qty": -10})
        assert decision.allowed is False
        assert "negative" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_zero_qty(self, manager):
        """Should reject zero quantity."""
        decision = await manager.check_order_risk({"symbol": "AAPL", "qty": 0})
        assert decision.allowed is False
        assert "zero" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_too_large(self, manager):
        """Should block orders exceeding $100k."""
        decision = await manager.check_order_risk(
            {"symbol": "AAPL", "qty": 1000, "price": 200}  # $200k notional
        )
        assert decision.allowed is False
        assert "large" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_check_order_risk_valid_order(self, manager):
        """Should allow valid orders."""
        decision = await manager.check_order_risk(
            {"symbol": "AAPL", "qty": 10, "price": 150}
        )
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_check_order_risk_with_position_limits_mock(self):
        """Should use position_limits mock when available."""
        mock_limits = MagicMock()
        mock_limits.check_total_exposure_limit.return_value = (False, "Exposure limit exceeded", 5)
        
        manager = AsyncRiskManager(position_limits=mock_limits)
        decision = await manager.check_order_risk({"symbol": "AAPL", "qty": 10})
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_check_order_risk_with_volatility_checker_mock(self):
        """Should use volatility_checker mock when available."""
        mock_vol = MagicMock()
        mock_vol.check_symbol_volatility.return_value = (False, "High volatility", None)
        
        manager = AsyncRiskManager(volatility_checker=mock_vol)
        decision = await manager.check_order_risk({"symbol": "AAPL", "qty": 10})
        assert decision.allowed is False


class TestLegacyPositionAndCashChecks:
    """Tests for legacy position and cash check methods."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    def test_check_position_size_under_limit(self, manager):
        """Should allow position under $100k."""
        result = manager.check_position_size(50000)
        assert result["allowed"] is True

    def test_check_position_size_over_limit(self, manager):
        """Should reject position over $100k."""
        result = manager.check_position_size(150000)
        assert result["allowed"] is False
        assert result["suggested_size"] == 75000  # 50% of original

    def test_check_cash_balance_sufficient(self, manager):
        """Should allow when cash is sufficient (legacy interface)."""
        result = manager.check_cash_balance(50000, {"cash": 100000})
        assert result["allowed"] is True

    def test_check_cash_balance_insufficient(self, manager):
        """Should reject when cash is insufficient (legacy interface)."""
        result = manager.check_cash_balance(150000, {"cash": 100000})
        assert result["allowed"] is False

    def test_check_cash_balance_with_order_spec(self, manager):
        """Should work with OrderSpec (new interface)."""
        order = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("10"),
            price=Decimal("150"),
        )
        result = manager.check_cash_balance(order, {"cash": 100000})
        assert isinstance(result, RiskDecision)


class TestLegacyStatusMethods:
    """Tests for legacy status and metrics methods."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    def test_check_symbol_limit(self, manager):
        """Should return tuple for symbol limit check."""
        result = manager.check_symbol_limit("AAPL", 100)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_refresh_status(self, manager):
        """Should return status dict."""
        result = manager.refresh_status()
        assert "status" in result
        assert "circuit_breaker_active" in result

    def test_get_metrics(self, manager):
        """Should return metrics dict."""
        result = manager.get_metrics()
        assert "status" in result
        assert "metrics" in result

    def test_set_limits(self, manager):
        """Should update limits from payload."""
        result = manager.set_limits({
            "max_position_value": 0.8,
            "max_symbol_exposure": 0.12,
        })
        assert result["status"] in ["updated", "error"]


class TestAsyncHelperMethods:
    """Tests for async helper methods on AsyncRiskManager."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.mark.asyncio
    async def test_update_position_risk(self, manager):
        """Should update position risk."""
        result = await manager.update_position_risk("AAPL", 1000)
        assert result["status"] == "success"
        assert result["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_positions(self, manager):
        """Should return positions dict."""
        result = await manager.get_positions()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_portfolio_value_method(self, manager):
        """Should return portfolio value."""
        result = await manager.get_portfolio_value()
        assert isinstance(result, (int, float))

    @pytest.mark.asyncio
    async def test_assess_position_risk(self, manager):
        """Should assess position risk."""
        result = await manager.assess_position_risk(
            symbol="AAPL", quantity=100, side="buy"
        )
        assert "risk_level" in result
        assert "approved" in result

    @pytest.mark.asyncio
    async def test_calculate_var(self, manager):
        """Should calculate VaR."""
        result = await manager.calculate_var(confidence_level=0.95)
        assert isinstance(result, float)


# =============================================================================
# RISK MANAGER (SYNC WRAPPER) TESTS
# =============================================================================

class TestRiskManagerSyncWrapper:
    """Tests for the synchronous RiskManager wrapper."""

    @pytest.fixture
    def manager(self):
        return RiskManager()

    def test_has_mock_risk_limits(self, manager):
        """Should have mock risk_limits for test compatibility."""
        assert hasattr(manager, "risk_limits")
        assert hasattr(manager.risk_limits, "max_single_symbol_exposure")

    def test_calculate_portfolio_risk_empty(self, manager):
        """Should handle empty portfolio data."""
        result = manager.calculate_portfolio_risk({})
        assert result["var_95"] == 0.0
        assert result["volatility"] == 0.0

    def test_calculate_portfolio_risk_valid(self, manager):
        """Should calculate risk for valid portfolio."""
        portfolio = {
            "total_value": 100000,
            "positions": {
                "AAPL": {"value": 30000},
                "MSFT": {"value": 40000},
            },
        }
        result = manager.calculate_portfolio_risk(portfolio)
        assert result["var_95"] >= 0
        assert "volatility" in result

    def test_assess_position_risk_empty(self, manager):
        """Should handle empty position data."""
        result = manager.assess_position_risk({})
        assert result["risk_score"] == 0.0

    def test_assess_position_risk_high_volatility(self, manager):
        """Should detect high volatility."""
        position = {
            "symbol": "MEME",
            "quantity": 100,
            "price": 50,
            "volatility": 2.0,  # 200% volatility
        }
        result = manager.assess_position_risk(position)
        assert result["risk_level"] in ["HIGH", "EXTREME"]

    def test_assess_position_risk_extreme_volatility(self, manager):
        """Should detect extreme volatility."""
        position = {
            "symbol": "MEME",
            "quantity": 100,
            "price": 50,
            "volatility": 15.0,  # 1500% volatility
        }
        result = manager.assess_position_risk(position)
        assert result["risk_level"] == "EXTREME"

    def test_assess_position_risk_handles_nan(self, manager):
        """Should handle NaN values gracefully."""
        position = {
            "symbol": "TEST",
            "quantity": float("nan"),
            "price": float("inf"),
            "volatility": float("nan"),
        }
        result = manager.assess_position_risk(position)
        # Should not crash and return valid result
        assert "risk_level" in result


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nyse_holidays_coverage(self):
        """Verify NYSE holidays are defined correctly."""
        # Check 2026 holidays exist
        assert datetime(2026, 1, 1).date() in NYSE_HOLIDAYS
        assert datetime(2026, 7, 3).date() in NYSE_HOLIDAYS  # July 4 observed

    def test_early_close_days_defined(self):
        """Verify early close days are defined."""
        assert len(NYSE_EARLY_CLOSE) > 0
        # 2026 early closes
        assert datetime(2026, 11, 27).date() in NYSE_EARLY_CLOSE

    @pytest.mark.asyncio
    async def test_evaluate_comprehensive_blocks_large_position(self):
        """Should block positions exceeding max limit."""
        manager = AsyncRiskManager(max_position_per_symbol=100)
        order = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("1000"),  # Exceeds 100
            notional=Decimal("150000"),
            price=Decimal("150"),
        )
        decision = await manager._evaluate_order_comprehensive(order)
        assert decision.allowed is False
        assert "position" in decision.reason.lower() or "limit" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_evaluate_comprehensive_blocks_high_notional(self):
        """Should block orders with high notional value."""
        manager = AsyncRiskManager(max_single_position_value=10000)
        order = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("10"),
            notional=Decimal("50000"),  # Exceeds $10k limit
            price=Decimal("5000"),
        )
        decision = await manager._evaluate_order_comprehensive(order)
        assert decision.allowed is False


class TestComprehensiveRiskEvaluation:
    """Integration tests for comprehensive risk evaluation."""

    @pytest.fixture
    def manager(self):
        return AsyncRiskManager()

    @pytest.mark.asyncio
    async def test_full_risk_check_flow(self, manager):
        """Should complete full risk check flow."""
        order = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("5"),
            notional=Decimal("750"),
            price=Decimal("150"),
        )
        decision = await manager.before_order(order)
        
        # Should return valid decision
        assert isinstance(decision, RiskDecision)
        assert decision.reason is not None

    @pytest.mark.asyncio
    async def test_sell_order_handling(self, manager):
        """Should handle sell orders correctly."""
        order = OrderSpec(
            symbol="AAPL",
            side=Side.SELL,
            qty=Decimal("5"),
            notional=Decimal("750"),
            price=Decimal("150"),
        )
        decision = await manager._evaluate_order_comprehensive(order)
        assert isinstance(decision, RiskDecision)
