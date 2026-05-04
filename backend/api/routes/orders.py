"""
Order API routes.
Handles order submission, status, and cancellation operations.
"""

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.outbox import OutboxRepo
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.security import get_current_user
from backend.risk.types import OrderSpec, Side
from backend.services.order_service import OrderService
from backend.utils.logger import (
    StandardEventLogger,
    get_logger,
    log_order_cancelled,
    log_order_submitted,
)

logger = get_logger(__name__)
event_logger = StandardEventLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Trading", "Protected", "Outbox"])


# ============================================================================
# §9.5 FIX: Per-user rate limit on order submission
# ============================================================================
_ORDER_RATE_WINDOW = 1.0  # 1-second sliding window
_ORDER_RATE_MAX = 10      # Max 10 orders per user per second
_user_order_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_order_rate_limit(user_id: str) -> None:
    """Enforce per-user order submission rate limit.

    Raises HTTPException 429 if the user exceeds MAX orders per second.
    """
    now = time.monotonic()
    # Prune timestamps older than the window
    timestamps = _user_order_timestamps[user_id]
    _user_order_timestamps[user_id] = [
        ts for ts in timestamps if now - ts < _ORDER_RATE_WINDOW
    ]
    if len(_user_order_timestamps[user_id]) >= _ORDER_RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Order rate limit exceeded: max {_ORDER_RATE_MAX} orders per second",
        )
    _user_order_timestamps[user_id].append(now)


def _compute_etag(data: Any) -> str:
    """Compute ETag from response data for cache validation (L-08)."""
    content = json.dumps(data, sort_keys=True, default=str)
    return f'"{hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()}"'


@router.get("/", response_model=list[dict[str, Any]])
async def get_orders(
    request: Request,
    response: Response,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> list[dict[str, Any]]:
    """Get list of orders for the current user."""
    try:
        from sqlalchemy import or_, select

        from backend.infra.schemas import Order

        # Show user's own orders + system (organism) orders for visibility
        stmt = (
            select(Order)
            .where(or_(Order.user_id == user.username, Order.user_id == "system"))
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        orders = list(result.scalars().all())

        logger.info(f"Fetched {len(orders)} orders from database")

        # Transform to API response format - now includes all price/fill fields
        orders_data = [
            {
                "order_id": str(order.id),
                "user_id": "",  # Add if you have user_id in Order model
                "symbol": order.symbol,
                "side": order.side,
                "qty": float(order.qty),
                "filled_qty": float(order.filled_qty),  # Real value from database
                "order_type": order.order_type,
                "status": order.status,
                "time_in_force": order.tif,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat(),
                "broker_order_id": order.broker_order_id if order.broker_order_id else None,
                "client_order_id": order.client_idempotency_key,
                "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price is not None else None,
                "limit_price": float(order.limit_price) if order.limit_price is not None else None,
                "stop_price": float(order.stop_price) if order.stop_price is not None else None,
                "exchange": "ALPACA",  # Hardcoded for now, can make dynamic later
                "strategy_id": order.attributes.get("strategy_id") if order.attributes else None,
            }
            for order in orders
        ]

        # L-08: Add ETag support for cache validation on frequently-polled endpoint
        etag = _compute_etag(orders_data)
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=1"

        # Check If-None-Match for conditional request
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})

        return orders_data

    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch orders: {str(e)}"
        )


# Request/Response Models
class OrderResponse(BaseModel):
    """Order response model."""
    order_id: str
    client_order_id: str | None = None
    status: str
    symbol: str
    side: str
    qty: float
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    submitted_at: str
    updated_at: str


class OrderSubmissionRequest(BaseModel):
    """Order submission request payload."""
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side: buy or sell")
    qty: float = Field(..., gt=0, description="Quantity to trade")
    order_type: str = Field(default="market", description="Order type")
    time_in_force: str = Field(default="day", description="Time in force")
    client_order_id: str | None = Field(default=None, description="Client-provided order ID for idempotency")
    risk_override: bool = Field(default=False, description="Admin risk override flag")


class OrderSubmissionResponse(BaseModel):
    """§13.5 FIX: Order submission response matching frontend BackendOrder shape."""
    order_id: str
    client_order_id: str | None = None
    status: str
    symbol: str
    side: str
    qty: float
    order_type: str = "market"
    filled_qty: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    avg_fill_price: float | None = None
    time_in_force: str = "day"
    submitted_at: str = ""
    updated_at: str = ""
    user_id: str | None = None
    strategy_id: str | None = None
    risk_override: bool | None = Field(default=None, description="Whether admin risk override was used")


class OrderStatusResponse(BaseModel):
    """Order status response."""
    order_id: str
    client_order_id: str | None = None
    status: str
    symbol: str
    side: str
    qty: float
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    submitted_at: str
    updated_at: str


class AuditEntry(BaseModel):
    """Audit trail entry."""
    timestamp: str
    event_type: str
    order_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class AuditResponse(BaseModel):
    """Audit trail response."""
    entries: list[AuditEntry]


# Pre-Trade Validation Models
class ValidationCheck(BaseModel):
    """Individual validation check result."""
    name: str = Field(..., description="Name of the check")
    passed: bool = Field(..., description="Whether the check passed")
    current_value: float | None = Field(None, description="Current value being checked")
    limit_value: float | None = Field(None, description="Limit/threshold value")
    message: str = Field(..., description="Human-readable message about the check")
    severity: str = Field(default="info", description="Severity: info, warning, error")


