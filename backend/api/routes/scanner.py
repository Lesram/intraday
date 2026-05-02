"""
Market Scanner API Endpoints

Provides REST API for scanning and filtering stocks based on technical and fundamental criteria.

Features:
- Scan market with multiple filters
- Filter by price, volume, indicators (RSI, MACD, etc.)
- Predefined scan presets
- Real-time scanning results

Phase 7 - Market Data & Charting
Created: October 16, 2025
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
import pandas as pd
from pydantic import BaseModel, Field

# Audit-I finding I-2 (2026-05-02): scanner endpoints used get_current_user
# which silently returns None on missing auth — endpoints then 500-crashed
# anonymously instead of 401-ing. Switched to get_authenticated_user which
# raises 401 cleanly when no creds are present.
from backend.infra.security import (
    get_authenticated_user as get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanner", tags=["scanner"])

# ============================================================================
# ENUMS
# ============================================================================

class MACDSignal(str, Enum):
    ANY = "any"
    BULLISH = "bullish"
    BEARISH = "bearish"

class MovingAverageCrossover(str, Enum):
    NONE = "none"
    GOLDEN_CROSS = "golden_cross"  # 50 SMA crosses above 200 SMA
    DEATH_CROSS = "death_cross"    # 50 SMA crosses below 200 SMA

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ScanFilters(BaseModel):
    """Filter criteria for market scanner"""
    # Price filters
    price_min: float | None = Field(None, description="Minimum price", ge=0)
    price_max: float | None = Field(None, description="Maximum price", ge=0)

    # Volume filters
    volume_min: int | None = Field(None, description="Minimum volume", ge=0)
    volume_spike: float | None = Field(None, description="Volume spike multiplier (e.g., 2.0 = 2x avg volume)", ge=1.0)

    # RSI filters
    rsi_min: float | None = Field(None, description="Minimum RSI", ge=0, le=100)
    rsi_max: float | None = Field(None, description="Maximum RSI", ge=0, le=100)

    # MACD filters
    macd_signal: MACDSignal = Field(MACDSignal.ANY, description="MACD signal type")

    # Moving Average filters
    ma_crossover: MovingAverageCrossover = Field(MovingAverageCrossover.NONE, description="MA crossover type")
    above_sma_50: bool | None = Field(None, description="Price above 50 SMA")
    above_sma_200: bool | None = Field(None, description="Price above 200 SMA")

    # Gap filters
    gap_up: bool | None = Field(None, description="Gap up from previous close")
    gap_down: bool | None = Field(None, description="Gap down from previous close")
    gap_percentage: float | None = Field(1.0, description="Minimum gap percentage", ge=0)

    # ATR filter
    atr_multiplier: float | None = Field(None, description="ATR multiplier for volatility", ge=0)

    # Results
    limit: int = Field(50, description="Maximum results to return", ge=1, le=100)

class ScanResult(BaseModel):
    """Single scan result"""
    symbol: str
    price: float
    change: float
    change_percent: float
    volume: int
    avg_volume: int | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    atr: float | None = None
    score: float = Field(description="Match score (0-100)")
    signals: list[str] = Field(default_factory=list, description="Matched signals")

class ScanResponse(BaseModel):
    """Scan results response"""
    results: list[ScanResult]
    total: int
    scan_time: float
    filters_applied: int

class ScanPreset(BaseModel):
    """Predefined scan configuration"""
    name: str
    description: str
    filters: ScanFilters

# ============================================================================
# MOCK DATA (Replace with real data source)
# ============================================================================

# Popular symbols to scan
SCANNABLE_SYMBOLS = [
    'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'WMT',
    'UNH', 'JNJ', 'PG', 'MA', 'HD', 'DIS', 'PYPL', 'BAC', 'ADBE', 'CRM',
    'NFLX', 'CMCSA', 'XOM', 'VZ', 'KO', 'PEP', 'T', 'INTC', 'CSCO', 'PFE',
    'ABT', 'MRK', 'TMO', 'COST', 'AVGO', 'NKE', 'CVX', 'MCD', 'DHR', 'LLY',
    'TXN', 'NEE', 'UNP', 'ORCL', 'PM', 'BMY', 'QCOM', 'LIN', 'HON', 'AMD'
]

async def get_real_market_data(symbol: str) -> dict[str, Any] | None:
    """✅ REAL DATA: Fetch actual market data from Alpaca"""
    from datetime import datetime
    import os

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from backend.services.quote_manager import get_quote_manager

    try:
        quote_manager = get_quote_manager()

        # Get current quote
        quote = await quote_manager.get_quote(symbol)
        if not quote:
            return None

        # Get previous day's close for change calculation
        alpaca_client = StockHistoricalDataClient(
            api_key=os.getenv('ALPACA_API_KEY_ID'),
            secret_key=os.getenv('ALPACA_API_SECRET_KEY')
        )

        # Get last 2 days of data
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Day),
            start=datetime.now(UTC) - timedelta(days=7),
            limit=10
        )

        response = alpaca_client.get_stock_bars(request)

        # Check response format (SDK version compatibility)
        bars_data = None
        if response and hasattr(response, 'data'):
            bars_data = response.data.get(symbol)
        elif response and symbol in response:
            bars_data = response[symbol]

        if not bars_data or len(bars_data) < 2:
            return None

        bars = list(bars_data)
        today_bar = bars[-1]
        prev_bar = bars[-2]

        # Calculate change
        current_price = quote.last
        prev_close = float(prev_bar.close)
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100 if prev_close > 0 else 0

        # Calculate average volume (last 20 days)
        avg_volume = sum(float(bar.volume) for bar in bars) / len(bars)

        return {
            'symbol': symbol,
            'price': current_price,
            'change': round(change, 2),
            'change_percent': round(change_percent, 2),
            'volume': int(today_bar.volume),
            'avg_volume': int(avg_volume),
            'open': float(today_bar.open),
            'high': float(today_bar.high),
            'low': float(today_bar.low),
            'prev_close': prev_close,
        }

    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
        return None


async def calculate_indicators_for_symbol(symbol: str, bars_data: list = None) -> dict[str, float] | None:
    """✅ REAL DATA: Calculate real technical indicators using pandas_ta"""
    from datetime import datetime, timedelta
    import os

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    try:
        # Get historical bars if not provided
        if not bars_data:
            alpaca_client = StockHistoricalDataClient(
                api_key=os.getenv('ALPACA_API_KEY_ID'),
                secret_key=os.getenv('ALPACA_API_SECRET_KEY')
            )

            # Get 250 days for 200 SMA calculation
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(1, TimeFrameUnit.Day),
                start=datetime.now(UTC) - timedelta(days=365),
                limit=250
            )

            response = alpaca_client.get_stock_bars(request)

            # Check response format (SDK version compatibility)
            if response and hasattr(response, 'data'):
                bars_data = list(response.data.get(symbol, []))
            elif response and symbol in response:
                bars_data = list(response[symbol])
            else:
                return None

            if not bars_data:
                return None

        # Convert to DataFrame
        df = pd.DataFrame([{
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': int(bar.volume)
        } for bar in bars_data])

        if len(df) < 50:  # Need minimum data
            return None

        # Calculate indicators using pandas_ta
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.atr(length=14, append=True)

        # Get latest values
        latest = df.iloc[-1]

        return {
            'rsi': round(float(latest.get('RSI_14', 50)), 2),
            'macd': round(float(latest.get('MACD_12_26_9', 0)), 4),
            'macd_signal': round(float(latest.get('MACDs_12_26_9', 0)), 4),
            'sma_50': round(float(latest.get('SMA_50', latest['close'])), 2),
            'sma_200': round(float(latest.get('SMA_200', latest['close'])), 2),
            'atr': round(float(latest.get('ATRr_14', 0)), 2),
        }

    except AttributeError as e:
        # V4 P-P2 (2026-05-02): pandas_ta isn't a hard dependency in
        # paper deployment. Without it, df.ta accessor is missing and
        # an AttributeError used to flood ERROR per-symbol per-scan.
        # Downgrade to a single WARNING the first time the module is
        # detected as missing; everything else is DEBUG. Other
        # exceptions still log at ERROR.
        if "ta" in str(e).lower():
            global _PANDAS_TA_WARNED
            try:
                _PANDAS_TA_WARNED  # type: ignore[name-defined]
            except NameError:
                _PANDAS_TA_WARNED = False
            if not _PANDAS_TA_WARNED:
                logger.warning(
                    "pandas_ta not installed — scanner indicators "
                    "(RSI/MACD/SMA/ATR) skipped. Install pandas_ta "
                    "to re-enable."
                )
                _PANDAS_TA_WARNED = True
            else:
                logger.debug(
                    "pandas_ta indicators skipped for %s: %s", symbol, e,
                )
        else:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error calculating indicators for {symbol}: {e}")
        return None

# ============================================================================
# SCANNING LOGIC
# ============================================================================

def apply_filters(data: dict[str, Any], indicators: dict[str, float], filters: ScanFilters) -> tuple[bool, list[str], float]:
    """
    Apply filters to a symbol's data

    Returns:
        (matches, signals, score)
    """
    matches = True
    signals = []
    score = 0.0
    max_score = 0.0

    # Price filters
    if filters.price_min is not None:
        max_score += 10
        if data['price'] >= filters.price_min:
            score += 10
            signals.append(f"Price ≥ ${filters.price_min}")
        else:
            matches = False

    if filters.price_max is not None:
        max_score += 10
        if data['price'] <= filters.price_max:
            score += 10
            signals.append(f"Price ≤ ${filters.price_max}")
        else:
            matches = False

    # Volume filters
    if filters.volume_min is not None:
        max_score += 10
        if data['volume'] >= filters.volume_min:
            score += 10
            signals.append(f"Volume ≥ {filters.volume_min:,}")
        else:
            matches = False

    if filters.volume_spike is not None and data['avg_volume']:
        max_score += 15
        if data['volume'] >= data['avg_volume'] * filters.volume_spike:
            score += 15
            signals.append(f"Volume Spike {filters.volume_spike}x")
        else:
            matches = False

    # RSI filters
    if filters.rsi_min is not None:
        max_score += 10
        if indicators['rsi'] >= filters.rsi_min:
            score += 10
            signals.append(f"RSI ≥ {filters.rsi_min}")
        else:
            matches = False

    if filters.rsi_max is not None:
        max_score += 10
        if indicators['rsi'] <= filters.rsi_max:
            score += 10
            signals.append(f"RSI ≤ {filters.rsi_max}")
            if indicators['rsi'] <= 30:
                signals.append("OVERSOLD")
                score += 5
        else:
            matches = False

    # MACD signal
    if filters.macd_signal != MACDSignal.ANY:
        max_score += 15
        macd_diff = indicators['macd'] - indicators['macd_signal']

        if filters.macd_signal == MACDSignal.BULLISH and macd_diff > 0:
            score += 15
            signals.append("MACD Bullish")
        elif filters.macd_signal == MACDSignal.BEARISH and macd_diff < 0:
            score += 15
            signals.append("MACD Bearish")
        else:
            matches = False

    # Moving Average filters
    if filters.above_sma_50 is not None:
        max_score += 10
        is_above = data['price'] > indicators['sma_50']
        if is_above == filters.above_sma_50:
            score += 10
            signals.append(f"Price {'above' if is_above else 'below'} SMA 50")
        else:
            matches = False

    if filters.above_sma_200 is not None:
        max_score += 10
        is_above = data['price'] > indicators['sma_200']
        if is_above == filters.above_sma_200:
            score += 10
            signals.append(f"Price {'above' if is_above else 'below'} SMA 200")
        else:
            matches = False

    # MA Crossover
    if filters.ma_crossover != MovingAverageCrossover.NONE:
        max_score += 20
        sma_50_above_200 = indicators['sma_50'] > indicators['sma_200']

        if filters.ma_crossover == MovingAverageCrossover.GOLDEN_CROSS and sma_50_above_200:
            score += 20
            signals.append("GOLDEN CROSS")
        elif filters.ma_crossover == MovingAverageCrossover.DEATH_CROSS and not sma_50_above_200:
            score += 20
            signals.append("DEATH CROSS")
        else:
            matches = False

    # Gap filters
    if filters.gap_up is not None:
        max_score += 15
        gap_percent = ((data['price'] - data['prev_close']) / data['prev_close']) * 100
        is_gap_up = gap_percent >= (filters.gap_percentage or 1.0)

        if is_gap_up == filters.gap_up:
            score += 15
            if is_gap_up:
                signals.append(f"Gap Up {abs(gap_percent):.2f}%")
        else:
            matches = False

    if filters.gap_down is not None:
        max_score += 15
        gap_percent = ((data['price'] - data['prev_close']) / data['prev_close']) * 100
        is_gap_down = gap_percent <= -(filters.gap_percentage or 1.0)

        if is_gap_down == filters.gap_down:
            score += 15
            if is_gap_down:
                signals.append(f"Gap Down {abs(gap_percent):.2f}%")
        else:
            matches = False

    # ATR filter
    if filters.atr_multiplier is not None:
        max_score += 10
        expected_move = indicators['atr'] * filters.atr_multiplier
        actual_move = abs(data['price'] - data['prev_close'])

        if actual_move >= expected_move:
            score += 10
            signals.append(f"Move ≥ {filters.atr_multiplier}x ATR")
        else:
            matches = False

    # Calculate percentage score
    percentage_score = (score / max_score * 100) if max_score > 0 else 0

    return matches, signals, percentage_score

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/scan", response_model=ScanResponse)
async def scan_market(
    filters: ScanFilters,
    current_user: dict = Depends(get_current_user)
):
    """
    Scan market with filters

    Args:
        filters: Scan filter criteria
        current_user: Authenticated user

    Returns:
        List of matching stocks with scores and signals

    Example:
        POST /api/v1/scanner/scan
        {
          "price_min": 50,
          "price_max": 500,
          "volume_min": 1000000,
          "rsi_min": 30,
          "rsi_max": 70,
          "macd_signal": "bullish",
          "above_sma_50": true,
          "limit": 20
        }
    """
    try:
        # Use internal scan function (shared with WebSocket)
        return await scan_market_internal(filters)
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {str(e)}"
        )

@router.get("/presets", response_model=list[ScanPreset])
async def get_scan_presets(
    user = Depends(get_current_user)
):
    """
    Get predefined scan presets

    Returns:
        List of scan presets with configurations

    Example:
        GET /api/v1/scanner/presets
    """
    presets = [
        ScanPreset(
            name="Oversold Stocks",
            description="Stocks with RSI below 30 (potentially oversold)",
            filters=ScanFilters(
                rsi_max=30,
                volume_min=1000000,
                limit=20,
            )
        ),
        ScanPreset(
            name="Overbought Stocks",
            description="Stocks with RSI above 70 (potentially overbought)",
            filters=ScanFilters(
                rsi_min=70,
                volume_min=1000000,
                limit=20,
            )
        ),
        ScanPreset(
            name="Momentum Leaders",
            description="Strong momentum with bullish MACD and RSI > 50",
            filters=ScanFilters(
                rsi_min=50,
                macd_signal=MACDSignal.BULLISH,
                above_sma_50=True,
                volume_min=2000000,
                limit=20,
            )
        ),
        ScanPreset(
            name="Breakout Candidates",
            description="High volume with gap up",
            filters=ScanFilters(
                volume_spike=2.0,
                gap_up=True,
                gap_percentage=2.0,
                limit=20,
            )
        ),
        ScanPreset(
            name="Golden Cross",
            description="50 SMA crossed above 200 SMA",
            filters=ScanFilters(
                ma_crossover=MovingAverageCrossover.GOLDEN_CROSS,
                above_sma_50=True,
                above_sma_200=True,
                limit=20,
            )
        ),
        ScanPreset(
            name="High Volume",
            description="Stocks with unusually high volume",
            filters=ScanFilters(
                volume_spike=3.0,
                volume_min=5000000,
                limit=20,
            )
        ),
        ScanPreset(
            name="Value Stocks",
            description="Lower priced stocks with moderate RSI",
            filters=ScanFilters(
                price_min=10,
                price_max=100,
                rsi_min=40,
                rsi_max=60,
                volume_min=1000000,
                limit=30,
            )
        ),
        ScanPreset(
            name="Bearish Signals",
            description="Bearish MACD with price below key moving averages",
            filters=ScanFilters(
                macd_signal=MACDSignal.BEARISH,
                above_sma_50=False,
                above_sma_200=False,
                limit=20,
            )
        ),
    ]

    return presets

@router.get("/symbols")
async def get_scannable_symbols():
    """
    Get list of symbols available for scanning

    Returns:
        List of symbol strings
    """
    return {
        "symbols": SCANNABLE_SYMBOLS,
        "count": len(SCANNABLE_SYMBOLS)
    }


# ============================================================================
# WEBSOCKET ENDPOINT - Real-Time Scanner
# ============================================================================

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect


class ScannerConnectionManager:
    """Manages WebSocket connections for real-time scanning"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.scan_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept new connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Scanner WebSocket connected: {client_id}")

    def disconnect(self, client_id: str):
        """Remove connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.scan_tasks:
            self.scan_tasks[client_id].cancel()
            del self.scan_tasks[client_id]
        logger.info(f"Scanner WebSocket disconnected: {client_id}")

    async def send_scan_results(self, client_id: str, results: ScanResponse):
        """Send scan results to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(results.model_dump())
            except Exception as e:
                logger.error(f"Failed to send scan results to {client_id}: {e}")
                self.disconnect(client_id)

    async def start_scanning(self, client_id: str, filters: ScanFilters, interval: int = 10):
        """Start continuous scanning for a client"""
        while client_id in self.active_connections:
            try:
                # Perform scan
                results = await scan_market_internal(filters)

                # Send results
                await self.send_scan_results(client_id, results)

                # Wait before next scan
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scanning loop for {client_id}: {e}")
                await asyncio.sleep(interval)

