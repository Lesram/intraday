"""
Comprehensive test coverage for backend.infra.validation module.

This module provides 100% test coverage for all validation functions:
- validate_symbol: Trading symbol format validation
- validate_price: Price value validation with decimal precision
- validate_quantity: Quantity validation with fractional share support
- validate_order: Complete order data structure validation
- validate_portfolio_constraints: Portfolio constraint violation checking
- validate_risk_limits: Risk limit configuration validation
- validate_market_data: Market data structure validation

Tests cover all edge cases, error conditions, and valid scenarios to ensure
comprehensive validation behavior and achieve 100% code coverage.
"""

import pytest
from decimal import Decimal
import importlib.util


# Import the validation module using standalone import to ensure coverage tracking
def load_validation_module():
    """Load validation module using importlib for proper coverage."""
    spec = importlib.util.spec_from_file_location(
        "validation_module", 
        "backend/infra/validation.py"
    )
    validation_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validation_module)
    return validation_module


class TestInfraValidation:
    """Comprehensive test suite for backend.infra.validation module."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup validation module for each test."""
        self.validation = load_validation_module()

    def test_validate_symbol_valid_cases(self):
        """Test validate_symbol with valid symbol formats."""
        # Valid symbols should be normalized to uppercase
        assert self.validation.validate_symbol("AAPL") == "AAPL"
        assert self.validation.validate_symbol("aapl") == "AAPL"
        assert self.validation.validate_symbol("Msft") == "MSFT"
        assert self.validation.validate_symbol("GOOGL") == "GOOGL"
        
        # Valid symbols with numbers, dots, hyphens
        assert self.validation.validate_symbol("BRK.A") == "BRK.A"
        assert self.validation.validate_symbol("BRK-A") == "BRK-A"
        assert self.validation.validate_symbol("A123") == "A123"
        assert self.validation.validate_symbol("T") == "T"  # Single character
        assert self.validation.validate_symbol("ABCDEFGHIJ") == "ABCDEFGHIJ"  # Max 10 chars

    def test_validate_symbol_invalid_cases(self):
        """Test validate_symbol with invalid symbol formats."""
        # Empty symbol
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            self.validation.validate_symbol("")
        
        # Too long symbol (> 10 characters)
        with pytest.raises(ValueError, match="Symbol too long"):
            self.validation.validate_symbol("ABCDEFGHIJK")  # 11 characters
        
        # Symbol starting with number
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            self.validation.validate_symbol("1ABC")
        with pytest.raises(ValueError, match="Symbol cannot start with number"):
            self.validation.validate_symbol("9MSFT")
        
        # Invalid characters
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            self.validation.validate_symbol("AAP$L")
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            self.validation.validate_symbol("MSF&T")
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            self.validation.validate_symbol("GOO#L")
        with pytest.raises(ValueError, match="Invalid characters in symbol"):
            self.validation.validate_symbol("A@BC")

    def test_validate_price_valid_cases(self):
        """Test validate_price with valid price values."""
        # Basic valid prices
        assert self.validation.validate_price(100.0) == 100.0
        assert self.validation.validate_price(50.25) == 50.25
        assert self.validation.validate_price(0.01) == 0.01
        assert self.validation.validate_price(0.0001) == 0.0001
        
        # Price rounding to 4 decimal places (4 decimals are allowed)
        result = self.validation.validate_price(100.1234)
        assert result == 100.1234  # Exactly 4 decimal places
        
        # Large but valid prices
        assert self.validation.validate_price(99999999.0) == 99999999.0
        
        # Very small positive prices
        assert self.validation.validate_price(0.0001) == 0.0001

    def test_validate_price_invalid_cases(self):
        """Test validate_price with invalid price values."""
        # Negative and zero prices
        with pytest.raises(ValueError, match="Price must be positive"):
            self.validation.validate_price(0.0)
        with pytest.raises(ValueError, match="Price must be positive"):
            self.validation.validate_price(-10.0)
        with pytest.raises(ValueError, match="Price must be positive"):
            self.validation.validate_price(-0.01)
        
        # Price too large (> 100 million)
        with pytest.raises(ValueError, match="Price too large"):
            self.validation.validate_price(1e8 + 1)
        with pytest.raises(ValueError, match="Price too large"):
            self.validation.validate_price(200000000.0)
        
        # Too many decimal places (> 4)
        with pytest.raises(ValueError, match="Too many decimal places"):
            self.validation.validate_price(100.123456)
        with pytest.raises(ValueError, match="Too many decimal places"):
            self.validation.validate_price(50.00001)

    def test_validate_quantity_valid_cases(self):
        """Test validate_quantity with valid quantity values."""
        # Positive quantities
        assert self.validation.validate_quantity(100) == 100.0
        assert self.validation.validate_quantity(50.5) == 50.5
        assert self.validation.validate_quantity(0.1) == 0.1
        
        # Negative quantities (short positions)
        assert self.validation.validate_quantity(-100) == -100.0
        assert self.validation.validate_quantity(-50.5) == -50.5
        
        # Fractional shares allowed by default
        assert self.validation.validate_quantity(10.5) == 10.5
        assert self.validation.validate_quantity(0.25) == 0.25
        
        # Large but valid quantities
        assert self.validation.validate_quantity(99999999) == 99999999.0

    def test_validate_quantity_fractional_control(self):
        """Test validate_quantity with fractional share controls."""
        # Fractional shares allowed
        assert self.validation.validate_quantity(10.5, allow_fractional=True) == 10.5
        assert self.validation.validate_quantity(0.25, allow_fractional=True) == 0.25
        
        # Fractional shares not allowed - valid integer quantities
        assert self.validation.validate_quantity(100, allow_fractional=False) == 100.0
        assert self.validation.validate_quantity(50.0, allow_fractional=False) == 50.0  # Exact integer as float
        
        # Fractional shares not allowed - invalid fractional quantities
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            self.validation.validate_quantity(10.5, allow_fractional=False)
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            self.validation.validate_quantity(0.25, allow_fractional=False)

    def test_validate_quantity_invalid_cases(self):
        """Test validate_quantity with invalid quantity values."""
        # Zero quantity
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            self.validation.validate_quantity(0)
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            self.validation.validate_quantity(0.0)
        
        # Quantity too large (> 100 million)
        with pytest.raises(ValueError, match="Quantity too large"):
            self.validation.validate_quantity(1e8 + 1)
        with pytest.raises(ValueError, match="Quantity too large"):
            self.validation.validate_quantity(-1e8 - 1)
        with pytest.raises(ValueError, match="Quantity too large"):
            self.validation.validate_quantity(200000000)

    def test_validate_order_valid_cases(self):
        """Test validate_order with valid order data."""
        # Basic valid order
        order = {"symbol": "AAPL", "quantity": 100}
        result = self.validation.validate_order(order)
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["order_type"] == "market"  # Default
        
        # Order with price
        order = {"symbol": "msft", "quantity": 50, "price": 250.50}
        result = self.validation.validate_order(order)
        assert result["symbol"] == "MSFT"  # Normalized
        assert result["quantity"] == 50.0
        assert result["price"] == 250.50
        assert result["order_type"] == "market"
        
        # Order with different order types
        valid_types = ["market", "limit", "stop", "stop_limit"]
        for order_type in valid_types:
            order = {"symbol": "GOOGL", "quantity": 25, "order_type": order_type}
            result = self.validation.validate_order(order)
            assert result["order_type"] == order_type
        
        # Order type case insensitive
        order = {"symbol": "TSLA", "quantity": 10, "order_type": "LIMIT"}
        result = self.validation.validate_order(order)
        assert result["order_type"] == "limit"

    def test_validate_order_missing_fields(self):
        """Test validate_order with missing required fields."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required"):
            self.validation.validate_order({"quantity": 100})
        
        # Missing quantity
        with pytest.raises(ValueError, match="Quantity is required"):
            self.validation.validate_order({"symbol": "AAPL"})
        
        # Empty order
        with pytest.raises(ValueError, match="Symbol is required"):
            self.validation.validate_order({})

    def test_validate_order_invalid_fields(self):
        """Test validate_order with invalid field values."""
        # Invalid symbol
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            self.validation.validate_order({"symbol": "", "quantity": 100})
        
        # Invalid quantity
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            self.validation.validate_order({"symbol": "AAPL", "quantity": 0})
        
        # Invalid price
        with pytest.raises(ValueError, match="Price must be positive"):
            self.validation.validate_order({"symbol": "AAPL", "quantity": 100, "price": -50})
        
        # Invalid order type
        with pytest.raises(ValueError, match="Invalid order type: invalid"):
            self.validation.validate_order({
                "symbol": "AAPL", 
                "quantity": 100, 
                "order_type": "invalid"
            })

    def test_validate_portfolio_constraints_no_violations(self):
        """Test validate_portfolio_constraints with compliant portfolios."""
        # Well diversified portfolio
        portfolio = {
            "total_value": 100000,
            "positions": {
                "AAPL": {"weight": 0.20},
                "MSFT": {"weight": 0.20},
                "GOOGL": {"weight": 0.20},
                "TSLA": {"weight": 0.20},
                "NVDA": {"weight": 0.20}
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert violations == []
        
        # Small portfolio (< $10k) with few positions - still has concentration limits
        portfolio = {
            "total_value": 5000,
            "positions": {
                "AAPL": {"weight": 0.25},  # Under 30% concentration limit
                "MSFT": {"weight": 0.25},
                "GOOGL": {"weight": 0.25},
                "TSLA": {"weight": 0.25}
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert violations == []

    def test_validate_portfolio_constraints_concentration_violation(self):
        """Test validate_portfolio_constraints with concentration violations."""
        # Excessive concentration (> 30%)
        portfolio = {
            "total_value": 100000,
            "positions": {
                "AAPL": {"weight": 0.50},  # 50% concentration
                "MSFT": {"weight": 0.25},
                "GOOGL": {"weight": 0.25}
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 2  # Concentration + diversification violations
        violation_text = " ".join(violations)
        assert "Excessive concentration" in violation_text
        assert "50.0%" in violation_text
        assert "Portfolio lacks diversification" in violation_text

    def test_validate_portfolio_constraints_exposure_violation(self):
        """Test validate_portfolio_constraints with total exposure violations."""
        # Total exposure > 100%
        portfolio = {
            "total_value": 100000,
            "positions": {
                "AAPL": {"weight": 0.30},
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.30},
                "TSLA": {"weight": 0.30}  # Total = 120%
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 2  # Exposure + diversification violations
        violation_text = " ".join(violations)
        assert "Total portfolio exposure exceeds 100%" in violation_text
        assert "120.0%" in violation_text
        assert "Portfolio lacks diversification" in violation_text

    def test_validate_portfolio_constraints_diversification_violation(self):
        """Test validate_portfolio_constraints with diversification violations."""
        # Large portfolio (> $10k) with < 5 positions
        portfolio = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.30},
                "MSFT": {"weight": 0.30},
                "GOOGL": {"weight": 0.25},
                "TSLA": {"weight": 0.15}  # Only 4 positions
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 1
        assert "Portfolio lacks diversification" in violations[0]
        assert "minimum 5 positions" in violations[0]

    def test_validate_portfolio_constraints_multiple_violations(self):
        """Test validate_portfolio_constraints with multiple violations."""
        # Multiple violations: concentration + exposure + diversification
        portfolio = {
            "total_value": 50000,
            "positions": {
                "AAPL": {"weight": 0.60},  # Concentration violation
                "MSFT": {"weight": 0.60}   # Exposure violation, diversification violation
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 3  # All three violations
        violation_text = " ".join(violations)
        assert "Excessive concentration" in violation_text
        assert "Total portfolio exposure exceeds 100%" in violation_text
        assert "Portfolio lacks diversification" in violation_text

    def test_validate_portfolio_constraints_edge_cases(self):
        """Test validate_portfolio_constraints edge cases."""
        # Empty positions
        portfolio = {"total_value": 100000, "positions": {}}
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 1
        assert "Portfolio lacks diversification" in violations[0]
        
        # Missing positions key
        portfolio = {"total_value": 100000}
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 1
        assert "Portfolio lacks diversification" in violations[0]
        
        # Missing total_value (defaults to 0) - concentration violation only (100% total is at limit)
        portfolio = {
            "positions": {
                "AAPL": {"weight": 0.50},  # Exceeds 30% concentration limit
                "MSFT": {"weight": 0.50}
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert len(violations) == 1  # Only concentration violation
        assert "Excessive concentration" in violations[0]
        assert "50.0%" in violations[0]

    def test_validate_risk_limits_valid_cases(self):
        """Test validate_risk_limits with valid risk limits."""
        # Basic valid limits
        limits = {
            "max_position_size": 0.3,
            "min_position_size": 0.01,
            "max_var": 0.05,
            "max_drawdown": 0.15
        }
        result = self.validation.validate_risk_limits(limits)
        assert result == limits
        
        # Default values should be preserved
        limits = {}
        result = self.validation.validate_risk_limits(limits)
        assert result == limits

    def test_validate_risk_limits_conflicting_position_sizes(self):
        """Test validate_risk_limits with conflicting position size limits."""
        # min_position_size > max_position_size
        with pytest.raises(ValueError, match="Conflicting risk limits"):
            self.validation.validate_risk_limits({
                "max_position_size": 0.1,
                "min_position_size": 0.2
            })
        
        # Equal limits should be valid
        limits = {
            "max_position_size": 0.2,
            "min_position_size": 0.2
        }
        result = self.validation.validate_risk_limits(limits)
        assert result == limits

    def test_validate_risk_limits_invalid_var(self):
        """Test validate_risk_limits with invalid VaR limits."""
        # VaR <= 0
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_var": 0.0})
        
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_var": -0.1})
        
        # VaR > 1
        with pytest.raises(ValueError, match="max_var must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_var": 1.1})
        
        # VaR = 1 should be valid (boundary case)
        result = self.validation.validate_risk_limits({"max_var": 1.0})
        assert result["max_var"] == 1.0

    def test_validate_risk_limits_invalid_drawdown(self):
        """Test validate_risk_limits with invalid drawdown limits."""
        # Drawdown <= 0
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_drawdown": 0.0})
        
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_drawdown": -0.1})
        
        # Drawdown > 1
        with pytest.raises(ValueError, match="max_drawdown must be between 0 and 1"):
            self.validation.validate_risk_limits({"max_drawdown": 1.1})
        
        # Drawdown = 1 should be valid (boundary case)
        result = self.validation.validate_risk_limits({"max_drawdown": 1.0})
        assert result["max_drawdown"] == 1.0

    def test_validate_market_data_valid_cases(self):
        """Test validate_market_data with valid market data."""
        # Basic valid market data
        data = {
            "symbol": "AAPL",
            "price": 150.50,
            "timestamp": "2023-01-01T10:00:00Z"
        }
        result = self.validation.validate_market_data(data)
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.50
        assert result["timestamp"] == "2023-01-01T10:00:00Z"
        
        # Market data with volume
        data = {
            "symbol": "msft",
            "price": 250.75,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 1000000
        }
        result = self.validation.validate_market_data(data)
        assert result["symbol"] == "MSFT"  # Normalized
        assert result["volume"] == 1000000
        
        # Market data with zero volume (valid)
        data = {
            "symbol": "GOOGL",
            "price": 2500.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 0
        }
        result = self.validation.validate_market_data(data)
        assert result["volume"] == 0

    def test_validate_market_data_missing_fields(self):
        """Test validate_market_data with missing required fields."""
        # Missing symbol
        with pytest.raises(ValueError, match="Symbol is required in market data"):
            self.validation.validate_market_data({
                "price": 150.0,
                "timestamp": "2023-01-01T10:00:00Z"
            })
        
        # Missing price
        with pytest.raises(ValueError, match="Price is required in market data"):
            self.validation.validate_market_data({
                "symbol": "AAPL",
                "timestamp": "2023-01-01T10:00:00Z"
            })
        
        # Missing timestamp
        with pytest.raises(ValueError, match="Timestamp is required in market data"):
            self.validation.validate_market_data({
                "symbol": "AAPL",
                "price": 150.0
            })

    def test_validate_market_data_invalid_fields(self):
        """Test validate_market_data with invalid field values."""
        # Invalid symbol
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            self.validation.validate_market_data({
                "symbol": "",
                "price": 150.0,
                "timestamp": "2023-01-01T10:00:00Z"
            })
        
        # Invalid price
        with pytest.raises(ValueError, match="Price must be positive"):
            self.validation.validate_market_data({
                "symbol": "AAPL",
                "price": -150.0,
                "timestamp": "2023-01-01T10:00:00Z"
            })
        
        # Invalid volume (negative)
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            self.validation.validate_market_data({
                "symbol": "AAPL",
                "price": 150.0,
                "timestamp": "2023-01-01T10:00:00Z",
                "volume": -1000
            })
        
        # Invalid volume (too large)
        with pytest.raises(ValueError, match="Volume too large"):
            self.validation.validate_market_data({
                "symbol": "AAPL",
                "price": 150.0,
                "timestamp": "2023-01-01T10:00:00Z",
                "volume": 1e13  # > 1 trillion
            })

    def test_validate_market_data_edge_cases(self):
        """Test validate_market_data edge cases."""
        # Large but valid volume
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 999999999999  # Just under 1 trillion
        }
        result = self.validation.validate_market_data(data)
        assert result["volume"] == 999999999999
        
        # Volume exactly at limit
        data = {
            "symbol": "AAPL",
            "price": 150.0,
            "timestamp": "2023-01-01T10:00:00Z",
            "volume": 1e12  # Exactly 1 trillion
        }
        result = self.validation.validate_market_data(data)
        assert result["volume"] == 1e12

    def test_integration_all_functions_work_together(self):
        """Integration test: verify all functions work correctly together."""
        # Create a complex order that uses multiple validation functions
        order_data = {
            "symbol": "aapl",  # Will be normalized
            "quantity": 100.5,  # Fractional
            "price": 150.1234,  # Will be rounded
            "order_type": "LIMIT"  # Will be lowercased
        }
        
        validated_order = self.validation.validate_order(order_data)
        assert validated_order["symbol"] == "AAPL"
        assert validated_order["quantity"] == 100.5
        assert validated_order["price"] == 150.1234  # Rounded to 4 decimals
        assert validated_order["order_type"] == "limit"
        
        # Test portfolio constraints with this order
        portfolio = {
            "total_value": 50000,
            "positions": {
                validated_order["symbol"]: {"weight": 0.25},
                "MSFT": {"weight": 0.25},
                "GOOGL": {"weight": 0.25},
                "TSLA": {"weight": 0.15},
                "NVDA": {"weight": 0.10}
            }
        }
        violations = self.validation.validate_portfolio_constraints(portfolio)
        assert violations == []  # Should be compliant
        
        # Test risk limits
        risk_limits = {
            "max_position_size": 0.30,
            "min_position_size": 0.05,
            "max_var": 0.05,
            "max_drawdown": 0.20
        }
        validated_limits = self.validation.validate_risk_limits(risk_limits)
        assert validated_limits == risk_limits
        
        # Test market data
        market_data = {
            "symbol": validated_order["symbol"].lower(),  # Will be normalized
            "price": validated_order["price"],
            "timestamp": "2023-01-01T15:30:00Z",
            "volume": 2500000
        }
        validated_market_data = self.validation.validate_market_data(market_data)
        assert validated_market_data["symbol"] == "AAPL"
        assert validated_market_data["price"] == validated_order["price"]