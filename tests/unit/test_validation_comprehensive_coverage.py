"""
Comprehensive test suite for backend.infra.validation module.

This module has 247 lines with comprehensive validation functions for trading data.
Focus on achieving high coverage across all validation functions:

- validate_symbol: Trading symbol validation
- validate_price: Price validation with decimal constraints
- validate_quantity: Quantity validation with fractional share support
- validate_order: Complete order data validation
- validate_portfolio_constraints: Portfolio constraint checking
- validate_risk_limits: Risk limit configuration validation
- validate_market_data: Market data structure validation
"""

import pytest
from decimal import Decimal

# Test environment setup
import os
os.environ['DISABLE_ML'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

# Import the module under test
from backend.infra.validation import (
    validate_symbol,
    validate_price,
    validate_quantity,
    validate_order,
    validate_portfolio_constraints,
    validate_risk_limits,
    validate_market_data,
)


class TestValidateSymbol:
    """Test validate_symbol function."""

    def test_valid_symbols(self):
        """Test valid symbol formats."""
        # Basic symbols
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_symbol("aapl") == "AAPL"  # Case normalization
        assert validate_symbol("MSFT") == "MSFT"
        
        # Symbols with numbers
        assert validate_symbol("TSLA1") == "TSLA1"
        assert validate_symbol("BRK.A") == "BRK.A"
        
        # Symbols with hyphens
        assert validate_symbol("SOME-FUND") == "SOME-FUND"
        
        # Mixed case
        assert validate_symbol("gOoGl") == "GOOGL"

    def test_empty_symbol(self):
        """Test empty symbol validation."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol("")
        
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol(None)

    def test_too_long_symbol(self):
        """Test symbol length validation."""
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_symbol("VERYLONGSYMBOL")  # 14 characters
        
        # 10 characters should be OK
        assert validate_symbol("EXACTLYTEN") == "EXACTLYTEN"

    def test_symbol_starting_with_number(self):
        """Test symbol cannot start with number."""
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_symbol("1AAPL")
        
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_symbol("9MSFT")

    def test_invalid_characters(self):
        """Test invalid characters in symbol."""
        # Special characters not allowed
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("AAPL@")
        
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("MSFT$")
        
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("GOOGL!")
        
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("TSLA#")

    def test_single_character_symbol(self):
        """Test single character symbols."""
        assert validate_symbol("A") == "A"
        assert validate_symbol("z") == "Z"

    def test_symbols_with_dots_and_hyphens(self):
        """Test symbols with allowed special characters."""
        assert validate_symbol("BRK.A") == "BRK.A"
        assert validate_symbol("BRK.B") == "BRK.B"
        assert validate_symbol("SOME-ETF") == "SOME-ETF"
        assert validate_symbol("A-B.C") == "A-B.C"


class TestValidatePrice:
    """Test validate_price function."""

    def test_valid_prices(self):
        """Test valid price values."""
        assert validate_price(100.0) == 100.0
        assert validate_price(1.50) == 1.5
        assert validate_price(0.01) == 0.01
        assert validate_price(99999.9999) == 99999.9999

    def test_zero_price(self):
        """Test zero price validation."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(0.0)

    def test_negative_price(self):
        """Test negative price validation."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-10.0)
        
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-0.01)

    def test_too_large_price(self):
        """Test price upper limit validation."""
        with pytest.raises(ValueError, match="Price too large"):
            validate_price(1e9)  # $1 billion per share
        
        # Just under limit should work
        assert validate_price(9e7) == 9e7

    def test_decimal_places_limit(self):
        """Test decimal places validation."""
        # 4 decimal places should work
        assert validate_price(123.4567) == 123.4567
        
        # More than 4 decimal places should raise error
        with pytest.raises(ValueError, match="Too many decimal places"):
            validate_price(123.45678)

    def test_price_rounding(self):
        """Test price rounding to 4 decimal places."""
        # The validate_price function uses quantize to round properly
        # Only exact 4 decimal places are returned
        result = validate_price(123.4567)
        assert result == 123.4567
        
        # Verify the function returns a properly quantized decimal
        result = validate_price(100.0)
        assert result == 100.0

    def test_integer_prices(self):
        """Test integer price inputs."""
        assert validate_price(100) == 100.0
        assert validate_price(1) == 1.0

    def test_very_small_prices(self):
        """Test very small valid prices."""
        assert validate_price(0.0001) == 0.0001
        assert validate_price(0.001) == 0.001


class TestValidateQuantity:
    """Test validate_quantity function."""

    def test_valid_quantities(self):
        """Test valid quantity values."""
        assert validate_quantity(100) == 100.0
        assert validate_quantity(1.5) == 1.5
        assert validate_quantity(-50) == -50.0  # Short positions
        assert validate_quantity(0.1) == 0.1

    def test_zero_quantity(self):
        """Test zero quantity validation."""
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0)
        
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0.0)

    def test_too_large_quantity(self):
        """Test quantity upper limit validation."""
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(1e9)  # 1 billion shares
        
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(-1e9)  # Negative also too large

    def test_fractional_shares_allowed(self):
        """Test fractional shares when allowed."""
        # Default allows fractional
        assert validate_quantity(1.5) == 1.5
        assert validate_quantity(0.1) == 0.1
        
        # Explicitly allow fractional
        assert validate_quantity(1.5, allow_fractional=True) == 1.5

    def test_fractional_shares_not_allowed(self):
        """Test fractional shares when not allowed."""
        # Integer quantities should work
        assert validate_quantity(100, allow_fractional=False) == 100.0
        assert validate_quantity(1, allow_fractional=False) == 1.0
        
        # Fractional should raise error
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            validate_quantity(1.5, allow_fractional=False)
        
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            validate_quantity(0.1, allow_fractional=False)

    def test_negative_quantities(self):
        """Test negative quantities (short positions)."""
        assert validate_quantity(-100) == -100.0
        assert validate_quantity(-1.5) == -1.5

    def test_float_integers(self):
        """Test float values that are actually integers."""
        # These should work even when fractional not allowed
        assert validate_quantity(100.0, allow_fractional=False) == 100.0
        assert validate_quantity(1.0, allow_fractional=False) == 1.0


class TestValidateOrder:
    """Test validate_order function."""

    def test_valid_basic_order(self):
        """Test valid basic order validation."""
        order = {
            "symbol": "AAPL",
            "quantity": 100
        }
        
        result = validate_order(order)
        
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["order_type"] == "market"  # Default

    def test_valid_limit_order(self):
        """Test valid limit order validation."""
        order = {
            "symbol": "msft",
            "quantity": 50,
            "price": 300.50,
            "order_type": "limit"
        }
        
        result = validate_order(order)
        
        assert result["symbol"] == "MSFT"
        assert result["quantity"] == 50.0
        assert result["price"] == 300.50
        assert result["order_type"] == "limit"

    def test_missing_required_fields(self):
        """Test missing required field validation."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_order({"quantity": 100})
        
        # Missing quantity
        with pytest.raises(ValueError, match="Quantity is required"):
            validate_order({"symbol": "AAPL"})

    def test_invalid_symbol_in_order(self):
        """Test invalid symbol in order."""
        order = {
            "symbol": "1INVALID",
            "quantity": 100
        }
        
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_order(order)

    def test_invalid_quantity_in_order(self):
        """Test invalid quantity in order."""
        order = {
            "symbol": "AAPL",
            "quantity": 0
        }
        
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_order(order)

    def test_invalid_price_in_order(self):
        """Test invalid price in order."""
        order = {
            "symbol": "AAPL",
            "quantity": 100,
            "price": -10.0
        }
        
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_order(order)

    def test_invalid_order_type(self):
        """Test invalid order type validation."""
        order = {
            "symbol": "AAPL",
            "quantity": 100,
            "order_type": "invalid_type"
        }
        
        with pytest.raises(ValueError, match="Invalid order type: invalid_type"):
            validate_order(order)

    def test_valid_order_types(self):
        """Test all valid order types."""
        order_types = ["market", "limit", "stop", "stop_limit"]
        
        for order_type in order_types:
            order = {
                "symbol": "AAPL",
                "quantity": 100,
                "order_type": order_type
            }
            
            result = validate_order(order)
            assert result["order_type"] == order_type

    def test_order_type_case_normalization(self):
        """Test order type case normalization."""
        order = {
            "symbol": "AAPL",
            "quantity": 100,
            "order_type": "LIMIT"
        }
        
        result = validate_order(order)
        assert result["order_type"] == "limit"

    def test_order_data_modification(self):
        """Test that order data is properly modified."""
        original_order = {
            "symbol": "aapl",
            "quantity": 100,
            "price": 150.1234,  # Exactly 4 decimal places
            "order_type": "LIMIT"
        }
        
        result = validate_order(original_order)
        
        # Verify transformations
        assert result["symbol"] == "AAPL"  # Uppercase
        assert result["quantity"] == 100.0  # Float conversion
        assert result["price"] == 150.1234  # Exactly as provided
        assert result["order_type"] == "limit"  # Lowercase


class TestValidatePortfolioConstraints:
    """Test validate_portfolio_constraints function."""

    def test_empty_portfolio(self):
        """Test empty portfolio validation."""
        portfolio = {"positions": {}}
        violations = validate_portfolio_constraints(portfolio)
        assert violations == []

    def test_valid_diversified_portfolio(self):
        """Test valid diversified portfolio."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.20},
                "MSFT": {"weight": 0.20},
                "GOOGL": {"weight": 0.20},
                "TSLA": {"weight": 0.20},
                "NVDA": {"weight": 0.20}
            },
            "total_value": 50000
        }
        
        violations = validate_portfolio_constraints(portfolio)
        assert violations == []

    def test_excessive_concentration(self):
        """Test excessive concentration violation."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.50},  # 50% concentration
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.20}
            }
        }
        
        violations = validate_portfolio_constraints(portfolio)
        assert len(violations) == 1
        assert "Excessive concentration" in violations[0]
        assert "50.0%" in violations[0]

    def test_total_exposure_violation(self):
        """Test total exposure violation."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.30},
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.25},
                "TSLA": {"weight": 0.20}  # Total 105%
            }
        }
        
        violations = validate_portfolio_constraints(portfolio)
        # Should have total exposure violation but not concentration
        assert any("Total portfolio exposure exceeds 100%" in v for v in violations)
        assert not any("Excessive concentration" in v for v in violations)

    def test_diversification_violation(self):
        """Test diversification violation."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.50},
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.20}
            },
            "total_value": 50000  # > $10k but only 3 positions
        }
        
        violations = validate_portfolio_constraints(portfolio)
        assert any("lacks diversification" in v for v in violations)

    def test_small_portfolio_no_diversification_requirement(self):
        """Test small portfolio doesn't require diversification."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.50},
                "MSFT": {"weight": 0.50}
            },
            "total_value": 5000  # < $10k
        }
        
        violations = validate_portfolio_constraints(portfolio)
        # Should not have diversification violation
        assert not any("lacks diversification" in v for v in violations)

    def test_multiple_violations(self):
        """Test multiple constraint violations."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.60},  # Excessive concentration
                "MSFT": {"weight": 0.50}   # Total exposure > 100%
            },
            "total_value": 50000  # Lacks diversification
        }
        
        violations = validate_portfolio_constraints(portfolio)
        assert len(violations) >= 2  # Should have multiple violations

    def test_negative_weights(self):
        """Test negative weights (short positions)."""
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.30},
                "MSFT": {"weight": -0.20},  # Short position
                "GOOGL": {"weight": 0.20}
            }
        }
        
        violations = validate_portfolio_constraints(portfolio)
        # Should handle absolute values correctly
        assert violations == []

    def test_missing_position_weight(self):
        """Test positions missing weight data."""
        portfolio = {
            "positions": {
                "AAPL": {},  # Missing weight
                "MSFT": {"weight": 0.30}
            }
        }
        
        violations = validate_portfolio_constraints(portfolio)
        # Should handle missing weights (default to 0)
        assert violations == []


