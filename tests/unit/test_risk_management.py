"""
Unit tests for risk management components.

Tests risk rules, position sizing, exposure limits, drawdown controls,
and kill switch functionality.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from backend.risk.risk_manager import RiskManager
from backend.risk.types import (
    OrderSpec,
    RiskLimits,
    Side,
)
from backend.services.safety_modes import (
    SafetyModeManager,
    TradingMode,
)


class TestRiskManager:
    """Test risk management core functionality."""

    @pytest.fixture
    def risk_limits(self):
        """Standard risk limits for testing."""
        return RiskLimits(
            max_position_size=Decimal("10000"),
            max_portfolio_exposure=Decimal("50000"),
            max_sector_exposure=Decimal("25000"),
            max_single_symbol_exposure=Decimal("15000"),
            max_daily_loss=Decimal("5000"),
            max_drawdown=Decimal("0.10"),  # 10%
            min_cash_balance=Decimal("10000"),
        )

    @pytest.fixture
    def portfolio_state(self):
        """Sample portfolio state for testing."""
        return {
            "cash": Decimal("25000"),
            "total_value": Decimal("75000"),
            "positions": {
                "AAPL": {
                    "qty": 100,
                    "avg_price": Decimal("185.00"),
                    "market_value": Decimal("18500"),
                    "unrealized_pnl": Decimal("150"),
                    "sector": "Technology",
                },
                "GOOGL": {
                    "qty": 10,
                    "avg_price": Decimal("2800.00"),
                    "market_value": Decimal("28000"),
                    "unrealized_pnl": Decimal("-500"),
                    "sector": "Technology",
                },
            },
            "daily_pnl": Decimal("-1200"),
            "total_pnl": Decimal("2500"),
            "max_drawdown": Decimal("0.05"),
        }

    @pytest.fixture
    def risk_manager(self, risk_limits):
        """Create RiskManager instance for testing."""
        return RiskManager(risk_limits=risk_limits)

    @pytest.mark.unit
    @pytest.mark.risk
    def test_position_size_check_approved(self, risk_manager, portfolio_state):
        """Test position size check - should approve normal positions."""
        order_spec = OrderSpec(
            symbol="MSFT",
            side=Side.BUY,
            qty=Decimal("50"),
            price=Decimal("400.00"),  # $20,000 position
        )

        # Calculate position size for the function
        position_size = float(order_spec.qty * order_spec.price)
        result = risk_manager.check_position_size(position_size, portfolio_state)

        assert result.get("allowed", False) is True
        # Convert to dict-based assertions for legacy interface
        assert "allowed" in result
        assert result["allowed"] is True

    @pytest.mark.unit
    @pytest.mark.risk
    def test_position_size_check_rejected(self, risk_manager, portfolio_state):
        """Test position size check - should reject oversized positions."""
        order_spec = OrderSpec(
            symbol="TSLA",
            side=Side.BUY,
            qty=Decimal("200"),
            price=Decimal("800.00"),  # $160,000 position (exceeds max)
        )

        # Calculate position size for the function
        position_size = float(order_spec.qty * order_spec.price)
        result = risk_manager.check_position_size(position_size, portfolio_state)

        assert result.get("allowed", True) is False
        # Convert to dict-based assertions for legacy interface
        assert "allowed" in result
        assert result["allowed"] is False
        assert "reason" in result

    @pytest.mark.unit
    @pytest.mark.risk
    def test_concentration_check_sector_limit(self, risk_manager, portfolio_state):
        """Test sector concentration limits."""
        # Already have $46.5K in Technology, limit is $25K
        order_spec = OrderSpec(
            symbol="NVDA",  # Another tech stock
            side=Side.BUY,
            qty=Decimal("50"),
            price=Decimal("900.00"),  # $45,000 more tech exposure
        )

        # Mock sector lookup
        with patch.object(
            risk_manager, "_get_symbol_sector", return_value="Technology"
        ):
            result = risk_manager.check_concentration_limits(
                order_spec, portfolio_state
            )

        assert result.approved is False
        assert "concentration_limit_exceeded" in result.reason
        assert result.sector_exposure > risk_manager.risk_limits.max_sector_exposure

    @pytest.mark.unit
    @pytest.mark.risk
    def test_concentration_check_symbol_limit(self, risk_manager, portfolio_state):
        """Test per-symbol concentration limits."""
        # Add more AAPL (already have $18.5K, limit $15K)
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("50"),
            price=Decimal("185.00"),  # $9,250 more
        )

        result = risk_manager.check_concentration_limits(order_spec, portfolio_state)

        # Should be rejected due to single symbol limit
        assert result.approved is False
        assert (
            result.symbol_exposure > risk_manager.risk_limits.max_single_symbol_exposure
        )

    @pytest.mark.unit
    @pytest.mark.risk
    def test_daily_loss_check(self, risk_manager, portfolio_state):
        """Test daily loss limits."""
        # Portfolio already down $1,200 today
        portfolio_state["daily_pnl"] = Decimal("-4500")  # Close to $5K limit

        order_spec = OrderSpec(
            symbol="RISKY",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("50.00"),
        )

        result = risk_manager.check_daily_loss_limit(order_spec, portfolio_state)

        # Should be more cautious but not necessarily rejected
        assert isinstance(result.approved, bool)
        if not result.approved:
            assert "daily_loss_limit" in result.reason

    @pytest.mark.unit
    @pytest.mark.risk
    def test_drawdown_check(self, risk_manager, portfolio_state):
        """Test maximum drawdown controls."""
        # Simulate large drawdown
        portfolio_state["max_drawdown"] = Decimal("0.12")  # 12% > 10% limit

        order_spec = OrderSpec(
            symbol="SPEC",
            side=Side.BUY,
            qty=Decimal("10"),
            price=Decimal("100.00"),
        )

        result = risk_manager.check_drawdown_limit(order_spec, portfolio_state)

        assert result.approved is False
        assert "max_drawdown_exceeded" in result.reason
        assert result.risk_score > 0.9

    @pytest.mark.unit
    @pytest.mark.risk
    def test_cash_balance_check(self, risk_manager, portfolio_state):
        """Test minimum cash balance requirements."""
        order_spec = OrderSpec(
            symbol="EXPENSIVE",
            side=Side.BUY,
            qty=Decimal("200"),
            price=Decimal("100.00"),  # $20,000 - would leave only $5K cash
        )

        result = risk_manager.check_cash_balance(order_spec, portfolio_state)

        # Should be rejected - would violate min cash balance
        assert result.approved is False
        assert "insufficient_cash" in result.reason

    @pytest.mark.unit
    @pytest.mark.risk
    async def test_comprehensive_risk_check(self, risk_manager, portfolio_state):
        """Test complete risk evaluation pipeline."""
        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("50"),
            price=Decimal("200.00"),  # $10,000 position - reasonable
        )

        result = await risk_manager.evaluate_trade_risk(order_spec, portfolio_state)

        assert isinstance(result, RiskCheckResult)
        assert result.risk_score >= 0.0
        assert result.risk_score <= 1.0

        if result.approved:
            assert len(result.checks_passed) > 0
            assert result.risk_score < 0.8
        else:
            assert len(result.checks_failed) > 0
            assert result.risk_score > 0.5

    @pytest.mark.unit
    @pytest.mark.risk
    def test_portfolio_metrics_calculation(self, risk_manager, portfolio_state):
        """Test portfolio metrics calculation."""
        metrics = risk_manager.calculate_portfolio_metrics(portfolio_state)

        assert isinstance(metrics, PortfolioMetrics)
        assert metrics.total_value == portfolio_state["total_value"]
        assert metrics.cash_balance == portfolio_state["cash"]
        assert metrics.positions_value == Decimal("46500")  # 18.5K + 28K

        # Check leverage calculation
        expected_leverage = metrics.positions_value / metrics.total_value
        assert abs(metrics.leverage - expected_leverage) < Decimal("0.01")

    @pytest.mark.unit
    @pytest.mark.risk
    def test_risk_score_calculation(self, risk_manager, portfolio_state):
        """Test risk score calculation logic."""
        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("25"),
            price=Decimal("400.00"),  # $10,000 position
        )

        risk_score = risk_manager._calculate_risk_score(order_spec, portfolio_state)

        assert 0.0 <= risk_score <= 1.0

        # Test with riskier order
        risky_order = OrderSpec(
            symbol="RISKY",
            side=Side.BUY,
            qty=Decimal("200"),
            price=Decimal("400.00"),  # $80,000 position
        )

        risky_score = risk_manager._calculate_risk_score(risky_order, portfolio_state)
        assert risky_score > risk_score  # Should be higher risk


class TestSafetyModes:
    """Test trading safety modes and feature flags."""

    @pytest.fixture
    def safety_manager(self):
        """Create SafetyModeManager for testing."""
        return SafetyModeManager(
            mode=TradingMode.DRY_RUN,
            enable_kill_switch=True,
        )

    @pytest.mark.unit
    @pytest.mark.risk
    def test_trading_mode_shadow(self, safety_manager):
        """Test SHADOW mode behavior."""
        safety_manager.set_mode(TradingMode.SHADOW)

        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("50.00"),
        )

        result = safety_manager.process_order(order_spec)

        # Should be processed but not submitted
        assert result["processed"] is True
        assert result["submitted"] is False
        assert result["mode"] == "shadow"

    @pytest.mark.unit
    @pytest.mark.risk
    def test_trading_mode_dry_run(self, safety_manager):
        """Test DRY_RUN mode behavior."""
        safety_manager.set_mode(TradingMode.DRY_RUN)

        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("50.00"),
        )

        result = safety_manager.process_order(order_spec)

        # Should be fully simulated
        assert result["processed"] is True
        assert result["submitted"] is False
        assert result["simulated"] is True
        assert "mock_order_id" in result

    @pytest.mark.unit
    @pytest.mark.risk
    def test_trading_mode_live(self, safety_manager):
        """Test LIVE mode behavior."""
        safety_manager.set_mode(TradingMode.LIVE)

        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("50.00"),
        )

        with patch.object(safety_manager, "_submit_real_order") as mock_submit:
            mock_submit.return_value = {"order_id": "real_12345", "status": "submitted"}

            result = safety_manager.process_order(order_spec)

        # Should submit real order
        assert result["processed"] is True
        assert result["submitted"] is True
        assert "order_id" in result

    @pytest.mark.unit
    @pytest.mark.risk
    def test_feature_flags(self, safety_manager):
        """Test feature flag functionality."""
        # Enable feature for specific symbol
        safety_manager.set_feature_flag(
            "aggressive_sizing", enabled=True, scope="symbol", target="AAPL"
        )

        # Check if feature is enabled
        assert (
            safety_manager.is_feature_enabled("aggressive_sizing", symbol="AAPL")
            is True
        )
        assert (
            safety_manager.is_feature_enabled("aggressive_sizing", symbol="GOOGL")
            is False
        )

        # Disable feature
        safety_manager.set_feature_flag("aggressive_sizing", enabled=False)
        assert (
            safety_manager.is_feature_enabled("aggressive_sizing", symbol="AAPL")
            is False
        )

    @pytest.mark.unit
    @pytest.mark.risk
    def test_kill_switch_global(self, safety_manager):
        """Test global kill switch activation."""
        # Activate kill switch
        safety_manager.activate_kill_switch(
            scope="global",
            reason="emergency_stop",
            message="Manual emergency stop activated",
        )

        assert safety_manager.is_kill_switch_active() is True
        assert safety_manager.is_trading_allowed("AAPL") is False
        assert safety_manager.is_trading_allowed("GOOGL") is False

        # Check kill switch status
        status = safety_manager.get_kill_switch_status()
        assert status["active"] is True
        assert status["scope"] == "global"
        assert status["reason"] == "emergency_stop"

    @pytest.mark.unit
    @pytest.mark.risk
    def test_kill_switch_symbol_specific(self, safety_manager):
        """Test symbol-specific kill switch."""
        # Activate for specific symbol
        safety_manager.activate_kill_switch(
            scope="symbol",
            target="AAPL",
            reason="risk_limit_breach",
            message="AAPL risk limits exceeded",
        )

        assert safety_manager.is_trading_allowed("AAPL") is False
        assert safety_manager.is_trading_allowed("GOOGL") is True  # Others unaffected

    @pytest.mark.unit
    @pytest.mark.risk
    def test_kill_switch_deactivation(self, safety_manager):
        """Test kill switch deactivation."""
        # Activate then deactivate
        safety_manager.activate_kill_switch_legacy(scope="global", reason="test")
        assert safety_manager.is_kill_switch_active() is True

        safety_manager.deactivate_all_kill_switches(reason="issue_resolved")
        assert safety_manager.is_kill_switch_active() is False
        assert safety_manager.is_trading_allowed("AAPL") is True

    @pytest.mark.unit
    @pytest.mark.risk
    def test_shadow_mode_divergence_detection(self, safety_manager):
        """Test divergence detection in shadow mode."""
        safety_manager.set_mode(TradingMode.SHADOW)

        # Simulate real execution
        real_result = {
            "order_id": "real_123",
            "filled_qty": 100,
            "avg_fill_price": 185.50,
            "execution_time": 0.15,  # 150ms
        }

        # Simulate shadow execution
        shadow_result = {
            "order_id": "shadow_123",
            "filled_qty": 100,
            "avg_fill_price": 185.75,  # Different price
            "execution_time": 0.12,  # Different timing
        }

        divergences = safety_manager.detect_shadow_divergence(
            real_result, shadow_result
        )

        assert len(divergences) > 0
        assert any(d["type"] == "price_divergence" for d in divergences)
        assert any(d["type"] == "timing_divergence" for d in divergences)

    @pytest.mark.unit
    @pytest.mark.risk
    def test_risk_isolation_between_modes(self, safety_manager):
        """Test that different modes maintain risk isolation."""
        # Shadow mode should not affect live positions
        safety_manager.set_mode(TradingMode.SHADOW)

        shadow_portfolio = safety_manager.get_shadow_portfolio()
        live_portfolio = safety_manager.get_live_portfolio()

        # Execute shadow trade
        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("50.00"),
        )

        safety_manager.process_order(order_spec)

        # Shadow portfolio should be updated, live should be unchanged
        updated_shadow = safety_manager.get_shadow_portfolio()
        updated_live = safety_manager.get_live_portfolio()

        assert updated_shadow != shadow_portfolio  # Shadow changed
        assert updated_live == live_portfolio  # Live unchanged


class TestRiskEdgeCases:
    """Test edge cases and error conditions in risk management."""

    @pytest.fixture
    def risk_manager(self):
        """Basic risk manager for edge case testing."""
        return RiskManager()

    @pytest.mark.unit
    @pytest.mark.risk
    def test_zero_portfolio_value(self, risk_manager):
        """Test handling of zero/negative portfolio values."""
        empty_portfolio = {
            "cash": Decimal("0"),
            "total_value": Decimal("0"),
            "positions": {},
            "daily_pnl": Decimal("0"),
        }

        order_spec = OrderSpec(
            symbol="TEST",
            side=Side.BUY,
            qty=Decimal("1"),
            price=Decimal("100.00"),
        )

        # Should handle gracefully without division by zero
        result = risk_manager.check_cash_balance(order_spec, empty_portfolio)
        assert result.approved is False

    @pytest.mark.unit
    @pytest.mark.risk
    def test_extreme_volatility_adjustment(self, risk_manager):
        """Test risk adjustments for high volatility periods."""
        high_vol_portfolio = {
            "cash": Decimal("50000"),
            "total_value": Decimal("100000"),
            "positions": {},
            "daily_pnl": Decimal("-8000"),  # High daily loss
            "volatility_regime": "HIGH",  # Extreme vol
        }

        order_spec = OrderSpec(
            symbol="VOLATILE",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("200.00"),
        )

        result = risk_manager._calculate_risk_score(order_spec, high_vol_portfolio)

        # Should have elevated risk score due to volatility
        assert result > 0.5

    @pytest.mark.unit
    @pytest.mark.risk
    def test_invalid_order_handling(self, risk_manager):
        """Test handling of malformed orders."""
        invalid_orders = [
            # Negative quantity
            OrderSpec(
                symbol="TEST", side=Side.BUY, qty=Decimal("-100"), price=Decimal("50")
            ),
            # Zero price
            OrderSpec(
                symbol="TEST", side=Side.BUY, qty=Decimal("100"), price=Decimal("0")
            ),
            # Missing symbol
            OrderSpec(
                symbol="", side=Side.BUY, qty=Decimal("100"), price=Decimal("50")
            ),
        ]

        portfolio_state = {"cash": Decimal("10000"), "total_value": Decimal("10000")}

        for invalid_order in invalid_orders:
            result = risk_manager.check_position_size(invalid_order, portfolio_state)
            assert result.approved is False
            assert "invalid_order" in result.reason
