"""
Comprehensive tests for backend.utils.validators and backend.infra.validation modules

Tests all validation functions for trading inputs and data.
Target: 0% → 90%+ coverage for:
- backend/utils/validators.py (257 lines)
- backend/infra/validation.py (247 lines)
"""

import pytest
from decimal import Decimal

from backend.utils.validators import (
    ValidationError,
    Validator,
    StringValidator,
    NumberValidator,
    EmailValidator,
    validate_symbol,
    validate_quantity,
    validate_price,
    validate_order_side,
    validate_order_type,
    validate_timeframe,
    validate_email,
)

from backend.infra.validation import (
    validate_symbol as infra_validate_symbol,
    validate_price as infra_validate_price,
    validate_quantity as infra_validate_quantity,
    validate_order as infra_validate_order,
)


class TestBaseValidator:
    """Test base Validator class"""
    
    def test_validator_optional(self):
        """Test validator allows None when not required"""
        validator = Validator(required=False)
        assert validator.validate(None) is None
    
    def test_validator_required(self):
        """Test validator raises when None and required"""
        validator = Validator(required=True)
        with pytest.raises(ValidationError, match="required"):
            validator.validate(None)
    
    def test_validator_accepts_value(self):
        """Test validator accepts non-None value"""
        validator = Validator(required=True)
        assert validator.validate("test") == "test"


class TestStringValidator:
    """Test StringValidator class"""
    
    def test_string_validator_min_length(self):
        """Test string minimum length validation"""
        validator = StringValidator(min_length=5)
        
        with pytest.raises(ValidationError, match="too short"):
            validator.validate("abc")
        
        assert validator.validate("abcde") == "abcde"
    
    def test_string_validator_max_length(self):
        """Test string maximum length validation"""
        validator = StringValidator(max_length=10)
        
        with pytest.raises(ValidationError, match="too long"):
            validator.validate("a" * 11)
        
        assert validator.validate("a" * 10) == "a" * 10
    
    def test_string_validator_pattern(self):
        """Test string pattern validation"""
        validator = StringValidator(pattern=r'^[A-Z]+$')
        
        with pytest.raises(ValidationError, match="format invalid"):
            validator.validate("abc123")
        
        assert validator.validate("ABC") == "ABC"
    
    def test_string_validator_not_string(self):
        """Test validation fails for non-string"""
        validator = StringValidator()
        
        with pytest.raises(ValidationError, match="must be a string"):
            validator.validate(123)
    
    def test_string_validator_combined_rules(self):
        """Test string validator with multiple rules"""
        validator = StringValidator(min_length=2, max_length=5, pattern=r'^[A-Z]+$')
        
        with pytest.raises(ValidationError):
            validator.validate("A")  # Too short
        
        with pytest.raises(ValidationError):
            validator.validate("ABCDEF")  # Too long
        
        with pytest.raises(ValidationError):
            validator.validate("ABC1")  # Invalid pattern
        
        assert validator.validate("ABC") == "ABC"


class TestNumberValidator:
    """Test NumberValidator class"""
    
    def test_number_validator_min_value(self):
        """Test number minimum value validation"""
        validator = NumberValidator(min_value=0)
        
        with pytest.raises(ValidationError, match="too small"):
            validator.validate(-1)
        
        assert validator.validate(0) == 0
        assert validator.validate(10) == 10
    
    def test_number_validator_max_value(self):
        """Test number maximum value validation"""
        validator = NumberValidator(max_value=100)
        
        with pytest.raises(ValidationError, match="too large"):
            validator.validate(101)
        
        assert validator.validate(100) == 100
    
    def test_number_validator_range(self):
        """Test number range validation"""
        validator = NumberValidator(min_value=1, max_value=10)
        
        with pytest.raises(ValidationError):
            validator.validate(0)
        
        with pytest.raises(ValidationError):
            validator.validate(11)
        
        assert validator.validate(5) == 5
    
    def test_number_validator_accepts_decimal(self):
        """Test number validator accepts Decimal"""
        validator = NumberValidator(min_value=0, max_value=100)
        value = Decimal("50.5")
        assert validator.validate(value) == value
    
    def test_number_validator_not_number(self):
        """Test validation fails for non-number"""
        validator = NumberValidator()
        
        with pytest.raises(ValidationError, match="must be a number"):
            validator.validate("not a number")


class TestEmailValidator:
    """Test EmailValidator class"""
    
    def test_email_validator_valid_email(self):
        """Test email validator with valid emails"""
        validator = EmailValidator()
        
        assert validator.validate("test@example.com") == "test@example.com"
        assert validator.validate("user.name@domain.co.uk") == "user.name@domain.co.uk"
        assert validator.validate("test+tag@example.com") == "test+tag@example.com"
    
    def test_email_validator_invalid_email(self):
        """Test email validator with invalid emails"""
        validator = EmailValidator()
        
        with pytest.raises(ValidationError):
            validator.validate("notanemail")
        
        with pytest.raises(ValidationError):
            validator.validate("@example.com")
        
        with pytest.raises(ValidationError):
            validator.validate("test@")
        
        with pytest.raises(ValidationError):
            validator.validate("test @example.com")  # Space


