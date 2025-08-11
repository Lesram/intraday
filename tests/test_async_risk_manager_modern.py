"""
Modern Risk Manager Tests
Tests for AsyncRiskManager with proper typing using OrderSpec and PortfolioState.
This is the preferred test pattern for new risk management tests.
"""
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
import pytest

from backend.risk.risk_manager import AsyncRiskManager, RiskMathUtils
from backend.risk.types import OrderSpec, PortfolioState, RiskDecision, RiskLimits


class TestAsyncRiskManagerModern:
    """Modern tests for AsyncRiskManager with proper typing."""

    def setup_method(self):
        """Setup for each test method."""
        self.risk_manager = AsyncRiskManager(
            max_position_per_symbol=10000,
            max_single_position_value=100000,
            max_portfolio_var=0.05
        )

    @pytest.mark.asyncio
    async def test_before_order_basic_validation(self):
        """Test basic order validation with OrderSpec."""
        # Create a reasonable order
        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            notional=Decimal("15000"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order)

        assert isinstance(decision, RiskDecision)
        assert isinstance(decision.allowed, bool)
        assert isinstance(decision.reason, str)
        assert decision.original_qty == Decimal("100")

    @pytest.mark.asyncio
    async def test_before_order_excessive_position_size(self):
        """Test position size limits enforcement."""
        # Create order that exceeds position limits
        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("15000"),  # Exceeds max_position_per_symbol
            notional=Decimal("2250000"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order)

        # Should be blocked due to position size
        assert not decision.allowed
        assert "position_limit" in decision.reason or "limit" in decision.reason

    @pytest.mark.asyncio
    async def test_before_order_excessive_notional_value(self):
        """Test notional value limits enforcement."""
        # Create order with excessive notional value
        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("1000"),
            notional=Decimal("200000"),  # Exceeds max_single_position_value
            price=Decimal("200.0")
        )

        decision = await self.risk_manager.before_order(order)

        # Should be blocked due to notional value
        assert not decision.allowed
        assert "value" in decision.reason or "notional" in decision.reason

    @pytest.mark.asyncio
    async def test_before_order_with_portfolio_state(self):
        """Test risk assessment with explicit portfolio state."""
        portfolio_state = PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            positions={"AAPL": Decimal("100")},
            sector_map={"AAPL": "Technology"},
            last_updated=datetime.now(timezone.utc)
        )

        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("50"),
            notional=Decimal("7500"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order, portfolio_state)

        assert isinstance(decision, RiskDecision)
        # This should generally be allowed
        # The specific outcome depends on risk calculations

    @pytest.mark.asyncio
    async def test_before_order_sell_side(self):
        """Test sell order handling."""
        order = OrderSpec(
            symbol="AAPL",
            side="sell",
            qty=Decimal("100"),
            notional=Decimal("15000"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order)

        assert isinstance(decision, RiskDecision)
        assert decision.original_qty == Decimal("100")

    @pytest.mark.asyncio
    async def test_before_order_market_order(self):
        """Test market order (no price specified)."""
        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            notional=Decimal("15000"),
            price=None  # Market order
        )

        decision = await self.risk_manager.before_order(order)

        assert isinstance(decision, RiskDecision)
        # Should handle market orders appropriately

    @pytest.mark.asyncio
    async def test_risk_decision_structure(self):
        """Test that RiskDecision contains all expected fields."""
        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("50"),
            notional=Decimal("7500"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order)

        # Verify decision structure
        assert hasattr(decision, 'allowed')
        assert hasattr(decision, 'reason')
        assert hasattr(decision, 'adjustments')
        assert hasattr(decision, 'limits')
        assert hasattr(decision, 'original_qty')
        assert hasattr(decision, 'adjusted_qty')
        assert hasattr(decision, 'timestamp')

        # Verify types
        assert isinstance(decision.adjustments, dict)
        assert isinstance(decision.limits, dict)
        assert decision.timestamp is not None

    @pytest.mark.asyncio
    async def test_concurrent_risk_checks(self):
        """Test concurrent risk checks for multiple orders."""
        orders = [
            OrderSpec(
                symbol=f"STOCK_{i}",
                side="buy",
                qty=Decimal("100"),
                notional=Decimal("10000"),
                price=Decimal("100.0")
            )
            for i in range(5)
        ]

        # Execute risk checks concurrently
        tasks = [self.risk_manager.before_order(order) for order in orders]
        decisions = await asyncio.gather(*tasks)

        # All should be decisions
        assert len(decisions) == 5
        assert all(isinstance(d, RiskDecision) for d in decisions)

    @pytest.mark.asyncio
    async def test_metrics_recording(self):
        """Test that risk decisions record appropriate metrics."""
        # Mock the metrics registry to capture calls
        mock_metrics = Mock()
        self.risk_manager.metrics = mock_metrics
        
        # Configure mock methods
        mock_counter = Mock()
        mock_histogram = Mock()
        mock_metrics.counter.return_value = mock_counter
        mock_metrics.histogram.return_value = mock_histogram

        order = OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            notional=Decimal("15000"),
            price=Decimal("150.0")
        )

        decision = await self.risk_manager.before_order(order)

        # Verify metrics were called
        assert mock_metrics.counter.called
        assert mock_metrics.histogram.called

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in risk assessment."""
        # Mock an internal method to raise an exception
        with patch.object(self.risk_manager, '_evaluate_order_comprehensive') as mock_eval:
            mock_eval.side_effect = Exception("Test error")
            
            order = OrderSpec(
                symbol="AAPL",
                side="buy",
                qty=Decimal("100"),
                notional=Decimal("15000"),
                price=Decimal("150.0")
            )

            decision = await self.risk_manager.before_order(order)

            # Should return blocked decision on error
            assert not decision.allowed
            assert "other" in decision.reason or "error" in decision.reason.lower()


class TestRiskMathUtilsModern:
    """Modern tests for risk mathematics utilities."""

    def setup_method(self):
        """Setup for each test method."""
        self.math_utils = RiskMathUtils()

    def test_kelly_fraction_normal_case(self):
        """Test Kelly fraction calculation with normal parameters."""
        kelly = self.math_utils.kelly_fraction(
            mean_return=0.1,
            variance=0.04,
            kelly_floor=0.0,
            kelly_ceiling=0.2
        )
        
        assert isinstance(kelly, float)
        assert 0.0 <= kelly <= 0.2
        # With mean_return=0.1 and variance=0.04, kelly = 0.1/0.04 = 2.5
        # But should be capped at kelly_ceiling=0.2
        assert kelly <= 0.2

    def test_kelly_fraction_edge_cases(self):
        """Test Kelly fraction calculation edge cases."""
        # Zero or negative return
        kelly_zero = self.math_utils.kelly_fraction(0.0, 0.04)
        assert kelly_zero == 0.0

        kelly_negative = self.math_utils.kelly_fraction(-0.01, 0.04)
        assert kelly_negative == 0.0

        # Zero variance
        kelly_no_var = self.math_utils.kelly_fraction(0.1, 0.0)
        assert kelly_no_var == 0.0

    def test_ewma_volatility(self):
        """Test EWMA volatility calculation."""
        import numpy as np
        
        returns = np.array([0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.018, 0.003])
        volatility = self.math_utils.ewma_volatility(returns)
        
        assert isinstance(volatility, float)
        assert volatility > 0
        assert volatility < 1.0  # Reasonable volatility range

    def test_parametric_var(self):
        """Test parametric VaR calculation."""
        returns = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.018, 0.003, -0.01, 0.007]
        
        var_95 = self.math_utils.parametric_var(returns, confidence=0.05)  # 95% confidence
        var_99 = self.math_utils.parametric_var(returns, confidence=0.01)  # 99% confidence
        
        assert isinstance(var_95, float)
        assert isinstance(var_99, float)
        # VaR at 99% should be higher than 95%
        assert var_99 >= var_95
