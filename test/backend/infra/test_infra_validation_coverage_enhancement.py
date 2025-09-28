"""
Comprehensive test suite for backend.infra.validation module.
Targets 100% coverage from 0% baseline by testing all validation functions, error conditions, and edge cases.
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
    validate_market_data
)


class TestValidateSymbol:
    """Test symbol validation with comprehensive edge cases."""

    def test_validate_symbol_valid_cases(self):
        """Test valid symbol formats."""
        # Standard symbols
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_symbol("aapl") == "AAPL"  # Case normalization
        assert validate_symbol("GOOGL") == "GOOGL"
        assert validate_symbol("MSFT") == "MSFT"
        
        # Complex symbols with allowed characters
        assert validate_symbol("A.B") == "A.B"  # Dot allowed
        assert validate_symbol("A-B") == "A-B"  # Hyphen allowed
        assert validate_symbol("A123") == "A123"  # Numbers allowed
        assert validate_symbol("ABC123.DE") == "ABC123.DE"
        
    def test_validate_symbol_empty_string(self):
        """Test empty symbol rejection."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol("")
            
    def test_validate_symbol_none_value(self):
        """Test None symbol rejection."""
        with pytest.raises((ValueError, TypeError)):
            validate_symbol(None)
            
    def test_validate_symbol_too_long(self):
        """Test symbol length validation."""
        long_symbol = "A" * 11  # 11 characters
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_symbol(long_symbol)
            
    def test_validate_symbol_starts_with_number(self):
        """Test symbol starting with number rejection."""
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_symbol("1ABC")
            
    def test_validate_symbol_invalid_characters(self):
        """Test invalid character rejection."""
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("A@BC")
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("A BC")  # Space not allowed
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            validate_symbol("A#BC")


class TestValidatePrice:
    """Test price validation with comprehensive edge cases."""

    def test_validate_price_valid_cases(self):
        """Test valid price values."""
        assert validate_price(10.0) == 10.0
        assert validate_price(100.50) == 100.50
        assert validate_price(0.0001) == 0.0001  # Minimum precision
        assert validate_price(999999.9999) == 999999.9999
        
    def test_validate_price_zero_and_negative(self):
        """Test zero and negative price rejection."""
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(0.0)
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-10.0)
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-0.01)
            
    def test_validate_price_too_large(self):
        """Test price upper limit."""
        with pytest.raises(ValueError, match="Price too large"):
            validate_price(1e8 + 1)  # Over $100 million
            
    def test_validate_price_too_many_decimals(self):
        """Test decimal precision limits."""
        with pytest.raises(ValueError, match="Too many decimal places"):
            validate_price(10.12345)  # 5 decimal places, max is 4
            
    def test_validate_price_decimal_rounding(self):
        """Test decimal rounding behavior."""
        # Should round to 4 decimal places
        result = validate_price(10.1235)
        assert result == 10.1235
        
    def test_validate_price_edge_values(self):
        """Test edge case price values."""
        # Just under the limit
        assert validate_price(99999999.9999) == 99999999.9999
        # Very small positive value
        assert validate_price(0.0001) == 0.0001


class TestValidateQuantity:
    """Test quantity validation with fractional share controls."""

    def test_validate_quantity_valid_cases(self):
        """Test valid quantity values."""
        assert validate_quantity(100) == 100.0
        assert validate_quantity(10.5) == 10.5
        assert validate_quantity(-50) == -50.0  # Short positions
        assert validate_quantity(0.1, allow_fractional=True) == 0.1
        
    def test_validate_quantity_zero_rejection(self):
        """Test zero quantity rejection."""
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0)
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0.0)
            
    def test_validate_quantity_too_large(self):
        """Test quantity upper limits."""
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(1e8 + 1)  # Over 100 million shares
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(-1e8 - 1)  # Negative also checked
            
    def test_validate_quantity_fractional_control(self):
        """Test fractional share controls."""
        # Fractional allowed
        assert validate_quantity(10.5, allow_fractional=True) == 10.5
        
        # Fractional not allowed
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            validate_quantity(10.5, allow_fractional=False)
            
        # Integer values should work with fractional disabled
        assert validate_quantity(10, allow_fractional=False) == 10.0
        assert validate_quantity(10.0, allow_fractional=False) == 10.0
        
    def test_validate_quantity_edge_values(self):
        """Test edge case quantity values."""
        # Just under the limit
        assert validate_quantity(99999999.0) == 99999999.0
        # Very small values
        assert validate_quantity(0.001, allow_fractional=True) == 0.001