class TestValidateRiskLimits:
    """Test validate_risk_limits function."""

    def test_valid_risk_limits(self):
        """Test valid risk limits configuration."""
        limits = {
            "max_position_size": 0.20,
            "min_position_size": 0.01,
            "max_var": 0.05,
            "max_drawdown": 0.15
        }
        
        result = validate_risk_limits(limits)
        assert result == limits

    def test_conflicting_position_limits(self):
        """Test conflicting position size limits."""
        limits = {
            "max_position_size": 0.10,
            "min_position_size": 0.20  # Min > Max
        }
        
        with pytest.raises(ValueError, match="Conflicting risk limits"):
            validate_risk_limits(limits)

    def test_invalid_var_limits(self):
        """Test invalid VaR limits."""
        # VaR too low
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": 0.0})
        
        # VaR too high
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": 1.5})
        
        # Negative VaR
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits({"max_var": -0.1})

    def test_invalid_drawdown_limits(self):
        """Test invalid drawdown limits."""
        # Drawdown too low
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": 0.0})
        
        # Drawdown too high
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": 1.5})
        
        # Negative drawdown
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits({"max_drawdown": -0.1})

    def test_partial_risk_limits(self):
        """Test partial risk limits configuration."""
        # Should work with defaults
        limits = {"max_var": 0.03}
        result = validate_risk_limits(limits)
        assert result["max_var"] == 0.03

    def test_edge_case_var_values(self):
        """Test edge case VaR values."""
        # Just above 0 should work
        limits = {"max_var": 0.001}
        result = validate_risk_limits(limits)
        assert result["max_var"] == 0.001
        
        # Exactly 1.0 should work
        limits = {"max_var": 1.0}
        result = validate_risk_limits(limits)
        assert result["max_var"] == 1.0

    def test_edge_case_drawdown_values(self):
        """Test edge case drawdown values."""
        # Just above 0 should work
        limits = {"max_drawdown": 0.001}
        result = validate_risk_limits(limits)
        assert result["max_drawdown"] == 0.001
        
        # Exactly 1.0 should work
        limits = {"max_drawdown": 1.0}
        result = validate_risk_limits(limits)
        assert result["max_drawdown"] == 1.0


