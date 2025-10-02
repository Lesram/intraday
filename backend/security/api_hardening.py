#!/usr/bin/env python3
"""
Production API Hardening Framework
Comprehensive request validation, sanitization, and security
"""

import re
import json
import time
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
from functools import wraps
import asyncio

try:
    from pydantic import BaseModel, validator, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    ValidationError = ValueError

class SecurityLevel(Enum):
    """API security levels"""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    INTERNAL = "internal"
    ADMIN = "admin"

class InputSanitizer:
    """Input sanitization and validation utilities"""
    
    # Common regex patterns
    PATTERNS = {
        'symbol': re.compile(r'^[A-Z]{1,5}$'),
        'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
        'alphanumeric': re.compile(r'^[a-zA-Z0-9]+$'),
        'uuid': re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
        'decimal': re.compile(r'^\d+\.?\d*$'),
        'order_side': re.compile(r'^(buy|sell)$'),
        'order_type': re.compile(r'^(market|limit|stop|stop_limit)$'),
        'time_in_force': re.compile(r'^(day|gtc|ioc|fok)$')
    }
    
    # Dangerous patterns to block
    BLOCKED_PATTERNS = [
        re.compile(r'[<>"\';()&+]'),  # HTML/SQL injection
        re.compile(r'(script|javascript|vbscript)', re.IGNORECASE),
        re.compile(r'(union|select|insert|delete|drop|create)', re.IGNORECASE),
        re.compile(r'(\.\./|\\\.\\)', re.IGNORECASE),  # Path traversal
        re.compile(r'(eval|exec|system|shell)', re.IGNORECASE)  # Code execution
    ]
    
    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 255, allow_special: bool = False) -> str:
        """Sanitize string input"""
        
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        
        # Trim whitespace
        value = value.strip()
        
        # Check length
        if len(value) > max_length:
            raise ValueError(f"String length exceeds maximum of {max_length}")
        
        # Check for blocked patterns
        if not allow_special:
            for pattern in cls.BLOCKED_PATTERNS:
                if pattern.search(value):
                    raise ValueError(f"String contains blocked pattern")
        
        # HTML encode special characters
        replacements = {
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;'
        }
        
        for char, replacement in replacements.items():
            value = value.replace(char, replacement)
        
        return value
    
    @classmethod
    def validate_symbol(cls, symbol: str) -> str:
        """Validate trading symbol"""
        
        symbol = cls.sanitize_string(symbol, max_length=10).upper()
        
        if not cls.PATTERNS['symbol'].match(symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        return symbol
    
    @classmethod
    def validate_quantity(cls, qty: Union[int, float, str]) -> float:
        """Validate order quantity"""
        
        try:
            qty_float = float(qty)
        except (ValueError, TypeError):
            raise ValueError("Quantity must be a valid number")
        
        if qty_float <= 0:
            raise ValueError("Quantity must be positive")
        
        if qty_float > 1000000:  # 1M share limit
            raise ValueError("Quantity exceeds maximum allowed")
        
        return qty_float
    
    @classmethod
    def validate_price(cls, price: Union[float, str, None]) -> Optional[float]:
        """Validate price input"""
        
        if price is None:
            return None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            raise ValueError("Price must be a valid number")
        
        if price_float <= 0:
            raise ValueError("Price must be positive")
        
        if price_float > 100000:  # $100K per share limit
            raise ValueError("Price exceeds maximum allowed")
        
        # Round to 2 decimal places
        return round(price_float, 2)
    
    @classmethod
    def validate_enum_value(cls, value: str, valid_values: List[str]) -> str:
        """Validate enum value"""
        
        value = cls.sanitize_string(value, max_length=50).lower()
        
        if value not in valid_values:
            raise ValueError(f"Invalid value '{value}'. Must be one of: {valid_values}")
        
        return value

@dataclass
class APIRequest:
    """API request structure with metadata"""
    endpoint: str
    method: str
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: str
    user_agent: str
    timestamp: datetime
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, Any] = field(default_factory=dict)
    body_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValidationResult:
    """Request validation result"""
    is_valid: bool
    sanitized_data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