# Global connection manager
scanner_manager = ScannerConnectionManager()

async def scan_market_internal(filters: ScanFilters) -> ScanResponse:
    """✅ REAL DATA: Internal function to perform market scan with real Alpaca data"""
    start_time = datetime.now()
    results = []

    # Batch fetch quotes for all symbols (much faster than individual calls)
    from backend.services.quote_manager import get_quote_manager
    quote_manager = get_quote_manager()
    quotes_dict = await quote_manager.get_quotes(SCANNABLE_SYMBOLS)

    logger.info(f"Fetched {len(quotes_dict)} quotes for scanning")

    # Scan symbols that have quotes
    for symbol in SCANNABLE_SYMBOLS:
        if symbol not in quotes_dict:
            continue

        try:
            # Get market data (real data)
            market_data = await get_real_market_data(symbol)
            if not market_data:
                continue

            # Calculate indicators (real calculations)
            indicators = await calculate_indicators_for_symbol(symbol)
            if not indicators:
                continue

            # Apply filters
            matches, signals, score = apply_filters(market_data, indicators, filters)

            if matches:
                results.append(ScanResult(
                    symbol=symbol,
                    price=market_data['price'],
                    change=market_data['change'],
                    change_percent=market_data['change_percent'],
                    volume=market_data['volume'],
                    avg_volume=market_data.get('avg_volume'),
                    rsi=indicators.get('rsi'),
                    macd=indicators.get('macd'),
                    macd_signal=indicators.get('macd_signal'),
                    sma_50=indicators.get('sma_50'),
                    sma_200=indicators.get('sma_200'),
                    atr=indicators.get('atr'),
                    score=score,
                    signals=signals
                ))
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            continue

    # Sort by score (highest first)
    results.sort(key=lambda x: x.score, reverse=True)

    # Limit results
    results = results[:filters.limit]

    # Calculate scan time
    scan_time = (datetime.now() - start_time).total_seconds()

    # Count filters applied
    filters_applied = sum([
        filters.price_min is not None,
        filters.price_max is not None,
        filters.volume_min is not None,
        filters.volume_spike is not None,
        filters.rsi_min is not None,
        filters.rsi_max is not None,
        filters.macd_signal != MACDSignal.ANY,
        filters.ma_crossover != MovingAverageCrossover.NONE,
        filters.above_sma_50 is not None,
        filters.above_sma_200 is not None,
        filters.gap_up is not None,
        filters.gap_down is not None,
        filters.atr_multiplier is not None,
    ])

    return ScanResponse(
        results=results,
        total=len(results),
        scan_time=scan_time,
        filters_applied=filters_applied
    )

