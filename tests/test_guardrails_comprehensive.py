"""
Comprehensive tests for backend.infra.guardrails

Tests trading guardrails including:
- Symbol whitelisting
- Daily limits (notional, order count)
- Trading window enforcement
- Kill switches
- Rate limiting
- Admin overrides
"""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest

from backend.infra.guardrails import (
    GuardrailCode,
    GuardrailResult,
    GuardrailViolation,
    OrderRequest,
    TradingGuardrails,
    get_guardrails,
    validate_order_guardrails,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def guardrails():
    """Create TradingGuardrails instance with test configuration."""
    with patch.dict('os.environ', {
        'SYMBOL_WHITELIST': 'AAPL,MSFT,GOOGL,TSLA',
        'DAILY_NOTIONAL_CAP_USD': '50000',
        'MAX_DAILY_ORDERS': '50',
        'MAX_ORDER_SIZE': '100',
        'TRADING_WINDOW_START': '00:00',
        'TRADING_WINDOW_END': '23:59',
        'TRADING_PAUSED': 'false',
        'MAX_ORDERS_PER_MINUTE': '20',
        'RISK_ALLOW_ADMIN_OVERRIDE': 'true',
    }):
        return TradingGuardrails()


@pytest.fixture
def valid_order():
    """Create a valid order request."""
    return OrderRequest(
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        order_type="market"
    )


@pytest.fixture
def admin_order():
    """Create an admin order request with override."""
    return OrderRequest(
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        order_type="market",
        user_id="admin_user",
        is_admin=True,
        risk_override=True
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestTradingGuardrailsInit:
    """Tests for TradingGuardrails initialization."""
    
    def test_init_loads_config(self, guardrails):
        """Test that init loads configuration."""
        assert 'AAPL' in guardrails.symbol_whitelist
        assert guardrails.daily_notional_cap_usd == Decimal('50000')
        assert guardrails.max_daily_orders == 50
        assert guardrails.max_order_size == Decimal('100')
        
    def test_init_sets_daily_stats(self, guardrails):
        """Test that init sets up daily stats."""
        assert guardrails._daily_stats['orders_count'] == 0
        assert guardrails._daily_stats['notional_usd'] == Decimal('0')
        
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        with patch.dict('os.environ', {}, clear=True):
            g = TradingGuardrails()
            assert 'SPY' in g.symbol_whitelist or 'AAPL' in g.symbol_whitelist


# ============================================================================
# EXCEPTION AND MODEL TESTS
# ============================================================================

class TestGuardrailViolation:
    """Tests for GuardrailViolation exception."""
    
    def test_violation_attributes(self):
        """Test violation has required attributes."""
        violation = GuardrailViolation(
            code="TEST_CODE",
            message="Test message",
            details={'key': 'value'}
        )
        
        assert violation.code == "TEST_CODE"
        assert violation.message == "Test message"
        assert violation.details == {'key': 'value'}
        assert str(violation) == "Test message"
        
    def test_violation_default_details(self):
        """Test violation with no details."""
        violation = GuardrailViolation(code="TEST", message="Test")
        assert violation.details == {}


class TestOrderRequest:
    """Tests for OrderRequest model."""
    
    def test_order_request_minimal(self):
        """Test order request with minimal fields."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            qty=Decimal("10")
        )
        
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.qty == Decimal("10")
        assert order.order_type == "market"
        assert order.is_admin is False
        
    def test_order_request_full(self):
        """Test order request with all fields."""
        order = OrderRequest(
            symbol="MSFT",
            side="sell",
            qty=Decimal("50"),
            order_type="limit",
            limit_price=Decimal("380.00"),
            user_id="user123",
            is_admin=True,
            risk_override=True
        )
        
        assert order.limit_price == Decimal("380.00")
        assert order.is_admin is True
        assert order.risk_override is True


class TestGuardrailResult:
    """Tests for GuardrailResult model."""
    
    def test_result_allowed(self):
        """Test allowed result."""
        result = GuardrailResult(
            allowed=True,
            violations=[],
            warnings=[],
            details={}
        )
        assert result.allowed is True


class TestGuardrailCode:
    """Tests for GuardrailCode enum."""
    
    def test_all_codes_exist(self):
        """Test all expected codes exist."""
        assert GuardrailCode.SYMBOL_NOT_ALLOWED.value == "SYMBOL_NOT_ALLOWED"
        assert GuardrailCode.DAILY_NOTIONAL_EXCEEDED.value == "DAILY_NOTIONAL_EXCEEDED"
        assert GuardrailCode.TRADING_PAUSED.value == "TRADING_PAUSED"
        assert GuardrailCode.RATE_LIMIT_EXCEEDED.value == "RATE_LIMIT_EXCEEDED"


# ============================================================================
# VALIDATE ORDER TESTS
# ============================================================================

class TestValidateOrder:
    """Tests for validate_order method."""
    
    @pytest.mark.asyncio
    async def test_valid_order_allowed(self, guardrails, valid_order):
        """Test valid order is allowed."""
        result = await guardrails.validate_order(valid_order)
        
        assert result.allowed is True
        assert len(result.violations) == 0
        
    @pytest.mark.asyncio
    async def test_invalid_symbol_rejected(self, guardrails):
        """Test order with invalid symbol is rejected."""
        order = OrderRequest(
            symbol="INVALID_SYMBOL",
            side="buy",
            qty=Decimal("10")
        )
        
        result = await guardrails.validate_order(order)
        
        assert result.allowed is False
        assert len(result.violations) == 1
        assert result.violations[0]['code'] == GuardrailCode.SYMBOL_NOT_ALLOWED
        
    @pytest.mark.asyncio
    async def test_admin_override_converts_violation_to_warning(self, guardrails):
        """Test admin override converts violation to warning."""
        order = OrderRequest(
            symbol="INVALID_SYMBOL",
            side="buy",
            qty=Decimal("10"),
            user_id="admin",
            is_admin=True,
            risk_override=True
        )
        
        result = await guardrails.validate_order(order)
        
        assert result.allowed is True
        assert len(result.violations) == 0
        assert len(result.warnings) == 1


# ============================================================================
# TRADING PAUSED TESTS
# ============================================================================

class TestCheckTradingPaused:
    """Tests for _check_trading_paused method."""
    
    def test_trading_not_paused(self, guardrails, valid_order):
        """Test no exception when trading not paused."""
        guardrails.trading_paused = False
        guardrails._check_trading_paused(valid_order)  # Should not raise
        
    def test_trading_paused_raises(self, guardrails, valid_order):
        """Test exception raised when trading paused."""
        guardrails.trading_paused = True
        
        with pytest.raises(GuardrailViolation) as exc_info:
            guardrails._check_trading_paused(valid_order)
            
        assert exc_info.value.code == GuardrailCode.TRADING_PAUSED


# ============================================================================
# TRADING WINDOW TESTS
# ============================================================================

class TestCheckTradingWindow:
    """Tests for _check_trading_window method."""
    
    def test_within_trading_window(self, guardrails, valid_order):
        """Test no exception when within trading window."""
        guardrails.trading_window_start = time(0, 0)
        guardrails.trading_window_end = time(23, 59)
        
        guardrails._check_trading_window(valid_order)  # Should not raise
        
    def test_outside_trading_window(self, guardrails, valid_order):
        """Test exception when outside trading window."""
        # Set window to a time in the past (will always be outside)
        guardrails.trading_window_start = time(0, 0)
        guardrails.trading_window_end = time(0, 1)
        
        now = datetime.now(UTC).time()
        if now > time(0, 1):
            with pytest.raises(GuardrailViolation) as exc_info:
                guardrails._check_trading_window(valid_order)
            assert exc_info.value.code == GuardrailCode.MARKET_CLOSED


# ============================================================================
# SYMBOL WHITELIST TESTS
# ============================================================================

class TestCheckSymbolWhitelist:
    """Tests for _check_symbol_whitelist method."""
    
    def test_symbol_in_whitelist(self, guardrails, valid_order):
        """Test no exception for whitelisted symbol."""
        guardrails._check_symbol_whitelist(valid_order)  # Should not raise
        
    def test_symbol_not_in_whitelist(self, guardrails):
        """Test exception for non-whitelisted symbol."""
        order = OrderRequest(
            symbol="NOT_WHITELISTED",
            side="buy",
            qty=Decimal("10")
        )
        
        with pytest.raises(GuardrailViolation) as exc_info:
            guardrails._check_symbol_whitelist(order)
            
        assert exc_info.value.code == GuardrailCode.SYMBOL_NOT_ALLOWED


# ============================================================================
# ORDER SIZE TESTS
# ============================================================================

class TestCheckOrderSizeLimits:
    """Tests for _check_order_size_limits method."""
    
    def test_order_within_size_limit(self, guardrails, valid_order):
        """Test no exception for order within size limit."""
        guardrails._check_order_size_limits(valid_order)  # Should not raise
        
    def test_order_exceeds_size_limit(self, guardrails):
        """Test exception for order exceeding size limit."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            qty=Decimal("1000")  # Exceeds default limit
        )
        
        with pytest.raises(GuardrailViolation) as exc_info:
            guardrails._check_order_size_limits(order)
            
        assert exc_info.value.code == GuardrailCode.ORDER_SIZE_EXCEEDED


# ============================================================================
# DAILY ORDER LIMIT TESTS
# ============================================================================

class TestCheckDailyOrderLimit:
    """Tests for _check_daily_order_limit method."""
    
    def test_within_daily_order_limit(self, guardrails, valid_order):
        """Test no exception when within daily limit."""
        guardrails._check_daily_order_limit(valid_order)  # Should not raise
        
    def test_exceeds_daily_order_limit(self, guardrails, valid_order):
        """Test exception when exceeding daily order limit."""
        guardrails._daily_stats['orders_count'] = guardrails.max_daily_orders
        
        with pytest.raises(GuardrailViolation) as exc_info:
            guardrails._check_daily_order_limit(valid_order)
            
        assert exc_info.value.code == GuardrailCode.DAILY_ORDER_LIMIT_EXCEEDED


# ============================================================================
# DAILY NOTIONAL LIMIT TESTS
# ============================================================================

class TestCheckDailyNotionalLimit:
    """Tests for _check_daily_notional_limit method."""
    
    @pytest.mark.asyncio
    async def test_within_daily_notional(self, guardrails, valid_order):
        """Test no exception when within daily notional."""
        await guardrails._check_daily_notional_limit(valid_order)  # Should not raise
        
    @pytest.mark.asyncio
    async def test_exceeds_daily_notional(self, guardrails):
        """Test exception when exceeding daily notional."""
        order = OrderRequest(
            symbol="AAPL",
            side="buy",
            qty=Decimal("1000")  # 1000 * $175 = $175,000 exceeds $50,000 limit
        )
        
        with pytest.raises(GuardrailViolation) as exc_info:
            await guardrails._check_daily_notional_limit(order)
            
        assert exc_info.value.code == GuardrailCode.DAILY_NOTIONAL_EXCEEDED


# ============================================================================
# RATE LIMIT TESTS
# ============================================================================

class TestCheckRateLimits:
    """Tests for _check_rate_limits method."""
    
    def test_within_rate_limit(self, guardrails, valid_order):
        """Test no exception when within rate limit."""
        guardrails._check_rate_limits(valid_order)  # Should not raise
        
    def test_exceeds_rate_limit(self, guardrails, valid_order):
        """Test exception when exceeding rate limit."""
        # Simulate max orders in current minute
        current_minute = datetime.now(UTC).replace(second=0, microsecond=0)
        user_key = valid_order.user_id or "anonymous"
        guardrails._rate_limits[user_key] = {
            current_minute: guardrails.max_orders_per_minute
        }
        
        with pytest.raises(GuardrailViolation) as exc_info:
            guardrails._check_rate_limits(valid_order)
            
        assert exc_info.value.code == GuardrailCode.RATE_LIMIT_EXCEEDED


# ============================================================================
# GET ESTIMATED PRICE TESTS
# ============================================================================

class TestGetEstimatedPrice:
    """Tests for _get_estimated_price method."""
    
    @pytest.mark.asyncio
    async def test_known_symbol_price(self, guardrails):
        """Test getting price for known symbol."""
        price = await guardrails._get_estimated_price("AAPL")
        assert price == Decimal("175.00")
        
    @pytest.mark.asyncio
    async def test_unknown_symbol_default_price(self, guardrails):
        """Test getting default price for unknown symbol."""
        price = await guardrails._get_estimated_price("UNKNOWN")
        assert price == Decimal("100.00")


# ============================================================================
# RECORD ORDER SUBMITTED TESTS
# ============================================================================

class TestRecordOrderSubmitted:
    """Tests for record_order_submitted method."""
    
    def test_record_increments_order_count(self, guardrails, valid_order):
        """Test recording order increments count."""
        initial_count = guardrails._daily_stats['orders_count']
        
        guardrails.record_order_submitted(valid_order)
        
        assert guardrails._daily_stats['orders_count'] == initial_count + 1
        
    def test_record_with_notional(self, guardrails, valid_order):
        """Test recording order with notional value."""
        notional = Decimal("1750.00")
        
        guardrails.record_order_submitted(valid_order, estimated_notional=notional)
        
        assert guardrails._daily_stats['notional_usd'] == notional
        
    def test_record_updates_rate_limits(self, guardrails, valid_order):
        """Test recording order updates rate limits."""
        valid_order.user_id = "test_user"
        
        guardrails.record_order_submitted(valid_order)
        
        assert "test_user" in guardrails._rate_limits


# ============================================================================
# GET CURRENT LIMITS TESTS
# ============================================================================

class TestGetCurrentLimits:
    """Tests for get_current_limits method."""
    
    def test_returns_all_limits(self, guardrails):
        """Test get_current_limits returns all expected fields."""
        limits = guardrails.get_current_limits()
        
        assert 'symbol_whitelist' in limits
        assert 'daily_limits' in limits
        assert 'order_limits' in limits
        assert 'trading_window' in limits
        assert 'status' in limits
        
    def test_returns_remaining_orders(self, guardrails):
        """Test limits show remaining orders."""
        guardrails._daily_stats['orders_count'] = 10
        
        limits = guardrails.get_current_limits()
        
        assert limits['daily_limits']['orders']['used'] == 10
        assert limits['daily_limits']['orders']['remaining'] == 40  # 50 - 10


# ============================================================================
# RESET DAILY STATS TESTS
# ============================================================================

class TestResetDailyStats:
    """Tests for _reset_daily_stats_if_needed method."""
    
    def test_no_reset_same_day(self, guardrails):
        """Test stats not reset on same day."""
        guardrails._daily_stats['orders_count'] = 5
        
        guardrails._reset_daily_stats_if_needed()
        
        assert guardrails._daily_stats['orders_count'] == 5
        
    def test_reset_on_new_day(self, guardrails):
        """Test stats reset when day changes."""
        guardrails._daily_stats['orders_count'] = 5
        guardrails._daily_stats['last_reset'] = (datetime.now(UTC) - timedelta(days=1)).date()
        
        guardrails._reset_daily_stats_if_needed()
        
        assert guardrails._daily_stats['orders_count'] == 0


# ============================================================================
# PARSE TIME TESTS
# ============================================================================

class TestParseTime:
    """Tests for _parse_time method."""
    
    def test_valid_time_format(self, guardrails):
        """Test parsing valid time format."""
        result = guardrails._parse_time("14:30")
        assert result == time(14, 30)
        
    def test_invalid_time_format(self, guardrails):
        """Test parsing invalid time format returns default."""
        result = guardrails._parse_time("invalid")
        assert result == time(14, 30)  # Default


# ============================================================================
# IS TRADING WINDOW OPEN TESTS
# ============================================================================

class TestIsTradingWindowOpen:
    """Tests for _is_trading_window_open method."""
    
    def test_window_open(self, guardrails):
        """Test returns True when window is open."""
        guardrails.trading_window_start = time(0, 0)
        guardrails.trading_window_end = time(23, 59)
        
        assert guardrails._is_trading_window_open() is True


# ============================================================================
# GLOBAL INSTANCE TESTS
# ============================================================================

class TestGetGuardrails:
    """Tests for get_guardrails function."""
    
    def test_returns_singleton(self):
        """Test get_guardrails returns singleton."""
        import backend.infra.guardrails as module
        module._guardrails_instance = None  # Reset
        
        g1 = get_guardrails()
        g2 = get_guardrails()
        
        assert g1 is g2


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================

class TestValidateOrderGuardrails:
    """Tests for validate_order_guardrails function."""
    
    @pytest.mark.asyncio
    async def test_convenience_function(self):
        """Test convenience function works."""
        import backend.infra.guardrails as module
        
        # Reset global instance
        module._guardrails_instance = None
        
        with patch.dict('os.environ', {
            'SYMBOL_WHITELIST': 'AAPL,MSFT',
            'TRADING_WINDOW_START': '00:00',
            'TRADING_WINDOW_END': '23:59',
        }):
            module._guardrails_instance = None
            
            result = await validate_order_guardrails(
                symbol="AAPL",
                side="buy",
                qty=Decimal("10")
            )
            
            assert isinstance(result, GuardrailResult)
