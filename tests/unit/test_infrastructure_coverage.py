"""
High-impact test suite for infrastructure utilities and helpers.
Covers validation, logging, and utility functions.
"""

import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime, time
from unittest.mock import Mock, patch
from backend.infra.validation import (
    validate_symbol,
    validate_price,
    validate_quantity,
    validate_order,
    validate_market_data,
)
from backend.utils.helpers import (
    is_market_hours,
    generate_trade_id,
    calculate_returns,
    safe_divide,
    round_to_tick_size,
    calculate_position_value,
)


class TestInfrastructureCoverage:
    """High-coverage tests for infrastructure components."""

    @pytest.mark.unit
    def test_validate_symbol_valid_cases(self):
        """Test symbol validation with valid symbols.""" 
        # Standard symbols
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_symbol("MSFT") == "MSFT"
        assert validate_symbol("GOOGL") == "GOOGL"
        
        # ETFs
        assert validate_symbol("SPY") == "SPY"
        assert validate_symbol("QQQ") == "QQQ"
        
        # Case conversion
        assert validate_symbol("aapl") == "AAPL"

    @pytest.mark.unit  
    def test_validate_symbol_invalid_cases(self):
        """Test symbol validation with invalid symbols."""
        # Empty or None
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            validate_symbol("")
            
        # Invalid characters
        with pytest.raises(ValueError):
            validate_symbol("AAP@L")
            
        # Too long
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_symbol("VERYLONGSYMBOL")

    @pytest.mark.unit
    def test_validate_price_valid_cases(self):
        """Test price validation with valid prices."""
        assert validate_price(100.50) == 100.50
        assert validate_price(150.25) == 150.25
        assert validate_price(1) == 1.0
        assert validate_price(0.01) == 0.01

    @pytest.mark.unit
    def test_validate_price_invalid_cases(self):
        """Test price validation with invalid prices.""" 
        # Negative price
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(-10.0)
            
        # Zero price
        with pytest.raises(ValueError, match="Price must be positive"):
            validate_price(0)
            
        # Too large
        with pytest.raises(ValueError, match="Price too large"):
            validate_price(1e9)

    @pytest.mark.unit
    def test_validate_quantity_valid_cases(self):
        """Test quantity validation with valid quantities."""
        assert validate_quantity(100) == 100.0
        assert validate_quantity(1) == 1.0
        assert validate_quantity(1000) == 1000.0
        
        # Fractional shares
        assert validate_quantity(10.5) == 10.5

    @pytest.mark.unit
    def test_validate_quantity_invalid_cases(self):
        """Test quantity validation with invalid quantities."""
        # Zero quantity
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            validate_quantity(0)
            
        # Too large
        with pytest.raises(ValueError, match="Quantity too large"):
            validate_quantity(1e9)

    @pytest.mark.unit
    def test_validate_order_valid_cases(self):
        """Test order validation with valid orders."""
        valid_order = {
            'symbol': 'AAPL',
            'quantity': 100,
        }
        
        result = validate_order(valid_order)
        assert result['symbol'] == 'AAPL'
        assert result['quantity'] == 100.0

    @pytest.mark.unit
    def test_validate_order_invalid_cases(self):
        """Test order validation with invalid orders."""
        # Missing required fields
        invalid_order = {
            'symbol': 'AAPL',
            # Missing quantity
        }
        
        with pytest.raises(ValueError, match="Quantity is required"):
            validate_order(invalid_order)

    @pytest.mark.unit
    def test_validate_market_data_valid_cases(self):
        """Test market data validation."""
        valid_data = {
            'symbol': 'AAPL',
            'price': 150.00,
            'timestamp': datetime.now(),
            'volume': 1000
        }
        
        result = validate_market_data(valid_data)
        assert result['symbol'] == 'AAPL'
        assert result['price'] == 150.00

    @pytest.mark.unit
    def test_validate_market_data_invalid_cases(self):
        """Test market data validation with invalid data."""
        # Missing required fields
        invalid_data = {
            'symbol': 'AAPL',
            # Missing price, timestamp
        }
        
        with pytest.raises(ValueError):
            validate_market_data(invalid_data)

    @pytest.mark.unit
    def test_generate_trade_id(self):
        """Test trade ID generation."""
        trade_id1 = generate_trade_id()
        trade_id2 = generate_trade_id()
        
        # Should be different
        assert trade_id1 != trade_id2
        
        # Should be strings
        assert isinstance(trade_id1, str)
        assert isinstance(trade_id2, str)

    @pytest.mark.unit
    def test_safe_divide(self):
        """Test safe division function."""
        # Normal division
        assert safe_divide(10, 2) == 5.0
        
        # Division by zero with default
        assert safe_divide(10, 0) == 0.0
        
        # Division by zero with custom default
        assert safe_divide(10, 0, default=-1.0) == -1.0

    @pytest.mark.unit
    def test_round_to_tick_size(self):
        """Test tick size rounding."""
        # Default tick size (0.01)
        assert round_to_tick_size(100.123) == 100.12
        assert round_to_tick_size(100.125) == 100.12
        assert round_to_tick_size(100.129) == 100.13
        
        # Custom tick size
        assert round_to_tick_size(100.123, tick_size=0.05) == 100.10
        assert round_to_tick_size(100.126, tick_size=0.05) == 100.15

    @pytest.mark.unit
    def test_calculate_position_value(self):
        """Test position value calculation."""
        assert calculate_position_value(100, 50.0) == 5000.0
        assert calculate_position_value(50, 25.5) == 1275.0
        assert calculate_position_value(-100, 30.0) == -3000.0  # Short position

    @pytest.mark.unit
    def test_calculate_returns(self):
        """Test returns calculation."""
        prices = pd.Series([100, 110, 105, 115, 120])
        returns = calculate_returns(prices)
        
        # Should have one less return than prices
        assert len(returns) == len(prices) - 1
        
        # First return should be 10%
        assert abs(returns.iloc[0] - 0.10) < 1e-6

    @pytest.mark.unit
    @patch('backend.utils.helpers.datetime')
    def test_is_market_hours_trading_hours(self, mock_datetime):
        """Test market hours detection during trading hours."""
        # Mock datetime to return Tuesday 2:00 PM ET
        mock_now = Mock()
        mock_now.time.return_value = time(14, 0)  # 2:00 PM
        mock_now.weekday.return_value = 1  # Tuesday
        mock_datetime.now.return_value = mock_now
        
        result = is_market_hours()
        # Should be True during trading hours on weekday
        assert result is True

    @pytest.mark.unit  
    @patch('backend.utils.helpers.datetime')
    def test_is_market_hours_weekend(self, mock_datetime):
        """Test market hours detection on weekends."""
        # Mock datetime to return Saturday 2:00 PM
        mock_now = Mock()
        mock_now.time.return_value = time(14, 0)  # 2:00 PM
        mock_now.weekday.return_value = 5  # Saturday
        mock_datetime.now.return_value = mock_now
        
        result = is_market_hours()
        # Should be False on weekends
        assert result is False

    @pytest.mark.unit
    def test_validation_error_messages(self):
        """Test validation functions provide meaningful error messages."""
        try:
            validate_symbol("")
        except ValueError as e:
            assert "symbol" in str(e).lower()
            
        try:
            validate_price(-100)
        except ValueError as e:
            assert "price" in str(e).lower()

    @pytest.mark.unit
    def test_utility_functions_edge_cases(self):
        """Test utility functions handle edge cases gracefully."""
        # Safe divide with zero
        assert safe_divide(0, 5) == 0.0
        
        # Position value with zero quantity
        assert calculate_position_value(0, 100) == 0.0
        
        # Round to tick with zero
        assert round_to_tick_size(0) == 0.0

    @pytest.mark.unit
    def test_price_validation_decimal_places(self):
        """Test price validation handles decimal places correctly."""
        # Valid decimal places (up to 4)
        assert validate_price(100.1234) == 100.1234
        
        # Too many decimal places should be rounded
        result = validate_price(100.12345)
        assert abs(result - 100.1235) < 1e-6  # Rounded to 4 decimal places

    @pytest.mark.unit
    def test_order_validation_with_price(self):
        """Test order validation including price."""
        order_with_price = {
            'symbol': 'MSFT',
            'quantity': 50,
            'price': 300.50,
            'order_type': 'limit'
        }
        
        result = validate_order(order_with_price)
        assert result['symbol'] == 'MSFT'
        assert result['quantity'] == 50.0
        assert result['price'] == 300.50
        assert result['order_type'] == 'limit'

    @pytest.mark.unit
    def test_market_data_volume_validation(self):
        """Test market data volume validation."""
        # Valid volume
        data_with_volume = {
            'symbol': 'TSLA',
            'price': 250.0,
            'timestamp': datetime.now(),
            'volume': 50000
        }
        
        result = validate_market_data(data_with_volume)
        assert result['volume'] == 50000
        
        # Invalid negative volume
        data_negative_volume = {
            'symbol': 'TSLA',
            'price': 250.0,
            'timestamp': datetime.now(),
            'volume': -1000
        }
        
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_market_data(data_negative_volume)