@router.websocket("/ws")
async def scanner_websocket(
    websocket: WebSocket,
    token: str | None = None
):
    """
    WebSocket endpoint for real-time market scanning.

    Client sends:
    {
        "action": "start" | "stop" | "update_filters",
        "filters": { ... },  // ScanFilters object
        "interval": 10       // Scan interval in seconds (default: 10)
    }

    Server sends:
    {
        "results": [...],    // List of ScanResult objects
        "total": 10,
        "scan_time": 0.5,
        "filters_applied": 3,
        "timestamp": "2025-10-16T..."
    }
    """
    # Generate client ID
    client_id = f"scanner_{id(websocket)}"

    # SECURITY FIX: Validate JWT token before accepting WebSocket connections
    if not token:
        await websocket.close(code=4001, reason="Authentication required: provide ?token=<jwt>")
        return

    try:
        from backend.infra.security import decode_token
        claims = decode_token(token)
        user_id = claims.get("sub", "anonymous")
        client_id = f"scanner_{user_id}_{id(websocket)}"
    except Exception:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    await scanner_manager.connect(websocket, client_id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            action = message.get('action')

            if action == 'start':
                # Start continuous scanning
                filters_dict = message.get('filters', {})
                filters = ScanFilters(**filters_dict)
                interval = message.get('interval', 10)

                # Cancel existing task if any
                if client_id in scanner_manager.scan_tasks:
                    scanner_manager.scan_tasks[client_id].cancel()

                # Start new scanning task
                task = asyncio.create_task(
                    scanner_manager.start_scanning(client_id, filters, interval)
                )
                scanner_manager.scan_tasks[client_id] = task

                # Send confirmation
                await websocket.send_json({
                    "status": "started",
                    "message": f"Scanning started with {interval}s interval"
                })

            elif action == 'stop':
                # Stop scanning
                if client_id in scanner_manager.scan_tasks:
                    scanner_manager.scan_tasks[client_id].cancel()
                    del scanner_manager.scan_tasks[client_id]

                await websocket.send_json({
                    "status": "stopped",
                    "message": "Scanning stopped"
                })

            elif action == 'update_filters':
                # Update filters and restart scanning
                filters_dict = message.get('filters', {})
                filters = ScanFilters(**filters_dict)
                interval = message.get('interval', 10)

                # Cancel and restart
                if client_id in scanner_manager.scan_tasks:
                    scanner_manager.scan_tasks[client_id].cancel()

                task = asyncio.create_task(
                    scanner_manager.start_scanning(client_id, filters, interval)
                )
                scanner_manager.scan_tasks[client_id] = task

                await websocket.send_json({
                    "status": "updated",
                    "message": "Filters updated, scanning restarted"
                })

            elif action == 'ping':
                # Heartbeat
                await websocket.send_json({
                    "status": "pong",
                    "timestamp": datetime.now().isoformat()
                })

            else:
                await websocket.send_json({
                    "status": "error",
                    "message": f"Unknown action: {action}"
                })

    except WebSocketDisconnect:
        scanner_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        scanner_manager.disconnect(client_id)


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

import csv
import io

from fastapi.responses import StreamingResponse


@router.post("/export/csv")
async def export_scan_results_csv(
    filters: ScanFilters,
    current_user: dict = Depends(get_current_user)
):
    """
    Export scan results as CSV

    Args:
        filters: Scan filter criteria
        current_user: Authenticated user

    Returns:
        CSV file with scan results
    """
    try:
        # Perform scan
        scan_response = await scan_market_internal(filters)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Symbol', 'Price', 'Change', 'Change %', 'Volume', 'Avg Volume',
            'RSI', 'MACD', 'MACD Signal', 'SMA 50', 'SMA 200', 'ATR',
            'Score', 'Signals'
        ])

        # Write data
        for result in scan_response.results:
            writer.writerow([
                result.symbol,
                result.price,
                result.change,
                result.change_percent,
                result.volume,
                result.avg_volume or '',
                result.rsi or '',
                result.macd or '',
                result.macd_signal or '',
                result.sma_50 or '',
                result.sma_200 or '',
                result.atr or '',
                result.score,
                ', '.join(result.signals)
            ])

        # Get CSV content
        output.seek(0)
        csv_content = output.getvalue()

        # Create response
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )

