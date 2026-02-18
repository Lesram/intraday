"""
Trading Signals API routes.
Handles deterministic signal generation and retrieval operations.
"""

import asyncio
from datetime import datetime
import time
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.signals import SignalRequest as SchemaSignalRequest
from backend.api.schemas.signals import SignalResponse as SchemaSignalResponse
from backend.config import get_settings
from backend.infra.db import get_db_session
from backend.infra.outbox import OutboxRepo
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.security import get_current_user
from backend.services.order_service import OrderService
from backend.strategies.basic import BasicStrategy
from backend.utils.logger import get_event_logger, get_logger, log_order_submitted

logger = get_logger(__name__)
event_logger = get_event_logger("signals")

router = APIRouter(prefix="/signals", tags=["Trading Signals"])


# Request Models
class SignalRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    signal_strength: float = Field(..., description="Signal strength")
    timestamp: str = Field(..., description="Signal timestamp")
    features: dict[str, float] = Field(default_factory=dict, description="Signal features")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Signal metadata")


class BatchSignalsRequest(BaseModel):
    """Batch signals request for multiple symbols."""
    symbols: list[str] = Field(..., description="List of trading symbols")
    lookback: int = Field(default=200, ge=50, le=1000, description="Historical data lookback period")


# Response Models - Use schema version for new endpoints
# Keep legacy SignalResponse for backward compatibility
class LegacySignalResponse(BaseModel):
    """Legacy trading signal response for backward compatibility."""
    symbol: str
    signal_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    target_price: float = None
    position_size: float = None
    timestamp: str
    metadata: dict[str, Any] = {}

# Use the new schema version as primary SignalResponse
SignalResponse = SchemaSignalResponse

# Use the new schema version as primary SignalResponse
SignalResponse = SchemaSignalResponse


class MultiSignalsResponse(BaseModel):
    """Multiple signals response."""
    signals: dict[str, Any]
    timestamp: str


class AdvancedSignalsResponse(BaseModel):
    """Advanced signals with features and risk metrics."""
    signals: dict[str, Any]
    features: dict[str, Any] = None
    risk_metrics: dict[str, Any] = None
    timestamp: str


class ActOnSignalRequest(BaseModel):
    """Request model for act-on-signal endpoint."""
    symbol: str = Field(..., description="Trading symbol")
    lookback: int = Field(default=200, ge=50, le=1000, description="Historical data lookback period")
    size_mode: str = Field(default="fixed", description="Position sizing mode: 'fixed' or 'risk'")
    fixed_qty: float = Field(default=100.0, gt=0, description="Fixed quantity for 'fixed' size mode")
    risk_budget_pct: float = Field(default=0.01, gt=0, le=0.1, description="Risk budget as portfolio percentage for 'risk' mode")
    portfolio_value: float = Field(default=100000.0, gt=0, description="Portfolio value for risk-based sizing")


class ActOnSignalResponse(BaseModel):
    """Response model for act-on-signal endpoint."""
    symbol: str
    action: str  # "buy", "sell", "hold"
    signal: dict[str, Any]
    order: dict[str, Any] | None = None  # Order details if action is buy/sell
    timestamp: str


# Service Dependencies
async def fetch_closes(symbol: str, client, lookback: int = 200) -> list[float]:
    """
    Fetch historical close prices for a symbol.

    Args:
        symbol: Trading symbol
        client: Market data client (Alpaca or mock)
        lookback: Number of historical periods to fetch

    Returns:
        List of close prices (oldest to newest)
    """
    try:
        # Check if this is the real Alpaca data client
        if hasattr(client, 'get_historical_closes'):
            # Use Alpaca data client method directly
            close_prices = await client.get_historical_closes(symbol, lookback=lookback, timeframe="1Day")
            logger.info(f"Fetched {len(close_prices)} close prices for {symbol} from Alpaca")
            return close_prices
        else:
            # Use legacy mock client interface
            price_data = await client.get_historical_data(
                symbol, timeframe="1Day", limit=lookback
            )

            if hasattr(price_data, 'empty') and price_data.empty:
                logger.warning(f"No price data available for {symbol}")
                return []

            # Extract close prices as list
            if hasattr(price_data, 'close'):
                close_prices = price_data['close'].tolist()
            elif isinstance(price_data, dict) and 'close' in price_data:
                close_prices = price_data['close']
            else:
                logger.warning(f"Unexpected price data format for {symbol}")
                return []

            logger.info(f"Fetched {len(close_prices)} close prices for {symbol} from mock")
            return close_prices

    except Exception as e:
        logger.error(f"Error fetching close prices for {symbol}: {e}")
        return []


