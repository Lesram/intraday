"""
Comprehensive tests for backend.api.errors and backend.infra.alerting modules

Tests error handling classes and alerting infrastructure.
Target: 0% → 85%+ coverage for:
- backend/api/errors.py (376 lines)
- backend/infra/alerting.py (516 lines)
"""

import pytest
from fastapi import status

from backend.api.errors import (
    ErrorCodes,
    APIError,
    RiskError,
)


class TestErrorCodes:
    """Test ErrorCodes constants"""
    
    def test_error_codes_auth(self):
        """Test authentication error codes exist"""
        assert ErrorCodes.UNAUTHORIZED == "UNAUTHORIZED"
        assert ErrorCodes.FORBIDDEN == "FORBIDDEN"
        assert ErrorCodes.TOKEN_EXPIRED == "TOKEN_EXPIRED"
        assert ErrorCodes.INVALID_CREDENTIALS == "INVALID_CREDENTIALS"
    
    def test_error_codes_validation(self):
        """Test validation error codes exist"""
        assert ErrorCodes.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCodes.INVALID_INPUT == "INVALID_INPUT"
        assert ErrorCodes.MISSING_FIELD == "MISSING_FIELD"
        assert ErrorCodes.INVALID_FORMAT == "INVALID_FORMAT"
    
    def test_error_codes_business_logic(self):
        """Test business logic error codes exist"""
        assert ErrorCodes.INSUFFICIENT_FUNDS == "INSUFFICIENT_FUNDS"
        assert ErrorCodes.RISK_LIMIT_EXCEEDED == "RISK_LIMIT_EXCEEDED"
        assert ErrorCodes.ORDER_NOT_FOUND == "ORDER_NOT_FOUND"
        assert ErrorCodes.DUPLICATE_ORDER == "DUPLICATE_ORDER"
        assert ErrorCodes.MARKET_CLOSED == "MARKET_CLOSED"
        assert ErrorCodes.INVALID_SYMBOL == "INVALID_SYMBOL"
    
    def test_error_codes_system(self):
        """Test system error codes exist"""
        assert ErrorCodes.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert ErrorCodes.SERVICE_UNAVAILABLE == "SERVICE_UNAVAILABLE"
        assert ErrorCodes.DATABASE_ERROR == "DATABASE_ERROR"
        assert ErrorCodes.TIMEOUT_ERROR == "TIMEOUT_ERROR"
        assert ErrorCodes.RATE_LIMITED == "RATE_LIMITED"


class TestAPIError:
    """Test APIError class"""
    
    def test_api_error_basic(self):
        """Test basic API error creation"""
        error = APIError(
            code="TEST_ERROR",
            message="Test error message"
        )
        
        assert error.code == "TEST_ERROR"
        assert error.message == "Test error message"
        assert error.status_code == status.HTTP_400_BAD_REQUEST  # Default
        assert error.field is None
        assert error.context == {}
    
    def test_api_error_with_status_code(self):
        """Test API error with custom status code"""
        error = APIError(
            code="NOT_FOUND",
            message="Resource not found",
            status_code=status.HTTP_404_NOT_FOUND
        )
        
        assert error.status_code == 404
    
    def test_api_error_with_field(self):
        """Test API error with field reference"""
        error = APIError(
            code="INVALID_FIELD",
            message="Invalid quantity",
            field="quantity"
        )
        
        assert error.field == "quantity"
    
    def test_api_error_with_context(self):
        """Test API error with additional context"""
        context = {"user_id": 123, "symbol": "AAPL"}
        error = APIError(
            code="CONTEXT_ERROR",
            message="Error with context",
            context=context
        )
        
        assert error.context == context
        assert error.context["user_id"] == 123
    
    def test_api_error_inherits_exception(self):
        """Test API error inherits from Exception"""
        error = APIError("CODE", "Message")
        assert isinstance(error, Exception)
    
    def test_api_error_str_representation(self):
        """Test API error string representation"""
        error = APIError("TEST", "Test message")
        error_str = str(error)
        assert "Test message" in error_str