@router.post("/export/json")
async def export_scan_results_json(
    filters: ScanFilters,
    current_user: dict = Depends(get_current_user)
):
    """
    Export scan results as JSON

    Args:
        filters: Scan filter criteria
        current_user: Authenticated user

    Returns:
        JSON file with scan results
    """
    try:
        # Perform scan
        scan_response = await scan_market_internal(filters)

        # Create JSON response using model_dump_json
        json_content = scan_response.model_dump_json(indent=2)

        return StreamingResponse(
            iter([json_content]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    except Exception as e:
        logger.error(f"JSON export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# ============================================================================
# CUSTOM PRESETS ENDPOINTS (In-Memory Storage for MVP)
# ============================================================================

# In-memory storage for custom presets (per user)
# WARNING: Data is lost on restart. Must be migrated to database for production.
import warnings as _scanner_warnings
_scanner_warnings.warn(
    "Scanner custom_presets uses in-memory storage — data will be lost on restart. "
    "Wire to database before production deployment.",
    RuntimeWarning,
    stacklevel=1,
)
user_custom_presets: dict[str, list[dict[str, Any]]] = {}

class CustomPreset(BaseModel):
    """User's custom scan preset"""
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=200)
    filters: ScanFilters
    created_at: datetime | None = None

@router.get("/presets/custom", response_model=list[CustomPreset])
async def get_custom_presets(current_user: dict = Depends(get_current_user)):
    """
    Get user's custom scan presets

    Returns:
        List of user's custom presets
    """
    user_id = current_user.username

    presets = user_custom_presets.get(user_id, [])
    return [CustomPreset(**preset) for preset in presets]

@router.post("/presets/custom", response_model=CustomPreset)
async def create_custom_preset(
    preset: CustomPreset,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new custom scan preset

    Args:
        preset: Preset configuration
        current_user: Authenticated user

    Returns:
        Created preset with ID
    """
    user_id = current_user.username

    # Generate ID
    preset_id = f"preset_{datetime.now().timestamp()}_{id(preset)}"
    preset.id = preset_id
    preset.created_at = datetime.now()

    # Store preset
    if user_id not in user_custom_presets:
        user_custom_presets[user_id] = []

    user_custom_presets[user_id].append(preset.dict())

    logger.info(f"Created custom preset '{preset.name}' for user {user_id}")
    return preset

@router.put("/presets/custom/{preset_id}", response_model=CustomPreset)
async def update_custom_preset(
    preset_id: str,
    preset: CustomPreset,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing custom preset

    Args:
        preset_id: Preset ID to update
        preset: Updated preset data
        current_user: Authenticated user

    Returns:
        Updated preset
    """
    user_id = current_user.username

    if user_id not in user_custom_presets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found"
        )

    # Find and update preset
    presets = user_custom_presets[user_id]
    for i, p in enumerate(presets):
        if p.get('id') == preset_id:
            preset.id = preset_id
            preset.created_at = p.get('created_at')
            presets[i] = preset.dict()
            logger.info(f"Updated custom preset '{preset.name}' for user {user_id}")
            return preset

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Preset not found"
    )

@router.delete("/presets/custom/{preset_id}")
async def delete_custom_preset(
    preset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a custom preset

    Args:
        preset_id: Preset ID to delete
        current_user: Authenticated user

    Returns:
        Success message
    """
    user_id = current_user.username

    if user_id not in user_custom_presets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found"
        )

    # Find and delete preset
    presets = user_custom_presets[user_id]
    for i, p in enumerate(presets):
        if p.get('id') == preset_id:
            deleted_name = p.get('name')
            del presets[i]
            logger.info(f"Deleted custom preset '{deleted_name}' for user {user_id}")
            return {"message": f"Preset '{deleted_name}' deleted successfully"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Preset not found"
    )


