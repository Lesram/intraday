"""
Comprehensive tests for backend.utils.validators

Targets 70%+ coverage for validation utilities:
- Validator classes (Validator, StringValidator, NumberValidator, EmailValidator)
- Module-level validation functions
"""

from decimal import Decimal
import pytest

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
    validate_password,
    validate_portfolio_allocation,
    validate_order_data,
    validate_risk_parameters,
    is_valid_json,
    sanitize_input,
    validate_date_range,
)


# ============================================================================
# BASE VALIDATOR TESTS
# ============================================================================

class TestValidator:
    """Tests for base Validator class"""
    
    def test_validate_not_required_none(self):
        """Test validate allows None when not required"""
        v = Validator(required=False)
        result = v.validate(None)
        assert result is None
        
    def test_validate_required_none_raises(self):
        """Test validate raises when None and required"""
        v = Validator(required=True)
        with pytest.raises(ValidationError):
            v.validate(None)
            
    def test_validate_value_passed_through(self):
        """Test validate passes through non-None values"""
        v = Validator()
        result = v.validate("test")
        assert result == "test"


# ============================================================================
# STRING VALIDATOR TESTS
# ============================================================================

class TestStringValidator:
    """Tests for StringValidator class"""
    
    def test_validate_valid_string(self):
        """Test valid string passes"""
        v = StringValidator()
        result = v.validate("test")
        assert result == "test"
        
    def test_validate_too_short(self):
        """Test string too short raises"""
        v = StringValidator(min_length=5)
        with pytest.raises(ValidationError):
            v.validate("abc")
            
    def test_validate_too_long(self):
        """Test string too long raises"""
        v = StringValidator(max_length=3)
        with pytest.raises(ValidationError):
            v.validate("abcdef")
            
    def test_validate_pattern_matches(self):
        """Test pattern matching works"""
        v = StringValidator(pattern=r'^[A-Z]+$')
        result = v.validate("ABC")
        assert result == "ABC"
        
    def test_validate_pattern_fails(self):
        """Test pattern mismatch raises"""
        v = StringValidator(pattern=r'^[A-Z]+$')
        with pytest.raises(ValidationError):
            v.validate("abc")
            
    def test_validate_non_string(self):
        """Test non-string raises"""
        v = StringValidator()
        with pytest.raises(ValidationError):
            v.validate(123)
            
    def test_validate_none_when_not_required(self):
        """Test None allowed when not required"""
        v = StringValidator(required=False)
        result = v.validate(None)
        assert result is None


# ============================================================================
# NUMBER VALIDATOR TESTS
# ============================================================================

class TestNumberValidator:
    """Tests for NumberValidator class"""
    
    def test_validate_valid_int(self):
        """Test valid integer passes"""
        v = NumberValidator()
        result = v.validate(42)
        assert result == 42
        
    def test_validate_valid_float(self):
        """Test valid float passes"""
        v = NumberValidator()
        result = v.validate(3.14)
        assert result == 3.14
        
    def test_validate_valid_decimal(self):
        """Test valid Decimal passes"""
        v = NumberValidator()
        result = v.validate(Decimal("10.50"))
        assert result == Decimal("10.50")
        
    def test_validate_below_min(self):
        """Test value below min raises"""
        v = NumberValidator(min_value=10)
        with pytest.raises(ValidationError):
            v.validate(5)
            
    def test_validate_above_max(self):
        """Test value above max raises"""
        v = NumberValidator(max_value=100)
        with pytest.raises(ValidationError):
            v.validate(150)
            
    def test_validate_non_number(self):
        """Test non-number raises"""
        v = NumberValidator()
        with pytest.raises(ValidationError):
            v.validate("not a number")
            
    def test_validate_none_when_not_required(self):
        """Test None allowed when not required"""
        v = NumberValidator(required=False)
        result = v.validate(None)
        assert result is None


# ============================================================================
# EMAIL VALIDATOR TESTS
# ============================================================================

class TestEmailValidator:
    """Tests for EmailValidator class"""
    
    def test_validate_valid_email(self):
        """Test valid email passes"""
        v = EmailValidator()
        result = v.validate("user@example.com")
        assert result == "user@example.com"
        
    def test_validate_invalid_email(self):
        """Test invalid email raises"""
        v = EmailValidator()
        with pytest.raises(ValidationError):
            v.validate("not-an-email")


# ============================================================================
# VALIDATE SYMBOL TESTS
# ============================================================================

class TestValidateSymbol:
    """Tests for validate_symbol function"""
    
    def test_valid_symbol_uppercase(self):
        """Test valid uppercase symbol"""
        result = validate_symbol("AAPL")
        assert result == "AAPL"
        
    def test_valid_symbol_lowercase(self):
        """Test lowercase converted to uppercase"""
        result = validate_symbol("aapl")
        assert result == "AAPL"
        
    def test_empty_symbol_raises(self):
        """Test empty symbol raises"""
        with pytest.raises(ValidationError):
            validate_symbol("")
            
    def test_none_symbol_raises(self):
        """Test None symbol raises"""
        with pytest.raises(ValidationError):
            validate_symbol(None)
            
    def test_too_long_symbol_raises(self):
        """Test symbol > 5 chars raises"""
        with pytest.raises(ValidationError):
            validate_symbol("TOOLONG")
            
    def test_numeric_symbol_raises(self):
        """Test symbol with numbers raises"""
        with pytest.raises(ValidationError):
            validate_symbol("ABC123")