class TestRiskError:
    """Test RiskError class"""
    
    def test_risk_error_basic(self):
        """Test basic risk error creation"""
        error = RiskError(message="Risk limit exceeded")
        
        assert error.code == ErrorCodes.RISK_LIMIT_EXCEEDED
        assert error.message == "Risk limit exceeded"
        assert error.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    
    def test_risk_error_with_issues(self):
        """Test risk error with issues list"""
        issues = ["Position size too large", "Leverage exceeded"]
        error = RiskError(
            message="Multiple risk violations",
            issues=issues
        )
        
        assert error.context["issues"] == issues
        assert len(error.context["issues"]) == 2
    
    def test_risk_error_with_warnings(self):
        """Test risk error with warnings list"""
        warnings = ["Approaching daily loss limit", "High volatility"]
        error = RiskError(
            message="Risk warnings",
            warnings=warnings
        )
        
        assert error.context["warnings"] == warnings
    
    def test_risk_error_with_risk_score(self):
        """Test risk error with risk score"""
        error = RiskError(
            message="High risk",
            risk_score=8.5
        )
        
        assert error.context["risk_score"] == 8.5
    
    def test_risk_error_with_all_fields(self):
        """Test risk error with all optional fields"""
        error = RiskError(
            message="Comprehensive risk error",
            issues=["Issue 1", "Issue 2"],
            warnings=["Warning 1"],
            risk_score=9.2,
            context={"user_id": 456}
        )
        
        assert error.context["issues"] == ["Issue 1", "Issue 2"]
        assert error.context["warnings"] == ["Warning 1"]
        assert error.context["risk_score"] == 9.2
        assert error.context["user_id"] == 456
    
    def test_risk_error_empty_issues_warnings(self):
        """Test risk error with no issues/warnings defaults to empty lists"""
        error = RiskError(message="Test")
        
        assert error.context["issues"] == []
        assert error.context["warnings"] == []
        assert error.context["risk_score"] is None


# ============================================================================
# ALERTING TESTS
# ============================================================================

from backend.infra.alerting import (
    AlertSeverity,
    AlertCategory,
    AlertConfig,
    AlertDeduplicator,
    AlertRateLimiter,
)


class TestAlertSeverity:
    """Test AlertSeverity enum"""
    
    def test_alert_severity_values(self):
        """Test all severity levels exist"""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.ERROR.value == "error"
        assert AlertSeverity.CRITICAL.value == "critical"
    
    def test_alert_severity_enum_members(self):
        """Test severity enum has expected members"""
        severities = [s.name for s in AlertSeverity]
        assert "INFO" in severities
        assert "WARNING" in severities
        assert "ERROR" in severities
        assert "CRITICAL" in severities


class TestAlertCategory:
    """Test AlertCategory enum"""
    
    def test_alert_category_values(self):
        """Test all category values exist"""
        assert AlertCategory.RISK_VIOLATION.value == "risk_violation"
        assert AlertCategory.ORDER_FAILURE.value == "order_failure"
        assert AlertCategory.SYSTEM_ERROR.value == "system_error"
        assert AlertCategory.CONNECTIVITY.value == "connectivity"
        assert AlertCategory.PERFORMANCE.value == "performance"
        assert AlertCategory.SECURITY.value == "security"
    
    def test_alert_category_enum_members(self):
        """Test category enum has expected members"""
        categories = [c.name for c in AlertCategory]
        assert "RISK_VIOLATION" in categories
        assert "ORDER_FAILURE" in categories
        assert "SYSTEM_ERROR" in categories


