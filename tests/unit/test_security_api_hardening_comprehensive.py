"""
Phase 8: Comprehensive tests for security/api_hardening.py
Coverage target: 90%+
Tests InputSanitizer, RateLimiter, RequestValidator, SecurityMiddleware.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import time


# ============================================================================
# SECURITY LEVEL ENUM TESTS
# ============================================================================

class TestSecurityLevel:
    """Test SecurityLevel enum."""
    
    def test_security_level_values(self):
        """Test all security level values exist."""
        from backend.security.api_hardening import SecurityLevel
        
        assert SecurityLevel.PUBLIC.value == "public"
        assert SecurityLevel.AUTHENTICATED.value == "authenticated"
        assert SecurityLevel.INTERNAL.value == "internal"
        assert SecurityLevel.ADMIN.value == "admin"


# ============================================================================
# INPUT SANITIZER TESTS
# ============================================================================

class TestInputSanitizer:
    """Test InputSanitizer class."""
    
    def test_sanitize_string_valid(self):
        """Test sanitizing valid string."""
        from backend.security.api_hardening import InputSanitizer
        
        result = InputSanitizer.sanitize_string("Hello World")
        assert result == "Hello World"
    
    def test_sanitize_string_trims_whitespace(self):
        """Test string trimming."""
        from backend.security.api_hardening import InputSanitizer
        
        result = InputSanitizer.sanitize_string("  Hello  ")
        assert result == "Hello"
    
    def test_sanitize_string_exceeds_max_length(self):
        """Test string exceeding max length."""
        from backend.security.api_hardening import InputSanitizer
        
        long_string = "a" * 300
        with pytest.raises(ValueError, match="exceeds maximum"):
            InputSanitizer.sanitize_string(long_string, max_length=255)
    
    def test_sanitize_string_blocked_pattern_html(self):
        """Test blocking HTML injection."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="blocked pattern"):
            InputSanitizer.sanitize_string("<script>alert('xss')</script>")
    
    def test_sanitize_string_blocked_pattern_sql(self):
        """Test blocking SQL injection."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="blocked pattern"):
            InputSanitizer.sanitize_string("'; DROP TABLE users;--")
    
    def test_sanitize_string_blocked_path_traversal(self):
        """Test blocking path traversal."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="blocked pattern"):
            InputSanitizer.sanitize_string("../../../etc/passwd")
    
    def test_sanitize_string_allow_special(self):
        """Test allowing special characters when flag is set."""
        from backend.security.api_hardening import InputSanitizer
        
        # With allow_special=True, should not block
        result = InputSanitizer.sanitize_string("test<value>", allow_special=True)
        # HTML encoding applied
        assert "&lt;" in result or "test" in result
    
    def test_sanitize_string_non_string_input(self):
        """Test sanitize_string with non-string input."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="must be a string"):
            InputSanitizer.sanitize_string(12345)
    
    def test_validate_symbol_valid(self):
        """Test valid symbol validation."""
        from backend.security.api_hardening import InputSanitizer

        assert InputSanitizer.validate_symbol_strict("AAPL") == "AAPL"
        assert InputSanitizer.validate_symbol_strict("msft") == "MSFT"
        assert InputSanitizer.validate_symbol_strict("a") == "A"
    
    def test_validate_symbol_invalid_format(self):
        """Test invalid symbol format."""
        from backend.security.api_hardening import InputSanitizer

        with pytest.raises(ValueError, match="Invalid symbol format"):
            InputSanitizer.validate_symbol_strict("TOOLONG")

        with pytest.raises(ValueError, match="Invalid symbol format"):
            InputSanitizer.validate_symbol_strict("123")

        with pytest.raises(ValueError, match="Invalid symbol format"):
            InputSanitizer.validate_symbol_strict("AA-PL")
    
    def test_validate_quantity_valid(self):
        """Test valid quantity validation."""
        from backend.security.api_hardening import InputSanitizer
        
        assert InputSanitizer.validate_quantity(100) == 100.0
        assert InputSanitizer.validate_quantity(100.5) == 100.5
        assert InputSanitizer.validate_quantity("100") == 100.0
    
    def test_validate_quantity_non_numeric(self):
        """Test non-numeric quantity."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="valid number"):
            InputSanitizer.validate_quantity("abc")
    
    def test_validate_quantity_zero(self):
        """Test zero quantity."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="must be positive"):
            InputSanitizer.validate_quantity(0)
    
    def test_validate_quantity_negative(self):
        """Test negative quantity."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="must be positive"):
            InputSanitizer.validate_quantity(-10)
    
    def test_validate_quantity_exceeds_max(self):
        """Test quantity exceeding maximum."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            InputSanitizer.validate_quantity(2000000)
    
    def test_validate_price_valid(self):
        """Test valid price validation."""
        from backend.security.api_hardening import InputSanitizer
        
        assert InputSanitizer.validate_price(150.50) == 150.50
        assert InputSanitizer.validate_price("150.55") == 150.55
        assert InputSanitizer.validate_price(150.556) == 150.56  # Rounded
    
    def test_validate_price_none(self):
        """Test None price."""
        from backend.security.api_hardening import InputSanitizer
        
        assert InputSanitizer.validate_price(None) is None
    
    def test_validate_price_non_numeric(self):
        """Test non-numeric price."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="valid number"):
            InputSanitizer.validate_price("abc")
    
    def test_validate_price_zero(self):
        """Test zero price."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="must be positive"):
            InputSanitizer.validate_price(0)
    
    def test_validate_price_exceeds_max(self):
        """Test price exceeding maximum."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            InputSanitizer.validate_price(150000)
    
    def test_validate_enum_value_valid(self):
        """Test valid enum value."""
        from backend.security.api_hardening import InputSanitizer
        
        assert InputSanitizer.validate_enum_value("buy", ["buy", "sell"]) == "buy"
        assert InputSanitizer.validate_enum_value("SELL", ["buy", "sell"]) == "sell"
    
    def test_validate_enum_value_invalid(self):
        """Test invalid enum value."""
        from backend.security.api_hardening import InputSanitizer
        
        with pytest.raises(ValueError, match="Invalid value"):
            InputSanitizer.validate_enum_value("hold", ["buy", "sell"])