class TestValidateOrder:
    """Test order data validation with comprehensive field validation."""

    def test_validate_order_valid_complete_order(self):
        """Test valid complete order data."""
        order_data = {
            "symbol": "aapl",
            "quantity": 100,
            "price": 150.50,
            "order_type": "LIMIT"
        }
        result = validate_order(order_data)
        
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["price"] == 150.50
        assert result["order_type"] == "limit"
        
    def test_validate_order_minimal_required_fields(self):
        """Test order with only required fields."""
        order_data = {
            "symbol": "MSFT",
            "quantity": 50
        }
        result = validate_order(order_data)
        
        assert result["symbol"] == "MSFT"
        assert result["quantity"] == 50.0
        assert result["order_type"] == "market"  # Default
        
    def test_validate_order_missing_required_fields(self):
        """Test missing required field validation."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_order({"quantity": 100})
            
        # Missing quantity
        with pytest.raises(ValueError, match="Quantity is required"):
            validate_order({"symbol": "AAPL"})
            
        # Missing both
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_order({})
            
    def test_validate_order_invalid_order_type(self):
        """Test invalid order type validation."""
        order_data = {
            "symbol": "AAPL",
            "quantity": 100,
            "order_type": "invalid_type"
        }
        with pytest.raises(ValueError, match="Invalid order type: invalid_type"):
            validate_order(order_data)
            
    def test_validate_order_valid_order_types(self):
        """Test all valid order types."""
        order_data_base = {"symbol": "AAPL", "quantity": 100}
        
        valid_types = ["market", "limit", "stop", "stop_limit"]
        for order_type in valid_types:
            order_data = {**order_data_base, "order_type": order_type}
            result = validate_order(order_data)
            assert result["order_type"] == order_type.lower()
            
    def test_validate_order_case_insensitive_order_type(self):
        """Test case insensitive order type handling."""
        order_data = {
            "symbol": "AAPL",
            "quantity": 100,
            "order_type": "MARKET"
        }
        result = validate_order(order_data)
        assert result["order_type"] == "market"
        
    def test_validate_order_symbol_validation_integration(self):
        """Test that order validation calls symbol validation."""
        order_data = {
            "symbol": "1INVALID",
            "quantity": 100
        }
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_order(order_data)
            
    def test_validate_order_quantity_validation_integration(self):
        """Test that order validation calls quantity validation."""
        order_data = {
            "symbol": "AAPL",
            "quantity": 0  # Invalid quantity
        }
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_order(order_data)
            
    def test_validate_order_price_validation_integration(self):
        """Test that order validation calls price validation when price provided."""
        order_data = {
            "symbol": "AAPL",
            "quantity": 100,
            "price": -10.0  # Invalid price
        }
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_order(order_data)


class TestValidatePortfolioConstraints:
    """Test portfolio constraint validation with concentration and diversification rules."""

    def test_validate_portfolio_constraints_no_violations(self):
        """Test portfolio with no constraint violations."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.20},  # 20%
                "GOOGL": {"weight": 0.15}, # 15%
                "MSFT": {"weight": 0.15},  # 15%
                "TSLA": {"weight": 0.10},  # 10%
                "AMZN": {"weight": 0.10},  # 10%
                "META": {"weight": 0.30}   # 30% - just at limit
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert violations == []
        
    def test_validate_portfolio_constraints_concentration_violation(self):
        """Test excessive concentration violation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.40},  # 40% - exceeds 30% limit
                "GOOGL": {"weight": 0.20},
                "MSFT": {"weight": 0.20},
                "TSLA": {"weight": 0.15},
                "AMZN": {"weight": 0.05}
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Excessive concentration" in violations[0]
        assert "40.0%" in violations[0]
        
    def test_validate_portfolio_constraints_exposure_violation(self):
        """Test total exposure violation."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.30},
                "GOOGL": {"weight": 0.25},
                "MSFT": {"weight": 0.25},
                "TSLA": {"weight": 0.25},  # Total = 105%
                "AMZN": {"weight": 0.05}
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Total portfolio exposure exceeds 100%" in violations[0]
        
    def test_validate_portfolio_constraints_diversification_violation(self):
        """Test diversification violation."""
        portfolio_data = {
            "total_value": 20000,  # > $10k but < 5 positions
            "positions": {
                "AAPL": {"weight": 0.30},
                "GOOGL": {"weight": 0.30},
                "MSFT": {"weight": 0.25},
                "TSLA": {"weight": 0.15}  # Only 4 positions
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Portfolio lacks diversification" in violations[0]
        
    def test_validate_portfolio_constraints_multiple_violations(self):
        """Test multiple simultaneous violations."""
        portfolio_data = {
            "total_value": 20000,
            "positions": {
                "AAPL": {"weight": 0.50},  # Concentration violation
                "GOOGL": {"weight": 0.35}, # Exposure violation (85% + 50% = 135%)
                "MSFT": {"weight": 0.35}   # Diversification violation (3 positions)
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 3  # All three violations
        
    def test_validate_portfolio_constraints_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty positions
        portfolio_data = {"total_value": 20000, "positions": {}}
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Portfolio lacks diversification" in violations[0]
        
        # Small portfolio (diversification rule doesn't apply)
        portfolio_data = {
            "total_value": 5000,  # < $10k
            "positions": {
                "AAPL": {"weight": 0.60},  # Still concentration violation
                "GOOGL": {"weight": 0.40}
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Excessive concentration" in violations[0]
        
    def test_validate_portfolio_constraints_negative_weights(self):
        """Test handling of short positions (negative weights)."""
        portfolio_data = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.20},
                "GOOGL": {"weight": -0.35}, # Short position concentration
                "MSFT": {"weight": 0.15},
                "TSLA": {"weight": 0.10},
                "AMZN": {"weight": 0.10}
            }
        }
        violations = validate_portfolio_constraints(portfolio_data)
        assert len(violations) == 1
        assert "Excessive concentration" in violations[0]
        assert "35.0%" in violations[0]


class TestValidateRiskLimits:
    """Test risk limit validation with comprehensive parameter checking."""

    def test_validate_risk_limits_valid_configuration(self):
        """Test valid risk limit configuration."""
        risk_limits = {
            "max_position_size": 0.20,
            "min_position_size": 0.01,
            "max_var": 0.05,
            "max_drawdown": 0.15
        }
        result = validate_risk_limits(risk_limits)
        assert result == risk_limits
        
    def test_validate_risk_limits_conflicting_position_sizes(self):
        """Test conflicting min/max position size validation."""
        risk_limits = {
            "max_position_size": 0.10,
            "min_position_size": 0.20  # min > max
        }
        with pytest.raises(ValueError, match="Conflicting risk limits"):
            validate_risk_limits(risk_limits)
            
    def test_validate_risk_limits_invalid_var(self):
        """Test invalid VaR limit validation."""
        # VaR too low
        risk_limits = {"max_var": 0.0}
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
        # VaR too high
        risk_limits = {"max_var": 1.5}
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
        # Negative VaR
        risk_limits = {"max_var": -0.05}
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
    def test_validate_risk_limits_invalid_drawdown(self):
        """Test invalid drawdown limit validation."""
        # Drawdown too low
        risk_limits = {"max_drawdown": 0.0}
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
        # Drawdown too high  
        risk_limits = {"max_drawdown": 1.5}
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
        # Negative drawdown
        risk_limits = {"max_drawdown": -0.10}
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            validate_risk_limits(risk_limits)
            
    def test_validate_risk_limits_edge_boundary_values(self):
        """Test edge case boundary values."""
        # Boundary values that should be valid
        risk_limits = {
            "max_position_size": 1.0,
            "min_position_size": 0.0,
            "max_var": 1.0,
            "max_drawdown": 1.0
        }
        result = validate_risk_limits(risk_limits)
        assert result == risk_limits
        
    def test_validate_risk_limits_partial_configuration(self):
        """Test partial risk limit configurations."""
        # Only some fields provided (others use defaults)
        risk_limits = {"max_var": 0.03}
        result = validate_risk_limits(risk_limits)
        assert result["max_var"] == 0.03


class TestValidateMarketData:
    """Test market data validation with comprehensive field validation."""

    def test_validate_market_data_complete_valid(self):
        """Test complete valid market data."""
        market_data = {
            "symbol": "aapl",
            "price": 150.25,
            "timestamp": "2024-01-01T10:00:00Z",
            "volume": 1000000
        }
        result = validate_market_data(market_data)
        
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.25
        assert result["timestamp"] == "2024-01-01T10:00:00Z"
        assert result["volume"] == 1000000
        
    def test_validate_market_data_minimal_required(self):
        """Test market data with only required fields."""
        market_data = {
            "symbol": "GOOGL",
            "price": 2500.50,
            "timestamp": "2024-01-01T10:00:00Z"
        }
        result = validate_market_data(market_data)
        
        assert result["symbol"] == "GOOGL"
        assert result["price"] == 2500.50
        assert result["timestamp"] == "2024-01-01T10:00:00Z"
        
    def test_validate_market_data_missing_fields(self):
        """Test missing required field validation."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            validate_market_data({"price": 100.0, "timestamp": "2024-01-01T10:00:00Z"})
            
        # Missing price
        with pytest.raises(ValueError, match="Price is required"):
            validate_market_data({"symbol": "AAPL", "timestamp": "2024-01-01T10:00:00Z"})
            
        # Missing timestamp
        with pytest.raises(ValueError, match="Timestamp is required"):
            validate_market_data({"symbol": "AAPL", "price": 100.0})
            
    def test_validate_market_data_invalid_fields(self):
        """Test invalid field value validation."""
        base_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2024-01-01T10:00:00Z"
        }
        
        # Invalid symbol
        invalid_data = {**base_data, "symbol": "1INVALID"}
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            validate_market_data(invalid_data)
            
        # Invalid price
        invalid_data = {**base_data, "price": -150.0}
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_market_data(invalid_data)
            
    def test_validate_market_data_volume_validation(self):
        """Test volume field validation."""
        base_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2024-01-01T10:00:00Z"
        }
        
        # Valid volume
        valid_data = {**base_data, "volume": 1500000}
        result = validate_market_data(valid_data)
        assert result["volume"] == 1500000
        
        # Negative volume
        invalid_data = {**base_data, "volume": -1000}
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_market_data(invalid_data)
            
        # Volume too large
        invalid_data = {**base_data, "volume": 1e12 + 1}
        with pytest.raises(ValueError, match="Volume too large"):
            validate_market_data(invalid_data)
            
    def test_validate_market_data_edge_cases(self):
        """Test edge case market data values."""
        base_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2024-01-01T10:00:00Z"
        }
        
        # Zero volume (should be valid)
        zero_volume_data = {**base_data, "volume": 0}
        result = validate_market_data(zero_volume_data)
        assert result["volume"] == 0
        
        # Maximum volume (just under limit)
        max_volume_data = {**base_data, "volume": 999999999999}  # Just under 1e12
        result = validate_market_data(max_volume_data)
        assert result["volume"] == 999999999999


if __name__ == "__main__":
    pytest.main([__file__])