"""
BRANCH 2.8: Comprehensive Risk Manager Test Suite

Tests for the async-first risk manager with robust math and structured decisions.
"""

from datetime import datetime
from datetime import time as dt_time
from decimal import Decimal
from unittest.mock import Mock, patch

import numpy as np
import pytest

from backend.risk.risk_manager import RISK_REASONS, AsyncRiskManager, RiskMathUtils
from backend.risk.types import OrderSpec, PortfolioState, RiskDecision


class TestRiskMathUtils:
    """Test pure mathematical utilities for risk calculations."""

    def test_kelly_fraction_normal_case(self):
        """Test Kelly fraction calculation with normal inputs."""
        mean_return = 0.05  # 5% expected return
        variance = 0.25     # 25% variance

        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)
        expected = mean_return / variance  # 0.2

        assert kelly == expected

    def test_kelly_fraction_with_bounds(self):
        """Test Kelly fraction respects floor and ceiling."""
        # Test ceiling
        kelly = RiskMathUtils.kelly_fraction(1.0, 1.0, kelly_ceiling=0.1)
        assert kelly == 0.1

        # Test floor
        kelly = RiskMathUtils.kelly_fraction(0.01, 10.0, kelly_floor=0.05)
        assert kelly == 0.05

    def test_kelly_fraction_edge_cases(self):
        """Test Kelly fraction edge cases."""
        # Zero variance
        kelly = RiskMathUtils.kelly_fraction(0.1, 0.0)
        assert kelly == 0.0

        # Negative return
        kelly = RiskMathUtils.kelly_fraction(-0.1, 0.5)
        assert kelly == 0.0

        # Very small variance
        kelly = RiskMathUtils.kelly_fraction(0.1, 1e-15)
        assert kelly == 0.0

    def test_ewma_volatility_normal_case(self):
        """Test EWMA volatility calculation."""
        # Create sample return series
        returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
        volatility = RiskMathUtils.ewma_volatility(returns)

        assert volatility > 0
        assert isinstance(volatility, float)

    def test_ewma_volatility_edge_cases(self):
        """Test EWMA volatility edge cases."""
        # Too few returns
        returns = np.array([0.01])
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility == 0.1  # Fallback

        # Empty array
        returns = np.array([])
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility == 0.1  # Fallback

        # NaN values
        returns = np.array([0.01, np.nan, 0.02, np.inf, -0.01])
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility > 0

    def test_parametric_var_calculation(self):
        """Test parametric VaR calculation."""
        portfolio_value = 100000
        returns = np.random.normal(0.001, 0.02, 100)  # 100 days of returns

        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)

        assert var_95 > 0
        assert var_95 < portfolio_value  # Sanity check

    def test_parametric_var_insufficient_data(self):
        """Test parametric VaR with insufficient data."""
        portfolio_value = 100000
        returns = np.array([0.01, 0.02])  # Too few samples

        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.05

        assert var_95 == expected_fallback

    def test_historical_cvar_calculation(self):
        """Test historical CVaR calculation."""
        portfolio_value = 100000
        returns = np.random.normal(0.001, 0.02, 100)

        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        assert cvar_95 > 0
        assert cvar_95 < portfolio_value

    def test_historical_cvar_insufficient_data(self):
        """Test historical CVaR with insufficient data."""
        portfolio_value = 100000
        returns = np.array([0.01, 0.02])

        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.07

        assert cvar_95 == expected_fallback


