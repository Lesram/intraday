"""
Data models for market data and financial data structures.
Pydantic models for data validation and serialization.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class MarketDataPoint(BaseModel):
    """Individual market data point with OHLCV data."""
    
    symbol: str = Field(..., description="Trading symbol")
    timestamp: datetime = Field(..., description="Data timestamp") 
    open: Decimal = Field(..., gt=0, description="Opening price")
    high: Decimal = Field(..., gt=0, description="High price")
    low: Decimal = Field(..., gt=0, description="Low price")
    close: Decimal = Field(..., gt=0, description="Closing price")
    volume: int = Field(..., ge=0, description="Trading volume")
    
    @validator("high")
    def validate_high_price(cls, v, values):
        """Ensure high price is >= open, low, and close."""
        if "open" in values and v < values["open"]:
            raise ValueError("High price cannot be less than open price")
        if "low" in values and v < values["low"]:
            raise ValueError("High price cannot be less than low price")
        if "close" in values and v < values["close"]:
            raise ValueError("High price cannot be less than close price")
        return v
    
    @validator("low")  
    def validate_low_price(cls, v, values):
        """Ensure low price is <= open, high, and close."""
        if "open" in values and v > values["open"]:
            raise ValueError("Low price cannot be greater than open price")
        if "high" in values and v > values["high"]:
            raise ValueError("Low price cannot be greater than high price")
        if "close" in values and v > values["close"]:
            raise ValueError("Low price cannot be greater than close price")
        return v


class TradingSignal(BaseModel):
    """Trading signal data structure."""
    
    symbol: str = Field(..., description="Trading symbol")
    signal_type: str = Field(..., description="Signal type (buy/sell/hold)")
    strength: float = Field(..., ge=0, le=1, description="Signal strength (0-1)")
    confidence: float = Field(..., ge=0, le=1, description="Signal confidence (0-1)")
    timestamp: datetime = Field(..., description="Signal generation timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional signal metadata")
    
    @validator("signal_type")
    def validate_signal_type(cls, v):
        """Validate signal type is one of the allowed values."""
        allowed_types = {"buy", "sell", "hold", "strong_buy", "strong_sell"}
        if v.lower() not in allowed_types:
            raise ValueError(f"Signal type must be one of: {allowed_types}")
        return v.lower()


class PortfolioSnapshot(BaseModel):
    """Portfolio snapshot at a point in time."""
    
    timestamp: datetime = Field(..., description="Snapshot timestamp")
    total_value: Decimal = Field(..., ge=0, description="Total portfolio value")
    cash_balance: Decimal = Field(..., ge=0, description="Available cash balance")
    positions: list[dict[str, Any]] = Field(default_factory=list, description="Current positions")
    daily_pnl: Optional[Decimal] = Field(None, description="Daily profit/loss")
    total_pnl: Optional[Decimal] = Field(None, description="Total profit/loss")
    
    @validator("positions")
    def validate_positions(cls, v):
        """Validate positions structure."""
        for position in v:
            required_keys = {"symbol", "quantity", "avg_price"}
            if not required_keys.issubset(position.keys()):
                raise ValueError(f"Position must contain keys: {required_keys}")
        return v


class RiskMetrics(BaseModel):
    """Risk metrics for portfolio analysis."""
    
    var_95: Optional[float] = Field(None, description="Value at Risk (95%)")
    var_99: Optional[float] = Field(None, description="Value at Risk (99%)")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    max_drawdown: Optional[float] = Field(None, description="Maximum drawdown")
    volatility: Optional[float] = Field(None, ge=0, description="Portfolio volatility")
    beta: Optional[float] = Field(None, description="Portfolio beta")
    
    @validator("max_drawdown")
    def validate_max_drawdown(cls, v):
        """Ensure max drawdown is non-positive."""
        if v is not None and v > 0:
            raise ValueError("Maximum drawdown should be non-positive")
        return v