def get_market_data_client():
    """Get market data client based on settings.

    Defaults to real Alpaca data. Mock client is used only when
    USE_MOCK_DATA is explicitly set to True (e.g. in CI/testing).
    """
    settings = get_settings()

    # Use real data by default; mock only when explicitly requested
    use_mock = getattr(settings, 'USE_MOCK_DATA', False)

    if use_mock:
        return get_mock_alpaca_client()
    else:
        # Use real Alpaca data client
        try:
            from backend.integrations.alpaca_data import get_alpaca_data_client
            return get_alpaca_data_client()
        except ImportError as e:
            logger.warning(f"AlpacaDataClient not available, falling back to mock: {e}")
            return get_mock_alpaca_client()


def get_mock_alpaca_client():
    """Get mock Alpaca client with deterministic (but realistic) data.

    Used ONLY when USE_MOCK_DATA=True (CI/testing) or when the real
    Alpaca integration is unavailable.  All randomness is seeded from
    the symbol hash so results are reproducible.
    """
    import numpy as np
    import pandas as pd

    class MockAlpacaClient:
        """Deterministic mock market-data client for CI/testing."""

        async def get_historical_data(self, symbol: str, timeframe: str, limit: int):
            """Generate deterministic OHLCV data seeded by symbol hash."""
            seed = hash(symbol) % 1000000
            rng = np.random.default_rng(seed)

            base_price = 100 + (seed % 200)
            dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')

            # Geometric Brownian Motion with mean-reversion (Ornstein–Uhlenbeck)
            mu = 0.0002        # slight daily drift
            sigma = 0.015      # 1.5% daily vol (realistic equity)
            theta = 0.05       # mean-reversion speed
            prices = [float(base_price)]

            for i in range(1, limit):
                log_ret = mu - theta * (np.log(prices[-1] / base_price)) + sigma * rng.standard_normal()
                prices.append(prices[-1] * np.exp(log_ret))

            prices_arr = np.array(prices)
            intraday_spread = rng.uniform(0.002, 0.008, size=limit)
            highs = prices_arr * (1 + intraday_spread)
            lows = prices_arr * (1 - intraday_spread)
            volumes = rng.integers(50_000, 500_000, size=limit)

            return pd.DataFrame({
                'open': prices_arr * (1 + rng.normal(0, 0.001, limit)),
                'high': highs,
                'low': lows,
                'close': prices_arr,
                'volume': volumes,
            }, index=dates)

    return MockAlpacaClient()


def get_basic_strategy() -> BasicStrategy:
    """Get configured BasicStrategy instance with production-grade thresholds."""
    return BasicStrategy(
        rsi_buy=30,    # Standard oversold threshold
        rsi_sell=70,   # Standard overbought threshold
        sma_fast=20,
        sma_slow=50,
        tp_pct=2.0,
        sl_pct=1.0
    )


def get_authenticated_user(current_user=Depends(get_current_user)):
    """Get authenticated user for protected endpoints"""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )
    return current_user