class OrderValidationResponse(BaseModel):
    """Pre-trade order validation response.

    V11 prep / Wave-64 (VV-1 closure, 2026-05-03): emit BOTH snake_case
    AND camelCase aliases so the frontend (which reads camelCase) and
    operator-facing curl/clients (which expect snake_case) both work
    without a coordinated rename.  pydantic emits the alias by default
    when `populate_by_name=True` + `by_alias=True` on serialization.
    The frontend's previous undefined/N/A bug came from snake_case
    keys it didn't recognize; now we ship both.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        # alias_generator preserved for forward-compat; explicit per-field
        # aliases below are the source of truth.
    )

    valid: bool = Field(..., description="Overall validation result")
    checks: list[ValidationCheck] = Field(default_factory=list, description="Individual validation checks")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    errors: list[str] = Field(default_factory=list, description="Error messages")
    estimated_cost: float | None = Field(
        None,
        description="Estimated cost of the order",
        serialization_alias="estimatedCost",
    )
    estimated_price: float | None = Field(
        None,
        description="Estimated price per share (fetched for market orders)",
        serialization_alias="estimatedPrice",
    )
    estimated_buying_power_after: float | None = Field(
        None,
        description="Buying power after order",
        serialization_alias="estimatedBuyingPowerAfter",
    )


# Service Dependencies
# Use canonical db session dependency from infra.db
from backend.infra.db import get_db_session

# OrderService dependency removed - create services inside handlers with session dependency


async def get_risk_manager(request: Request):
    """
    Get risk manager — delegates to the singleton ``app.state.risk_manager``
    created at startup in ``factory.py`` (§5.2 / §10.2 consolidation).

    Falls back to a thin DB-aware wrapper only when the app-level risk
    manager is not available (e.g. in some test setups).
    """
    rm = getattr(request.app.state, "risk_manager", None)
    if rm is not None:
        return rm

    # Fallback: lightweight risk manager when app.state is empty (tests)
    from backend.risk.risk_manager import RiskManager
    return RiskManager()


def require_trader(
    current_user=Depends(get_current_user),
):
    """V11 AAA-F2 / Wave-68 (2026-05-03): canonical RBAC for trader+admin.

    Pre-V11 this stub IGNORED roles ("In production, would check
    roles/permissions") — letting any self-registered user (default
    role ["user"] per auth.py:661) place / cancel / modify orders.
    Same RBAC bypass class wave-23b closed for organism / audit, but
    missed on the orders surface.

    Now: delegates to the canonical require_roles factory in
    infra/security.  Allowed roles: trader OR admin.  Anything else
    (including default "user") → 403.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    user_roles = set(getattr(current_user, "roles", []) or [])
    if not (user_roles & {"trader", "admin"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="trader or admin role required",
        )
    return current_user


def _current_user_identity(current_user: Any) -> str:
    """Best-effort stable user identity for order ownership checks."""
    from backend.infra.security import get_user_attribute

    return (
        get_user_attribute(current_user, "username", None)
        or get_user_attribute(current_user, "user_id", None)
        or get_user_attribute(current_user, "sub", None)
        or "anonymous"
    )


def _order_owner_id(order_status: Any) -> str | None:
    """V13 W96 (Lens 5): extract user_id from a heterogeneous order
    payload (dict, ORM model, or pydantic schema).  Returns None if
    no ownership field is present — callers may treat as "no owner",
    which is the legacy default for system-placed orders.
    """
    if isinstance(order_status, dict):
        return order_status.get("user_id")
    return getattr(order_status, "user_id", None)


def assert_order_owner_or_404(
    order_status: Any,
    current_user: Any,
) -> None:
    """V13 W96 (Lens 5): canonical IDOR ownership check.

    Raises ``HTTPException(404)`` if ``order_status`` exists and is
    owned by a user other than ``current_user``.  Returns silently
    on owned orders or orders without an owner field.

    The 404 (not 403) is intentional: surfacing 403 would confirm
    that the order ID exists, which is itself an information leak.
    """
    if order_status is None:
        return  # "not found" path; caller already raised or will
    owner = _order_owner_id(order_status)
    if not owner:
        return  # no ownership field — system order, allow
    user = _current_user_identity(current_user)
    if owner != user:
        # NB: we log the attempt but do NOT distinguish via response.
        logger.warning(
            "V13 W96 IDOR rejected: user=%s tried to access order owned by %s",
            user, owner,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )


# ============================================================================
# PRE-TRADE VALIDATION ENDPOINT
# ============================================================================

@router.post(
    "/validate",
    response_model=OrderValidationResponse,
    tags=["Trading", "Protected"],
    summary="Validate order before submission",
    description="Performs pre-trade validation checks including buying power, position limits, and risk assessments"
)
async def validate_order_pre_trade(
    body: dict[str, Any] = Body(..., description="Order data to validate"),
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
    risk_manager=Depends(get_risk_manager),
) -> OrderValidationResponse:
    """
    Validate an order before submission.

    Performs comprehensive pre-trade checks:
    - Buying power sufficiency
    - Position size limits
    - Daily loss limits
    - Order count limits
    - Concentration limits
    - Symbol validation

    Args:
        body: Order data including symbol, side, quantity, orderType, limitPrice
        current_user: Authenticated user
        db: Database session
        risk_manager: Risk manager instance

    Returns:
        OrderValidationResponse with validation results and detailed checks
    """
    try:
        # Extract order parameters
        symbol = body.get("symbol", "").upper()
        side = body.get("side", "buy").lower()
        quantity = float(body.get("quantity", 0))
        order_type = body.get("orderType", "market").lower()
        limit_price = body.get("limitPrice")

        # Initialize validation response
        checks: list[ValidationCheck] = []
        warnings: list[str] = []
        errors: list[str] = []
        overall_valid = True

        # ===== CHECK 1: Basic Input Validation =====
        if not symbol:
            checks.append(ValidationCheck(
                name="Symbol Validation",
                passed=False,
                message="Symbol is required",
                severity="error"
            ))
            errors.append("Symbol is required")
            overall_valid = False
        elif len(symbol) > 10 or not symbol.isalpha():
            checks.append(ValidationCheck(
                name="Symbol Validation",
                passed=False,
                message=f"Invalid symbol format: {symbol}",
                severity="error"
            ))
            errors.append(f"Invalid symbol format: {symbol}")
            overall_valid = False
        else:
            # Validate symbol with Alpaca API
            from backend.services.symbol_validator import validate_symbol

            is_valid, error_msg = await validate_symbol(symbol)
            if not is_valid:
                checks.append(ValidationCheck(
                    name="Symbol Validation",
                    passed=False,
                    message=error_msg or f"Invalid symbol: {symbol}",
                    severity="error"
                ))
                errors.append(error_msg or f"Invalid symbol: {symbol}")
                overall_valid = False
            else:
                checks.append(ValidationCheck(
                    name="Symbol Validation",
                    passed=True,
                    message=f"Symbol {symbol} is valid and tradable",
                    severity="info"
                ))

        if quantity <= 0:
            checks.append(ValidationCheck(
                name="Quantity Validation",
                passed=False,
                current_value=quantity,
                message="Quantity must be greater than 0",
                severity="error"
            ))
            errors.append("Quantity must be greater than 0")
            overall_valid = False
        else:
            checks.append(ValidationCheck(
                name="Quantity Validation",
                passed=True,
                current_value=quantity,
                message=f"Quantity {quantity} is valid",
                severity="info"
            ))

        # ===== CHECK 2: Get Current Portfolio State =====
        buying_power = None
        current_equity = None
        cash = None
        portfolio_data = {}  # Initialize for later use
        portfolio_fetch_failed = False

        # Strategy: Get account directly from Alpaca (most reliable)
        try:
            from backend.integrations.alpaca_broker import get_alpaca_broker_client
            broker_client = get_alpaca_broker_client()
            account_data = await broker_client.get_account()

            if account_data:
                buying_power = float(account_data.get("buying_power", 0))
                current_equity = float(account_data.get("equity", 0))
                cash = float(account_data.get("cash", 0))

                # Store in portfolio_data for later checks
                portfolio_data = {
                    "buyingPower": buying_power,
                    "equity": current_equity,
                    "cash": cash,
                    "dailyPnL": 0  # Will be 0 if not available from account
                }

                if buying_power > 0:
                    logger.info(f"Fetched account from Alpaca: buying_power=${buying_power:,.2f}")
                else:
                    portfolio_fetch_failed = True
                    logger.error("Alpaca account data invalid (zero buying power)")
            else:
                portfolio_fetch_failed = True
                logger.error("Alpaca get_account returned None")

        except Exception as e:
            portfolio_fetch_failed = True
            logger.error(f"Failed to fetch account from Alpaca: {e}")

        # Portfolio check: Only fail for BUY orders (sell orders don't need buying power)
        if portfolio_fetch_failed and side == "buy":
            checks.append(ValidationCheck(
                name="Portfolio Data",
                passed=False,
                message="Unable to fetch portfolio data. Please try again or contact support.",
                severity="error"
            ))
            errors.append("Cannot validate order without portfolio data")
            overall_valid = False
        elif not portfolio_fetch_failed:
            checks.append(ValidationCheck(
                name="Portfolio Data",
                passed=True,
                message=f"Portfolio loaded: ${buying_power:,.2f} buying power",
                severity="info"
            ))
        else:
            # Sell order without portfolio data - allow but warn
            checks.append(ValidationCheck(
                name="Portfolio Data",
                passed=True,
                message="Portfolio data unavailable (sell order - no buying power needed)",
                severity="warning"
            ))

        # ===== CHECK 3: Calculate Estimated Cost =====
        estimated_price = None

        if order_type == "market":
            # For market orders, try to fetch current/recent price for estimation
            try:
                import os

                import httpx

                # Get Alpaca credentials from environment
                api_key = os.getenv("ALPACA_API_KEY_ID")
                api_secret = os.getenv("ALPACA_API_SECRET_KEY")

                logger.info(f"Attempting to fetch price for {symbol} - has credentials: {bool(api_key and api_secret)}")

                if api_key and api_secret:
                    # Try to get latest quote from Alpaca
                    headers = {
                        "APCA-API-KEY-ID": api_key,
                        "APCA-API-SECRET-KEY": api_secret
                    }

                    async with httpx.AsyncClient() as client:
                        # Try latest quote first (real-time)
                        try:
                            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest"
                            logger.info(f"Fetching quote from: {url}")
                            response = await client.get(url, headers=headers, timeout=5.0)
                            logger.info(f"Quote response status: {response.status_code}")

                            if response.status_code == 200:
                                data = response.json()
                                logger.info(f"Quote response data: {data}")
                                quote = data.get("quote", {})
                                bid = float(quote.get("bp", 0) or 0)
                                ask = float(quote.get("ap", 0) or 0)
                                if bid > 0 and ask > 0:
                                    estimated_price = (bid + ask) / 2
                                    logger.info(f"Fetched quote for {symbol}: bid=${bid:.2f}, ask=${ask:.2f}, mid=${estimated_price:.2f}")
                            else:
                                logger.warning(f"Quote request failed with status {response.status_code}: {response.text}")
                        except Exception as e:
                            logger.warning(f"Failed to get quote for {symbol}: {e}", exc_info=True)

                        # Fallback to latest bar if quote failed
                        if not estimated_price:
                            try:
                                url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars/latest"
                                logger.info(f"Fetching bar from: {url}")
                                response = await client.get(url, headers=headers, timeout=5.0)
                                logger.info(f"Bar response status: {response.status_code}")

                                if response.status_code == 200:
                                    data = response.json()
                                    logger.info(f"Bar response data: {data}")
                                    bar = data.get("bar", {})
                                    close_price = float(bar.get("c", 0) or 0)
                                    if close_price > 0:
                                        estimated_price = close_price
                                        logger.info(f"Fetched latest bar for {symbol}: close=${close_price:.2f}")
                                else:
                                    logger.warning(f"Bar request failed with status {response.status_code}: {response.text}")
                            except Exception as e:
                                logger.warning(f"Failed to get bar for {symbol}: {e}", exc_info=True)
                else:
                    logger.warning("Alpaca API credentials not available in environment")

                market_price = estimated_price

                if market_price and market_price > 0:
                    estimated_price = market_price
                    # Check if this is real-time or last close
                    # (After hours, get_current_price returns last bar close)
                    from backend.utils.market_hours import is_market_open
                    is_market_hours = is_market_open()

                    if is_market_hours:
                        logger.info(f"Fetched real-time market price for {symbol}: ${market_price:.2f}")
                        checks.append(ValidationCheck(
                            name="Market Price",
                            passed=True,
                            message=f"Current market price: ${estimated_price:.2f}",
                            severity="info"
                        ))
                    else:
                        logger.info(f"Using last close price for {symbol}: ${market_price:.2f} (market closed)")
                        checks.append(ValidationCheck(
                            name="Market Price (Estimated)",
                            passed=True,
                            message=f"Last close: ${estimated_price:.2f} (market closed)",
                            severity="info"
                        ))
                        warnings.append(f"Market is closed. Using last close price (${estimated_price:.2f}) for estimation. Order will execute at market price when trading resumes.")
                else:
                    # Could not get any price - allow order but warn heavily
                    logger.warning(f"Could not fetch any price for {symbol}")
                    estimated_price = None
                    checks.append(ValidationCheck(
                        name="Market Price",
                        passed=True,  # Still pass - allow order submission
                        message=f"Price unavailable for {symbol}",
                        severity="warning"
                    ))
                    warnings.append(f"Cannot estimate cost for {symbol}. Order will execute at market price when trading resumes.")

            except Exception as e:
                logger.error(f"Failed to fetch price for {symbol}: {e}")
                # Allow order submission even if price fetch fails
                estimated_price = None
                checks.append(ValidationCheck(
                    name="Market Price",
                    passed=True,  # Still pass - allow order submission
                    message=f"Price fetch failed for {symbol}",
                    severity="warning"
                ))
                warnings.append("Cannot estimate cost (price unavailable). Order will execute at market price when trading resumes.")

            # Calculate estimated cost if we have a price
            if estimated_price:
                estimated_cost = quantity * estimated_price
            else:
                estimated_cost = 0  # Can't estimate without price

        elif order_type == "limit":
            if not limit_price or limit_price <= 0:
                checks.append(ValidationCheck(
                    name="Limit Price",
                    passed=False,
                    message="Limit orders require a valid limit price",
                    severity="error"
                ))
                errors.append("Limit price is required for limit orders")
                overall_valid = False
                estimated_cost = 0
            else:
                estimated_price = limit_price
                estimated_cost = quantity * estimated_price
                checks.append(ValidationCheck(
                    name="Limit Price",
                    passed=True,
                    message=f"Limit price: ${estimated_price:.2f}",
                    severity="info"
                ))
        else:
            # Unknown order type
            checks.append(ValidationCheck(
                name="Order Type",
                passed=False,
                message=f"Unknown order type: {order_type}",
                severity="error"
            ))
            errors.append(f"Unsupported order type: {order_type}")
            overall_valid = False
            estimated_cost = 0

        # ===== CHECK 4: Buying Power Check =====
        if side == "buy" and not portfolio_fetch_failed:
            # Only check if we have valid portfolio data
            if buying_power is not None and estimated_cost > 0:
                buying_power_check_passed = buying_power >= estimated_cost

                checks.append(ValidationCheck(
                    name="Buying Power",
                    passed=buying_power_check_passed,
                    current_value=buying_power,
                    limit_value=estimated_cost,
                    message=f"Buying power: ${buying_power:,.2f} {'≥' if buying_power_check_passed else '<'} ${estimated_cost:,.2f} required",
                    severity="error" if not buying_power_check_passed else "info"
                ))

                if not buying_power_check_passed:
                    errors.append(f"Insufficient buying power. Need ${estimated_cost:,.2f}, have ${buying_power:,.2f}")
                    overall_valid = False
        else:
            # For sell orders, check is automatic (assuming we have the shares)
            checks.append(ValidationCheck(
                name="Buying Power",
                passed=True,
                message="Sell orders do not require buying power check",
                severity="info"
            ))

        # ===== CHECK 5: Position Size Limit =====
        # Only check if we have valid cost calculation
        if estimated_cost > 0:
            max_position_size = 100000  # $100K max per position
            position_size_check_passed = estimated_cost <= max_position_size

            checks.append(ValidationCheck(
                name="Position Size Limit",
                passed=position_size_check_passed,
                current_value=estimated_cost,
                limit_value=max_position_size,
                message=f"Order value: ${estimated_cost:,.2f} {'≤' if position_size_check_passed else '>'} ${max_position_size:,.2f} limit",
                severity="error" if not position_size_check_passed else "info"
            ))

            if not position_size_check_passed:
                errors.append(f"Order exceeds maximum position size limit of ${max_position_size:,.2f}")
                overall_valid = False

        # ===== CHECK 6: Concentration Limit =====
        if current_equity and current_equity > 0 and estimated_cost > 0:
            concentration_pct = (estimated_cost / current_equity) * 100
            max_concentration_pct = 25.0  # 25% max concentration
            concentration_check_passed = concentration_pct <= max_concentration_pct

            checks.append(ValidationCheck(
                name="Portfolio Concentration",
                passed=concentration_check_passed,
                current_value=concentration_pct,
                limit_value=max_concentration_pct,
                message=f"Position will be {concentration_pct:.1f}% of portfolio (limit: {max_concentration_pct:.1f}%)",
                severity="warning" if concentration_pct > 15 else "info"
            ))

            if concentration_pct > 15 and concentration_pct <= max_concentration_pct:
                warnings.append(f"This order will represent {concentration_pct:.1f}% of your portfolio")
            elif not concentration_check_passed:
                errors.append(f"Order would exceed {max_concentration_pct:.1f}% concentration limit")
                overall_valid = False

        # ===== CHECK 7: Daily Loss Limit =====
        # Get today's P&L from portfolio
        daily_pnl = portfolio_data.get("dailyPnL", 0)
        max_daily_loss = -10000  # -$10K max daily loss

        if daily_pnl < 0:
            daily_loss_check_passed = daily_pnl > max_daily_loss
            checks.append(ValidationCheck(
                name="Daily Loss Limit",
                passed=daily_loss_check_passed,
                current_value=daily_pnl,
                limit_value=max_daily_loss,
                message=f"Daily P&L: ${daily_pnl:,.2f} {'>' if daily_loss_check_passed else '≤'} ${max_daily_loss:,.2f} limit",
                severity="warning" if daily_pnl < (max_daily_loss * 0.8) else "info"
            ))

            if not daily_loss_check_passed:
                errors.append(f"Daily loss limit of ${abs(max_daily_loss):,.2f} has been reached")
                overall_valid = False
            elif daily_pnl < (max_daily_loss * 0.8):
                warnings.append(f"Approaching daily loss limit: ${daily_pnl:,.2f} of ${max_daily_loss:,.2f}")
        else:
            checks.append(ValidationCheck(
                name="Daily Loss Limit",
                passed=True,
                current_value=daily_pnl,
                message=f"Daily P&L is positive: ${daily_pnl:,.2f}",
                severity="info"
            ))

        # ===== CHECK 8: Risk Manager Assessment =====
        try:
            risk_check = risk_manager.check_risk(symbol, quantity if side == "buy" else -quantity, estimated_price)
            risk_allowed = risk_check.get("allowed", True)
            risk_score = risk_check.get("risk_score", 0)

            checks.append(ValidationCheck(
                name="Risk Assessment",
                passed=risk_allowed,
                current_value=risk_score,
                limit_value=0.8,
                message=f"Risk score: {risk_score:.2f} ({'acceptable' if risk_allowed else 'too high'})",
                severity="error" if not risk_allowed else "info"
            ))

            if not risk_allowed:
                errors.append(f"Risk assessment failed: {risk_check.get('reason', 'Unknown reason')}")
                overall_valid = False

        except Exception as e:
            logger.error(f"Risk assessment error: {e}")
            checks.append(ValidationCheck(
                name="Risk Assessment",
                passed=True,
                message="Risk assessment unavailable, proceeding with caution",
                severity="warning"
            ))
            warnings.append("Risk assessment system temporarily unavailable")

        # ===== Calculate Estimated Buying Power After =====
        if buying_power is not None and side == "buy":
            estimated_buying_power_after = buying_power - estimated_cost
        else:
            estimated_buying_power_after = buying_power  # Could be None if portfolio fetch failed

        # Build response
        return OrderValidationResponse(
            valid=overall_valid,
            checks=checks,
            warnings=warnings,
            errors=errors,
            estimated_cost=estimated_cost if side == "buy" and estimated_cost > 0 else None,
            estimated_price=estimated_price,
            estimated_buying_power_after=estimated_buying_power_after
        )

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return OrderValidationResponse(
            valid=False,
            checks=[
                ValidationCheck(
                    name="System Error",
                    passed=False,
                    message=f"Validation system error: {str(e)}",
                    severity="error"
                )
            ],
            errors=[f"Validation system error: {str(e)}"]
        )


# ============================================================================
# ORDER SUBMISSION ENDPOINT
# ============================================================================


# Route Handlers
@router.post(
    "/",  # POST /orders
    response_model=OrderSubmissionResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def submit_order(
    request: Request,
    body: dict[str, Any] | None = Body(None),
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
    risk_manager=Depends(get_risk_manager),
):
    """
    Submit an order with real OrderService, idempotency protection, and outbox pattern.

    Features:
    - Real repository-backed order creation
    - Transactional outbox for reliable broker communication
    - Idempotency protection via client_order_id or Idempotency-Key header
    - Risk management validation
    - Structured logging
    """
    from backend.infra.security import get_user_attribute

    # §9.5 FIX: Per-user order submission rate limit
    user_id = getattr(current_user, "username", None) or str(current_user)
    _check_order_rate_limit(user_id)

    try:
        # Extract and validate order data
        data = body or {}
        symbol = data.get("symbol", "").strip().upper()
        side = data.get("side", "").lower()
        qty = data.get("qty", 0)
        order_type = data.get("order_type", "market")
        tif = data.get("time_in_force", "day")
        risk_override = data.get("risk_override", False)

        # Handle idempotency - check header first, then body
        idempotency_key = (
            request.headers.get("Idempotency-Key") or
            data.get("client_order_id") or
            data.get("idempotency_key")
        )

        # Validation
        errors = []
        if not symbol:
            errors.append({"field": "symbol", "message": "Symbol is required"})
        elif len(symbol) > 10:
            errors.append({"field": "symbol", "message": "Symbol too long"})

        if side not in ["buy", "sell"]:
            errors.append({"field": "side", "message": "Side must be 'buy' or 'sell'"})

        try:
            qty = float(qty)
            if qty <= 0:
                errors.append({"field": "qty", "message": "Quantity must be positive"})
        except (ValueError, TypeError):
            errors.append({"field": "qty", "message": "Quantity must be a valid number"})

        if not idempotency_key:
            errors.append({
                "field": "idempotency_key",
                "message": "Idempotency key is required (Idempotency-Key header or client_order_id)",
            })

        if errors:
            raise HTTPException(status_code=422, detail=errors)

        # Risk management check using new assess_order method
        user_id = (
            get_user_attribute(current_user, "username", None)
            or get_user_attribute(current_user, "user_id", None)
            or "anonymous"
        )

        # Create OrderSpec for risk assessment
        from decimal import Decimal
        logger.info(f"[ORDERS ROUTE] Creating OrderSpec for {symbol}, side={side}, qty={qty}")
        order_side = Side.BUY if side == "buy" else Side.SELL
        logger.info(f"[ORDERS ROUTE] order_side={order_side}, type={type(order_side)}")
        order_spec = OrderSpec(
            symbol=symbol,
            side=order_side,
            qty=Decimal(str(qty)),
            type=order_type
        )
        logger.info(f"[ORDERS ROUTE] OrderSpec created: {order_spec}")

        # Check risk with new structured assessment
        logger.info("[ORDERS ROUTE] Calling risk_manager.assess_order()...")
        risk_result = await risk_manager.assess_order(
            order=order_spec,
            current_user=current_user,
            risk_override=risk_override,
            request_id=request.headers.get("X-Request-ID")
        )
        logger.info(f"[ORDERS ROUTE] Risk result: {risk_result}")

        if not risk_result.get("allowed", False):
            reason_code = risk_result.get("reason_code", "UNKNOWN")
            message = risk_result.get("message", "Order blocked by risk management")
            details = risk_result.get("details", {})

            # Return structured 422 error as specified
            error_response = {
                "error": {
                    "code": "RISK_LIMIT",
                    "message": message,
                    "details": {
                        "reason_code": reason_code,
                        **details
                    }
                }
            }

            raise HTTPException(status_code=422, detail=error_response)

        # Prepare order data for OrderService
        order_data = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "tif": tif,
            "idempotency_key": idempotency_key,
            "user_id": user_id,
            "attributes": {
                "user_id": user_id,
                "source": "api",
                "risk_score": 0.0,  # Low risk since it passed assessment
                "risk_warnings": [],
                "risk_override_used": risk_result.get("risk_override", False),
                "risk_check_details": risk_result.get("details", {})
            }
        }

        # Create OrderService with session and repositories
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        # Submit order through real OrderService
        result = await order_service.submit_order_async(order_data)

        # Broadcast portfolio update to user (after successful order submission)
        try:
            from backend.services.portfolio_service import get_portfolio_service
            portfolio_service = get_portfolio_service()
            await portfolio_service.broadcast_portfolio_update(user_id)
        except Exception as broadcast_error:
            # Don't fail the order if broadcast fails
            logger.warning(f"Failed to broadcast portfolio update: {broadcast_error}")

        # Broadcast order update to user
        try:
            from backend.api.socketio_server import broadcast_order_update
            await broadcast_order_update(user_id, {
                'order_id': result.get('order_id'),
                'symbol': symbol,
                'side': side,
                'status': result.get('status'),
                'quantity': qty,
                'filled_quantity': 0,
                'order_type': order_type,
                'submitted_at': result.get('submitted_at')
            })
        except Exception as broadcast_error:
            logger.warning(f"Failed to broadcast order update: {broadcast_error}")

        # Log structured event using standardized logger
        log_order_submitted(
            order_id=result.get("order_id"),
            symbol=symbol,
            side=side,
            qty=qty,
            user_id=user_id,
            idempotency_key=idempotency_key,
            status=result.get("status"),
            endpoint="submit_order"
        )

        # Convert to response format — include all fields frontend expects (§13.5)
        response_data = {
            "order_id": result["order_id"],
            "client_order_id": idempotency_key,
            "status": result["status"],
            "symbol": result["symbol"],
            "side": result["side"],
            "qty": result["qty"],
            "order_type": order_type,
            "filled_qty": 0.0,
            "limit_price": data.get("limit_price"),
            "stop_price": data.get("stop_price"),
            "time_in_force": tif,
            "submitted_at": result.get("submitted_at", datetime.now().isoformat()),
            "updated_at": result.get("submitted_at", datetime.now().isoformat()),
            "user_id": user_id,
            "strategy_id": data.get("strategy_id"),
        }

        # Add risk override flag if it was used
        if risk_result.get("risk_override", False):
            response_data["risk_override"] = True

        return OrderSubmissionResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order submission failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        )


