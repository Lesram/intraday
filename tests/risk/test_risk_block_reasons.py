"""
Test risk blocking logic with comprehensive table of edge cases.
"""

import pytest
from decimal import Decimal
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

from backend.risk.types import RiskLimits, OrderSpec, PortfolioRisk
from backend.risk.risk_manager import RiskManager


class TestRiskBlockReasons:
    """Test risk blocking with comprehensive coverage of edge cases"""

    @pytest.fixture
    def risk_manager(self):
        """Create RiskManager with mocked dependencies"""
        with patch('backend.risk.manager.RiskManager.__init__', return_value=None):
            manager = RiskManager.__new__(RiskManager)
            manager.metrics = MagicMock()
            manager.portfolio = MagicMock()
            manager.config = MagicMock()
            return manager

    @pytest.fixture
    def base_risk_limits(self):
        """Create base risk limits for testing"""
        return RiskLimits(
            max_position_size=Decimal('10000'),
            max_order_size=Decimal('1000'),
            daily_loss_limit=Decimal('5000'),
            max_leverage=Decimal('2.0'),
            max_concentration=Decimal('0.1')  # 10%
        )

    @pytest.fixture
    def base_portfolio_risk(self):
        """Create base portfolio risk state"""
        return PortfolioRisk(
            total_equity=Decimal('100000'),
            unrealized_pnl=Decimal('0'),
            daily_pnl=Decimal('0'),
            leverage=Decimal('1.0'),
            var_95=Decimal('1000')
        )

    @pytest.mark.parametrize("scenario,expected_allowed,expected_reason,expected_adjustment", [
        # Basic valid orders
        ("positive_mu_normal_vol", True, None, Decimal('100')),
        # Negative μ cases
        ("negative_expected_return", False, "negative_expected_return", Decimal('0')),
        ("zero_expected_return", False, "zero_expected_return", Decimal('0')),
        # Low volatility cases  
        ("zero_volatility", False, "zero_volatility", Decimal('0')),
        ("extremely_low_volatility", False, "low_volatility", Decimal('0')),
        # Daily cap cases
        ("daily_volume_cap_exceeded", False, "daily_volume_cap_exceeded", Decimal('0')),
        ("daily_cap_partial_adjustment", True, "adjusted_for_daily_cap", Decimal('50')),
        # Leverage cases
        ("max_leverage_exceeded", False, "max_leverage_exceeded", Decimal('0')),
        ("leverage_partial_adjustment", True, "adjusted_for_leverage_limit", Decimal('75')),
        # Kill switch cases
        ("kill_switch_active", False, "kill_switch_active", Decimal('0')),
        ("normal_buy_order", True, None, None),
        ("normal_sell_order", True, None, None),
        
        # Size violations
        ("order_exceeds_max_size", False, "order_size_exceeded", 1000),
        ("position_would_exceed_max", False, "position_limit_exceeded", 500),
        
        # PnL violations  
        ("daily_loss_limit_hit", False, "daily_loss_limit", None),
        ("negative_mean_return", False, "negative_expected_return", None),
        
        # Volatility violations
        ("zero_volatility_suspicious", False, "suspicious_volatility", None),
        ("extreme_high_volatility", False, "volatility_too_high", None),
        
        # Leverage violations
        ("max_leverage_exceeded", False, "leverage_exceeded", None),
        ("leverage_near_margin_call", False, "margin_risk", None),
        
        # Kill switch scenarios
        ("kill_switch_active", False, "kill_switch_active", None),
        ("emergency_halt_active", False, "emergency_halt", None),
        
        # Market conditions
        ("market_closed", False, "market_closed", None),
        ("low_liquidity", False, "insufficient_liquidity", 100),
        
        # Concentration risk
        ("concentration_limit_exceeded", False, "concentration_risk", 200),
        ("sector_exposure_too_high", False, "sector_concentration", 150),
    ])
    def test_risk_blocking_scenarios(
        self, 
        risk_manager, 
        base_risk_limits, 
        base_portfolio_risk,
        scenario, 
        expected_allowed, 
        expected_reason, 
        expected_adjustment
    ):
        """Test comprehensive risk blocking scenarios"""
        
        # Create order spec based on scenario
        order_spec = self._create_order_for_scenario(scenario)
        
        # Mock portfolio state based on scenario  
        portfolio_risk = self._create_portfolio_for_scenario(scenario, base_portfolio_risk)
        
        # Mock risk limits based on scenario
        risk_limits = self._create_limits_for_scenario(scenario, base_risk_limits)
        
        # Setup mocks
        risk_manager.portfolio.get_current_risk.return_value = portfolio_risk
        risk_manager.config.get_risk_limits.return_value = risk_limits
        risk_manager._is_market_open.return_value = scenario != "market_closed"
        risk_manager._is_kill_switch_active.return_value = scenario in ["kill_switch_active", "emergency_halt_active"]
        
        # Execute risk check
        result = risk_manager.validate_order(order_spec)
        
        allowed, reason, adjusted_qty = result
        
        # Verify results
        assert allowed == expected_allowed, f"Scenario {scenario}: expected allowed={expected_allowed}, got {allowed}"
        
        if not expected_allowed:
            assert reason == expected_reason, f"Scenario {scenario}: expected reason={expected_reason}, got {reason}"
            
            # Verify metrics were incremented
            risk_manager.metrics.increment.assert_called()
            metric_call = risk_manager.metrics.increment.call_args
            assert "orders_blocked_total" in str(metric_call)
            assert expected_reason in str(metric_call) or "reason" in str(metric_call)
        
        if expected_adjustment is not None:
            assert adjusted_qty == expected_adjustment, f"Scenario {scenario}: expected adjustment={expected_adjustment}, got {adjusted_qty}"

    def _create_order_for_scenario(self, scenario: str) -> OrderSpec:
        """Create order spec based on test scenario"""
        base_order = OrderSpec(
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            client_order_id=f"test_{scenario}",
            timestamp=datetime.now(UTC)
        )
        
        # Modify order based on scenario
        if scenario == "order_exceeds_max_size":
            base_order.quantity = 2000  # Exceeds max of 1000
        elif scenario == "position_would_exceed_max":
            base_order.quantity = 1500  # Would exceed position limit
        elif scenario == "normal_sell_order":
            base_order.side = "sell"
        elif scenario == "concentration_limit_exceeded":
            base_order.quantity = 5000  # Large position
        elif scenario == "low_liquidity":
            base_order.quantity = 500
            base_order.symbol = "ILLIQUID_STOCK"
        
        return base_order

    def _create_portfolio_for_scenario(self, scenario: str, base: PortfolioRisk) -> PortfolioRisk:
        """Create portfolio risk state based on scenario"""
        portfolio = PortfolioRisk(
            total_equity=base.total_equity,
            unrealized_pnl=base.unrealized_pnl,
            daily_pnl=base.daily_pnl,
            leverage=base.leverage,
            var_95=base.var_95
        )
        
        # Modify based on scenario
        if scenario == "daily_loss_limit_hit":
            portfolio.daily_pnl = Decimal('-6000')  # Exceeds -5000 limit
        elif scenario == "max_leverage_exceeded":
            portfolio.leverage = Decimal('2.5')  # Exceeds 2.0 limit
        elif scenario == "leverage_near_margin_call":
            portfolio.leverage = Decimal('1.9')  # Close to limit
        elif scenario == "negative_mean_return":
            portfolio.unrealized_pnl = Decimal('-2000')
            portfolio.daily_pnl = Decimal('-1000')
        elif scenario == "position_would_exceed_max":
            # Mock existing large position
            portfolio.total_equity = Decimal('50000')  # Smaller equity for concentration calc
        
        return portfolio

    def _create_limits_for_scenario(self, scenario: str, base: RiskLimits) -> RiskLimits:
        """Create risk limits based on scenario"""
        limits = RiskLimits(
            max_position_size=base.max_position_size,
            max_order_size=base.max_order_size,
            daily_loss_limit=base.daily_loss_limit,
            max_leverage=base.max_leverage,
            max_concentration=base.max_concentration
        )
        
        # Modify based on scenario
        if scenario == "zero_volatility_suspicious":
            limits.min_volatility = Decimal('0.01')  # Minimum volatility requirement
        elif scenario == "extreme_high_volatility":
            limits.max_volatility = Decimal('0.5')  # Maximum volatility allowed
        
        return limits

    def test_risk_metrics_labels_correctness(self, risk_manager, base_risk_limits, base_portfolio_risk):
        """Test that risk metrics have correct labels"""
        # Test blocked order
        order_spec = OrderSpec(
            symbol="AAPL",
            side="buy", 
            quantity=2000,  # Exceeds max order size
            order_type="market",
            client_order_id="test_metrics",
            timestamp=datetime.now(UTC)
        )
        
        risk_manager.portfolio.get_current_risk.return_value = base_portfolio_risk
        risk_manager.config.get_risk_limits.return_value = base_risk_limits
        
        # Execute risk check
        allowed, reason, _ = risk_manager.validate_order(order_spec)
        
        assert not allowed
        assert reason == "order_size_exceeded"
        
        # Verify metric was called with correct labels
        risk_manager.metrics.increment.assert_called()
        call_args = risk_manager.metrics.increment.call_args
        
        # Should have called with orders_blocked_total metric
        metric_name = call_args[0][0]
        assert metric_name == "orders_blocked_total"
        
        # Should have reason label
        if len(call_args) > 1 and 'labels' in call_args[1]:
            labels = call_args[1]['labels']
            assert labels.get('reason') == reason

    def test_position_sizing_adjustment(self, risk_manager, base_risk_limits, base_portfolio_risk):
        """Test that position sizing suggests appropriate adjustments"""
        order_spec = OrderSpec(
            symbol="AAPL",
            side="buy",
            quantity=1500,  # Too large
            order_type="market", 
            client_order_id="test_adjustment",
            timestamp=datetime.now(UTC)
        )
        
        risk_manager.portfolio.get_current_risk.return_value = base_portfolio_risk
        risk_manager.config.get_risk_limits.return_value = base_risk_limits
        
        # Mock position sizing logic
        with patch.object(risk_manager, '_calculate_max_allowed_quantity', return_value=800):
            allowed, reason, adjusted_qty = risk_manager.validate_order(order_spec)
        
        assert not allowed
        assert adjusted_qty == 800
        assert adjusted_qty < order_spec.quantity

    def test_kill_switch_blocks_all_orders(self, risk_manager, base_risk_limits, base_portfolio_risk):
        """Test that kill switch blocks all orders regardless of other factors"""
        # Create perfectly valid order
        order_spec = OrderSpec(
            symbol="AAPL",
            side="buy",
            quantity=50,  # Small, safe size
            order_type="market",
            client_order_id="test_kill_switch", 
            timestamp=datetime.now(UTC)
        )
        
        risk_manager.portfolio.get_current_risk.return_value = base_portfolio_risk
        risk_manager.config.get_risk_limits.return_value = base_risk_limits
        risk_manager._is_kill_switch_active.return_value = True
        
        allowed, reason, _ = risk_manager.validate_order(order_spec)
        
        assert not allowed
        assert reason == "kill_switch_active"
        
        # Should still record metric
        risk_manager.metrics.increment.assert_called()

    def test_market_hours_enforcement(self, risk_manager, base_risk_limits, base_portfolio_risk):
        """Test market hours enforcement"""
        order_spec = OrderSpec(
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            client_order_id="test_market_hours",
            timestamp=datetime.now(UTC)
        )
        
        risk_manager.portfolio.get_current_risk.return_value = base_portfolio_risk
        risk_manager.config.get_risk_limits.return_value = base_risk_limits
        risk_manager._is_market_open.return_value = False
        
        allowed, reason, _ = risk_manager.validate_order(order_spec)
        
        assert not allowed
        assert reason == "market_closed"

    def test_volatility_based_blocking(self, risk_manager, base_risk_limits, base_portfolio_risk):
        """Test volatility-based risk blocking"""
        order_spec = OrderSpec(
            symbol="VOLATILE_STOCK",
            side="buy", 
            quantity=100,
            order_type="market",
            client_order_id="test_volatility",
            timestamp=datetime.now(UTC)
        )
        
        # Mock extremely high volatility
        with patch.object(risk_manager, '_get_symbol_volatility', return_value=Decimal('0.8')):  # 80% volatility
            risk_manager.portfolio.get_current_risk.return_value = base_portfolio_risk
            
            # Set volatility limit
            limits = base_risk_limits
            limits.max_volatility = Decimal('0.5')  # 50% max
            risk_manager.config.get_risk_limits.return_value = limits
            
            allowed, reason, _ = risk_manager.validate_order(order_spec)
            
            assert not allowed
            assert reason == "volatility_too_high"

    @pytest.mark.parametrize("pnl,limit,should_block", [
        (Decimal('-4999'), Decimal('-5000'), False),  # Just under limit
        (Decimal('-5000'), Decimal('-5000'), True),   # At limit  
        (Decimal('-5001'), Decimal('-5000'), True),   # Over limit
        (Decimal('1000'), Decimal('-5000'), False),   # Positive PnL
    ])
    def test_daily_pnl_limit_boundary_conditions(
        self, 
        risk_manager, 
        base_risk_limits, 
        base_portfolio_risk, 
        pnl, 
        limit, 
        should_block
    ):
        """Test daily PnL limit boundary conditions"""
        order_spec = OrderSpec(
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market", 
            client_order_id="test_pnl_boundary",
            timestamp=datetime.now(UTC)
        )
        
        # Set portfolio PnL
        portfolio_risk = base_portfolio_risk
        portfolio_risk.daily_pnl = pnl
        risk_manager.portfolio.get_current_risk.return_value = portfolio_risk
        
        # Set PnL limit
        limits = base_risk_limits
        limits.daily_loss_limit = abs(limit)  # Store as positive value
        risk_manager.config.get_risk_limits.return_value = limits
        
        allowed, reason, _ = risk_manager.validate_order(order_spec)
        
        if should_block:
            assert not allowed
            assert reason == "daily_loss_limit"
        else:
            # Might be blocked for other reasons, but not PnL
            if not allowed:
                assert reason != "daily_loss_limit"
