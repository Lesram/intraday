"""
Validation utilities stub for infrastructure compatibility.
Provides validation functions that tests expect to find.
"""

from typing import Dict, Any, List, Optional, Union
import re
from decimal import Decimal

class ValidationError(Exception):
    """Custom validation error."""
    pass

class Validator:
    """Base validator class."""
    
    def __init__(self, required: bool = False):
        self.required = required
        
    def validate(self, value: Any) -> Any:
        """Validate value."""
        if self.required and value is None:
            raise ValidationError("Value is required")
        return value

class StringValidator(Validator):
    """String validator."""
    
    def __init__(self, min_length: int = 0, max_length: int = None, pattern: str = None, **kwargs):
        super().__init__(**kwargs)
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = re.compile(pattern) if pattern else None
        
    def validate(self, value: str) -> str:
        """Validate string."""
        value = super().validate(value)
        if value is None:
            return value
            
        if not isinstance(value, str):
            raise ValidationError("Value must be a string")
            
        if len(value) < self.min_length:
            raise ValidationError(f"String too short (min {self.min_length})")
            
        if self.max_length and len(value) > self.max_length:
            raise ValidationError(f"String too long (max {self.max_length})")
            
        if self.pattern and not self.pattern.match(value):
            raise ValidationError("String format invalid")
            
        return value

class NumberValidator(Validator):
    """Number validator."""
    
    def __init__(self, min_value: Union[int, float] = None, max_value: Union[int, float] = None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        
    def validate(self, value: Union[int, float]) -> Union[int, float]:
        """Validate number."""
        value = super().validate(value)
        if value is None:
            return value
            
        if not isinstance(value, (int, float, Decimal)):
            raise ValidationError("Value must be a number")
            
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"Value too small (min {self.min_value})")
            
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"Value too large (max {self.max_value})")
            
        return value

class EmailValidator(StringValidator):
    """Email validator."""
    
    def __init__(self, **kwargs):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        super().__init__(pattern=email_pattern, **kwargs)

# Module-level validation functions
def validate_symbol(symbol: str) -> str:
    """Validate trading symbol."""
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("Symbol must be a non-empty string")
    
    if not re.match(r'^[A-Z]{1,5}$', symbol.upper()):
        raise ValidationError("Symbol must be 1-5 uppercase letters")
        
    return symbol.upper()

def validate_quantity(quantity: Union[int, float]) -> float:
    """Validate order quantity."""
    if quantity is None:
        raise ValidationError("Quantity is required")
        
    if not isinstance(quantity, (int, float)):
        raise ValidationError("Quantity must be a number")
        
    if quantity <= 0:
        raise ValidationError("Quantity must be positive")
        
    return float(quantity)

def validate_price(price: Union[int, float]) -> float:
    """Validate price."""
    if price is None:
        raise ValidationError("Price is required")
        
    if not isinstance(price, (int, float)):
        raise ValidationError("Price must be a number")
        
    if price <= 0:
        raise ValidationError("Price must be positive")
        
    return float(price)

def validate_order_side(side: str) -> str:
    """Validate order side."""
    valid_sides = ['BUY', 'SELL', 'buy', 'sell']
    if side not in valid_sides:
        raise ValidationError(f"Invalid order side. Must be one of: {valid_sides}")
    return side.upper()

def validate_order_type(order_type: str) -> str:
    """Validate order type."""
    valid_types = ['MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT', 'market', 'limit', 'stop', 'stop_limit']
    if order_type not in valid_types:
        raise ValidationError(f"Invalid order type. Must be one of: {valid_types}")
    return order_type.upper()

def validate_timeframe(timeframe: str) -> str:
    """Validate timeframe."""
    valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']
    if timeframe not in valid_timeframes:
        raise ValidationError(f"Invalid timeframe. Must be one of: {valid_timeframes}")
    return timeframe

def validate_email(email: str) -> str:
    """Validate email address."""
    validator = EmailValidator(required=True)
    return validator.validate(email)

def validate_password(password: str) -> str:
    """Validate password."""
    if not password:
        raise ValidationError("Password is required")
        
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")
        
    if not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain at least one uppercase letter")
        
    if not re.search(r'[a-z]', password):
        raise ValidationError("Password must contain at least one lowercase letter")
        
    if not re.search(r'\d', password):
        raise ValidationError("Password must contain at least one digit")
        
    return password

def validate_portfolio_allocation(allocations: Dict[str, float]) -> Dict[str, float]:
    """Validate portfolio allocation."""
    if not isinstance(allocations, dict):
        raise ValidationError("Allocations must be a dictionary")
        
    total = sum(allocations.values())
    if abs(total - 1.0) > 0.01:  # Allow small floating point errors
        raise ValidationError("Allocations must sum to 1.0")
        
    for symbol, allocation in allocations.items():
        validate_symbol(symbol)
        if allocation < 0 or allocation > 1:
            raise ValidationError("Each allocation must be between 0 and 1")
            
    return allocations

def validate_order_data(order: Dict[str, Any]) -> Dict[str, Any]:
    """Validate complete order data."""
    required_fields = ['symbol', 'quantity', 'side', 'type']
    
    for field in required_fields:
        if field not in order:
            raise ValidationError(f"Missing required field: {field}")
    
    validated = {
        'symbol': validate_symbol(order['symbol']),
        'quantity': validate_quantity(order['quantity']),
        'side': validate_order_side(order['side']),
        'type': validate_order_type(order['type'])
    }
    
    if 'price' in order:
        validated['price'] = validate_price(order['price'])
        
    if 'stop_price' in order:
        validated['stop_price'] = validate_price(order['stop_price'])
        
    return validated

def validate_risk_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate risk management parameters."""
    if 'max_position_size' in params:
        params['max_position_size'] = validate_price(params['max_position_size'])
        
    if 'stop_loss' in params:
        if params['stop_loss'] <= 0 or params['stop_loss'] >= 1:
            raise ValidationError("Stop loss must be between 0 and 1")
            
    if 'take_profit' in params:
        if params['take_profit'] <= 0:
            raise ValidationError("Take profit must be positive")
            
    return params

# Data validation helpers
def is_valid_json(data: str) -> bool:
    """Check if string is valid JSON."""
    try:
        import json
        json.loads(data)
        return True
    except (ValueError, TypeError):
        return False

def sanitize_input(value: str) -> str:
    """Sanitize input string."""
    if not isinstance(value, str):
        return str(value)
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\']', '', value)
    return sanitized.strip()

def validate_date_range(start_date: str, end_date: str) -> tuple:
    """Validate date range."""
    from datetime import datetime
    
    try:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except ValueError:
        raise ValidationError("Invalid date format. Use ISO format.")
        
    if start >= end:
        raise ValidationError("Start date must be before end date")
        
    return start, end