class RateLimiter:
    """Advanced rate limiting with multiple strategies"""
    
    def __init__(self):
        """Initialize rate limiter"""
        self.request_counts = {}  # user_id -> timestamps
        self.blocked_ips = {}     # ip -> block_until
        
        # Rate limits (requests per minute)
        self.limits = {
            SecurityLevel.PUBLIC: 60,
            SecurityLevel.AUTHENTICATED: 300,
            SecurityLevel.INTERNAL: 1000,
            SecurityLevel.ADMIN: 5000
        }
    
    def check_rate_limit(self, user_id: str, ip_address: str, security_level: SecurityLevel) -> Dict[str, Any]:
        """Check if request should be rate limited"""
        
        now = time.time()
        
        # Check IP blocks
        if ip_address in self.blocked_ips:
            if now < self.blocked_ips[ip_address]:
                return {
                    'allowed': False,
                    'reason': 'ip_blocked',
                    'retry_after': int(self.blocked_ips[ip_address] - now)
                }
            else:
                del self.blocked_ips[ip_address]
        
        # Get rate limit for security level
        limit = self.limits.get(security_level, 60)
        
        # Clean old requests (older than 1 minute)
        cutoff = now - 60
        if user_id in self.request_counts:
            self.request_counts[user_id] = [
                ts for ts in self.request_counts[user_id] if ts > cutoff
            ]
        else:
            self.request_counts[user_id] = []
        
        # Check current count
        current_count = len(self.request_counts[user_id])
        
        if current_count >= limit:
            # Block aggressive users
            if current_count > limit * 2:
                self.blocked_ips[ip_address] = now + 300  # Block for 5 minutes
            
            return {
                'allowed': False,
                'reason': 'rate_limit_exceeded',
                'current_count': current_count,
                'limit': limit,
                'retry_after': 60
            }
        
        # Allow request
        self.request_counts[user_id].append(now)
        
        return {
            'allowed': True,
            'current_count': current_count + 1,
            'limit': limit,
            'remaining': limit - current_count - 1
        }

