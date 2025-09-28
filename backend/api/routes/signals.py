"""
Trading Signals API routes.
Handles deterministic signal generation and retrieval operations.
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Any, Dict, List
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from backend.infra.security import get_current_user
from backend.utils.logger import get_logger, log_event, get_event_logger
from backend.strategies.basic import BasicStrategy
from backend.config import get_settings

logger = get_logger(__name__)
event_logger = get_event_logger("signals")

router = APIRouter(prefix="/signals", tags=["Trading Signals"])


# Request Models
class SignalRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    signal_strength: float = Field(..., description="Signal strength")
    timestamp: str = Field(..., description="Signal timestamp")
    features: Dict[str, float] = Field(default_factory=dict, description="Signal features")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Signal metadata")


class BatchSignalsRequest(BaseModel):
    """Batch signals request for multiple symbols."""
    symbols: List[str] = Field(..., description="List of trading symbols")
    lookback: int = Field(default=200, ge=50, le=1000, description="Historical data lookback period")


# Response Models
class SignalResponse(BaseModel):
    """Trading signal response."""
    symbol: str
    signal_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    target_price: float = None
    position_size: float = None
    timestamp: str
    metadata: Dict[str, Any] = {}


class MultiSignalsResponse(BaseModel):
    """Multiple signals response."""
    signals: Dict[str, Any]
    timestamp: str


class AdvancedSignalsResponse(BaseModel):
    """Advanced signals with features and risk metrics."""
    signals: Dict[str, Any]
    features: Dict[str, Any] = None
    risk_metrics: Dict[str, Any] = None
    timestamp: str


# Service Dependencies
async def fetch_closes(symbol: str, client, lookback: int = 200) -> List[float]:
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
        # Get historical data
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
            
        logger.info(f"Fetched {len(close_prices)} close prices for {symbol}")
        return close_prices
        
    except Exception as e:
        logger.error(f"Error fetching close prices for {symbol}: {e}")
        return []


def get_market_data_client():
    """Get market data client based on settings."""
    settings = get_settings()
    
    # Check if we should use mock data (for testing or development)
    use_mock = getattr(settings, 'USE_MOCK_DATA', True)  # Default to mock for safety
    
    if use_mock:
        return get_mock_alpaca_client()
    else:
        # In production, use real Alpaca client
        try:
            from backend.data.alpaca_client import AlpacaClient
            return AlpacaClient()
        except ImportError:
            logger.warning("AlpacaClient not available, falling back to mock")
            return get_mock_alpaca_client()


def get_mock_alpaca_client():
    """Get mock Alpaca client with deterministic (but realistic) data."""
    import pandas as pd
    import numpy as np
    
    class MockAlpacaClient:
        async def get_historical_data(self, symbol: str, timeframe: str, limit: int):
            """Generate deterministic price data based on symbol hash."""
            # Use symbol hash for deterministic but varied data per symbol
            seed = hash(symbol) % 1000000
            np.random.seed(seed)
            
            # Generate realistic price movements
            base_price = 100 + (seed % 200)  # Price between 100-300
            dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')
            
            # Generate price series with realistic characteristics
            returns = np.random.normal(0, 0.02, limit)  # 2% daily volatility
            prices = [base_price]
            
            for i in range(1, limit):
                # Add momentum and mean reversion
                momentum = 0.1 * returns[i-1] if i > 0 else 0
                mean_reversion = -0.05 * (prices[-1] - base_price) / base_price
                
                price_change = returns[i] + momentum + mean_reversion
                new_price = prices[-1] * (1 + price_change)
                prices.append(max(new_price, 1.0))  # Ensure positive prices
            
            # Create OHLC data
            highs = [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices]
            lows = [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices]
            volumes = [1000 + int(abs(np.random.normal(0, 500))) for _ in prices]
            
            data = pd.DataFrame({
                'open': prices,
                'high': highs,
                'low': lows,
                'close': prices,
                'volume': volumes
            }, index=dates)
            
            return data
    
    return MockAlpacaClient()


def get_basic_strategy() -> BasicStrategy:
    """Get configured BasicStrategy instance."""
    return BasicStrategy(
        rsi_buy=30,
        rsi_sell=70,
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
    start_time = time.time()

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

        return SignalResponse(
            symbol=symbol,
            signal_type=decision["action"].upper(),
            confidence=decision["confidence"],
            target_price=close_prices[-1] * (1 + decision["tp_pct"] / 100) if decision["action"] == "buy" else close_prices[-1] * (1 - decision["tp_pct"] / 100),
            position_size=decision["confidence"] * 100,  # Scale position by confidence
            timestamp=datetime.now().isoformat(),
            metadata={
                "source": "basic_strategy",
                "reason": decision["reason"],
                "tp_pct": decision["tp_pct"],
                "sl_pct": decision["sl_pct"],
                "processing_time_ms": (time.time() - start_time) * 1000
            }
        )

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
        signals_map: Dict[str, Any] = {}
        
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
    response_model=MultiSignalsResponse,
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
        signals_map: Dict[str, Any] = {}
        
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
                    "reason": decision["reason"],
                    "current_price": close_prices[-1] if close_prices else None
                }
                
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
                signals_map[symbol] = {"error": str(e)}

        return MultiSignalsResponse(
            signals=signals_map,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.exception(f"Error in get_batch_signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_signal(
    signal_request: SignalRequest,
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
                "signal_strength": signal_request.signal_strength,
                "user_id": getattr(current_user, 'id', None)
            }
        )
        
        # In a real implementation, this would:
        # 1. Validate the signal
        # 2. Store it in the database
        # 3. Potentially trigger automated trading
        
        return {
            "signal_id": signal_id,
            "status": "accepted",
            "symbol": signal_request.symbol,
            "signal_strength": signal_request.signal_strength,
            "processed_at": datetime.now().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error creating signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