class TestAlertConfig:
    """Test AlertConfig class"""
    
    def test_alert_config_defaults(self):
        """Test alert config with default values"""
        config = AlertConfig()
        
        assert config.slack_webhook_url is None
        assert config.pagerduty_routing_key is None
        assert config.environment == "development"
        assert config.dedup_window_seconds == 300
        assert config.rate_limit_per_minute == 30
    
    def test_alert_config_with_values(self):
        """Test alert config with custom values"""
        config = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
            pagerduty_routing_key="pd_key_123",
            environment="production",
            dedup_window_seconds=600,
            rate_limit_per_minute=60
        )
        
        assert config.slack_webhook_url == "https://hooks.slack.com/test"
        assert config.pagerduty_routing_key == "pd_key_123"
        assert config.environment == "production"
        assert config.dedup_window_seconds == 600
        assert config.rate_limit_per_minute == 60


class TestAlertDeduplicator:
    """Test AlertDeduplicator class"""
    
    @pytest.mark.asyncio
    async def test_deduplicator_allows_first_alert(self):
        """Test deduplicator allows first occurrence of alert"""
        dedup = AlertDeduplicator(window_seconds=300)
        
        should_send = await dedup.should_send(
            AlertCategory.SYSTEM_ERROR,
            AlertSeverity.ERROR,
            "Test error"
        )
        
        assert should_send is True
    
    @pytest.mark.asyncio
    async def test_deduplicator_blocks_duplicate(self):
        """Test deduplicator blocks duplicate alert"""
        dedup = AlertDeduplicator(window_seconds=300)
        
        # First alert
        await dedup.should_send(
            AlertCategory.SYSTEM_ERROR,
            AlertSeverity.ERROR,
            "Test error"
        )
        
        # Duplicate alert
        should_send = await dedup.should_send(
            AlertCategory.SYSTEM_ERROR,
            AlertSeverity.ERROR,
            "Test error"
        )
        
        assert should_send is False
    
    @pytest.mark.asyncio
    async def test_deduplicator_allows_different_alerts(self):
        """Test deduplicator allows different alerts"""
        dedup = AlertDeduplicator(window_seconds=300)
        
        # First alert
        await dedup.should_send(
            AlertCategory.SYSTEM_ERROR,
            AlertSeverity.ERROR,
            "Error 1"
        )
        
        # Different alert
        should_send = await dedup.should_send(
            AlertCategory.SYSTEM_ERROR,
            AlertSeverity.ERROR,
            "Error 2"  # Different title
        )
        
        assert should_send is True
    
    @pytest.mark.asyncio
    async def test_deduplicator_hash_generation(self):
        """Test deduplicator generates hash keys"""
        dedup = AlertDeduplicator()
        
        hash1 = dedup._hash_alert(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.CRITICAL,
            "Test"
        )
        
        hash2 = dedup._hash_alert(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.CRITICAL,
            "Test"
        )
        
        # Same inputs should generate same hash
        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated to 16 chars


class TestAlertRateLimiter:
    """Test AlertRateLimiter class"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self):
        """Test rate limiter allows requests within limit"""
        limiter = AlertRateLimiter(max_per_minute=30)
        
        # Should allow first request
        allowed = await limiter.acquire()
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit"""
        limiter = AlertRateLimiter(max_per_minute=3)
        
        # Acquire 3 slots (at limit)
        for _ in range(3):
            await limiter.acquire()
        
        # 4th request should be blocked
        allowed = await limiter.acquire()
        assert allowed is False
    
    @pytest.mark.asyncio
    async def test_rate_limiter_tracks_timestamps(self):
        """Test rate limiter tracks request timestamps"""
        limiter = AlertRateLimiter(max_per_minute=10)
        
        # Make some requests
        await limiter.acquire()
        await limiter.acquire()
        
        # Should have 2 timestamps
        assert len(limiter._timestamps) == 2
    
    @pytest.mark.asyncio
    async def test_rate_limiter_different_limits(self):
        """Test rate limiters with different max rates"""
        limiter_low = AlertRateLimiter(max_per_minute=2)
        limiter_high = AlertRateLimiter(max_per_minute=100)
        
        # Low limiter should hit limit quickly
        await limiter_low.acquire()
        await limiter_low.acquire()
        assert await limiter_low.acquire() is False
        
        # High limiter should still allow
        assert await limiter_high.acquire() is True