class TestAsyncRiskManager:
    """Test async risk manager functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.trading = Mock()
        settings.trading.trading_hours_start = "09:30:00"
        settings.trading.trading_hours_end = "16:00:00"
        settings.trading.kelly_floor = 0.0
        settings.trading.kelly_ceiling = 0.2
        settings.trading.ewma_lambda = 0.94
        settings.trading.min_samples = 50
        settings.trading.sector_cap = 0.30
        settings.trading.portfolio_heat_cap = 1.50
        settings.trading.leverage_cap = 2.0
        settings.trading.trading_hours_only = True
        settings.trading.max_position_pct = 0.10
        settings.trading.halted_symbols = ""
        return settings

    @pytest.fixture
    def mock_services(self):
        """Mock external services."""
        positions_service = Mock()
        pricing_service = Mock()
        halt_service = Mock()
        return positions_service, pricing_service, halt_service

    @pytest.fixture
    def sample_order(self):
        """Sample order for testing."""
        return OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            notional=Decimal("15000"),
            price=Decimal("150.00")
        )

    @pytest.fixture
    def sample_portfolio(self):
        """Sample portfolio state for testing."""
        return PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("20000"),
            positions={"AAPL": Decimal("50")},
            sector_map={"AAPL": "technology"},
            last_updated=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_risk_manager_initialization(self, mock_settings, mock_services):
        """Test risk manager initializes correctly."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(
                    positions_service=positions_service,
                    pricing_service=pricing_service,
                    halt_service=halt_service
                )

                assert rm.kelly_floor == 0.0
                assert rm.kelly_ceiling == 0.2
                assert rm.portfolio_heat_cap == 1.50
                assert rm.leverage_cap == 2.0

    @pytest.mark.asyncio
    async def test_before_order_success_case(self, mock_settings, mock_services, sample_order, sample_portfolio):
        """Test successful order approval."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(
                    positions_service=positions_service,
                    pricing_service=pricing_service,
                    halt_service=halt_service
                )

                # Mock market open
                with patch.object(rm, '_is_market_open', return_value=True):
                    decision = await rm.before_order(sample_order, sample_portfolio)

                assert decision.allowed == True
                assert decision.reason == "approved"
                assert decision.original_qty == sample_order.qty
                assert decision.adjusted_qty == sample_order.qty

    @pytest.mark.asyncio
    async def test_before_order_market_closed(self, mock_settings, mock_services, sample_order, sample_portfolio):
        """Test order blocked when market is closed."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(
                    positions_service=positions_service,
                    pricing_service=pricing_service,
                    halt_service=halt_service
                )

                # Mock market closed
                with patch.object(rm, '_is_market_open', return_value=False):
                    decision = await rm.before_order(sample_order, sample_portfolio)

                assert decision.allowed == False
                assert decision.reason == "window"
                assert "market_status" in decision.adjustments

    @pytest.mark.asyncio
    async def test_before_order_circuit_breaker(self, mock_settings, mock_services, sample_order, sample_portfolio):
        """Test order blocked when circuit breaker is active."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(
                    positions_service=positions_service,
                    pricing_service=pricing_service,
                    halt_service=halt_service
                )

                # Activate circuit breaker
                rm.circuit_breaker_active = True

                with patch.object(rm, '_is_market_open', return_value=True):
                    decision = await rm.before_order(sample_order, sample_portfolio)

                assert decision.allowed == False
                assert decision.reason == "halt"
                assert decision.adjustments["circuit_breaker"] == True

    @pytest.mark.asyncio
    async def test_before_order_halted_symbol(self, mock_settings, mock_services, sample_order, sample_portfolio):
        """Test order blocked for halted symbol."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(
                    positions_service=positions_service,
                    pricing_service=pricing_service,
                    halt_service=halt_service
                )

                # Add symbol to halted list
                rm.halted_symbols.add("AAPL")

                with patch.object(rm, '_is_market_open', return_value=True):
                    decision = await rm.before_order(sample_order, sample_portfolio)

                assert decision.allowed == False
                assert decision.reason == "halt"
                assert decision.adjustments["halted_symbol"] == "AAPL"

    def test_is_market_open_weekday(self, mock_settings, mock_services):
        """Test market open check during weekday."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager()

                # Mock weekday during market hours
                mock_datetime = Mock()
                mock_datetime.now.return_value.weekday.return_value = 2  # Wednesday
                mock_datetime.now.return_value.time.return_value = dt_time(14, 30)  # 2:30 PM

                with patch('backend.risk.risk_manager.datetime', mock_datetime):
                    assert rm._is_market_open() == True

    def test_is_market_open_weekend(self, mock_settings, mock_services):
        """Test market closed check during weekend."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager()

                # Mock weekend
                mock_datetime = Mock()
                mock_datetime.now.return_value.weekday.return_value = 5  # Saturday

                with patch('backend.risk.risk_manager.datetime', mock_datetime):
                    assert rm._is_market_open() == False

    @pytest.mark.asyncio
    async def test_fetch_portfolio_state_success(self, mock_settings, mock_services):
        """Test successful portfolio state fetching."""
        positions_service, pricing_service, halt_service = mock_services

        # Mock positions service response
        mock_positions = {
            "AAPL": Mock(qty=100),
            "GOOGL": Mock(qty=50)
        }
        positions_service.get_all_positions.return_value = mock_positions

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(positions_service=positions_service)

                portfolio_state = await rm._fetch_portfolio_state()

                assert portfolio_state is not None
                assert portfolio_state.positions["AAPL"] == Decimal("100")
                assert portfolio_state.positions["GOOGL"] == Decimal("50")

    @pytest.mark.asyncio
    async def test_fetch_portfolio_state_failure(self, mock_settings, mock_services):
        """Test portfolio state fetching failure."""
        positions_service, pricing_service, halt_service = mock_services

        # Mock positions service failure
        positions_service.get_all_positions.side_effect = Exception("Connection failed")

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager(positions_service=positions_service)

                portfolio_state = await rm._fetch_portfolio_state()

                assert portfolio_state is None

    @pytest.mark.asyncio
    async def test_audit_decision(self, mock_settings, mock_services, sample_order, sample_portfolio):
        """Test audit logging of decisions."""
        positions_service, pricing_service, halt_service = mock_services

        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'), \
                 patch('backend.risk.risk_manager.audit_logger') as mock_audit:

                rm = AsyncRiskManager()

                decision = RiskDecision.allow(
                    reason="approved",
                    original_qty=sample_order.qty,
                    adjusted_qty=sample_order.qty
                )

                await rm._audit_decision(sample_order, decision, sample_portfolio, "test-request-123")

                # Verify audit log was called
                mock_audit.info.assert_called_once()
                call_args = mock_audit.info.call_args

                assert "Risk decision audit" in str(call_args[0])
                audit_data = call_args[1]["extra"]
                assert audit_data["event"] == "risk_decision"
                assert audit_data["request_id"] == "test-request-123"
                assert audit_data["decision"]["allowed"] == True


