"""
Comprehensive tests for backend/infra/validation.py
Tests input validation utilities with edge cases.
Target: Increase coverage from 0% to 90%+
"""

import pytest
from decimal import Decimal

from backend.infra.validation import (
    validate_symbol,
    validate_price,
    validate_quantity,
    validate_order,
    validate_portfolio_constraints,
    validate_risk_limits,
    validate_market_data,
)

pytestmark = pytest.mark.unit


# ============================================================================
# VALIDATE SYMBOL TESTS
# ============================================================================

class TestValidateSymbol:
    """Tests for validate_symbol function."""

    def test_valid_uppercase_symbol(self):
        """Test valid uppercase symbol passes."""
        result = validate_symbol("AAPL")
        assert result == "AAPL"

    def test_valid_lowercase_symbol(self):
        """Test lowercase symbol is normalized to uppercase."""
        result = validate_symbol("aapl")
        assert result == "AAPL"

    def test_valid_mixed_case_symbol(self):
        """Test mixed case symbol is normalized."""
        result = validate_symbol("AaPl")
        assert result == "AAPL"

    def test_valid_symbol_with_dot(self):
        """Test symbol with dot is valid."""
        result = validate_symbol("BRK.A")
        assert result == "BRK.A"

    def test_valid_symbol_with_hyphen(self):
        """Test symbol with hyphen is valid."""
        result = validate_symbol("BF-B")
        assert result == "BF-B"

    def test_valid_symbol_with_numbers(self):
        """Test symbol with numbers is valid."""
        result = validate_symbol("A123")
        assert result == "A123"

    def test_empty_symbol_raises_error(self):
        """Test empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol("")

    def test_symbol_too_long_raises_error(self):
        """Test symbol longer than 10 chars raises ValueError."""
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_symbol("ABCDEFGHIJK")

    def test_symbol_starting_with_number_raises_error(self):
        """Test symbol starting with number raises ValueError."""
        with pytest.raises(ValueError, match="cannot start with number"):
            validate_symbol("123ABC")

    def test_symbol_with_special_chars_raises_error(self):
        """Test symbol with special characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid characters"):
            validate_symbol("AAPL!")

    def test_symbol_with_space_raises_error(self):
        """Test symbol with space raises ValueError."""
        with pytest.raises(ValueError, match="Invalid characters"):
            validate_symbol("AA PL")


# ============================================================================
# VALIDATE PRICE TESTS
# ============================================================================

class TestValidatePrice:
    """Tests for validate_price function."""

    def test_valid_price(self):
        """Test valid price passes."""
        result = validate_price(150.50)
        assert result == 150.50

    def test_price_with_4_decimals_passes(self):
        """Test price with exactly 4 decimal places passes."""
        result = validate_price(150.1234)
        assert result == 150.1234

    def test_small_valid_price(self):
        """Test small but valid price."""
        result = validate_price(0.0001)
        assert result == 0.0001

    def test_zero_price_raises_error(self):
        """Test zero price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(0)

    def test_negative_price_raises_error(self):
        """Test negative price raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-100.0)

    def test_price_too_large_raises_error(self):
        """Test price over $100 million raises ValueError."""
        with pytest.raises(ValueError, match="Price too large"):
            validate_price(1e9)

    def test_price_at_max_boundary(self):
        """Test price at maximum boundary passes."""
        result = validate_price(1e8 - 1)  # Just under $100 million
        assert result == 99999999.0

    def test_price_with_5_decimals_raises_error(self):
        """Test price with 5+ decimal places (exact) raises ValueError."""
        with pytest.raises(ValueError, match="Too many decimal places"):
            validate_price(1.00001)


# ============================================================================
# VALIDATE QUANTITY TESTS
# ============================================================================

class TestValidateQuantity:
    """Tests for validate_quantity function."""

    def test_valid_integer_quantity(self):
        """Test valid integer quantity passes."""
        result = validate_quantity(100)
        assert result == 100.0

    def test_valid_fractional_quantity(self):
        """Test valid fractional quantity passes when allowed."""
        result = validate_quantity(100.5, allow_fractional=True)
        assert result == 100.5

    def test_negative_quantity_allowed(self):
        """Test negative quantity (for short sells) is allowed."""
        result = validate_quantity(-100)
        assert result == -100.0

    def test_zero_quantity_raises_error(self):
        """Test zero quantity raises ValueError."""
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0)

    def test_quantity_too_large_raises_error(self):
        """Test quantity over 100 million raises ValueError."""
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(1e9)

    def test_negative_quantity_too_large_raises_error(self):
        """Test negative quantity magnitude over limit raises ValueError."""
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(-1e9)

    def test_fractional_not_allowed_with_whole_number(self):
        """Test whole number passes when fractional not allowed."""
        result = validate_quantity(100, allow_fractional=False)
        assert result == 100.0

    def test_fractional_not_allowed_raises_error(self):
        """Test fractional quantity raises error when not allowed."""
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            validate_quantity(100.5, allow_fractional=False)


