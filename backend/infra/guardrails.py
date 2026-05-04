"""
Production Trading Guardrails

Hedge fund grade risk management controls for order submission.
Implements multiple layers of protection including:
- Symbol whitelisting
- Daily notional caps
- Trading window enforcement
- Circuit breakers
- Kill switches
- Order size limits
- Rate limiting

All guardrails are configurable via environment variables and can be overridden
by admin users when RISK_ALLOW_ADMIN_OVERRIDE=true.
"""

from datetime import UTC, datetime, time
from decimal import Decimal
from enum import Enum
import os
from typing import Any

from pydantic import BaseModel

from backend.config import get_settings
from backend.services.quote_manager import get_quote_manager
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class GuardrailViolation(Exception):
    """Raised when a guardrail is violated."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class GuardrailCode(str, Enum):
    """Guardrail violation codes."""
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    DAILY_NOTIONAL_EXCEEDED = "DAILY_NOTIONAL_EXCEEDED"
    ORDER_SIZE_EXCEEDED = "ORDER_SIZE_EXCEEDED"
    MARKET_CLOSED = "MARKET_CLOSED"
    TRADING_PAUSED = "TRADING_PAUSED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    DAILY_ORDER_LIMIT_EXCEEDED = "DAILY_ORDER_LIMIT_EXCEEDED"


class OrderRequest(BaseModel):
    """Order request model for guardrail validation."""
    symbol: str
    side: str
    qty: Decimal
    order_type: str = "market"
    limit_price: Decimal | None = None
    user_id: str | None = None
    is_admin: bool = False
    risk_override: bool = False


class GuardrailResult(BaseModel):
    """Result of guardrail validation."""
    allowed: bool
    violations: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    details: dict[str, Any]


class TradingGuardrails:
    """
    Production trading guardrails implementation.

    Provides comprehensive risk management controls for order submission
    with configurable limits and override capabilities.
    """

    def __init__(self):
        """Initialize guardrails with configuration from environment."""
        self.settings = get_settings()

        # Load guardrail configuration
        self._load_config()

        # Daily tracking (in production, this should be backed by Redis/database)
        self._daily_stats = {
            'orders_count': 0,
            'notional_usd': Decimal('0'),
            'last_reset': datetime.now(UTC).date()
        }

        # Rate limiting tracking
        self._rate_limits = {}

        logger.info("Trading guardrails initialized",
                   symbol_whitelist=self.symbol_whitelist,
                   daily_notional_cap=self.daily_notional_cap_usd,
                   max_order_size=self.max_order_size,
                   trading_paused=self.trading_paused,
                   allow_admin_override=self.allow_admin_override)

    def _load_config(self):
        """Load guardrail configuration from environment."""
        # Symbol whitelist
        whitelist_str = os.getenv("SYMBOL_WHITELIST", "AAPL,MSFT,GOOGL,TSLA,NVDA,SPY,QQQ")
        self.symbol_whitelist = set(symbol.strip() for symbol in whitelist_str.split(","))

        # Daily limits
        self.daily_notional_cap_usd = Decimal(os.getenv("DAILY_NOTIONAL_CAP_USD", "10000"))
        self.max_daily_orders = int(os.getenv("MAX_DAILY_ORDERS", "100"))

        # Order limits
        self.max_order_size = Decimal(os.getenv("MAX_ORDER_SIZE", "100"))

        # Trading window (UTC times)
        self.trading_window_start = self._parse_time(os.getenv("TRADING_WINDOW_START", "14:30"))
        self.trading_window_end = self._parse_time(os.getenv("TRADING_WINDOW_END", "21:00"))

        # Kill switches and circuit breakers
        self.trading_paused = os.getenv("TRADING_PAUSED", "false").lower() in ("true", "1", "yes")
        self.circuit_breaker_pct = Decimal(os.getenv("CIRCUIT_BREAKER_PCT", "5.0"))

        # Rate limiting
        self.max_orders_per_minute = int(os.getenv("MAX_ORDERS_PER_MINUTE", "10"))

        # Admin overrides
        self.allow_admin_override = os.getenv("RISK_ALLOW_ADMIN_OVERRIDE", "true").lower() in ("true", "1", "yes")

    def _parse_time(self, time_str: str) -> time:
        """Parse time string in HH:MM format."""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except (ValueError, AttributeError):
            logger.warning("Invalid time format, using default", time_str=time_str)
            return time(14, 30)  # Default to market open

    def _reset_daily_stats_if_needed(self):
        """Reset daily statistics if date has changed."""
        current_date = datetime.now(UTC).date()
        if self._daily_stats['last_reset'] != current_date:
            logger.info("Resetting daily statistics",
                       old_date=str(self._daily_stats['last_reset']),
                       new_date=str(current_date),
                       old_orders=self._daily_stats['orders_count'],
                       old_notional=str(self._daily_stats['notional_usd']))

            self._daily_stats = {
                'orders_count': 0,
                'notional_usd': Decimal('0'),
                'last_reset': current_date
            }

    async def validate_order(self, order: OrderRequest) -> GuardrailResult:
        """
        Validate order against all guardrails.

        Args:
            order: Order request to validate

        Returns:
            GuardrailResult with validation outcome
        """
        violations = []
        warnings = []

        logger.info("Validating order against guardrails",
                   symbol=order.symbol,
                   side=order.side,
                   qty=str(order.qty),
                   is_admin=order.is_admin,
                   risk_override=order.risk_override)

        # Reset daily stats if needed
        self._reset_daily_stats_if_needed()

        try:
            # 1. Check if trading is globally paused
            self._check_trading_paused(order)

            # 2. Check trading window
            self._check_trading_window(order)

            # 3. Check symbol whitelist
            self._check_symbol_whitelist(order)

            # 4. Check order size limits
            self._check_order_size_limits(order)

            # 5. Check daily order count limit
            self._check_daily_order_limit(order)

            # 6. Check daily notional limit (requires price estimation)
            await self._check_daily_notional_limit(order)

            # 7. Check rate limits
            self._check_rate_limits(order)

            # 8. Check circuit breakers (placeholder - would need market data)
            self._check_circuit_breakers(order)

        except GuardrailViolation as violation:
            # Check if admin can override this violation
            if order.is_admin and order.risk_override and self.allow_admin_override:
                warnings.append({
                    "code": violation.code,
                    "message": f"ADMIN OVERRIDE: {violation.message}",
                    "details": violation.details
                })
                logger.warning("Admin override applied for guardrail violation",
                              code=violation.code,
                              message=violation.message,
                              user_id=order.user_id)
            else:
                violations.append({
                    "code": violation.code,
                    "message": violation.message,
                    "details": violation.details
                })
                logger.error("Guardrail violation detected",
                           code=violation.code,
                           message=violation.message,
                           symbol=order.symbol,
                           qty=str(order.qty))

        # Determine if order is allowed
        allowed = len(violations) == 0

        # Log validation result
        logger.info("Order validation completed",
                   symbol=order.symbol,
                   allowed=allowed,
                   violations_count=len(violations),
                   warnings_count=len(warnings))

        return GuardrailResult(
            allowed=allowed,
            violations=violations,
            warnings=warnings,
            details={
                'daily_orders_used': self._daily_stats['orders_count'],
                'daily_orders_limit': self.max_daily_orders,
                'daily_notional_used': str(self._daily_stats['notional_usd']),
                'daily_notional_limit': str(self.daily_notional_cap_usd),
                'trading_window': f"{self.trading_window_start}-{self.trading_window_end} UTC",
                'trading_paused': self.trading_paused
            }
        )

    def _check_trading_paused(self, order: OrderRequest):
        """Check if trading is globally paused."""
        if self.trading_paused:
            raise GuardrailViolation(
                code=GuardrailCode.TRADING_PAUSED,
                message="Trading is currently paused",
                details={'can_override': self.allow_admin_override and order.is_admin}
            )

    def _check_trading_window(self, order: OrderRequest):
        """Check if order is submitted during allowed trading hours.

        Audit-K finding K-1 (2026-05-02): the trading window was checked
        against UTC time-of-day. Window default 14:30-21:00 UTC = 9:30-16:00
        EST in winter, but 10:30-17:00 EDT in summer (DST shift). To make
        this DST-safe, prefer the canonical `is_market_open` helper if
        you don't need a custom window. Kept the literal-time fallback
        for users who set explicit TRADING_WINDOW_START/END.
        """
        try:
            from backend.utils.market_hours import is_market_open
            # If user is using defaults (14:30 / 21:00 UTC), use canonical
            # market-hours helper for DST-correctness.
            if (
                str(self.trading_window_start) == "14:30:00"
                and str(self.trading_window_end) == "21:00:00"
            ):
                if not is_market_open(include_extended=False):
                    now_utc = datetime.now(UTC).time()
                    raise GuardrailViolation(
                        code=GuardrailCode.MARKET_CLOSED,
                        message="Trading window closed (canonical market_hours)",
                        details={
                            "current_time_utc": str(now_utc),
                            "can_override": self.allow_admin_override and order.is_admin,
                        },
                    )
                return
        except ImportError:
            pass

        # Custom-window fallback (still UTC-literal — user's responsibility)
        now_utc = datetime.now(UTC).time()
        if not (self.trading_window_start <= now_utc <= self.trading_window_end):
            raise GuardrailViolation(
                code=GuardrailCode.MARKET_CLOSED,
                message=f"Trading only allowed between {self.trading_window_start} and {self.trading_window_end} UTC",
                details={
                    'current_time_utc': str(now_utc),
                    'trading_window_start': str(self.trading_window_start),
                    'trading_window_end': str(self.trading_window_end),
                    'can_override': self.allow_admin_override and order.is_admin
                }
            )

    def _check_symbol_whitelist(self, order: OrderRequest):
        """Check if symbol is in whitelist."""
        if order.symbol.upper() not in self.symbol_whitelist:
            raise GuardrailViolation(
                code=GuardrailCode.SYMBOL_NOT_ALLOWED,
                message=f"Symbol '{order.symbol}' not in whitelist",
                details={
                    'symbol': order.symbol,
                    'allowed_symbols': list(self.symbol_whitelist),
                    'can_override': self.allow_admin_override and order.is_admin
                }
            )

    def _check_order_size_limits(self, order: OrderRequest):
        """Check if order size is within limits."""
        if order.qty > self.max_order_size:
            raise GuardrailViolation(
                code=GuardrailCode.ORDER_SIZE_EXCEEDED,
                message=f"Order size {order.qty} exceeds maximum {self.max_order_size}",
                details={
                    'order_qty': str(order.qty),
                    'max_order_size': str(self.max_order_size),
                    'can_override': self.allow_admin_override and order.is_admin
                }
            )

    def _check_daily_order_limit(self, order: OrderRequest):
        """Check if daily order count limit is exceeded."""
        if self._daily_stats['orders_count'] >= self.max_daily_orders:
            raise GuardrailViolation(
                code=GuardrailCode.DAILY_ORDER_LIMIT_EXCEEDED,
                message=f"Daily order limit {self.max_daily_orders} exceeded",
                details={
                    'daily_orders_count': self._daily_stats['orders_count'],
                    'max_daily_orders': self.max_daily_orders,
                    'can_override': self.allow_admin_override and order.is_admin
                }
            )

    async def _check_daily_notional_limit(self, order: OrderRequest):
        """Check if daily notional limit would be exceeded."""
        # For market orders, we need to estimate the notional value
        # This is a simplified implementation - in production, use real-time quotes
        estimated_price = await self._get_estimated_price(order.symbol)
        estimated_notional = order.qty * estimated_price

        if self._daily_stats['notional_usd'] + estimated_notional > self.daily_notional_cap_usd:
            raise GuardrailViolation(
                code=GuardrailCode.DAILY_NOTIONAL_EXCEEDED,
                message="Daily notional limit would be exceeded",
                details={
                    'current_notional': str(self._daily_stats['notional_usd']),
                    'order_notional': str(estimated_notional),
                    'total_notional': str(self._daily_stats['notional_usd'] + estimated_notional),
                    'daily_limit': str(self.daily_notional_cap_usd),
                    'estimated_price': str(estimated_price),
                    'can_override': self.allow_admin_override and order.is_admin
                }
            )

    def _check_rate_limits(self, order: OrderRequest):
        """Check if rate limits are exceeded."""
        current_minute = datetime.now(UTC).replace(second=0, microsecond=0)
        user_key = order.user_id or "anonymous"

        if user_key not in self._rate_limits:
            self._rate_limits[user_key] = {}

        user_limits = self._rate_limits[user_key]

        # Clean old entries (keep only current minute)
        user_limits = {k: v for k, v in user_limits.items() if k >= current_minute}
        self._rate_limits[user_key] = user_limits

        # Count orders in current minute
        current_count = user_limits.get(current_minute, 0)

        if current_count >= self.max_orders_per_minute:
            raise GuardrailViolation(
                code=GuardrailCode.RATE_LIMIT_EXCEEDED,
                message=f"Rate limit of {self.max_orders_per_minute} orders per minute exceeded",
                details={
                    'current_count': current_count,
                    'max_per_minute': self.max_orders_per_minute,
                    'user_id': user_key,
                    'can_override': False  # Rate limits typically cannot be overridden
                }
            )

    def _check_circuit_breakers(self, order: OrderRequest):
        """Check circuit breakers (placeholder implementation)."""
        # In production, this would check:
        # - Market volatility
        # - Portfolio exposure
        # - Sector concentration
        # - Recent P&L drawdown
        # For now, this is a placeholder
        pass

    async def _get_estimated_price(self, symbol: str) -> Decimal:
        """
        Get estimated price for notional calculations from real-time quotes.

        Uses QuoteManager (Redis-cached, Alpaca-backed) for live prices.
        Falls back to the order's limit_price or a conservative default
        so that guardrails are never silently bypassed.
        """
        try:
            qm = get_quote_manager()
            quote = await qm.get_quote(symbol)

            if quote is not None:
                # Prefer mid price (best estimate of fair value), then last trade
                price = quote.mid or quote.last
                if price and price > 0:
                    return Decimal(str(price))

            logger.warning(
                "No live quote available for notional estimate",
                symbol=symbol,
            )
        except Exception as e:
            logger.warning(
                "Failed to fetch quote for notional estimate",
                symbol=symbol,
                error=str(e),
            )

        # Conservative fallback: assume $500 per share so guardrails stay
        # protective rather than permissive.  This only fires when the quote
        # service is completely unreachable.
        return Decimal('500.00')

    def record_order_submitted(self, order: OrderRequest, estimated_notional: Decimal | None = None):
        """
        Record that an order was submitted for daily tracking.

        Args:
            order: Submitted order
            estimated_notional: Estimated notional value (if known)
        """
        self._reset_daily_stats_if_needed()

        # Update daily statistics
        self._daily_stats['orders_count'] += 1

        if estimated_notional:
            self._daily_stats['notional_usd'] += estimated_notional

        # Update rate limiting
        current_minute = datetime.now(UTC).replace(second=0, microsecond=0)
        user_key = order.user_id or "anonymous"

        if user_key not in self._rate_limits:
            self._rate_limits[user_key] = {}

        self._rate_limits[user_key][current_minute] = self._rate_limits[user_key].get(current_minute, 0) + 1

        logger.info("Order submission recorded in daily stats",
                   symbol=order.symbol,
                   daily_orders_count=self._daily_stats['orders_count'],
                   daily_notional=str(self._daily_stats['notional_usd']))

    def get_current_limits(self) -> dict[str, Any]:
        """
        Get current guardrail limits and usage.

        Returns:
            Dict with current limits and usage statistics
        """
        self._reset_daily_stats_if_needed()

        return {
            'symbol_whitelist': list(self.symbol_whitelist),
            'daily_limits': {
                'orders': {
                    'used': self._daily_stats['orders_count'],
                    'limit': self.max_daily_orders,
                    'remaining': self.max_daily_orders - self._daily_stats['orders_count']
                },
                'notional_usd': {
                    'used': str(self._daily_stats['notional_usd']),
                    'limit': str(self.daily_notional_cap_usd),
                    'remaining': str(self.daily_notional_cap_usd - self._daily_stats['notional_usd'])
                }
            },
            'order_limits': {
                'max_size': str(self.max_order_size),
                'max_per_minute': self.max_orders_per_minute
            },
            'trading_window': {
                'start_utc': str(self.trading_window_start),
                'end_utc': str(self.trading_window_end),
                'currently_open': self._is_trading_window_open()
            },
            'status': {
                'trading_paused': self.trading_paused,
                'allow_admin_override': self.allow_admin_override,
                'circuit_breaker_pct': str(self.circuit_breaker_pct)
            }
        }

    def _is_trading_window_open(self) -> bool:
        """Check if trading window is currently open."""
        now_utc = datetime.now(UTC).time()
        return self.trading_window_start <= now_utc <= self.trading_window_end


# Global guardrails instance
_guardrails_instance: TradingGuardrails | None = None


def get_guardrails() -> TradingGuardrails:
    """
    Get the global guardrails instance.

    Returns:
        TradingGuardrails: The guardrails instance
    """
    global _guardrails_instance
    if _guardrails_instance is None:
        _guardrails_instance = TradingGuardrails()
    return _guardrails_instance


async def validate_order_guardrails(
    symbol: str,
    side: str,
    qty: Decimal,
    order_type: str = "market",
    limit_price: Decimal | None = None,
    user_id: str | None = None,
    is_admin: bool = False,
    risk_override: bool = False
) -> GuardrailResult:
    """
    Convenience function to validate order against guardrails.

    Args:
        symbol: Trading symbol
        side: Order side (buy/sell)
        qty: Order quantity
        order_type: Order type
        limit_price: Limit price (for limit orders)
        user_id: User ID submitting the order
        is_admin: Whether user is admin
        risk_override: Whether admin is requesting risk override

    Returns:
        GuardrailResult with validation outcome
    """
    guardrails = get_guardrails()

    order = OrderRequest(
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        limit_price=limit_price,
        user_id=user_id,
        is_admin=is_admin,
        risk_override=risk_override
    )

    return await guardrails.validate_order(order)