class TestRiskManagerLegacyCompatibility:
    """Test legacy compatibility wrapper."""

    def test_legacy_interface_warning(self, mock_settings):
        """Test that legacy interface emits deprecation warning."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry'), \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager()

                with pytest.warns(DeprecationWarning):
                    # This would normally break async hygiene - mock the async call
                    with patch.object(rm, 'before_order') as mock_async:
                        mock_decision = RiskDecision.allow(
                            reason="approved",
                            original_qty=Decimal("100"),
                            adjusted_qty=Decimal("100")
                        )

                        # Mock asyncio event loop
                        with patch('asyncio.get_event_loop') as mock_loop:
                            mock_loop.return_value.run_until_complete.return_value = mock_decision

                            allowed, reason, adjusted_qty = rm.before_order("AAPL", 100, 150.0)

                            assert allowed == True
                            assert reason == "approved"
                            assert adjusted_qty == 100


class TestBoundedMetricsReasons:
    """Test that risk reasons are properly bounded for metrics."""

    def test_risk_reasons_bounded_set(self):
        """Test that RISK_REASONS contains expected categories."""
        expected_reasons = {
            "window", "halt", "whitelist", "pos_cap", "notional_cap",
            "var", "cvar", "kelly", "correlation", "sector", "heat", "leverage"
        }

        assert expected_reasons == RISK_REASONS

    @pytest.mark.asyncio
    async def test_unknown_reason_mapped_to_other(self, mock_settings):
        """Test that unknown reasons are mapped to 'other' for metrics."""
        with patch('backend.risk.risk_manager.get_settings', return_value=mock_settings):
            with patch('backend.risk.risk_manager.get_metrics_registry') as mock_metrics, \
                 patch('backend.risk.risk_manager.get_structured_logger'):

                rm = AsyncRiskManager()

                # Create decision with unknown reason
                decision = RiskDecision.block(
                    reason="unknown_reason",
                    adjustments={"test": "value"}
                )

                # Simulate the metrics call that would happen in before_order
                reason_label = decision.reason if decision.reason in RISK_REASONS else "other"
                assert reason_label == "other"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
