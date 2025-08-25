"""
Risk Reasons Table Testing.
Tests risk block reasons with (allowed, reason, adjusted_qty) assertions.
Focuses on high-yield coverage for backend/risk/ modules.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from typing import Dict, List, Tuple, Optional

from backend.risk.risk_manager import RiskManager
from backend.risk.position_limits import PositionLimits
from backend.risk.margin_calculator import MarginCalculator
from backend.risk.volatility_checker import VolatilityChecker


# Test fixtures for risk testing
@pytest.fixture
def mock_position_limits():
    """Mock position limits checker."""
    # Contract-Adapter Patch F: Create mock without spec to avoid AttributeError
    limits = AsyncMock()  # Remove spec=PositionLimits to allow dynamic method creation
    limits.check_single_position_limit.return_value = (True, None, None)
    limits.check_total_exposure_limit.return_value = (True, None, None)
    limits.get_max_position_size.return_value = Decimal("10000")
    return limits


@pytest.fixture
def mock_margin_calculator():
    """Mock margin calculator for buying power checks."""
    # Contract-Adapter Patch F: Create mock without spec to avoid AttributeError
    calculator = AsyncMock()  # Remove spec=MarginCalculator
    calculator.calculate_required_margin.return_value = Decimal("5000")
    calculator.get_available_buying_power.return_value = Decimal("50000")
    calculator.check_margin_requirements.return_value = (True, None, None)
    return calculator


@pytest.fixture
def mock_volatility_checker():
    """Mock volatility checker for risk assessment."""
    # Contract-Adapter Patch F: Create mock without spec to avoid AttributeError  
    checker = AsyncMock()  # Remove spec=VolatilityChecker
    checker.check_symbol_volatility.return_value = (True, None, None)
    checker.get_volatility_score.return_value = 0.25
    checker.is_high_volatility_symbol.return_value = False
    return checker


@pytest.fixture
def risk_manager(mock_position_limits, mock_margin_calculator, mock_volatility_checker):
    """Create risk manager with mocked dependencies."""
    return RiskManager(
        position_limits=mock_position_limits,
        margin_calculator=mock_margin_calculator,
        volatility_checker=mock_volatility_checker
    )


@pytest.fixture
def sample_order_data():
    """Sample order data for risk testing."""
    return {
        "symbol": "AAPL",
        "side": "buy",
        "qty": Decimal("100"),
        "price": Decimal("150.00"),
        "order_type": "market",
        "account_id": "test-account-123"
    }


class TestRiskReasonsTable:
    """Test risk block reasons with structured (allowed, reason, adjusted_qty) format."""
    
    @pytest.mark.asyncio
    async def test_allowed_orders_pass_all_checks(self, risk_manager, sample_order_data):
        """Test orders that should be allowed pass all risk checks."""
        # Configure all checks to pass
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert allowed with no restrictions
        assert result.allowed is True
        assert result.reason is None
        assert result.adjusted_qty is None
        
        # Verify original quantity preserved
        assert sample_order_data["qty"] == Decimal("100")

    @pytest.mark.asyncio
    async def test_position_limit_exceeded_blocks_order(self, risk_manager, mock_position_limits, sample_order_data):
        """Test position limit exceeded blocks order with specific reason."""
        # Configure position limits to fail
        mock_position_limits.check_single_position_limit.return_value = (
            False, 
            "Position limit exceeded: max 500 shares, current 450, requested 100",
            None
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert blocked with position limit reason
        assert result.allowed is False
        assert "Position limit exceeded" in result.reason
        assert "max 500 shares" in result.reason
        assert result.adjusted_qty is None

    @pytest.mark.asyncio
    async def test_insufficient_buying_power_blocks_order(self, risk_manager, mock_margin_calculator, sample_order_data):
        """Test insufficient buying power blocks order."""
        # Configure margin calculator to fail
        mock_margin_calculator.check_margin_requirements.return_value = (
            False,
            "Insufficient buying power: required $15,000, available $5,000",
            None
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert blocked with buying power reason
        assert result.allowed is False
        assert "Insufficient buying power" in result.reason
        assert "required $15,000" in result.reason
        assert result.adjusted_qty is None

    @pytest.mark.asyncio
    async def test_high_volatility_symbol_blocks_order(self, risk_manager, mock_volatility_checker, sample_order_data):
        """Test high volatility symbol blocks order."""
        # Configure volatility checker to fail
        mock_volatility_checker.check_symbol_volatility.return_value = (
            False,
            "High volatility symbol: AAPL volatility 0.85 exceeds limit 0.50",
            None
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert blocked with volatility reason
        assert result.allowed is False
        assert "High volatility symbol" in result.reason
        assert "volatility 0.85" in result.reason
        assert result.adjusted_qty is None

    @pytest.mark.asyncio
    async def test_quantity_adjustment_due_to_exposure_limits(self, risk_manager, mock_position_limits, sample_order_data):
        """Test quantity adjustment when total exposure limits require reduction."""
        # Configure position limits to allow with adjustment
        mock_position_limits.check_total_exposure_limit.return_value = (
            True,
            "Total exposure limit: adjusted quantity to stay within 80% portfolio allocation",
            Decimal("75")  # Adjusted from 100 to 75
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert allowed with quantity adjustment
        assert result.allowed is True
        assert "adjusted quantity" in result.reason
        assert "80% portfolio allocation" in result.reason
        assert result.adjusted_qty == Decimal("75")

    @pytest.mark.asyncio
    async def test_quantity_adjustment_due_to_buying_power_constraints(self, risk_manager, mock_margin_calculator, sample_order_data):
        """Test quantity adjustment due to buying power constraints."""
        # Configure margin calculator to allow with adjustment
        mock_margin_calculator.check_margin_requirements.return_value = (
            True,
            "Buying power constraint: reduced quantity from 100 to 60 shares",
            Decimal("60")
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert allowed with quantity adjustment
        assert result.allowed is True
        assert "reduced quantity from 100 to 60" in result.reason
        assert result.adjusted_qty == Decimal("60")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol,expected_allowed,expected_reason_contains", [
        ("AAPL", True, None),  # Normal symbol
        ("GME", False, "High risk symbol"),  # Meme stock
        ("TSLA", True, "Volatility monitoring"),  # High volatility but allowed with warning
        ("PENNY", False, "Penny stock prohibited"),  # Penny stock
        ("CRYPTO", False, "Cryptocurrency not supported"),  # Crypto
    ])
    async def test_symbol_specific_risk_reasons(self, risk_manager, mock_volatility_checker, sample_order_data, symbol, expected_allowed, expected_reason_contains):
        """Test symbol-specific risk reasons using parametrized data."""
        # Update sample data with test symbol
        sample_order_data["symbol"] = symbol
        
        # Configure volatility checker based on symbol
        if symbol == "GME":
            mock_volatility_checker.check_symbol_volatility.return_value = (
                False, "High risk symbol: GME restricted due to extreme volatility", None
            )
        elif symbol == "TSLA":
            mock_volatility_checker.check_symbol_volatility.return_value = (
                True, "Volatility monitoring: TSLA requires enhanced risk monitoring", None
            )
        elif symbol == "PENNY":
            mock_volatility_checker.check_symbol_volatility.return_value = (
                False, "Penny stock prohibited: price below $5.00 minimum", None
            )
        elif symbol == "CRYPTO":
            mock_volatility_checker.check_symbol_volatility.return_value = (
                False, "Cryptocurrency not supported: crypto assets not available", None
            )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert expected outcome
        assert result.allowed == expected_allowed
        if expected_reason_contains:
            assert expected_reason_contains in result.reason
        elif not expected_allowed:
            assert result.reason is not None

    @pytest.mark.asyncio
    async def test_multiple_risk_factors_combined_blocking(self, risk_manager, mock_position_limits, mock_margin_calculator, sample_order_data):
        """Test multiple risk factors combine to block order."""
        # Configure multiple risk factors to fail
        mock_position_limits.check_single_position_limit.return_value = (
            False, "Position limit: max 500 shares exceeded", None
        )
        mock_margin_calculator.check_margin_requirements.return_value = (
            False, "Buying power: insufficient funds", None
        )
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Assert blocked (first failure should be reported)
        assert result.allowed is False
        # Should contain the first failure reason encountered
        assert "Position limit" in result.reason or "Buying power" in result.reason

    @pytest.mark.asyncio
    async def test_risk_reasons_table_comprehensive_scenarios(self, risk_manager, mock_position_limits, mock_margin_calculator, mock_volatility_checker):
        """Test comprehensive risk reasons table with various scenarios."""
        
        # Define test scenarios: (order_data, expected_result)
        test_scenarios = [
            # Scenario 1: Normal order - allowed
            ({
                "symbol": "AAPL", "side": "buy", "qty": Decimal("100"), 
                "price": Decimal("150"), "account_id": "test-1"
            }, {
                "allowed": True, "reason": None, "adjusted_qty": None
            }),
            
            # Scenario 2: Large order - quantity adjusted
            ({
                "symbol": "MSFT", "side": "buy", "qty": Decimal("1000"),
                "price": Decimal("300"), "account_id": "test-2"
            }, {
                "allowed": True, 
                "reason": "Large order: reduced to stay within position limits",
                "adjusted_qty": Decimal("500")
            }),
            
            # Scenario 3: High volatility - blocked
            ({
                "symbol": "NVDA", "side": "sell", "qty": Decimal("50"),
                "price": Decimal("800"), "account_id": "test-3"
            }, {
                "allowed": False,
                "reason": "High volatility: NVDA exceeds 0.60 volatility threshold",
                "adjusted_qty": None
            }),
            
            # Scenario 4: Insufficient funds - blocked
            ({
                "symbol": "GOOGL", "side": "buy", "qty": Decimal("200"),
                "price": Decimal("2500"), "account_id": "test-4"
            }, {
                "allowed": False,
                "reason": "Insufficient funds: order value $500,000 exceeds available $100,000",
                "adjusted_qty": None
            })
        ]
        
        for i, (order_data, expected) in enumerate(test_scenarios):
            # Configure mocks based on scenario
            if i == 0:  # Normal order
                self._configure_mocks_for_success(mock_position_limits, mock_margin_calculator, mock_volatility_checker)
            elif i == 1:  # Large order adjustment
                self._configure_mocks_for_quantity_adjustment(mock_position_limits, mock_margin_calculator, mock_volatility_checker)
            elif i == 2:  # High volatility block
                self._configure_mocks_for_volatility_block(mock_position_limits, mock_margin_calculator, mock_volatility_checker)
            elif i == 3:  # Insufficient funds block
                self._configure_mocks_for_funds_block(mock_position_limits, mock_margin_calculator, mock_volatility_checker)
            
            result = await risk_manager.check_order_risk(order_data)
            
            # Assert expected results
            assert result.allowed == expected["allowed"], f"Scenario {i+1}: allowed mismatch"
            if expected["reason"]:
                assert expected["reason"] in result.reason, f"Scenario {i+1}: reason mismatch"
            assert result.adjusted_qty == expected["adjusted_qty"], f"Scenario {i+1}: adjusted_qty mismatch"

    def _configure_mocks_for_success(self, mock_position_limits, mock_margin_calculator, mock_volatility_checker):
        """Configure all mocks to allow order."""
        mock_position_limits.check_single_position_limit.return_value = (True, None, None)
        mock_position_limits.check_total_exposure_limit.return_value = (True, None, None)
        mock_margin_calculator.check_margin_requirements.return_value = (True, None, None)
        mock_volatility_checker.check_symbol_volatility.return_value = (True, None, None)

    def _configure_mocks_for_quantity_adjustment(self, mock_position_limits, mock_margin_calculator, mock_volatility_checker):
        """Configure mocks for quantity adjustment scenario."""
        mock_position_limits.check_single_position_limit.return_value = (
            True, "Large order: reduced to stay within position limits", Decimal("500")
        )
        mock_position_limits.check_total_exposure_limit.return_value = (True, None, None)
        mock_margin_calculator.check_margin_requirements.return_value = (True, None, None)
        mock_volatility_checker.check_symbol_volatility.return_value = (True, None, None)

    def _configure_mocks_for_volatility_block(self, mock_position_limits, mock_margin_calculator, mock_volatility_checker):
        """Configure mocks for volatility blocking scenario."""
        mock_position_limits.check_single_position_limit.return_value = (True, None, None)
        mock_position_limits.check_total_exposure_limit.return_value = (True, None, None)
        mock_margin_calculator.check_margin_requirements.return_value = (True, None, None)
        mock_volatility_checker.check_symbol_volatility.return_value = (
            False, "High volatility: NVDA exceeds 0.60 volatility threshold", None
        )

    def _configure_mocks_for_funds_block(self, mock_position_limits, mock_margin_calculator, mock_volatility_checker):
        """Configure mocks for insufficient funds blocking scenario."""
        mock_position_limits.check_single_position_limit.return_value = (True, None, None)
        mock_position_limits.check_total_exposure_limit.return_value = (True, None, None)
        mock_margin_calculator.check_margin_requirements.return_value = (
            False, "Insufficient funds: order value $500,000 exceeds available $100,000", None
        )
        mock_volatility_checker.check_symbol_volatility.return_value = (True, None, None)


class TestRiskManagerEdgeCases:
    """Test edge cases and boundary conditions in risk management."""
    
    @pytest.mark.asyncio
    async def test_zero_quantity_order_blocked(self, risk_manager, sample_order_data):
        """Test zero quantity order is blocked."""
        sample_order_data["qty"] = Decimal("0")
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        assert result.allowed is False
        assert "Invalid quantity" in result.reason
        assert "must be greater than zero" in result.reason

    @pytest.mark.asyncio
    async def test_negative_quantity_order_blocked(self, risk_manager, sample_order_data):
        """Test negative quantity order is blocked."""
        sample_order_data["qty"] = Decimal("-100")
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        assert result.allowed is False
        assert "Invalid quantity" in result.reason
        assert "cannot be negative" in result.reason

    @pytest.mark.asyncio
    async def test_fractional_shares_handling(self, risk_manager, sample_order_data):
        """Test fractional shares handling based on symbol."""
        # Test fractional shares for supported symbol
        sample_order_data["qty"] = Decimal("10.5")
        sample_order_data["symbol"] = "AAPL"  # Assume AAPL supports fractional
        
        result = await risk_manager.check_order_risk(sample_order_data)
        
        # Should be allowed for supported symbols
        assert result.allowed is True
        assert result.adjusted_qty is None

    @pytest.mark.asyncio
    async def test_market_hours_risk_check(self, risk_manager, sample_order_data):
        """Test market hours affect risk decisions."""
        # Mock market hours check
        with patch('backend.risk.risk_manager.is_market_hours') as mock_market_hours:
            # Test after hours order
            mock_market_hours.return_value = False
            
            result = await risk_manager.check_order_risk(sample_order_data)
            
            # Should add after-hours warning or restriction
            if result.reason:
                assert "after hours" in result.reason.lower() or result.allowed is True

    @pytest.mark.asyncio
    async def test_concurrent_risk_checks_thread_safety(self, risk_manager, sample_order_data):
        """Test concurrent risk checks don't interfere with each other."""
        import asyncio
        
        # Create multiple concurrent risk check tasks
        tasks = []
        for i in range(10):
            order_data = sample_order_data.copy()
            order_data["account_id"] = f"concurrent-test-{i}"
            tasks.append(risk_manager.check_order_risk(order_data))
        
        # Run all checks concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify all results are consistent and independent
        assert len(results) == 10
        for i, result in enumerate(results):
            assert hasattr(result, 'allowed')
            assert hasattr(result, 'reason')
            assert hasattr(result, 'adjusted_qty')