# ============================================================================
# VALIDATE QUANTITY TESTS
# ============================================================================

class TestValidateQuantity:
    """Tests for validate_quantity function"""
    
    def test_valid_int_quantity(self):
        """Test valid integer quantity"""
        result = validate_quantity(100)
        assert result == 100.0
        
    def test_valid_float_quantity(self):
        """Test valid float quantity"""
        result = validate_quantity(50.5)
        assert result == 50.5
        
    def test_none_quantity_raises(self):
        """Test None quantity raises"""
        with pytest.raises(ValidationError):
            validate_quantity(None)
            
    def test_zero_quantity_raises(self):
        """Test zero quantity raises"""
        with pytest.raises(ValidationError):
            validate_quantity(0)
            
    def test_negative_quantity_raises(self):
        """Test negative quantity raises"""
        with pytest.raises(ValidationError):
            validate_quantity(-10)
            
    def test_string_quantity_raises(self):
        """Test string quantity raises"""
        with pytest.raises(ValidationError):
            validate_quantity("100")


# ============================================================================
# VALIDATE PRICE TESTS
# ============================================================================

class TestValidatePrice:
    """Tests for validate_price function"""
    
    def test_valid_price(self):
        """Test valid price"""
        result = validate_price(150.50)
        assert result == 150.50
        
    def test_none_price_raises(self):
        """Test None price raises"""
        with pytest.raises(ValidationError):
            validate_price(None)
            
    def test_zero_price_raises(self):
        """Test zero price raises"""
        with pytest.raises(ValidationError):
            validate_price(0)
            
    def test_negative_price_raises(self):
        """Test negative price raises"""
        with pytest.raises(ValidationError):
            validate_price(-10)


# ============================================================================
# VALIDATE ORDER SIDE TESTS
# ============================================================================

class TestValidateOrderSide:
    """Tests for validate_order_side function"""
    
    def test_valid_buy_uppercase(self):
        """Test BUY valid"""
        result = validate_order_side("BUY")
        assert result == "BUY"
        
    def test_valid_sell_uppercase(self):
        """Test SELL valid"""
        result = validate_order_side("SELL")
        assert result == "SELL"
        
    def test_valid_buy_lowercase(self):
        """Test buy converted to uppercase"""
        result = validate_order_side("buy")
        assert result == "BUY"
        
    def test_valid_sell_lowercase(self):
        """Test sell converted to uppercase"""
        result = validate_order_side("sell")
        assert result == "SELL"
        
    def test_invalid_side_raises(self):
        """Test invalid side raises"""
        with pytest.raises(ValidationError):
            validate_order_side("HOLD")


# ============================================================================
# VALIDATE ORDER TYPE TESTS
# ============================================================================

class TestValidateOrderType:
    """Tests for validate_order_type function"""
    
    def test_valid_market(self):
        """Test MARKET valid"""
        result = validate_order_type("MARKET")
        assert result == "MARKET"
        
    def test_valid_limit(self):
        """Test LIMIT valid"""
        result = validate_order_type("LIMIT")
        assert result == "LIMIT"
        
    def test_valid_stop(self):
        """Test STOP valid"""
        result = validate_order_type("STOP")
        assert result == "STOP"
        
    def test_valid_lowercase(self):
        """Test lowercase converted"""
        result = validate_order_type("market")
        assert result == "MARKET"
        
    def test_invalid_type_raises(self):
        """Test invalid type raises"""
        with pytest.raises(ValidationError):
            validate_order_type("INVALID")


# ============================================================================
# VALIDATE TIMEFRAME TESTS
# ============================================================================

class TestValidateTimeframe:
    """Tests for validate_timeframe function"""
    
    def test_valid_1m(self):
        """Test 1m timeframe"""
        result = validate_timeframe("1m")
        assert result == "1m"
        
    def test_valid_1d(self):
        """Test 1d timeframe"""
        result = validate_timeframe("1d")
        assert result == "1d"
        
    def test_invalid_timeframe_raises(self):
        """Test invalid timeframe raises"""
        with pytest.raises(ValidationError):
            validate_timeframe("2m")


# ============================================================================
# VALIDATE EMAIL TESTS
# ============================================================================

class TestValidateEmailFunction:
    """Tests for validate_email function"""
    
    def test_valid_email(self):
        """Test valid email"""
        result = validate_email("user@example.com")
        assert result == "user@example.com"


# ============================================================================
# VALIDATE PASSWORD TESTS
# ============================================================================