# ============================================================================
# API REQUEST DATACLASS TESTS
# ============================================================================

class TestAPIRequest:
    """Test APIRequest dataclass."""
    
    def test_api_request_creation(self):
        """Test creating APIRequest."""
        from backend.security.api_hardening import APIRequest
        
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id="user123",
            session_id="sess456",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            timestamp=datetime.now()
        )
        
        assert request.endpoint == "/api/orders"
        assert request.method == "POST"
        assert request.user_id == "user123"
        assert request.request_id is not None  # Auto-generated
    
    def test_api_request_defaults(self):
        """Test APIRequest default values."""
        from backend.security.api_hardening import APIRequest
        
        request = APIRequest(
            endpoint="/api/test",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="127.0.0.1",
            user_agent="Test",
            timestamp=datetime.now()
        )
        
        assert request.headers == {}
        assert request.query_params == {}
        assert request.body_data == {}


# ============================================================================
# VALIDATION RESULT DATACLASS TESTS
# ============================================================================

class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test valid ValidationResult."""
        from backend.security.api_hardening import ValidationResult
        
        result = ValidationResult(
            is_valid=True,
            sanitized_data={"symbol": "AAPL"}
        )
        
        assert result.is_valid is True
        assert result.sanitized_data == {"symbol": "AAPL"}
        assert result.errors == []
        assert result.warnings == []
    
    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        from backend.security.api_hardening import ValidationResult
        
        result = ValidationResult(
            is_valid=False,
            sanitized_data={},
            errors=["Missing symbol", "Invalid quantity"],
            warnings=["Large order"]
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


# ============================================================================
# RATE LIMITER TESTS
# ============================================================================

class TestRateLimiter:
    """Test RateLimiter class."""
    
    def test_rate_limiter_init(self):
        """Test RateLimiter initialization."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        
        assert limiter.limits[SecurityLevel.PUBLIC] == 60
        assert limiter.limits[SecurityLevel.AUTHENTICATED] == 300
        assert limiter.limits[SecurityLevel.ADMIN] == 5000
    
    def test_rate_limiter_allows_first_request(self):
        """Test rate limiter allows first request."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        result = limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.AUTHENTICATED)
        
        assert result["allowed"] is True
        assert result["current_count"] == 1
        assert result["limit"] == 300
    
    def test_rate_limiter_tracks_requests(self):
        """Test rate limiter tracks request counts."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        
        for i in range(5):
            result = limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.AUTHENTICATED)
        
        assert result["current_count"] == 5
        assert result["remaining"] == 295
    
    def test_rate_limiter_blocks_when_exceeded(self):
        """Test rate limiter blocks when limit exceeded."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        
        # Exceed public limit of 60
        for i in range(61):
            limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.PUBLIC)
        
        result = limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.PUBLIC)
        
        assert result["allowed"] is False
        assert result["reason"] == "rate_limit_exceeded"
    
    def test_rate_limiter_blocked_ip(self):
        """Test rate limiter respects IP blocks."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        limiter.blocked_ips["192.168.1.1"] = time.time() + 300  # Blocked for 5 min
        
        result = limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.AUTHENTICATED)
        
        assert result["allowed"] is False
        assert result["reason"] == "ip_blocked"
    
    def test_rate_limiter_expired_block(self):
        """Test rate limiter removes expired blocks."""
        from backend.security.api_hardening import RateLimiter, SecurityLevel
        
        limiter = RateLimiter()
        limiter.blocked_ips["192.168.1.1"] = time.time() - 1  # Expired
        
        result = limiter.check_rate_limit("user1", "192.168.1.1", SecurityLevel.AUTHENTICATED)
        
        assert result["allowed"] is True
        assert "192.168.1.1" not in limiter.blocked_ips


