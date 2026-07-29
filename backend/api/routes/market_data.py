"""
Market Data WebSocket API Endpoint

Provides WebSocket endpoint for real-time market data streaming to frontend clients.

Endpoint: /ws/market-data
Authentication: JWT token via query parameter
Protocol: JSON messages for subscribe/unsubscribe actions

Created: October 16, 2025 - Phase 7 Day 1
"""

from datetime import UTC
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.infra.security import decode_token, get_authenticated_user  # Use existing JWT decoder
from backend.services.market_data_service import get_market_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


# Response Models
class MarketDataStatsData(BaseModel):
    """Market data statistics."""
    total_clients: int
    total_subscriptions: int
    total_messages_sent: int
    uptime_seconds: float
    alpaca_connected: bool
    service_running: bool


class MarketDataStatsResponse(BaseModel):
    """Response for market data stats endpoint."""
    status: str
    data: MarketDataStatsData


class MarketDataHealthResponse(BaseModel):
    """Response for market data health endpoint."""
    status: str
    service_running: bool
    alpaca_connected: bool


class BarDataResponse(BaseModel):
    """Single OHLCV bar in response."""
    time: str | int
    open: float
    high: float
    low: float
    close: float
    volume: int


class HistoricalBarsResponse(BaseModel):
    """Response for historical bars endpoint."""
    symbol: str
    timeframe: str
    bars: list[dict[str, Any]]
    count: int