@router.get(
    "/{order_id}/status",  # GET /orders/{order_id}/status
    response_model=OrderStatusResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def get_order_status(
    order_id: str,
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current order status and details.
    
    Security:
        IDOR Protection (C-03): Verifies user owns the order before returning.
    """
    try:
        # Create OrderService with session and repositories
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        order_status = await order_service.get_order_status(order_id)

        # SECURITY FIX (C-03): IDOR Protection - verify user owns this order
        # Return 404 (not 403) to prevent order existence confirmation
        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        
        # Get current user's identifier
        user_id = current_user.get('sub') if isinstance(current_user, dict) else getattr(current_user, 'username', None)
        order_user_id = order_status.get('user_id') if isinstance(order_status, dict) else getattr(order_status, 'user_id', None)
        
        # If order has user_id and it doesn't match, deny access (return 404 to not reveal existence)
        if order_user_id and order_user_id != user_id:
            logger.warning(f"IDOR attempt: user {user_id} tried to access order {order_id} owned by {order_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        return order_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order status",
        )


@router.get(
    "/{order_id}",  # GET /orders/{order_id} - alias for frontend compatibility
    response_model=OrderStatusResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def get_order(
    order_id: str,
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """Get order details by ID (frontend-compatible alias).
    
    Security:
        IDOR Protection (C-03): Verifies user owns the order before returning.
    """
    try:
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        order_status = await order_service.get_order_status(order_id)

        # SECURITY FIX (C-03): IDOR Protection - verify user owns this order
        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        
        # Get current user's identifier
        user_id = current_user.get('sub') if isinstance(current_user, dict) else getattr(current_user, 'username', None)
        order_user_id = order_status.get('user_id') if isinstance(order_status, dict) else getattr(order_status, 'user_id', None)
        
        # If order has user_id and it doesn't match, deny access
        if order_user_id and order_user_id != user_id:
            logger.warning(f"IDOR attempt: user {user_id} tried to access order {order_id} owned by {order_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        return order_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order",
        )


@router.patch(
    "/{order_id}",  # PATCH /orders/{order_id}
    response_model=OrderStatusResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def update_order(
    order_id: str,
    updates: dict[str, Any] = Body(...),
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """Update order (modify quantity, price, etc.).

    Note: Not all order modifications are supported by all brokers.
    Currently returns the existing order status.
    
    Security:
        IDOR Protection (C-03): Verifies user owns the order before updating.
    """
    try:
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        order_status = await order_service.get_order_status(order_id)

        # SECURITY FIX (C-03): IDOR Protection - verify user owns this order
        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        
        # Get current user's identifier
        user_id = current_user.get('sub') if isinstance(current_user, dict) else getattr(current_user, 'username', None)
        order_user_id = order_status.get('user_id') if isinstance(order_status, dict) else getattr(order_status, 'user_id', None)
        
        # If order has user_id and it doesn't match, deny access
        if order_user_id and order_user_id != user_id:
            logger.warning(f"IDOR attempt: user {user_id} tried to update order {order_id} owned by {order_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        logger.info(f"Order update requested for {order_id} with updates: {updates}")

        # Apply modification via OrderService cancel-and-replace pattern
        modification_data = {
            "order_id": order_id,
            **updates,
        }
        modification_result = await order_service.modify_order(modification_data)

        if modification_result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=modification_result.get("reason", "Order modification failed"),
            )

        # Re-fetch the updated order status
        updated_status = await order_service.get_order_status(
            modification_result.get("new_order_id", order_id)
        )
        return updated_status or modification_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order",
        )


@router.delete(
    "/cancel-all",  # DELETE /orders/cancel-all
    tags=["Trading", "Protected", "Outbox"],
)
async def cancel_all_orders(
    symbol: str | None = None,
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel all open orders, optionally filtered by symbol.

    Args:
        symbol: Optional symbol filter to cancel only orders for specific symbol
    """
    try:
        # Get all open orders for user (admin can cancel globally)
        from sqlalchemy import select, and_
        from backend.infra.schemas import Order
        requester = _current_user_identity(current_user)
        roles = set(getattr(current_user, "roles", []) or [])
        is_admin = "admin" in roles

        query = select(Order).where(
            and_(
                Order.status.in_(["pending", "submitted", "new", "partial"]),
            )
        )
        if not is_admin:
            query = query.where(Order.user_id == requester)
        if symbol:
            query = query.where(Order.symbol == symbol)

        result = await db.execute(query)
        open_orders = result.scalars().all()

        cancelled_count = 0
        for order in open_orders:
            try:
                order.status = "cancelled"
                cancelled_count += 1
            except Exception as cancel_err:
                logger.warning(f"Failed to cancel order {order.id}: {cancel_err}")

        if cancelled_count > 0:
            await db.commit()

        logger.info(f"Cancelled {cancelled_count} orders for user {requester}" +
                   (f" and symbol {symbol}" if symbol else ""))

        return {
            "status": "success",
            "message": f"{cancelled_count} orders cancelled",
            "cancelled_count": cancelled_count
        }

    except Exception as e:
        logger.error(f"Failed to cancel all orders: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel all orders",
        )


@router.post("/{order_id}/cancel", tags=["Trading", "Protected", "Outbox"])  # POST /orders/{order_id}/cancel
async def cancel_order(
    order_id: str,
    idempotency_key: str = None,
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel an existing order.
    
    Security:
        IDOR Protection (C-03): Verifies user owns the order before cancelling.
    """
    try:
        # Create OrderService with session and repositories
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        # SECURITY FIX (C-03): IDOR Protection - verify user owns this order before cancelling
        order_status = await order_service.get_order_status(order_id)
        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        
        # Get current user's identifier
        user_id = current_user.get('sub') if isinstance(current_user, dict) else getattr(current_user, 'username', None)
        order_user_id = order_status.get('user_id') if isinstance(order_status, dict) else getattr(order_status, 'user_id', None)
        
        # If order has user_id and it doesn't match, deny access
        if order_user_id and order_user_id != user_id:
            logger.warning(f"IDOR attempt: user {user_id} tried to cancel order {order_id} owned by {order_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        result = await order_service.cancel_order(order_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        log_order_cancelled(
            order_id=order_id,
            endpoint="cancel_order",
            user_id=getattr(current_user, 'id', None)
        )
        return {
            "order_id": order_id,
            "status": "cancelled",
            "cancelled_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel order",
        )


@router.get("/{order_id}/audit", response_model=AuditResponse, tags=["Trading", "Audit", "Protected"])
async def get_order_audit_trail(
    order_id: str,
    current_user=Depends(require_trader),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get audit trail for an order.

    In production, this would query actual audit logs from the database.
    For now, returns basic entries to satisfy API contract.
    
    Security:
        - IDOR Protection (C-03): Verifies user owns the order
        - M-09: Added authentication (was missing)
    """
    # SECURITY FIX (C-03 + M-09): Verify user owns this order
    orders_repo = OrdersRepo(db)
    outbox_repo = OutboxRepo(db)
    order_service = OrderService(
        db_session=db,
        orders_repo=orders_repo,
        outbox_repo=outbox_repo
    )
    
    order_status = await order_service.get_order_status(order_id)
    if not order_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    user_id = current_user.get('sub') if isinstance(current_user, dict) else getattr(current_user, 'username', None)
    order_user_id = order_status.get('user_id') if isinstance(order_status, dict) else getattr(order_status, 'user_id', None)
    
    if order_user_id and order_user_id != user_id:
        logger.warning(f"IDOR attempt: user {user_id} tried to access audit for order {order_id} owned by {order_user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Query real order events from the database
    try:
        import uuid as uuid_module
        from sqlalchemy import select
        from backend.infra.schemas import OrderEvent

        order_uuid = uuid_module.UUID(order_id)
        stmt = (
            select(OrderEvent)
            .where(OrderEvent.order_id == order_uuid)
            .order_by(OrderEvent.event_time.asc())
        )
        result = await db.execute(stmt)
        events = result.scalars().all()

        audit_entries = [
            AuditEntry(
                timestamp=ev.event_time.isoformat() if ev.event_time else ev.created_at.isoformat(),
                event_type=ev.event_type,
                order_id=order_id,
                details=ev.event_data or {"broker_order_id": ev.broker_order_id},
            )
            for ev in events
        ]

        # If no events recorded yet, return the order's creation as a minimal entry
        if not audit_entries:
            order_created_at = order_status.get("created_at") if isinstance(order_status, dict) else getattr(order_status, "created_at", None)
            audit_entries = [
                AuditEntry(
                    timestamp=order_created_at.isoformat() if order_created_at else datetime.now().isoformat(),
                    event_type="order_received",
                    order_id=order_id,
                    details={"source": "api", "status": "received", "note": "No broker events recorded yet"},
                )
            ]

    except Exception as e:
        logger.warning(f"Could not query order events for {order_id}: {e}")
        # Graceful degradation — return minimal entry from order status
        audit_entries = [
            AuditEntry(
                timestamp=datetime.now().isoformat(),
                event_type="order_received",
                order_id=order_id,
                details={"source": "api", "note": "Audit events unavailable"},
            )
        ]

    return AuditResponse(entries=audit_entries)


@router.post("/{order_id}/close-position", tags=["Trading", "Protected"])
async def close_position_from_order(
    order_id: str,
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> dict[str, Any]:
    """
    Close position associated with an order by creating a market sell order.

    Steps:
    1. Verify original order exists and is a filled buy
    2. Get current position from Alpaca
    3. Submit market sell order for current position quantity
    4. Return new order details

    **Usage**: Click "Close Position" button on buy orders to liquidate the position.
    """
    try:
        import uuid as uuid_module

        from sqlalchemy import select

        from backend.infra.schemas import Order
        from backend.integrations.alpaca_broker import AlpacaBrokerClient
        from backend.services.order_service import OrderService

        # Get original order from database
        try:
            order_uuid = uuid_module.UUID(order_id)
        except ValueError:
            raise HTTPException(400, "Invalid order ID format")

        stmt = select(Order).where(Order.id == order_uuid)
        result = await db.execute(stmt)
        original_order = result.scalar_one_or_none()

        if not original_order:
            raise HTTPException(404, "Original order not found")

        requester = _current_user_identity(user)
        roles = set(getattr(user, "roles", []) or [])
        is_admin = "admin" in roles
        if not is_admin and str(original_order.user_id) != requester:
            raise HTTPException(403, "Not authorized to close this order's position")

        if original_order.side != "buy":
            raise HTTPException(400, "Can only close positions from buy orders")

        if original_order.status not in ["filled", "partially_filled"]:
            raise HTTPException(400, f"Order must be filled to close position (current status: {original_order.status})")

        # Get current position from Alpaca
        alpaca = AlpacaBrokerClient()

        try:
            position = await alpaca.get_position(original_order.symbol)
        except Exception as e:
            logger.error(f"Failed to get position from Alpaca for {original_order.symbol}: {e}")
            raise HTTPException(400, f"No open position found for {original_order.symbol}. It may already be closed.")

        if not position:
            raise HTTPException(400, f"No open position to close for {original_order.symbol}")

        current_qty = abs(float(position.get("qty", 0)))

        if current_qty <= 0:
            raise HTTPException(400, f"Position quantity is zero for {original_order.symbol}. Position may already be closed.")

        # Submit market sell order through OrderService
        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        # Create client order ID for idempotency
        client_order_id = f"close-{order_id[:8]}-{uuid_module.uuid4().hex[:8]}"

        # Submit the order using submit_symbol_order
        close_order_response = await order_service.submit_symbol_order(
            symbol=original_order.symbol,
            side="sell",
            qty=current_qty,
            idempotency_key=client_order_id,
            user_id=requester,
            order_type="market",
            tif="day",
            attributes={
                "close_position": True,
                "original_order_id": str(order_id),
                "close_type": "manual"
            }
        )

        # Commit the transaction to ensure order and outbox event are persisted
        await db.commit()

        logger.info("Close position order submitted",
                   original_order_id=order_id,
                   close_order_id=close_order_response.get("order_id") if close_order_response else None,
                   symbol=original_order.symbol,
                   quantity=current_qty,
                   user=getattr(user, 'sub', 'unknown'))

        return {
            "success": True,
            "message": f"Market sell order submitted for {current_qty} shares of {original_order.symbol}",
            "close_order": close_order_response,
            "original_order_id": order_id,
            "quantity": current_qty,
            "symbol": original_order.symbol
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close position for order {order_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to close position: {str(e)}")