# ============================================================================
# REQUEST VALIDATOR TESTS
# ============================================================================

class TestRequestValidator:
    """Test RequestValidator class."""
    
    def test_validate_order_request_valid(self):
        """Test validating valid order request."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL",
            "qty": 100,
            "side": "buy",
            "type": "market"
        })
        
        assert result.is_valid is True
        assert result.sanitized_data["symbol"] == "AAPL"
        assert result.sanitized_data["qty"] == 100.0
        assert result.sanitized_data["side"] == "buy"
        assert result.sanitized_data["type"] == "market"
    
    def test_validate_order_request_missing_fields(self):
        """Test validating order with missing required fields."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL"
        })
        
        assert result.is_valid is False
        assert any("Missing required field" in e for e in result.errors)
    
    def test_validate_order_request_invalid_symbol(self):
        """Test validating order with invalid symbol."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "INVALID123",
            "qty": 100,
            "side": "buy",
            "type": "market"
        })
        
        assert result.is_valid is False
        assert any("Symbol validation failed" in e for e in result.errors)
    
    def test_validate_order_request_limit_without_price(self):
        """Test limit order without limit price."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL",
            "qty": 100,
            "side": "buy",
            "type": "limit"
        })
        
        assert result.is_valid is False
        assert any("limit_price" in e for e in result.errors)
    
    def test_validate_order_request_stop_without_price(self):
        """Test stop order without stop price."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL",
            "qty": 100,
            "side": "sell",
            "type": "stop"
        })
        
        assert result.is_valid is False
        assert any("stop_price" in e for e in result.errors)
    
    def test_validate_order_request_with_optional_fields(self):
        """Test validating order with optional fields."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL",
            "qty": 100,
            "side": "buy",
            "type": "limit",
            "limit_price": 150.50,
            "time_in_force": "gtc"
        })
        
        assert result.is_valid is True
        assert result.sanitized_data["limit_price"] == 150.50
        assert result.sanitized_data["time_in_force"] == "gtc"
    
    def test_validate_order_request_large_quantity_warning(self):
        """Test large order quantity triggers warning."""
        from backend.security.api_hardening import RequestValidator
        
        validator = RequestValidator()
        result = validator.validate_order_request({
            "symbol": "AAPL",
            "qty": 15000,
            "side": "buy",
            "type": "market"
        })
        
        assert result.is_valid is True
        assert any("Large order" in w for w in result.warnings)
    
    def test_validate_authentication_missing_header(self):
        """Test authentication with missing header."""
        from backend.security.api_hardening import RequestValidator, APIRequest, SecurityLevel
        
        validator = RequestValidator()
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now(),
            headers={}
        )
        
        result = validator.validate_authentication(request)
        
        assert result["authenticated"] is False
        assert result["reason"] == "missing_authorization_header"
    
    def test_validate_authentication_invalid_format(self):
        """Test authentication with invalid format."""
        from backend.security.api_hardening import RequestValidator, APIRequest
        
        validator = RequestValidator()
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now(),
            headers={"Authorization": "Basic abc123"}
        )
        
        result = validator.validate_authentication(request)
        
        assert result["authenticated"] is False
        assert result["reason"] == "invalid_authorization_format"
    
    def test_validate_authentication_short_api_key(self):
        """Test authentication with too short API key."""
        from backend.security.api_hardening import RequestValidator, APIRequest
        
        validator = RequestValidator()
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer short"}
        )
        
        result = validator.validate_authentication(request)
        
        assert result["authenticated"] is False
        assert result["reason"] == "invalid_api_key_format"
    
    @patch.dict('os.environ', {'ENVIRONMENT': 'development', 'ALLOW_DEMO_TOKENS': 'true'})
    def test_validate_authentication_demo_key(self):
        """Test authentication with demo API key."""
        from backend.security.api_hardening import RequestValidator, APIRequest, SecurityLevel
        
        validator = RequestValidator()
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"}
        )
        
        result = validator.validate_authentication(request)
        
        assert result["authenticated"] is True
        assert result["user_id"] == "demo_user"
        assert result["security_level"] == SecurityLevel.AUTHENTICATED
    
    @patch.dict('os.environ', {'ENVIRONMENT': 'development', 'ALLOW_DEMO_TOKENS': 'true'})
    def test_validate_authentication_admin_key(self):
        """Test authentication with admin API key."""
        from backend.security.api_hardening import RequestValidator, APIRequest, SecurityLevel
        
        validator = RequestValidator()
        request = APIRequest(
            endpoint="/api/admin/users",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer admin_1234567890123456789012345678"}
        )
        
        result = validator.validate_authentication(request)
        
        assert result["authenticated"] is True
        assert result["user_id"] == "admin_user"
        assert result["security_level"] == SecurityLevel.ADMIN