@router.websocket("/ws")
async def market_data_websocket(
    websocket: WebSocket,
    token: str | None = Query(None, description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time market data.

    Authentication:
        Required via JWT token in query parameter: /ws?token=YOUR_JWT_TOKEN

    [Rest of docstring...]
    """

    # MUST accept connection first before we can do anything
    await websocket.accept()

    # Now authenticate AFTER accepting
    user_id = None
    try:
        if not token:
            logger.warning("WebSocket connection rejected: No token provided")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Decode and validate JWT token
        payload = decode_token(token)
        user_id = payload.get("sub") or payload.get("user_id")

        if not user_id:
            logger.warning("WebSocket connection rejected: Invalid token payload")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    logger.info(f"WebSocket connection authenticated for user {user_id}")

    # Get market data service instance
    service = get_market_data_service()

    # Register client
    client_id = None
    try:
        client_id = await service.add_client(websocket)
        logger.info(f"Client registered: {client_id} (user: {user_id})")

    except ValueError as e:
        # Max clients exceeded or other validation error
        await websocket.send_json({
            "type": "error",
            "message": str(e),
            "code": "CLIENT_LIMIT_EXCEEDED"
        })
        await websocket.close()
        logger.warning(f"Failed to register client: {e}")
        return

    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": "Failed to register client",
            "code": "REGISTRATION_FAILED"
        })
        await websocket.close()
        logger.error(f"Error registering client: {e}", exc_info=True)
        return

    # Main message handling loop
    try:
        async for message in websocket.iter_text():
            try:
                # Parse message
                import json
                data = json.loads(message)

                action = data.get("action")

                if action == "subscribe":
                    # Subscribe to symbol
                    symbol = data.get("symbol")

                    if not symbol:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Missing symbol parameter",
                            "code": "INVALID_REQUEST"
                        })
                        continue

                    try:
                        success = await service.subscribe(client_id, symbol)

                        if success:
                            logger.info(f"Client {client_id} subscribed to {symbol}")
                        else:
                            logger.warning(f"Failed to subscribe client {client_id} to {symbol}")

                    except ValueError as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e),
                            "code": "SUBSCRIPTION_FAILED"
                        })
                        logger.warning(f"Subscription failed for {client_id}: {e}")

                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to subscribe",
                            "code": "SUBSCRIPTION_ERROR"
                        })
                        logger.error(f"Error subscribing {client_id} to {symbol}: {e}", exc_info=True)

                elif action == "unsubscribe":
                    # Unsubscribe from symbol
                    symbol = data.get("symbol")

                    if not symbol:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Missing symbol parameter",
                            "code": "INVALID_REQUEST"
                        })
                        continue

                    try:
                        success = await service.unsubscribe(client_id, symbol)

                        if success:
                            logger.info(f"Client {client_id} unsubscribed from {symbol}")
                        else:
                            logger.warning(f"Failed to unsubscribe client {client_id} from {symbol}")

                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to unsubscribe",
                            "code": "UNSUBSCRIPTION_ERROR"
                        })
                        logger.error(f"Error unsubscribing {client_id} from {symbol}: {e}", exc_info=True)

                elif action == "pong":
                    # Pong response to ping (heartbeat)
                    logger.debug(f"Pong received from client {client_id}")
                    # Update last heartbeat in service
                    if client_id in service.clients:
                        from datetime import datetime
                        service.clients[client_id].last_heartbeat = datetime.now(UTC)

                elif action == "get_subscriptions":
                    # Get list of current subscriptions
                    subscriptions = service.get_subscriptions_for_client(client_id)
                    await websocket.send_json({
                        "type": "subscriptions",
                        "symbols": subscriptions
                    })
                    logger.debug(f"Sent subscriptions to client {client_id}: {subscriptions}")

                else:
                    # Unknown action
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action: {action}",
                        "code": "INVALID_ACTION"
                    })
                    logger.warning(f"Unknown action from client {client_id}: {action}")

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "code": "INVALID_JSON"
                })
                logger.warning(f"Invalid JSON from client {client_id}: {message[:200]}")

            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": "Error processing message",
                    "code": "PROCESSING_ERROR"
                })

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")

    except Exception as e:
        logger.error(f"Error in WebSocket connection for client {client_id}: {e}", exc_info=True)

    finally:
        # Cleanup: Remove client from service
        if client_id:
            await service.remove_client(client_id)
            logger.info(f"Client {client_id} removed from service")


@router.get("/stats", response_model=MarketDataStatsResponse)
async def get_market_data_stats(user = Depends(get_authenticated_user)) -> MarketDataStatsResponse:
    """
    Get market data service statistics.

    Returns current statistics about the market data service including:
    - Number of connected clients
    - Number of subscriptions
    - Total messages sent
    - Service uptime
    - Alpaca connection status

    Returns:
        dict: Service statistics
    """
    service = get_market_data_service()
    stats = service.get_stats()

    return MarketDataStatsResponse(
        status="success",
        data=MarketDataStatsData(
            total_clients=stats.total_clients,
            total_subscriptions=stats.total_subscriptions,
            total_messages_sent=stats.total_messages_sent,
            uptime_seconds=stats.uptime_seconds,
            alpaca_connected=stats.alpaca_connected,
            service_running=service.is_running
        )
    )


@router.get("/health", response_model=MarketDataHealthResponse)
async def health_check(user = Depends(get_authenticated_user)) -> MarketDataHealthResponse:
    """
    Health check endpoint for market data service.

    Returns:
        dict: Health status
    """
    service = get_market_data_service()

    is_healthy = service.is_running and service.alpaca_connected

    return MarketDataHealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        service_running=service.is_running,
        alpaca_connected=service.alpaca_connected
    )


@router.get("/bars", response_model=HistoricalBarsResponse)
async def get_historical_bars(
    symbol: str = Query(..., description="Stock symbol (e.g., AAPL)"),
    timeframe: str = Query("5m", description="Timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1D, 1W, 1M)"),
    start: str | None = Query(None, description="Start date (ISO 8601)"),
    end: str | None = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(100, ge=1, le=10000, description="Max number of bars"),
    user = Depends(get_authenticated_user)
) -> HistoricalBarsResponse:
    """
    Get historical OHLCV bars for a symbol.

    Args:
        symbol: Stock symbol
        timeframe: Bar timeframe
        start: Start date (optional)
        end: End date (optional)
        limit: Maximum bars to return (default: 100, max: 10000)

    Returns:
        dict: Historical bars data

    Example:
        GET /api/v1/market-data/bars?symbol=AAPL&timeframe=5m&limit=100
    """
    try:
        # ✅ REAL DATA: Fetch with yfinance fallback (FREE, unlimited, 15-min delayed)
        from datetime import UTC, datetime, timedelta
        import os

        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        import yfinance as yf

        from backend.services.cache import get_cache_service

        cache_service = get_cache_service()

        # Create cache key
        cache_key = f"{symbol.upper()}:{timeframe}:{start}:{end}:{limit}"

        # Check cache first (1 minute TTL for historical bars)
        cached_bars = await cache_service.get('bars', cache_key)
        if cached_bars:
            logger.debug(f"Cache hit for {cache_key}")
            return JSONResponse(content=cached_bars)

        bars = []

        # Try Alpaca first
        try:
            alpaca_client = StockHistoricalDataClient(
                api_key=os.getenv('ALPACA_API_KEY_ID'),
                secret_key=os.getenv('ALPACA_API_SECRET_KEY')
            )

            # Map timeframe to Alpaca TimeFrame
            timeframe_map = {
                '1m': TimeFrame(1, TimeFrameUnit.Minute),
                '5m': TimeFrame(5, TimeFrameUnit.Minute),
                '15m': TimeFrame(15, TimeFrameUnit.Minute),
                '30m': TimeFrame(30, TimeFrameUnit.Minute),
                '1h': TimeFrame(1, TimeFrameUnit.Hour),
                '4h': TimeFrame(4, TimeFrameUnit.Hour),
                '1D': TimeFrame(1, TimeFrameUnit.Day),
                '1W': TimeFrame(1, TimeFrameUnit.Week),
                '1M': TimeFrame(1, TimeFrameUnit.Month)
            }

            alpaca_timeframe = timeframe_map.get(timeframe, TimeFrame(5, TimeFrameUnit.Minute))

            # Calculate date range
            now = datetime.now(UTC)
            if start:
                start_date = datetime.fromisoformat(start.replace('Z', '+00:00'))
            else:
                start_date = now - timedelta(days=max(limit // 390, 7))

            if end:
                end_date = datetime.fromisoformat(end.replace('Z', '+00:00'))
            else:
                end_date = now

            # Fetch bars from Alpaca
            request = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=alpaca_timeframe,
                start=start_date,
                end=end_date,
                limit=limit
            )

            response = alpaca_client.get_stock_bars(request)

            # Check response format (SDK version compatibility)
            if response and hasattr(response, 'data') and symbol.upper() in response.data:
                alpaca_bars = response.data[symbol.upper()]
            elif response and symbol.upper() in response:
                alpaca_bars = response[symbol.upper()]
            else:
                alpaca_bars = []

            for bar in alpaca_bars:
                # Format timestamp based on timeframe
                if timeframe in ['1D', '1W', '1M']:
                    time_value = bar.timestamp.strftime("%Y-%m-%d")
                else:
                    time_value = int(bar.timestamp.timestamp())

                bars.append({
                    "time": time_value,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume)
                })

            # Smart validation based on timeframe and date range
            # For daily charts, we expect ~252 trading days per year
            # For intraday, we hit the 1000 bar limit quickly
            if timeframe in ['1D', '1W', '1M']:
                # For daily/weekly/monthly, calculate expected bars based on date range
                if start and end:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    days_diff = (end_dt - start_dt).days
                    # Approximate trading days (252 per year)
                    expected_bars = int(days_diff * 252 / 365)
                    min_acceptable = max(expected_bars * 0.5, 1)  # Accept 50%+ of expected
                else:
                    # No date range specified, accept any data
                    min_acceptable = 1

                if len(bars) >= min_acceptable:
                    logger.info(f"[SUCCESS] Alpaca: fetched {len(bars)} bars for {symbol} (expected ~{expected_bars if start and end else 'N/A'})")
                else:
                    raise Exception(f"Insufficient data from Alpaca: {len(bars)} bars (expected ~{expected_bars})")
            # For intraday charts, we're more likely to hit the 1000 limit
            # Accept data if we got at least 50 bars (reasonable minimum for indicators)
            elif len(bars) >= 50:
                logger.info(f"[SUCCESS] Alpaca: fetched {len(bars)} bars for {symbol}")
            else:
                raise Exception(f"Insufficient data from Alpaca: {len(bars)} bars (minimum 50)")

        except Exception as alpaca_error:
            logger.warning(f"[WARNING] Alpaca failed for {symbol}: {alpaca_error}")
            logger.info(f"[FALLBACK] Trying yfinance as fallback for {symbol}...")

            # FALLBACK: Use yfinance (FREE, unlimited, 15-min delayed)
            try:
                # Map timeframe to yfinance interval
                interval_map = {
                    '1m': '1m',
                    '5m': '5m',
                    '15m': '15m',
                    '30m': '30m',
                    '1h': '1h',
                    '4h': '4h',  # Not supported by yfinance, will use 1h
                    '1D': '1d',
                    '1W': '1wk',
                    '1M': '1mo'
                }

                yf_interval = interval_map.get(timeframe, '1d')

                # Calculate period or use start/end dates
                if start and end:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                else:
                    end_dt = datetime.now()
                    # Estimate period based on timeframe and limit
                    if timeframe in ['1D', '1W', '1M']:
                        days = limit if timeframe == '1D' else (limit * 7 if timeframe == '1W' else limit * 30)
                    else:
                        days = max(limit // 390, 7)  # Assume ~390 bars per day
                    start_dt = end_dt - timedelta(days=days)

                # Fetch from yfinance
                ticker = yf.Ticker(symbol.upper())
                df = ticker.history(
                    start=start_dt.strftime('%Y-%m-%d'),
                    end=end_dt.strftime('%Y-%m-%d'),
                    interval=yf_interval
                )

                if df.empty:
                    raise Exception(f"No data returned from yfinance for {symbol}")

                # Convert to bars format
                bars = []
                for timestamp, row in df.iterrows():
                    # Format timestamp based on timeframe
                    if timeframe in ['1D', '1W', '1M']:
                        time_value = timestamp.strftime("%Y-%m-%d")
                    else:
                        time_value = int(timestamp.timestamp())

                    bars.append({
                        "time": time_value,
                        "open": float(row['Open']),
                        "high": float(row['High']),
                        "low": float(row['Low']),
                        "close": float(row['Close']),
                        "volume": int(row['Volume'])
                    })

                logger.info(f"[SUCCESS] yfinance: Successfully fetched {len(bars)} bars for {symbol} (FREE, 15-min delayed)")

            except Exception as yf_error:
                logger.error(f"[ERROR] yfinance fallback also failed for {symbol}: {yf_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Both Alpaca and yfinance failed: {yf_error}"
                )

        result = HistoricalBarsResponse(
            symbol=symbol.upper(),
            timeframe=timeframe,
            bars=bars,
            count=len(bars)
        )

        # Cache result
        await cache_service.set('bars', cache_key, result.model_dump(), ttl=60)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch historical bars for {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch historical data: {str(e)}"
        )


# Export router for inclusion in main app
__all__ = ["router"]