class TestValidatePassword:
    """Tests for validate_password function"""
    
    def test_valid_password(self):
        """Test valid password"""
        result = validate_password("Password123")
        assert result == "Password123"
        
    def test_empty_password_raises(self):
        """Test empty password raises"""
        with pytest.raises(ValidationError):
            validate_password("")
            
    def test_too_short_raises(self):
        """Test short password raises"""
        with pytest.raises(ValidationError):
            validate_password("Pass1")
            
    def test_no_uppercase_raises(self):
        """Test no uppercase raises"""
        with pytest.raises(ValidationError):
            validate_password("password123")
            
    def test_no_lowercase_raises(self):
        """Test no lowercase raises"""
        with pytest.raises(ValidationError):
            validate_password("PASSWORD123")
            
    def test_no_digit_raises(self):
        """Test no digit raises"""
        with pytest.raises(ValidationError):
            validate_password("PasswordABC")


# ============================================================================
# VALIDATE PORTFOLIO ALLOCATION TESTS
# ============================================================================

class TestValidatePortfolioAllocation:
    """Tests for validate_portfolio_allocation function"""
    
    def test_valid_allocation(self):
        """Test valid allocation"""
        result = validate_portfolio_allocation({"AAPL": 0.5, "MSFT": 0.5})
        assert result == {"AAPL": 0.5, "MSFT": 0.5}
        
    def test_not_dict_raises(self):
        """Test non-dict raises"""
        with pytest.raises(ValidationError):
            validate_portfolio_allocation([0.5, 0.5])
            
    def test_not_sum_to_one_raises(self):
        """Test allocations not summing to 1 raises"""
        with pytest.raises(ValidationError):
            validate_portfolio_allocation({"AAPL": 0.3, "MSFT": 0.5})
            
    def test_negative_allocation_raises(self):
        """Test negative allocation raises"""
        with pytest.raises(ValidationError):
            validate_portfolio_allocation({"AAPL": -0.1, "MSFT": 1.1})


# ============================================================================
# VALIDATE ORDER DATA TESTS
# ============================================================================

class TestValidateOrderData:
    """Tests for validate_order_data function"""
    
    def test_valid_order(self):
        """Test valid order data"""
        order = {
            "symbol": "AAPL",
            "quantity": 100,
            "side": "BUY",
            "type": "MARKET"
        }
        result = validate_order_data(order)
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        
    def test_with_price(self):
        """Test order with price"""
        order = {
            "symbol": "AAPL",
            "quantity": 100,
            "side": "BUY",
            "type": "LIMIT",
            "price": 150.00
        }
        result = validate_order_data(order)
        assert result["price"] == 150.00
        
    def test_missing_field_raises(self):
        """Test missing required field raises"""
        order = {"symbol": "AAPL", "quantity": 100}
        with pytest.raises(ValidationError):
            validate_order_data(order)


# ============================================================================
# VALIDATE RISK PARAMETERS TESTS
# ============================================================================

class TestValidateRiskParameters:
    """Tests for validate_risk_parameters function"""
    
    def test_valid_params(self):
        """Test valid risk parameters"""
        params = {"max_position_size": 10000}
        result = validate_risk_parameters(params)
        assert result["max_position_size"] == 10000.0
        
    def test_invalid_stop_loss_raises(self):
        """Test invalid stop_loss raises"""
        params = {"stop_loss": 1.5}  # > 1
        with pytest.raises(ValidationError):
            validate_risk_parameters(params)
            
    def test_invalid_take_profit_raises(self):
        """Test invalid take_profit raises"""
        params = {"take_profit": -0.1}  # < 0
        with pytest.raises(ValidationError):
            validate_risk_parameters(params)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestIsValidJson:
    """Tests for is_valid_json function"""
    
    def test_valid_json(self):
        """Test valid JSON"""
        assert is_valid_json('{"key": "value"}') is True
        
    def test_invalid_json(self):
        """Test invalid JSON"""
        assert is_valid_json('not json') is False
        
    def test_none(self):
        """Test None returns False"""
        assert is_valid_json(None) is False


class TestSanitizeInput:
    """Tests for sanitize_input function"""
    
    def test_removes_dangerous_chars(self):
        """Test dangerous chars removed"""
        result = sanitize_input('<script>alert("xss")</script>')
        assert "<" not in result
        assert ">" not in result
        
    def test_strips_whitespace(self):
        """Test whitespace stripped"""
        result = sanitize_input("  test  ")
        assert result == "test"
        
    def test_non_string_converted(self):
        """Test non-string converted"""
        result = sanitize_input(123)
        assert result == "123"


class TestValidateDateRange:
    """Tests for validate_date_range function"""
    
    def test_valid_range(self):
        """Test valid date range"""
        start, end = validate_date_range("2024-01-01", "2024-12-31")
        assert start < end
        
    def test_start_after_end_raises(self):
        """Test start >= end raises"""
        with pytest.raises(ValidationError):
            validate_date_range("2024-12-31", "2024-01-01")
            
    def test_invalid_format_raises(self):
        """Test invalid date format raises"""
        with pytest.raises(ValidationError):
            validate_date_range("not-a-date", "2024-12-31")