class TestValidateSymbol:
    """Test validate_symbol function"""
    
    def test_validate_symbol_valid(self):
        """Test validation of valid symbols"""
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_symbol("aapl") == "AAPL"  # Converts to uppercase
        assert validate_symbol("MSFT") == "MSFT"
        assert validate_symbol("F") == "F"  # Single letter
    
    def test_validate_symbol_invalid_empty(self):
        """Test validation fails for empty symbol"""
        with pytest.raises(ValidationError):
            validate_symbol("")
    
    def test_validate_symbol_invalid_too_long(self):
        """Test validation fails for symbol too long"""
        with pytest.raises(ValidationError):
            validate_symbol("ABCDEF")  # More than 5 letters
    
    def test_validate_symbol_invalid_characters(self):
        """Test validation fails for invalid characters"""
        with pytest.raises(ValidationError):
            validate_symbol("AAP123")  # Contains numbers
        
        with pytest.raises(ValidationError):
            validate_symbol("AAP-L")  # Contains hyphen


class TestValidateQuantity:
    """Test validate_quantity function"""
    
    def test_validate_quantity_valid(self):
        """Test validation of valid quantities"""
        assert validate_quantity(10) == 10.0
        assert validate_quantity(100.5) == 100.5
        assert validate_quantity(1) == 1.0
    
    def test_validate_quantity_invalid_none(self):
        """Test validation fails for None"""
        with pytest.raises(ValidationError, match="required"):
            validate_quantity(None)
    
    def test_validate_quantity_invalid_negative(self):
        """Test validation fails for negative quantity"""
        with pytest.raises(ValidationError, match="positive"):
            validate_quantity(-10)
    
    def test_validate_quantity_invalid_zero(self):
        """Test validation fails for zero quantity"""
        with pytest.raises(ValidationError, match="positive"):
            validate_quantity(0)
    
    def test_validate_quantity_invalid_type(self):
        """Test validation fails for invalid type"""
        with pytest.raises(ValidationError, match="must be a number"):
            validate_quantity("not a number")


class TestValidatePrice:
    """Test validate_price function"""
    
    def test_validate_price_valid(self):
        """Test validation of valid prices"""
        assert validate_price(100) == 100.0
        assert validate_price(99.99) == 99.99
        assert validate_price(0.01) == 0.01
    
    def test_validate_price_invalid_none(self):
        """Test validation fails for None"""
        with pytest.raises(ValidationError, match="required"):
            validate_price(None)
    
    def test_validate_price_invalid_negative(self):
        """Test validation fails for negative price"""
        with pytest.raises(ValidationError, match="positive"):
            validate_price(-100)
    
    def test_validate_price_invalid_zero(self):
        """Test validation fails for zero price"""
        with pytest.raises(ValidationError, match="positive"):
            validate_price(0)
    
    def test_validate_price_invalid_type(self):
        """Test validation fails for invalid type"""
        with pytest.raises(ValidationError, match="must be a number"):
            validate_price("100")


class TestValidateOrderSide:
    """Test validate_order_side function"""
    
    def test_validate_order_side_valid(self):
        """Test validation of valid order sides"""
        assert validate_order_side("BUY") == "BUY"
        assert validate_order_side("buy") == "BUY"  # Converts to uppercase
        assert validate_order_side("SELL") == "SELL"
        assert validate_order_side("sell") == "SELL"
    
    def test_validate_order_side_invalid(self):
        """Test validation fails for invalid side"""
        with pytest.raises(ValidationError, match="Invalid order side"):
            validate_order_side("HOLD")
        
        with pytest.raises(ValidationError):
            validate_order_side("")


class TestValidateOrderType:
    """Test validate_order_type function"""
    
    def test_validate_order_type_valid(self):
        """Test validation of valid order types"""
        assert validate_order_type("MARKET") == "MARKET"
        assert validate_order_type("market") == "MARKET"
        assert validate_order_type("LIMIT") == "LIMIT"
        assert validate_order_type("STOP") == "STOP"
        assert validate_order_type("STOP_LIMIT") == "STOP_LIMIT"
    
    def test_validate_order_type_invalid(self):
        """Test validation fails for invalid order type"""
        with pytest.raises(ValidationError, match="Invalid order type"):
            validate_order_type("FOK")  # Fill-or-Kill not supported


class TestValidateTimeframe:
    """Test validate_timeframe function"""
    
    def test_validate_timeframe_valid(self):
        """Test validation of valid timeframes"""
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']
        for tf in valid_timeframes:
            assert validate_timeframe(tf) == tf
    
    def test_validate_timeframe_invalid(self):
        """Test validation fails for invalid timeframe"""
        with pytest.raises(ValidationError, match="Invalid timeframe"):
            validate_timeframe("2h")  # Not in valid list