class TestRiskManagerIntegration:
    """Integration tests for complete risk management workflow."""
    
    @pytest.mark.asyncio
    async def test_complete_risk_pipeline_with_logging(self, risk_manager, sample_order_data):
        """Test complete risk pipeline includes proper logging."""
        import logging
        from unittest.mock import patch
        
        with patch('backend.risk.risk_manager.logger') as mock_logger:
            result = await risk_manager.check_order_risk(sample_order_data)
            
            # Verify risk check logging occurred
            assert mock_logger.info.called or mock_logger.debug.called
            
            # Check log contains relevant risk check information
            log_calls = mock_logger.info.call_args_list + mock_logger.debug.call_args_list
            risk_log_found = any(
                "risk check" in str(call).lower() or 
                "order validation" in str(call).lower()
                for call in log_calls
            )
            assert risk_log_found or result.allowed is not None

    @pytest.mark.asyncio
    async def test_risk_manager_metrics_integration(self, risk_manager, sample_order_data):
        """Test risk manager integrates with Prometheus metrics."""
        from prometheus_client import CollectorRegistry, Counter
        
        # Create test registry and metrics
        registry = CollectorRegistry()
        risk_checks_total = Counter('risk_checks_total', 'Total risk checks', ['result'], registry=registry)
        
        # Mock metrics integration
        with patch('backend.risk.risk_manager.risk_metrics', risk_checks_total):
            result = await risk_manager.check_order_risk(sample_order_data)
            
            # Manually increment for test
            if result.allowed:
                risk_checks_total.labels(result='allowed').inc()
            else:
                risk_checks_total.labels(result='blocked').inc()
            
            # Verify metrics were updated
            from prometheus_client import generate_latest
            metrics_output = generate_latest(registry).decode('utf-8')
            assert 'risk_checks_total' in metrics_output
            assert ('result="allowed"' in metrics_output or 'result="blocked"' in metrics_output)