async def get_order_service(request: Request):
    """FastAPI dependency that provides an OrderService bound to a request-scoped DB session."""
    # Get sessionmaker from app state (configured during app lifespan)
    sessionmaker = getattr(request.app.state, 'sessionmaker', None)

    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database session not configured")

    # Normal path: create a session per request and bind real repositories.
    async with sessionmaker() as session:
        service = OrderService(
            db_session=session,
            sessionmaker=sessionmaker,
            orders_repo=OrdersRepo(session),
            outbox_repo=OutboxRepo(session),
        )
        try:
            yield service
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Route Handlers
@router.get(
    "/{symbol}",
    response_model=SignalResponse,
    tags=["Trading Signals"]
)
async def get_trading_signal(
    symbol: str,
    current_user=Depends(get_authenticated_user),
):
    """Get deterministic trading signal for a specific symbol"""
    time.time()

    try:
        # Get market data client
        client = get_market_data_client()

        # Fetch close prices
        close_prices = await fetch_closes(symbol, client, lookback=200)

        if not close_prices:
            raise HTTPException(
                status_code=404,
                detail=f"No market data available for {symbol}"
            )

        # Generate signal using BasicStrategy
        strategy = get_basic_strategy()
        decision = strategy.decide(close_prices=close_prices)

        # Log structured event using standardized logger
        event_logger.signal_decided(
            symbol=symbol,
            action=decision["action"],
            confidence=decision["confidence"],
            user_id=getattr(current_user, 'id', None),
            strategy="basic_rsi_sma",
            reason=decision["reason"],
            endpoint="single_symbol"
        )

        # Use from_decision for consistency and compatibility
        return SignalResponse.from_decision(symbol, decision)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/",
    response_model=MultiSignalsResponse,
    tags=["Trading Signals"],
)
async def get_all_signals(
    symbols: str = "AAPL,GOOGL,MSFT,TSLA,NVDA",
    current_user=Depends(get_authenticated_user),
):
    """Get deterministic trading signals for multiple symbols with async batch processing"""
    try:
        # Parse symbol list
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        if not symbol_list:
            raise HTTPException(status_code=400, detail="No valid symbols provided")

        # Get market data client and strategy
        client = get_market_data_client()
        strategy = get_basic_strategy()

        # Fetch closes for all symbols concurrently
        close_price_tasks = [
            fetch_closes(symbol, client, lookback=200)
            for symbol in symbol_list
        ]

        # Wait for all data fetching to complete
        close_prices_results = await asyncio.gather(*close_price_tasks, return_exceptions=True)

        # Process signals for each symbol
        signals_map: dict[str, Any] = {}

        for i, symbol in enumerate(symbol_list):
            try:
                close_prices = close_prices_results[i]

                if isinstance(close_prices, Exception):
                    logger.warning(f"Data fetch failed for {symbol}: {close_prices}")
                    signals_map[symbol] = {"error": "data_fetch_failed"}
                    continue

                if not close_prices:
                    signals_map[symbol] = {"error": "no_data_available"}
                    continue

                # Generate signal
                decision = strategy.decide(close_prices=close_prices)

                signals_map[symbol] = {
                    "action": decision["action"],
                    "confidence": decision["confidence"],
                    "tp_pct": decision["tp_pct"],
                    "sl_pct": decision["sl_pct"],
                    "reason": decision["reason"]
                }

                # Log each signal decision using standardized logger
                event_logger.signal_decided(
                    symbol=symbol,
                    action=decision["action"],
                    confidence=decision["confidence"],
                    user_id=getattr(current_user, 'id', None),
                    strategy="basic_rsi_sma",
                    reason=decision["reason"],
                    endpoint="batch_symbols",
                    batch=True
                )

            except Exception as e:
                logger.error(f"Error processing signal for {symbol}: {e}")
                signals_map[symbol] = {"error": str(e)}

        return MultiSignalsResponse(
            signals=signals_map,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.exception(f"Error in get_all_signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/batch",
    response_model=dict[str, SignalResponse],
    tags=["Trading Signals", "Protected"],
)
async def get_batch_signals(
    request: BatchSignalsRequest,
    current_user=Depends(get_authenticated_user),
):
    """
    Get deterministic trading signals for multiple symbols with configurable lookback.
    Supports async batch processing for improved performance.
    """
    try:
        symbol_list = [s.strip().upper() for s in request.symbols if s.strip()]

        if not symbol_list:
            raise HTTPException(status_code=400, detail="No valid symbols provided")

        if len(symbol_list) > 50:
            raise HTTPException(status_code=400, detail="Too many symbols (max 50)")

        # Get market data client and strategy
        client = get_market_data_client()
        strategy = get_basic_strategy()

        # Fetch closes for all symbols concurrently
        close_price_tasks = [
            fetch_closes(symbol, client, lookback=request.lookback)
            for symbol in symbol_list
        ]

        # Wait for all data fetching to complete
        close_prices_results = await asyncio.gather(*close_price_tasks, return_exceptions=True)

        # Process signals for each symbol
        signals_map: dict[str, Any] = {}

        for i, symbol in enumerate(symbol_list):
            try:
                close_prices = close_prices_results[i]

                if isinstance(close_prices, Exception):
                    logger.warning(f"Data fetch failed for {symbol}: {close_prices}")
                    signals_map[symbol] = {"error": "data_fetch_failed"}
                    continue

                if not close_prices:
                    signals_map[symbol] = {"error": "no_data_available"}
                    continue

                # Generate signal and create SignalResponse
                decision = strategy.decide(close_prices=close_prices)

                # Create SignalResponse using from_decision method
                signals_map[symbol] = SignalResponse.from_decision(symbol, decision)

                # Log each signal decision using standardized logger
                event_logger.signal_decided(
                    symbol=symbol,
                    action=decision["action"],
                    confidence=decision["confidence"],
                    user_id=getattr(current_user, 'id', None),
                    strategy="basic_rsi_sma",
                    reason=decision["reason"],
                    lookback=request.lookback,
                    endpoint="batch_advanced",
                    batch=True
                )

            except Exception as e:
                logger.error(f"Error processing signal for {symbol}: {e}")
                # For errors, create a hold signal with low confidence
                error_decision = {
                    "action": "hold",
                    "confidence": 0.0,
                    "tp_pct": 0.0,
                    "sl_pct": 0.0,
                    "reason": f"Error: {str(e)}"
                }
                signals_map[symbol] = SignalResponse.from_decision(symbol, error_decision)

        return signals_map

    except Exception as e:
        logger.exception(f"Error in get_batch_signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=SignalResponse)
async def create_signal(
    signal_request: SchemaSignalRequest,
    current_user=Depends(get_authenticated_user)
):
    """Create a new trading signal."""
    try:
        # Generate signal ID
        signal_id = str(uuid.uuid4())

        # Log signal creation
        logger.info(
            "SIGNAL_CREATED",
            extra={
                "signal_id": signal_id,
                "symbol": signal_request.symbol,
                "confidence": signal_request.confidence,
                "user_id": getattr(current_user, 'id', None)
            }
        )

        # Convert signal_request to decision format and return SignalResponse
        decision_dict = {
            "action": signal_request.signal_type.lower(),  # Convert BUY/SELL/HOLD to lowercase
            "confidence": signal_request.confidence,
            "tp_pct": 0.02,  # Default 2% take profit
            "sl_pct": 0.01,  # Default 1% stop loss
            "timestamp": signal_request.timestamp or datetime.utcnow().isoformat(),
            "reason": f"User submitted signal {signal_id}"
        }

        return SignalResponse.from_decision(signal_request.symbol, decision_dict)

    except Exception as e:
        logger.error(f"Error creating signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/act", response_model=ActOnSignalResponse)
async def act_on_signal(
    request: ActOnSignalRequest,
    current_user=Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session)
) -> ActOnSignalResponse:
    """
    Generate signal and act on it by submitting orders.

    This endpoint bridges the strategy layer with the order execution layer:
    1. Fetches historical data for the symbol
    2. Runs BasicStrategy.decide() to get trading signal
    3. If action is buy/sell, calculates position size and submits order
    4. Returns both signal and order details in response

    Size modes:
    - 'fixed': Use request.fixed_qty directly
    - 'risk': Calculate quantity based on risk_budget_pct and stop loss
    """
    try:
        symbol = request.symbol.upper().strip()
        timestamp = datetime.now().isoformat()

        # Get market data client and fetch historical closes
        client = get_market_data_client()
        closes = await fetch_closes(symbol, client, request.lookback)

        if not closes or len(closes) < 50:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient historical data for {symbol}"
            )

        # Run strategy to get signal
        strategy = get_basic_strategy()
        decision = strategy.decide(closes=closes)

        signal_data = {
            "symbol": symbol,
            "action": decision["action"],
            "confidence": decision["confidence"],
            "reason": decision.get("reason", ""),
            "indicators": decision.get("indicators", {}),
            "lookback": request.lookback
        }

        # Log signal decision
        event_logger.signal_decided(
            symbol=symbol,
            action=decision["action"],
            confidence=decision["confidence"],
            user_id=getattr(current_user, 'id', None),
            strategy="basic_rsi_sma",
            reason=decision["reason"],
            lookback=request.lookback,
            endpoint="act_on_signal"
        )

        # If signal is hold, return without creating order
        if decision["action"] == "hold":
            return ActOnSignalResponse(
                symbol=symbol,
                action="hold",
                signal=signal_data,
                order=None,
                timestamp=timestamp
            )

        # Calculate position size based on size_mode
        if request.size_mode == "fixed":
            quantity = request.fixed_qty
        elif request.size_mode == "risk":
            # Risk-based position sizing
            # Use stop loss percentage from strategy and risk budget
            sl_pct = strategy.sl_pct / 100.0  # Convert to decimal
            risk_amount = request.portfolio_value * request.risk_budget_pct

            # Estimate current price (use last close)
            current_price = closes[-1]

            # Calculate quantity: risk_amount / (price * sl_pct)
            quantity = risk_amount / (current_price * sl_pct)
            quantity = max(1.0, round(quantity, 2))  # Minimum 1 share
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid size_mode: {request.size_mode}. Must be 'fixed' or 'risk'"
            )

        # Apply production guardrails before order submission
        try:
            from decimal import Decimal

            from backend.infra.guardrails import validate_order_guardrails

            # Check if current user is admin (simplified check)
            user_id = getattr(current_user, 'id', 'system')
            is_admin = getattr(current_user, 'username', '') == 'admin'  # Simplified admin check

            # Validate against guardrails
            guardrail_result = await validate_order_guardrails(
                symbol=symbol,
                side="buy" if decision["action"] == "buy" else "sell",
                qty=Decimal(str(quantity)),
                order_type="market",
                user_id=user_id,
                is_admin=is_admin,
                risk_override=False  # Not exposed in this endpoint yet
            )

            if not guardrail_result.allowed:
                # Log guardrail violation
                violation_codes = [v['code'] for v in guardrail_result.violations]
                logger.warning("Order blocked by guardrails",
                              symbol=symbol,
                              side="buy" if decision["action"] == "buy" else "sell",
                              qty=quantity,
                              violations=violation_codes)

                # Return error response
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "GUARDRAIL_VIOLATION",
                        "message": "Order blocked by risk management guardrails",
                        "violations": guardrail_result.violations,
                        "details": guardrail_result.details
                    }
                )

            # Log any warnings (admin overrides)
            if guardrail_result.warnings:
                warning_codes = [w['code'] for w in guardrail_result.warnings]
                logger.info("Order allowed with guardrail warnings",
                           symbol=symbol,
                           warnings=warning_codes)

        except ImportError:
            logger.warning("Guardrails module not available, proceeding without validation")

        # Generate idempotency key
        idempotency_key = f"act-{symbol}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

        # Prepare order data
        side = "buy" if decision["action"] == "buy" else "sell"
        order_data = {
            "symbol": symbol,
            "side": side,
            "qty": quantity,
            "order_type": "market",
            "tif": "ioc",  # Immediate or Cancel
            "idempotency_key": idempotency_key,
            "attributes": {
                "user_id": getattr(current_user, 'id', 'system'),
                "source": "act_on_signal",
                "strategy": "basic_rsi_sma",
                "signal_confidence": decision["confidence"],
                "size_mode": request.size_mode,
                "risk_budget_pct": request.risk_budget_pct if request.size_mode == "risk" else None
            }
        }

        # Create OrderService with session and repositories
        try:
            orders_repo = OrdersRepo(db)
            outbox_repo = OutboxRepo(db)
            order_service = OrderService(
                db_session=db,
                orders_repo=orders_repo,
                outbox_repo=outbox_repo
            )

            # Submit order through OrderService
            order_result = await order_service.submit_order_async(order_data)

            # Check if order submission failed or returned None
            if not order_result:
                raise HTTPException(
                    status_code=500,
                    detail="Order submission failed - no result returned from order service"
                )

            # Record order in guardrails for daily tracking
            try:
                from decimal import Decimal

                from backend.infra.guardrails import OrderRequest, get_guardrails

                guardrails = get_guardrails()
                order_request = OrderRequest(
                    symbol=symbol,
                    side=side,
                    qty=Decimal(str(quantity)),
                    order_type="market",
                    user_id=user_id,
                    is_admin=is_admin
                )

                # Estimate notional value for tracking
                estimated_price = await guardrails._get_estimated_price(symbol)
                estimated_notional = Decimal(str(quantity)) * estimated_price

                guardrails.record_order_submitted(order_request, estimated_notional)

            except Exception as e:
                logger.warning("Failed to record order in guardrails tracking",
                              error=str(e),
                              order_id=order_result.get("order_id"))

        except Exception as order_error:
            # Log detailed error information for debugging
            logger.error(f"OrderService creation or order submission failed: {order_error}")
            logger.error(f"OrderService error type: {type(order_error).__name__}")
            logger.error(f"Database session state: {db}")

            # Return a mock order_result to prevent Pydantic validation error
            # This allows us to see the actual error instead of validation error
            order_result = {
                "status": "failed",
                "order_id": "error-" + str(uuid.uuid4())[:8],
                "symbol": symbol,
                "qty": quantity,
                "side": side,
                "idempotency_key": idempotency_key,
                "submitted_at": timestamp,
                "error": str(order_error)
            }

        # Log order submission
        log_order_submitted(
            order_id=order_result.get("order_id"),
            symbol=symbol,
            side=side,
            qty=quantity,
            user_id=getattr(current_user, 'id', None),
            idempotency_key=idempotency_key,
            status=order_result.get("status"),
            endpoint="act_on_signal"
        )

        order_details = {
            "order_id": order_result.get("order_id"),
            "status": order_result.get("status"),
            "symbol": symbol,
            "side": side,
            "qty": quantity,
            "order_type": "market",
            "tif": "ioc",
            "idempotency_key": idempotency_key,
            "submitted_at": order_result.get("submitted_at", timestamp),
            "size_mode": request.size_mode
        }

        return ActOnSignalResponse(
            symbol=symbol,
            action=decision["action"],
            signal=signal_data,
            order=order_details,
            timestamp=timestamp
        )

    except HTTPException:
        raise
    except Exception as e:
        import os
        import traceback
        logger.error(f"Error in act_on_signal for {request.symbol}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.error(f"Environment check - ALPACA_API_KEY_ID present: {bool(os.getenv('ALPACA_API_KEY_ID'))}")
        logger.error(f"Environment check - USE_MOCK_BROKER: {os.getenv('USE_MOCK_BROKER', 'not_set')}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process signal and execute order: {str(e)}"
        )