class TestValidateEmail:
    """Test validate_email function"""
    
    def test_validate_email_valid(self):
        """Test validation of valid email addresses"""
        assert validate_email("user@example.com") == "user@example.com"
    
    def test_validate_email_invalid(self):
        """Test validation fails for invalid email"""
        with pytest.raises(ValidationError):
            validate_email("not-an-email")


# ============================================================================
# INFRA VALIDATION TESTS
# ============================================================================

class TestInfraValidateSymbol:
    """Test infra.validation.validate_symbol function"""
    
    def test_infra_validate_symbol_valid(self):
        """Test validation of valid symbols"""
        assert infra_validate_symbol("AAPL") == "AAPL"
        assert infra_validate_symbol("aapl") == "AAPL"  # Converts to uppercase
        assert infra_validate_symbol("BRK.B") == "BRK.B"  # Allows dots
    
    def test_infra_validate_symbol_invalid_empty(self):
        """Test validation fails for empty symbol"""
        with pytest.raises(ValueError, match="cannot be empty"):
            infra_validate_symbol("")
    
    def test_infra_validate_symbol_invalid_too_long(self):
        """Test validation fails for symbol too long"""
        with pytest.raises(ValueError, match="too long"):
            infra_validate_symbol("A" * 11)
    
    def test_infra_validate_symbol_invalid_starts_with_number(self):
        """Test validation fails for symbol starting with number"""
        with pytest.raises(ValueError, match="cannot start with number"):
            infra_validate_symbol("1AAPL")
    
    def test_infra_validate_symbol_invalid_characters(self):
        """Test validation fails for invalid characters"""
        with pytest.raises(ValueError, match="Invalid characters"):
            infra_validate_symbol("AAP&L")


class TestInfraValidatePrice:
    """Test infra.validation.validate_price function"""
    
    def test_infra_validate_price_valid(self):
        """Test validation of valid prices"""
        assert infra_validate_price(100.0) == 100.0
        assert infra_validate_price(99.99) == 99.99
        assert abs(infra_validate_price(99.9999) - 99.9999) < 0.0001
    
    def test_infra_validate_price_invalid_negative(self):
        """Test validation fails for negative price"""
        with pytest.raises(ValueError, match="positive"):
            infra_validate_price(-100)
    
    def test_infra_validate_price_invalid_zero(self):
        """Test validation fails for zero price"""
        with pytest.raises(ValueError, match="positive"):
            infra_validate_price(0)
    
    def test_infra_validate_price_too_large(self):
        """Test validation fails for excessively large price"""
        with pytest.raises(ValueError, match="too large"):
            infra_validate_price(1e9)  # $1 billion per share
    
    def test_infra_validate_price_too_many_decimals(self):
        """Test validation fails for too many decimal places"""
        with pytest.raises(ValueError, match="Too many decimal places"):
            infra_validate_price(99.99999)  # More than 4 decimal places


class TestInfraValidateQuantity:
    """Test infra.validation.validate_quantity function"""
    
    def test_infra_validate_quantity_valid(self):
        """Test validation of valid quantities"""
        assert infra_validate_quantity(10) == 10.0
        assert infra_validate_quantity(100.5) == 100.5
        assert infra_validate_quantity(100.5, allow_fractional=True) == 100.5
    
    def test_infra_validate_quantity_invalid_zero(self):
        """Test validation fails for zero quantity"""
        with pytest.raises(ValueError, match="cannot be zero"):
            infra_validate_quantity(0)
    
    def test_infra_validate_quantity_too_large(self):
        """Test validation fails for excessively large quantity"""
        with pytest.raises(ValueError, match="too large"):
            infra_validate_quantity(1e9)
    
    def test_infra_validate_quantity_fractional_not_allowed(self):
        """Test validation fails for fractional shares when not allowed"""
        with pytest.raises(ValueError, match="Fractional shares not allowed"):
            infra_validate_quantity(10.5, allow_fractional=False)
    
    def test_infra_validate_quantity_fractional_allowed(self):
        """Test validation succeeds for fractional shares when allowed"""
        assert infra_validate_quantity(10.5, allow_fractional=True) == 10.5
    
    def test_infra_validate_quantity_negative(self):
        """Test validation handles negative quantity"""
        # Negative quantities might be allowed for short selling
        result = infra_validate_quantity(-10)
        assert result == -10.0


class TestInfraValidateOrder:
    """Test infra.validation.validate_order function"""
    
    def test_infra_validate_order_valid_market_order(self):
        """Test validation of valid market order"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market"
        }
        result = infra_validate_order(order)
        assert result is not None
    
    def test_infra_validate_order_valid_limit_order(self):
        """Test validation of valid limit order"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "limit",
            "price": 150.0
        }
        result = infra_validate_order(order)
        assert result is not None