class RequestValidator:
    """Comprehensive request validation"""
    
    def __init__(self):
        """Initialize request validator"""
        self.logger = logging.getLogger(__name__)
        self.rate_limiter = RateLimiter()
    
    def validate_order_request(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate order submission request"""
        
        errors = []
        warnings = []
        sanitized = {}
        
        try:
            # Required fields
            required_fields = ['symbol', 'qty', 'side', 'type']
            for field in required_fields:
                if field not in data:
                    errors.append(f"Missing required field: {field}")
            
            if errors:
                return ValidationResult(False, {}, errors)
            
            # Validate symbol
            try:
                sanitized['symbol'] = InputSanitizer.validate_symbol(data['symbol'])
            except ValueError as e:
                errors.append(f"Symbol validation failed: {str(e)}")
            
            # Validate quantity
            try:
                sanitized['qty'] = InputSanitizer.validate_quantity(data['qty'])
            except ValueError as e:
                errors.append(f"Quantity validation failed: {str(e)}")
            
            # Validate side
            try:
                sanitized['side'] = InputSanitizer.validate_enum_value(
                    data['side'], ['buy', 'sell']
                )
            except ValueError as e:
                errors.append(f"Side validation failed: {str(e)}")
            
            # Validate type
            try:
                sanitized['type'] = InputSanitizer.validate_enum_value(
                    data['type'], ['market', 'limit', 'stop', 'stop_limit']
                )
            except ValueError as e:
                errors.append(f"Order type validation failed: {str(e)}")
            
            # Validate optional fields
            if 'limit_price' in data:
                try:
                    sanitized['limit_price'] = InputSanitizer.validate_price(data['limit_price'])
                except ValueError as e:
                    errors.append(f"Limit price validation failed: {str(e)}")
            
            if 'stop_price' in data:
                try:
                    sanitized['stop_price'] = InputSanitizer.validate_price(data['stop_price'])
                except ValueError as e:
                    errors.append(f"Stop price validation failed: {str(e)}")
            
            # Validate time in force
            if 'time_in_force' in data:
                try:
                    sanitized['time_in_force'] = InputSanitizer.validate_enum_value(
                        data['time_in_force'], ['day', 'gtc', 'ioc', 'fok']
                    )
                except ValueError as e:
                    errors.append(f"Time in force validation failed: {str(e)}")
            else:
                sanitized['time_in_force'] = 'day'  # Default
            
            # Business logic validation
            if sanitized.get('type') == 'limit' and 'limit_price' not in sanitized:
                errors.append("Limit orders require limit_price")
            
            if sanitized.get('type') in ['stop', 'stop_limit'] and 'stop_price' not in sanitized:
                errors.append("Stop orders require stop_price")
            
            # Risk checks
            if sanitized.get('qty', 0) > 10000:
                warnings.append("Large order quantity - consider splitting")
            
            notional_value = sanitized.get('qty', 0) * sanitized.get('limit_price', 100)
            if notional_value > 1000000:  # $1M
                warnings.append("High notional value order")
            
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_data=sanitized,
            errors=errors,
            warnings=warnings
        )
    
    def validate_authentication(self, request: APIRequest) -> Dict[str, Any]:
        """Validate authentication and authorization"""
        
        # Check for required headers
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header:
            return {
                'authenticated': False,
                'reason': 'missing_authorization_header',
                'security_level': SecurityLevel.PUBLIC
            }
        
        # Validate API key format
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]
            
            if len(api_key) < 32:
                return {
                    'authenticated': False,
                    'reason': 'invalid_api_key_format',
                    'security_level': SecurityLevel.PUBLIC
                }
            
            # In production, validate against database
            # For now, simulate validation
            if api_key.startswith('demo_'):
                return {
                    'authenticated': True,
                    'user_id': 'demo_user',
                    'security_level': SecurityLevel.AUTHENTICATED
                }
            elif api_key.startswith('admin_'):
                return {
                    'authenticated': True,
                    'user_id': 'admin_user',
                    'security_level': SecurityLevel.ADMIN
                }
            else:
                return {
                    'authenticated': False,
                    'reason': 'invalid_api_key',
                    'security_level': SecurityLevel.PUBLIC
                }
        
        return {
            'authenticated': False,
            'reason': 'invalid_authorization_format',
            'security_level': SecurityLevel.PUBLIC
        }

class SecurityMiddleware:
    """Comprehensive security middleware for API protection"""
    
    def __init__(self):
        """Initialize security middleware"""
        self.logger = logging.getLogger(__name__)
        self.validator = RequestValidator()
        
        # Track suspicious activity
        self.suspicious_activity = {}
        self.blocked_requests = []
        
        # SLO integration
        try:
            from backend.monitoring.slo_metrics import get_slo_collector
            self.slo_collector = get_slo_collector()
        except ImportError:
            self.slo_collector = None
    
    def process_request(self, api_request: APIRequest, endpoint_security: SecurityLevel) -> Dict[str, Any]:
        """Process and validate incoming request"""
        
        start_time = time.time()
        
        try:
            # Step 1: Basic security checks
            security_result = self._perform_security_checks(api_request)
            if not security_result['passed']:
                return self._create_error_response(
                    'security_check_failed',
                    security_result['reason'],
                    403
                )
            
            # Step 2: Authentication
            auth_result = self.validator.validate_authentication(api_request)
            
            # Check if authentication level is sufficient
            required_level = endpoint_security
            actual_level = auth_result.get('security_level', SecurityLevel.PUBLIC)
            
            if not self._check_security_level(actual_level, required_level):
                return self._create_error_response(
                    'insufficient_permissions',
                    f"Endpoint requires {required_level.value} access",
                    403
                )
            
            # Step 3: Rate limiting
            user_id = auth_result.get('user_id', api_request.ip_address)
            rate_limit_result = self.validator.rate_limiter.check_rate_limit(
                user_id, api_request.ip_address, actual_level
            )
            
            if not rate_limit_result['allowed']:
                return self._create_error_response(
                    'rate_limit_exceeded',
                    rate_limit_result['reason'],
                    429,
                    {'retry_after': rate_limit_result.get('retry_after', 60)}
                )
            
            # Step 4: Request validation (if POST/PUT)
            validation_result = None
            if api_request.method in ['POST', 'PUT'] and api_request.body_data:
                if '/orders' in api_request.endpoint:
                    validation_result = self.validator.validate_order_request(api_request.body_data)
                    
                    if not validation_result.is_valid:
                        return self._create_error_response(
                            'validation_failed',
                            ', '.join(validation_result.errors),
                            400
                        )
            
            # Record successful security processing
            processing_time = (time.time() - start_time) * 1000
            
            if self.slo_collector:
                self.slo_collector.update_system_health(
                    component="api_security",
                    health_score=100.0
                )
            
            return {
                'success': True,
                'user_id': auth_result.get('user_id'),
                'security_level': actual_level,
                'rate_limit': rate_limit_result,
                'validation_result': validation_result,
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Security middleware error: {str(e)}")
            
            if self.slo_collector:
                self.slo_collector.update_system_health(
                    component="api_security",
                    health_score=25.0
                )
            
            return self._create_error_response(
                'internal_security_error',
                'Internal security processing error',
                500
            )
    
    def _perform_security_checks(self, request: APIRequest) -> Dict[str, Any]:
        """Perform basic security checks"""
        
        # Check for suspicious patterns in URL
        suspicious_patterns = [
            r'\.\./|\.\.\/',  # Path traversal
            r'<script|javascript:|data:',  # XSS attempts
            r'union|select|insert|drop',  # SQL injection
            r'system\(|exec\(|eval\(',  # Code injection
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, request.endpoint, re.IGNORECASE):
                self._record_suspicious_activity(request, f"Suspicious URL pattern: {pattern}")
                return {'passed': False, 'reason': 'suspicious_request_pattern'}
        
        # Check request size
        if len(json.dumps(request.body_data)) > 1024 * 1024:  # 1MB limit
            return {'passed': False, 'reason': 'request_too_large'}
        
        # Check user agent
        if not request.user_agent or len(request.user_agent) < 10:
            return {'passed': False, 'reason': 'invalid_user_agent'}
        
        return {'passed': True}
    
    def _check_security_level(self, actual: SecurityLevel, required: SecurityLevel) -> bool:
        """Check if actual security level meets requirement"""
        
        level_hierarchy = {
            SecurityLevel.PUBLIC: 0,
            SecurityLevel.AUTHENTICATED: 1,
            SecurityLevel.INTERNAL: 2,
            SecurityLevel.ADMIN: 3
        }
        
        return level_hierarchy.get(actual, 0) >= level_hierarchy.get(required, 0)
    
    def _record_suspicious_activity(self, request: APIRequest, reason: str):
        """Record suspicious activity for monitoring"""
        
        self.logger.warning(f"Suspicious activity from {request.ip_address}: {reason}")
        
        if request.ip_address not in self.suspicious_activity:
            self.suspicious_activity[request.ip_address] = []
        
        self.suspicious_activity[request.ip_address].append({
            'timestamp': request.timestamp,
            'reason': reason,
            'endpoint': request.endpoint,
            'user_agent': request.user_agent
        })
        
        # Auto-block after 5 suspicious requests in 10 minutes
        recent_activity = [
            activity for activity in self.suspicious_activity[request.ip_address]
            if activity['timestamp'] > datetime.now() - timedelta(minutes=10)
        ]
        
        if len(recent_activity) >= 5:
            self.validator.rate_limiter.blocked_ips[request.ip_address] = time.time() + 3600  # Block for 1 hour
            self.logger.error(f"Auto-blocked IP {request.ip_address} due to suspicious activity")
    
    def _create_error_response(self, error_code: str, message: str, status_code: int, 
                              headers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create standardized error response"""
        
        return {
            'success': False,
            'error': {
                'code': error_code,
                'message': message,
                'timestamp': datetime.now().isoformat()
            },
            'status_code': status_code,
            'headers': headers or {}
        }

# Decorator for API endpoint protection
def secure_endpoint(security_level: SecurityLevel = SecurityLevel.AUTHENTICATED):
    """Decorator to add security middleware to API endpoints"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request information (this would be framework-specific)
            # For demonstration, we'll create a mock request
            
            api_request = APIRequest(
                endpoint=kwargs.get('endpoint', '/api/orders'),
                method=kwargs.get('method', 'POST'),
                user_id=kwargs.get('user_id'),
                session_id=kwargs.get('session_id'),
                ip_address=kwargs.get('ip_address', '127.0.0.1'),
                user_agent=kwargs.get('user_agent', 'TradingPlatform/1.0'),
                timestamp=datetime.now(),
                headers=kwargs.get('headers', {}),
                body_data=kwargs.get('body_data', {})
            )
            
            # Process security
            security_middleware = SecurityMiddleware()
            security_result = security_middleware.process_request(api_request, security_level)
            
            if not security_result['success']:
                return security_result
            
            # Add security context to kwargs
            kwargs['security_context'] = security_result
            
            # Call original function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# Global security middleware instance
_security_middleware = None

def get_security_middleware() -> SecurityMiddleware:
    """Get global security middleware instance"""
    global _security_middleware
    if _security_middleware is None:
        _security_middleware = SecurityMiddleware()
    return _security_middleware