# ============================================================================
# VALIDATE ORDER TESTS
# ============================================================================

class TestValidateOrder:
    """Tests for validate_order function."""

    def test_valid_market_order(self):
        """Test valid market order passes."""
        order_data = {"symbol": "aapl", "quantity": 100}
        result = validate_order(order_data)
        
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["order_type"] == "market"

    def test_valid_limit_order(self):
        """Test valid limit order with price passes."""
        order_data = {
            "symbol": "MSFT",
            "quantity": 50,
            "price": 350.00,
            "order_type": "limit"
        }
        result = validate_order(order_data)
        
        assert result["symbol"] == "MSFT"
        assert result["quantity"] == 50.0
        assert result["price"] == 350.0
        assert result["order_type"] == "limit"

    def test_valid_stop_order(self):
        """Test valid stop order passes."""
        order_data = {
            "symbol": "GOOGL",
            "quantity": 10,
            "order_type": "stop"
        }
        result = validate_order(order_data)
        assert result["order_type"] == "stop"

    def test_valid_stop_limit_order(self):
        """Test valid stop_limit order passes."""
        order_data = {
            "symbol": "AMZN",
            "quantity": 5,
            "order_type": "stop_limit"
        }
        result = validate_order(order_data)
        assert result["order_type"] == "stop_limit"

    def test_order_type_case_insensitive(self):
        """Test order type is case insensitive."""
        order_data = {
            "symbol": "NVDA",
            "quantity": 25,
            "order_type": "LIMIT"
        }
        result = validate_order(order_data)
        assert result["order_type"] == "limit"

    def test_missing_symbol_raises_error(self):
        """Test missing symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_order({"quantity": 100})

    def test_missing_quantity_raises_error(self):
        """Test missing quantity raises ValueError."""
        with pytest.raises(ValueError, match="Quantity is required"):
            validate_order({"symbol": "AAPL"})

    def test_invalid_order_type_raises_error(self):
        """Test invalid order type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid order type"):
            validate_order({
                "symbol": "AAPL",
                "quantity": 100,
                "order_type": "fill_or_kill"  # Not supported
            })

    def test_invalid_symbol_in_order_raises_error(self):
        """Test invalid symbol in order raises ValueError."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_order({"symbol": "", "quantity": 100})

    def test_invalid_quantity_in_order_raises_error(self):
        """Test invalid quantity in order raises ValueError."""
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_order({"symbol": "AAPL", "quantity": 0})

    def test_invalid_price_in_order_raises_error(self):
        """Test invalid price in order raises ValueError."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_order({
                "symbol": "AAPL",
                "quantity": 100,
                "price": -50.0
            })


# ============================================================================
# VALIDATE PORTFOLIO CONSTRAINTS TESTS
# ============================================================================

