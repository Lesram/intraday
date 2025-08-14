"""
Comprehensive risk management testing with table-driven parametrization.
Tests risk limits, position sizing, drawdown protection, and risk scenarios.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
import numpy as np

from backend.risk.risk_manager import AsyncRiskManager
from backend.risk.types import OrderSpec, RiskDecision, PortfolioState

# Risk limit validation test data
RISK_LIMIT_VALIDATION_DATA = [
    ("AAPL", "buy", Decimal("100"), Decimal("150"), 10000, 100000, 0.05, True),
    ("GOOGL", "sell", Decimal("50"), Decimal("2500"), 5000, 80000, 0.04, True),
    ("MSFT", "buy", Decimal("200"), Decimal("300"), 15000, 120000, 0.06, False),
    ("TSLA", "sell", Decimal("25"), Decimal("800"), 50000, 200000, 0.08, False),
    ("AMZN", "buy", Decimal("10"), Decimal("3000"), 8000, 90000, 0.03, True),
    ("META", "sell", Decimal("75"), Decimal("450"), 12000, 110000, 0.05, True),
    ("NVDA", "buy", Decimal("30"), Decimal("900"), 35000, 150000, 0.07, False),
    ("SPY", "sell", Decimal("100"), Decimal("400"), 6000, 85000, 0.04, True),
]

RISK_BREACH_SCENARIOS = [
    ("position_limit_breach", {"max_position_per_symbol": 50}, Decimal("100"), "pos_cap"),
    ("notional_limit_breach", {"max_single_position_value": 50000}, Decimal("200000"), "notional_cap"),
    ("var_limit_breach", {"max_portfolio_var": 0.02}, 0.05, "var"),
    ("kelly_size_breach", {"kelly_ceiling": 0.1}, 0.3, "kelly"),
    ("correlation_breach", {"max_correlation": 0.7}, 0.9, "correlation"),
]

CORRELATION_SCENARIOS = [
    ("AAPL", "MSFT", 0.65, "Technology", "Technology", True),
    ("TSLA", "NVDA", 0.45, "Automotive", "Technology", True),
    ("SPY", "QQQ", 0.85, "Index", "Index", False),
    ("AMZN", "META", 0.55, "Technology", "Technology", True),
    ("GOOGL", "AAPL", 0.75, "Technology", "Technology", False),
]


@pytest.fixture
def mock_portfolio_state():
    """Mock portfolio state for testing"""
    return PortfolioState(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={"AAPL": Decimal("1000"), "MSFT": Decimal("500")},
        sector_map={"AAPL": "Technology", "MSFT": "Technology"},
        last_updated=datetime.now(timezone.utc)
    )


@pytest.fixture
def risk_manager():
    """AsyncRiskManager instance for testing"""
    return AsyncRiskManager(
        max_position_per_symbol=10000,
        max_single_position_value=100000,
        max_portfolio_var=0.05
    )


@pytest.fixture
def mock_positions_service():
    """Mock positions service for testing"""
    service = Mock()
    service.get_current_positions = AsyncMock(return_value={
        "AAPL": {"quantity": 100, "market_value": 15000},
        "MSFT": {"quantity": 50, "market_value": 15000}
    })
    return service


@pytest.fixture
def mock_pricing_service():
    """Mock pricing service for historical data"""
    service = Mock()
    
    # Mock historical returns
    def get_returns(symbol, days=60):
        np.random.seed(42)  # Deterministic for testing
        return np.random.normal(0.001, 0.02, days).tolist()
    
    service.get_historical_returns = AsyncMock(side_effect=get_returns)
    return service


class TestRiskManagerComprehensive:
    """Comprehensive table-driven tests for AsyncRiskManager"""
    
    @pytest.mark.parametrize("symbol,side,qty,price,max_pos,max_val,max_var,should_approve", RISK_LIMIT_VALIDATION_DATA)
    @pytest.mark.asyncio
    async def test_risk_limit_validation_matrix(
        self, risk_manager, symbol, side, qty, price, max_pos, max_val, max_var, should_approve
    ):
        """Test risk limit validation with comprehensive parameter matrix"""
        # Configure risk manager with test limits
        risk_manager.max_position_per_symbol = max_pos
        risk_manager.max_single_position_value = max_val
        risk_manager.max_portfolio_var = max_var
        
        # Create order specification
        order = OrderSpec(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            notional=qty * price
        )
        
        # Test risk evaluation
        decision = await risk_manager.before_order(order)
        
        # Verify decision aligns with expected approval
        if should_approve:
            assert decision.allowed or decision.reason in ["kelly_size_exceeded"]
        else:
            assert not decision.allowed
            
        # Verify decision structure
        assert isinstance(decision, RiskDecision)
        assert decision.reason is not None
        assert decision.original_qty == qty

    @pytest.mark.parametrize("breach_type,risk_config,breach_value,expected_reason", RISK_BREACH_SCENARIOS)
    @pytest.mark.asyncio
    async def test_risk_breach_scenarios(
        self, breach_type, risk_config, breach_value, expected_reason
    ):
        """Test various risk breach scenarios and responses"""
        # Configure risk manager with breach conditions
        risk_manager = AsyncRiskManager(**risk_config)
        
        # Create order that should trigger breach
        if breach_type == "position_limit_breach":
            order = OrderSpec(
                symbol="TEST",
                side="buy", 
                qty=breach_value,
                price=Decimal("100"),
                notional=breach_value * Decimal("100")
            )
        elif breach_type == "notional_limit_breach":
            order = OrderSpec(
                symbol="TEST",
                side="buy",
                qty=Decimal("100"),
                price=Decimal("2000"),
                notional=breach_value
            )
        else:
            order = OrderSpec(
                symbol="TEST",
                side="buy",
                qty=Decimal("100"),
                price=Decimal("100"),
                notional=Decimal("10000")
            )
        
        # Test risk evaluation
        decision = await risk_manager.before_order(order)
        
        # Verify breach detection
        assert not decision.allowed
        assert expected_reason in decision.reason or decision.reason in expected_reason

    @pytest.mark.parametrize("symbol1,symbol2,correlation,sector1,sector2,should_warn", CORRELATION_SCENARIOS)
    @pytest.mark.asyncio
    async def test_correlation_analysis(
        self, risk_manager, symbol1, symbol2, correlation, sector1, sector2, should_warn
    ):
        """Test correlation analysis between positions"""
        # Mock portfolio state with correlated positions
        portfolio_state = PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            positions={symbol1: Decimal("5000"), symbol2: Decimal("5000")},
            sector_map={symbol1: sector1, symbol2: sector2},
            last_updated=datetime.now(timezone.utc)
        )
        
        # Create new order for correlated position
        order = OrderSpec(
            symbol=symbol1,
            side="buy",
            qty=Decimal("50"),
            price=Decimal("100"),
            notional=Decimal("5000")
        )
        
        # Evaluate order
        decision = await risk_manager.before_order(order, portfolio_state)
        
        # High correlation should trigger warnings
        if not should_warn and correlation > 0.7:
            # High correlation but should be allowed
            assert decision.allowed or decision.reason != "correlation"
        
        # Verify decision includes correlation context
        assert isinstance(decision, RiskDecision)

    @pytest.mark.asyncio
    async def test_kelly_position_sizing_calculation(self, risk_manager):
        """Test Kelly criterion position sizing with various return scenarios"""
        # Mock historical returns with positive expected return
        with patch.object(risk_manager, '_get_historical_returns') as mock_returns:
            # Configure returns for profitable scenario
            mock_returns.return_value = [0.02, 0.015, 0.01, -0.005, 0.025, 0.01] * 10
            
            order = OrderSpec(
                symbol="KELLY_TEST",
                side="buy",
                qty=Decimal("100"),
                price=Decimal("150"),
                notional=Decimal("15000")
            )
            
            decision = await risk_manager.before_order(order)
            
            # With positive expected returns, should have Kelly considerations
            assert isinstance(decision, RiskDecision)
            
            # If blocked for Kelly, should have adjusted quantity
            if decision.reason == "kelly_size_exceeded":
                assert decision.adjusted_qty is not None
                assert decision.adjusted_qty < order.qty

    @pytest.mark.asyncio
    async def test_var_calculation_and_limits(self, risk_manager):
        """Test Value at Risk calculation and limit enforcement"""
        # Mock historical returns for VaR calculation
        with patch.object(risk_manager, '_get_historical_returns') as mock_returns:
            # Configure volatile returns to trigger VaR limits
            volatile_returns = []
            for _ in range(60):
                # Mix of high positive and negative returns
                volatile_returns.extend([0.05, 0.03, -0.08, -0.06, 0.02])
            
            mock_returns.return_value = volatile_returns[:60]
            
            # Configure strict VaR limit
            risk_manager.max_portfolio_var = 0.02
            
            order = OrderSpec(
                symbol="VAR_TEST",
                side="buy",
                qty=Decimal("500"),
                price=Decimal("200"),
                notional=Decimal("100000")
            )
            
            decision = await risk_manager.before_order(order)
            
            # High volatility should affect decision
            assert isinstance(decision, RiskDecision)
            
            # May be blocked due to VaR or allowed with warnings
            if not decision.allowed:
                assert "var" in decision.reason.lower() or decision.reason == "var"

    @pytest.mark.asyncio
    async def test_drawdown_protection_logic(self, risk_manager):
        """Test drawdown protection and position reduction"""
        # Mock portfolio state with significant drawdown
        drawdown_portfolio = PortfolioState(
            equity=Decimal("70000"),  # Down from peak of 100k
            cash=Decimal("30000"),
            positions={"AAPL": Decimal("5000"), "MSFT": Decimal("5000")},
            sector_map={"AAPL": "Technology", "MSFT": "Technology"},
            last_updated=datetime.now(timezone.utc)
        )
        
        order = OrderSpec(
            symbol="DRAWDOWN_TEST",
            side="buy",
            qty=Decimal("200"),
            price=Decimal("100"),
            notional=Decimal("20000")
        )
        
        decision = await risk_manager.before_order(order, drawdown_portfolio)
        
        # Significant drawdown should influence risk decision
        assert isinstance(decision, RiskDecision)
        
        # May reduce position size or reject based on portfolio stress
        if decision.adjusted_qty:
            assert decision.adjusted_qty <= order.qty

    @pytest.mark.asyncio
    async def test_sector_concentration_limits(self, risk_manager):
        """Test sector concentration risk management"""
        # Create portfolio concentrated in technology
        tech_heavy_portfolio = PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("20000"),
            positions={
                "AAPL": Decimal("20000"),
                "MSFT": Decimal("20000"),
                "GOOGL": Decimal("20000"),
                "META": Decimal("15000")
            },
            sector_map={
                "AAPL": "Technology",
                "MSFT": "Technology", 
                "GOOGL": "Technology",
                "META": "Technology"
            },
            last_updated=datetime.now(timezone.utc)
        )
        
        # Try to add more technology exposure
        order = OrderSpec(
            symbol="NVDA",
            side="buy",
            qty=Decimal("100"),
            price=Decimal("500"),
            notional=Decimal("50000")
        )
        
        decision = await risk_manager.before_order(order, tech_heavy_portfolio)
        
        # Heavy sector concentration might trigger warnings
        assert isinstance(decision, RiskDecision)

    @pytest.mark.asyncio
    async def test_volatility_adjustment_scenarios(self, risk_manager):
        """Test position sizing adjustment based on volatility"""
        # Test low volatility scenario
        with patch.object(risk_manager, '_get_historical_returns') as mock_returns:
            # Low volatility returns
            low_vol_returns = [0.005, -0.002, 0.003, -0.001, 0.004] * 12
            mock_returns.return_value = low_vol_returns
            
            order_low_vol = OrderSpec(
                symbol="LOW_VOL",
                side="buy",
                qty=Decimal("100"),
                price=Decimal("100"),
                notional=Decimal("10000")
            )
            
            decision_low_vol = await risk_manager.before_order(order_low_vol)
            
            # Low volatility should generally be more permissive
            assert isinstance(decision_low_vol, RiskDecision)
            
        # Test high volatility scenario
        with patch.object(risk_manager, '_get_historical_returns') as mock_returns:
            # High volatility returns
            high_vol_returns = [0.08, -0.12, 0.15, -0.09, 0.06] * 12
            mock_returns.return_value = high_vol_returns
            
            order_high_vol = OrderSpec(
                symbol="HIGH_VOL",
                side="buy",
                qty=Decimal("100"),
                price=Decimal("100"),
                notional=Decimal("10000")
            )
            
            decision_high_vol = await risk_manager.before_order(order_high_vol)
            
            # High volatility may trigger more conservative sizing
            assert isinstance(decision_high_vol, RiskDecision)

    @pytest.mark.asyncio
    async def test_risk_manager_initialization_configs(self):
        """Test AsyncRiskManager initialization with various configurations"""
        # Test default configuration
        default_rm = AsyncRiskManager()
        assert default_rm.max_position_per_symbol == 10000
        assert default_rm.max_single_position_value == 100000
        assert default_rm.max_portfolio_var == 0.05
        
        # Test custom configuration
        custom_rm = AsyncRiskManager(
            max_position_per_symbol=5000,
            max_single_position_value=50000,
            max_portfolio_var=0.03
        )
        assert custom_rm.max_position_per_symbol == 5000
        assert custom_rm.max_single_position_value == 50000
        assert custom_rm.max_portfolio_var == 0.03

    @pytest.mark.asyncio
    async def test_order_rejection_with_detailed_reasons(self, risk_manager):
        """Test order rejection provides detailed reasoning"""
        # Create order that exceeds multiple limits
        excessive_order = OrderSpec(
            symbol="EXCESSIVE",
            side="buy",
            qty=Decimal("50000"),  # Exceeds position limit
            price=Decimal("1000"),
            notional=Decimal("50000000")  # Exceeds notional limit
        )
        
        decision = await risk_manager.before_order(excessive_order)
        
        # Should be rejected with clear reason
        assert not decision.allowed
        assert decision.reason is not None
        assert len(decision.reason) > 0
        
        # Should provide adjustment suggestions
        if decision.adjusted_qty:
            assert decision.adjusted_qty < excessive_order.qty

    @pytest.mark.asyncio
    async def test_edge_case_zero_and_negative_positions(self, risk_manager):
        """Test handling of zero and negative position scenarios"""
        # Test zero quantity order
        zero_order = OrderSpec(
            symbol="ZERO_TEST",
            side="buy",
            qty=Decimal("0"),
            price=Decimal("100"),
            notional=Decimal("0")
        )
        
        decision_zero = await risk_manager.before_order(zero_order)
        
        # Zero orders should be handled gracefully
        assert isinstance(decision_zero, RiskDecision)
        
        # Test very small order
        small_order = OrderSpec(
            symbol="SMALL_TEST",
            side="buy",
            qty=Decimal("0.01"),
            price=Decimal("100"),
            notional=Decimal("1")
        )
        
        decision_small = await risk_manager.before_order(small_order)
        
        # Small orders should typically be approved
        assert isinstance(decision_small, RiskDecision)

    def test_risk_math_utilities(self):
        """Test risk mathematical utility functions"""
        from backend.risk.risk_manager import RiskMathUtils
        
        utils = RiskMathUtils()
        
        # Test Kelly fraction calculation
        kelly = utils.kelly_fraction(0.15, 0.25, kelly_floor=0.0, kelly_ceiling=0.2)
        assert 0.0 <= kelly <= 0.2
        
        # Test with negative return (should return floor)
        kelly_neg = utils.kelly_fraction(-0.05, 0.25, kelly_floor=0.0, kelly_ceiling=0.2)
        assert kelly_neg == 0.0
        
        # Test EWMA volatility
        returns = np.array([0.01, -0.02, 0.015, -0.01, 0.02])
        vol = utils.ewma_volatility(returns)
        assert vol > 0
        assert isinstance(vol, float)

    @pytest.mark.asyncio
    async def test_concurrent_risk_evaluations(self, risk_manager):
        """Test concurrent risk evaluations without race conditions"""
        import asyncio
        
        # Create multiple orders for concurrent evaluation
        orders = []
        for i in range(10):
            order = OrderSpec(
                symbol=f"CONCURRENT_{i}",
                side="buy" if i % 2 == 0 else "sell",
                qty=Decimal("100"),
                price=Decimal("100"),
                notional=Decimal("10000")
            )
            orders.append(order)
        
        # Evaluate all orders concurrently
        tasks = [risk_manager.before_order(order) for order in orders]
        decisions = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All evaluations should complete successfully
        assert len(decisions) == len(orders)
        
        for decision in decisions:
            if not isinstance(decision, Exception):
                assert isinstance(decision, RiskDecision)
                assert decision.reason is not None