class TestValidateMarketData:
    """Test validate_market_data function."""

    def test_valid_market_data(self):
        """Test valid market data validation."""
        data = {
            "symbol": "AAPL",
            "price": 150.50,
            "timestamp": "2023-01-01T10:00:00Z"
        }
        
        result = validate_market_data(data)
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.50
        assert result["timestamp"] == "2023-01-01T10:00:00Z"

    def test_missing_required_fields(self):
        """Test missing required field validation."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_market_data({"price": 150.0, "timestamp": "2023-01-01T10:00:00Z"})
        
        # Missing price
        with pytest.raises(ValueError, match="Price is required"):
            validate_market_data({"symbol": "AAPL", "timestamp": "2023-01-01T10:00:00Z"})
        
        # Missing timestamp
        with pytest.raises(ValueError, match="Timestamp is required"):
            validate_market_data({"symbol": "AAPL", "price": 150.0})

    def test_invalid_symbol_in_market_data(self):
        """Test invalid symbol in market data."""
        data = {
            "symbol": "1INVALID",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z"
        }
        
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_market_data(data)

    def test_invalid_price_in_market_data(self):
        """Test invalid price in market data."""
        data = {
            "symbol": "AAPL",
            "price": -150.0,
            "timestamp": "2023-01-01T10:00:00Z"
        }
        
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_market_data(data)

    def test_valid_volume_in_market_data(self):
        """Test valid volume in market data."""
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 1000000
        }
        
        result = validate_market_data(data)
        assert result["volume"] == 1000000

    def test_negative_volume(self):
        """Test negative volume validation."""
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": -1000
        }
        
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_market_data(data)

    def test_too_large_volume(self):
        """Test volume upper limit validation."""
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 1e13  # 10 trillion shares
        }
        
        with pytest.raises(ValueError, match="Volume too large"):
            validate_market_data(data)

    def test_zero_volume(self):
        """Test zero volume (should be allowed)."""
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 0
        }
        
        result = validate_market_data(data)
        assert result["volume"] == 0

    def test_market_data_transformations(self):
        """Test market data transformations."""
        data = {
            "symbol": "aapl",  # Should be uppercased
            "price": 150.1234,  # Exactly 4 decimal places
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 1000000
        }
        
        result = validate_market_data(data)
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.1234  # Exactly as provided

    def test_edge_case_volumes(self):
        """Test edge case volume values."""
        # Very large but valid volume
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 999999999999  # Just under limit
        }
        
        result = validate_market_data(data)
        assert result["volume"] == 999999999999


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    def test_all_functions_with_extreme_values(self):
        """Test all functions with extreme but valid values."""
        # Symbol at maximum length
        symbol = "A" * 10
        assert validate_symbol(symbol) == symbol
        
        # Price at maximum value (just under limit)
        max_price = 99999999.9999
        assert validate_price(max_price) == max_price
        
        # Quantity at maximum value (just under limit)
        max_quantity = 99999999
        assert validate_quantity(max_quantity) == max_quantity

    def test_comprehensive_order_validation(self):
        """Test comprehensive order validation with all fields."""
        order = {
            "symbol": "brk.a",
            "quantity": 0.5,
            "price": 500000.0,
            "order_type": "STOP_LIMIT"
        }
        
        result = validate_order(order)
        assert result["symbol"] == "BRK.A"
        assert result["quantity"] == 0.5
        assert result["price"] == 500000.0
        assert result["order_type"] == "stop_limit"

    def test_validation_function_independence(self):
        """Test that validation functions don't interfere with each other."""
        # Each function should work independently
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_price(100.0) == 100.0
        assert validate_quantity(50) == 50.0
        
        # Order validation should use all sub-validators
        order = {"symbol": "aapl", "quantity": 50, "price": 100.0}
        result = validate_order(order)
        assert result["symbol"] == "AAPL"
        assert result["price"] == 100.0
        assert result["quantity"] == 50.0

    def test_unicode_and_special_input_handling(self):
        """Test handling of unicode and special inputs."""
        # Unicode should be rejected in symbols
        with pytest.raises(ValueError):
            validate_symbol("ÄAPL")
        
        # Very precise decimal handling - only 4 decimal places allowed
        with pytest.raises(ValueError, match="Too many decimal places"):
            validate_price(123.45678901234)
        
        # Exactly 4 decimal places should work
        validated = validate_price(123.4567)
        assert validated == 123.4567


if __name__ == "__main__":
    pytest.main([__file__])