class TestValidatePortfolioConstraints:
    """Tests for validate_portfolio_constraints function."""

    def test_valid_diversified_portfolio(self):
        """Test diversified portfolio with no violations."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.20},
                "MSFT": {"weight": 0.20},
                "GOOGL": {"weight": 0.20},
                "AMZN": {"weight": 0.20},
                "NVDA": {"weight": 0.20},
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert violations == []

    def test_excessive_concentration_violation(self):
        """Test single position over 30% triggers violation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.35},  # Over 30% limit
                "MSFT": {"weight": 0.20},
                "GOOGL": {"weight": 0.15},
                "AMZN": {"weight": 0.15},
                "NVDA": {"weight": 0.15},
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        
        assert len(violations) == 1
        assert "Excessive concentration" in violations[0]

    def test_total_exposure_violation(self):
        """Test total exposure over 100% triggers violation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.30},
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.30},
                "AMZN": {"weight": 0.20},  # Total = 110%
                "NVDA": {"weight": 0.10},
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        
        violation_found = any("exceeds 100%" in v for v in violations)
        assert violation_found

    def test_diversification_violation(self):
        """Test portfolio over $10k with < 5 positions triggers violation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.25},
                "MSFT": {"weight": 0.25},
                "GOOGL": {"weight": 0.25},
                "AMZN": {"weight": 0.25},  # Only 4 positions
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        
        violation_found = any("lacks diversification" in v for v in violations)
        assert violation_found

    def test_small_portfolio_no_diversification_requirement(self):
        """Test portfolio under $10k has no diversification requirement."""
        portfolio_data = {
            "total_value": 5000,
            "positions": {
                "AAPL": {"weight": 0.25},
                "MSFT": {"weight": 0.25},
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        
        # Should not have diversification violation
        violation_found = any("lacks diversification" in v for v in violations)
        assert not violation_found

    def test_empty_portfolio(self):
        """Test empty portfolio passes."""
        portfolio_data = {"total_value": 0, "positions": {}}
        violations = validate_portfolio_constraints(portfolio_data)
        assert violations == []

    def test_short_positions_use_absolute_weight(self):
        """Test short positions use absolute value for weight calculation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": -0.35},  # Short position, abs() = 0.35 > 0.30
                "MSFT": {"weight": 0.15},
                "GOOGL": {"weight": 0.15},
                "AMZN": {"weight": 0.15},
                "NVDA": {"weight": 0.15},
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        
        violation_found = any("Excessive concentration" in v for v in violations)
        assert violation_found


# ============================================================================
# VALIDATE RISK LIMITS TESTS
# ============================================================================

class TestValidateRiskLimits:
    """Tests for validate_risk_limits function."""

    def test_valid_risk_limits(self):
        """Test valid risk limits pass."""
        risk_limits = {
            "max_position_size": 0.10,
            "min_position_size": 0.01,
            "max_var": 0.05,
            "max_drawdown": 0.20,
        }
        result = validate_risk_limits(risk_limits)
        assert result == risk_limits

    def test_default_values_used(self):
        """Test default values are applied."""
        result = validate_risk_limits({})
        # Should not raise, uses defaults
        assert result == {}

    def test_conflicting_position_sizes_raises_error(self):
        """Test min > max position size raises ValueError."""
        with pytest.raises(ValueError, match="Conflicting risk limits"):
            validate_risk_limits({
                "max_position_size": 0.05,
                "min_position_size": 0.10,
            })

    def test_invalid_max_var_zero(self):
        """Test zero max_var raises ValueError."""
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": 0})

    def test_invalid_max_var_negative(self):
        """Test negative max_var raises ValueError."""
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": -0.05})

    def test_invalid_max_var_over_one(self):
        """Test max_var over 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": 1.5})

    def test_invalid_max_drawdown_zero(self):
        """Test zero max_drawdown raises ValueError."""
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": 0})

    def test_invalid_max_drawdown_negative(self):
        """Test negative max_drawdown raises ValueError."""
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": -0.10})

    def test_invalid_max_drawdown_over_one(self):
        """Test max_drawdown over 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": 1.5})


# ============================================================================
# VALIDATE MARKET DATA TESTS
# ============================================================================

class TestValidateMarketData:
    """Tests for validate_market_data function."""

    def test_valid_market_data(self):
        """Test valid market data passes."""
        from datetime import datetime
        
        market_data = {
            "symbol": "aapl",
            "price": 150.50,
            "timestamp": datetime.now().isoformat(),
        }
        result = validate_market_data(market_data)
        
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.50

    def test_valid_market_data_with_volume(self):
        """Test market data with volume passes."""
        from datetime import datetime
        
        market_data = {
            "symbol": "MSFT",
            "price": 350.00,
            "timestamp": datetime.now().isoformat(),
            "volume": 1000000,
        }
        result = validate_market_data(market_data)
        
        assert result["volume"] == 1000000

    def test_missing_symbol_raises_error(self):
        """Test missing symbol raises ValueError."""
        from datetime import datetime
        
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_market_data({
                "price": 150.50,
                "timestamp": datetime.now().isoformat()
            })

    def test_missing_price_raises_error(self):
        """Test missing price raises ValueError."""
        from datetime import datetime
        
        with pytest.raises(ValueError, match="Price is required"):
            validate_market_data({
                "symbol": "AAPL",
                "timestamp": datetime.now().isoformat()
            })

    def test_missing_timestamp_raises_error(self):
        """Test missing timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Timestamp is required"):
            validate_market_data({
                "symbol": "AAPL",
                "price": 150.50
            })

    def test_negative_volume_raises_error(self):
        """Test negative volume raises ValueError."""
        from datetime import datetime
        
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_market_data({
                "symbol": "AAPL",
                "price": 150.50,
                "timestamp": datetime.now().isoformat(),
                "volume": -1000
            })

    def test_volume_too_large_raises_error(self):
        """Test volume over 1 trillion raises ValueError."""
        from datetime import datetime
        
        with pytest.raises(ValueError, match="Volume too large"):
            validate_market_data({
                "symbol": "AAPL",
                "price": 150.50,
                "timestamp": datetime.now().isoformat(),
                "volume": 2e12
            })

    def test_zero_volume_valid(self):
        """Test zero volume is valid (halted stock)."""
        from datetime import datetime
        
        market_data = {
            "symbol": "AAPL",
            "price": 150.50,
            "timestamp": datetime.now().isoformat(),
            "volume": 0
        }
        result = validate_market_data(market_data)
        assert result["volume"] == 0
