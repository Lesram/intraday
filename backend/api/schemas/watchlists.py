"""
Watchlist schemas for API requests/responses
"""
from datetime import datetime

from pydantic import BaseModel, Field


class WatchlistSymbolAdd(BaseModel):
    """Add symbol to watchlist request"""
    symbol: str = Field(..., min_length=1, max_length=10)


class WatchlistSymbolReorder(BaseModel):
    """Reorder watchlist symbols request"""
    symbols: list[str] = Field(..., description="Ordered list of symbols")


class WatchlistCreate(BaseModel):
    """Create watchlist request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    symbols: list[str] = Field(default_factory=list, description="Initial symbols")


class WatchlistUpdate(BaseModel):
    """Update watchlist request"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    symbols: list[str] | None = None


class WatchlistSymbolResponse(BaseModel):
    """Watchlist symbol response"""
    id: int
    symbol: str
    order: int

    class Config:
        from_attributes = True


class WatchlistResponse(BaseModel):
    """Watchlist response"""
    id: int
    user_id: int
    name: str
    description: str | None
    is_default: bool
    symbols: list[WatchlistSymbolResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