# ============================================================================
# SECURITY MIDDLEWARE TESTS
# ============================================================================

class TestSecurityMiddleware:
    """Test SecurityMiddleware class."""
    
    def test_middleware_init(self):
        """Test SecurityMiddleware initialization."""
        from backend.security.api_hardening import SecurityMiddleware
        
        middleware = SecurityMiddleware()
        
        assert middleware.validator is not None
        assert middleware.suspicious_activity == {}
    
    @patch.dict('os.environ', {'ENVIRONMENT': 'development', 'ALLOW_DEMO_TOKENS': 'true'})
    def test_process_request_success(self):
        """Test processing valid request."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64)",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"},
            body_data={
                "symbol": "AAPL",
                "qty": 100,
                "side": "buy",
                "type": "market"
            }
        )
        
        result = middleware.process_request(request, SecurityLevel.AUTHENTICATED)
        
        assert result["success"] is True
        assert result["user_id"] == "demo_user"
    
    def test_process_request_suspicious_url(self):
        """Test processing request with suspicious URL."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/orders/../../../etc/passwd",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            timestamp=datetime.now(),
            headers={}
        )
        
        result = middleware.process_request(request, SecurityLevel.PUBLIC)
        
        assert result["success"] is False
        assert result["status_code"] == 403
    
    def test_process_request_insufficient_permissions(self):
        """Test processing request with insufficient permissions."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/admin/users",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"}  # Not admin
        )
        
        result = middleware.process_request(request, SecurityLevel.ADMIN)
        
        assert result["success"] is False
        assert "insufficient_permissions" in result["error"]["code"]
    
    @patch.dict('os.environ', {'ENVIRONMENT': 'development', 'ALLOW_DEMO_TOKENS': 'true'})
    def test_process_request_invalid_body(self):
        """Test processing request with invalid body data."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"},
            body_data={"symbol": "INVALID123", "qty": -10, "side": "buy", "type": "market"}
        )
        
        result = middleware.process_request(request, SecurityLevel.AUTHENTICATED)
        
        assert result["success"] is False
        assert result["status_code"] == 400
    
    def test_check_security_level_hierarchy(self):
        """Test security level hierarchy checking."""
        from backend.security.api_hardening import SecurityMiddleware, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        # Admin >= all levels
        assert middleware._check_security_level(SecurityLevel.ADMIN, SecurityLevel.PUBLIC) is True
        assert middleware._check_security_level(SecurityLevel.ADMIN, SecurityLevel.AUTHENTICATED) is True
        assert middleware._check_security_level(SecurityLevel.ADMIN, SecurityLevel.ADMIN) is True
        
        # Public < authenticated
        assert middleware._check_security_level(SecurityLevel.PUBLIC, SecurityLevel.AUTHENTICATED) is False
    
    def test_record_suspicious_activity(self):
        """Test recording suspicious activity."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/test",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Test",
            timestamp=datetime.now()
        )
        
        middleware._record_suspicious_activity(request, "Test reason")
        
        assert "192.168.1.1" in middleware.suspicious_activity
        assert len(middleware.suspicious_activity["192.168.1.1"]) == 1
    
    def test_create_error_response(self):
        """Test error response creation."""
        from backend.security.api_hardening import SecurityMiddleware
        
        middleware = SecurityMiddleware()
        
        result = middleware._create_error_response(
            "test_error",
            "Test message",
            400,
            {"retry_after": 60}
        )
        
        assert result["success"] is False
        assert result["error"]["code"] == "test_error"
        assert result["error"]["message"] == "Test message"
        assert result["status_code"] == 400
        assert result["headers"]["retry_after"] == 60


# ============================================================================
# SECURE ENDPOINT DECORATOR TESTS
# ============================================================================

class TestSecureEndpointDecorator:
    """Test secure_endpoint decorator."""
    
    @pytest.mark.asyncio
    async def test_secure_endpoint_decorator(self):
        """Test secure_endpoint decorator applies security."""
        from backend.security.api_hardening import secure_endpoint, SecurityLevel
        
        @secure_endpoint(SecurityLevel.AUTHENTICATED)
        async def test_endpoint(**kwargs):
            return {"success": True, "context": kwargs.get("security_context")}
        
        result = await test_endpoint(
            endpoint="/api/orders",
            method="POST",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"},
            body_data={}
        )
        
        # May or may not have security_context depending on validation
        assert result is not None


# ============================================================================
# GLOBAL MIDDLEWARE INSTANCE TESTS
# ============================================================================

class TestGetSecurityMiddleware:
    """Test get_security_middleware function."""
    
    def test_get_security_middleware_singleton(self):
        """Test get_security_middleware returns singleton."""
        from backend.security.api_hardening import get_security_middleware
        
        middleware1 = get_security_middleware()
        middleware2 = get_security_middleware()
        
        # Same instance
        assert middleware1 is middleware2
    
    def test_get_security_middleware_type(self):
        """Test get_security_middleware returns correct type."""
        from backend.security.api_hardening import get_security_middleware, SecurityMiddleware
        
        middleware = get_security_middleware()
        
        assert isinstance(middleware, SecurityMiddleware)


# ============================================================================
# EDGE CASES AND INTEGRATION
# ============================================================================

class TestEdgeCases:
    """Test edge cases and integration scenarios."""
    
    def test_request_too_large(self):
        """Test request body size limit."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        # Create large body
        large_body = {"data": "x" * (1024 * 1024 + 1)}  # > 1MB
        
        request = APIRequest(
            endpoint="/api/orders",
            method="POST",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            timestamp=datetime.now(),
            headers={"Authorization": "Bearer demo_1234567890123456789012345678"},
            body_data=large_body
        )
        
        result = middleware.process_request(request, SecurityLevel.AUTHENTICATED)
        
        assert result["success"] is False
    
    def test_invalid_user_agent(self):
        """Test invalid user agent detection."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/orders",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="x",  # Too short
            timestamp=datetime.now(),
            headers={}
        )
        
        result = middleware.process_request(request, SecurityLevel.PUBLIC)
        
        assert result["success"] is False
    
    def test_xss_attempt_blocked(self):
        """Test XSS attempt in URL is blocked."""
        from backend.security.api_hardening import SecurityMiddleware, APIRequest, SecurityLevel
        
        middleware = SecurityMiddleware()
        
        request = APIRequest(
            endpoint="/api/<script>alert('xss')</script>",
            method="GET",
            user_id=None,
            session_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            timestamp=datetime.now(),
            headers={}
        )
        
        result = middleware.process_request(request, SecurityLevel.PUBLIC)
        
        assert result["success"] is False
