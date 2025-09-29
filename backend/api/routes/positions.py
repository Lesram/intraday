"""
Positions API routes for portfolio management.
Provides GET /positions endpoint with support for mock data, Alpaca API, and database.
"""

from datetime import UTC, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.config import get_settings
from backend.infra.security import AuthenticatedUser, get_authenticated_user

router = APIRouter(prefix="/positions", tags=["Positions"])


class PositionDTO(BaseModel):
    """Position data transfer object."""
    symbol: str
    qty: float
    avg_price: float
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None
    updated_at: datetime


def get_mock_positions() -> List[PositionDTO]:
    """Return deterministic demo positions for testing and development."""
    now = datetime.now(UTC)
    
    return [
        PositionDTO(
            symbol="AAPL",
            qty=10.0,
            avg_price=180.0,
            market_price=185.50,
            market_value=1855.0,
            unrealized_pl=55.0,
            updated_at=now
        ),
        PositionDTO(
            symbol="GOOGL", 
            qty=5.0,
            avg_price=2750.0,
            market_price=2800.25,
            market_value=14001.25,
            unrealized_pl=251.25,
            updated_at=now
        ),
        PositionDTO(
            symbol="MSFT",
            qty=15.0,
            avg_price=420.0,
            market_price=415.75,
            market_value=6236.25,
            unrealized_pl=-63.75,
            updated_at=now
        ),
    ]


async def get_alpaca_positions() -> List[PositionDTO]:
    """Fetch positions from Alpaca API."""
    try:
        # TODO: Implement actual Alpaca API integration
        # For now, return mock data with a note
        positions = get_mock_positions()
        
        # Mark as Alpaca-sourced for identification
        for position in positions:
            position.symbol = f"{position.symbol}_ALPACA"
            
        return positions
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch positions from Alpaca: {str(e)}"
        )


async def get_database_positions() -> List[PositionDTO]:
    """Fetch positions from database."""
    try:
        # TODO: Implement actual database query
        # This would query the positions table and map to DTOs
        
        # For now, return mock data indicating database source
        positions = get_mock_positions()
        
        # Mark as database-sourced for identification  
        for position in positions:
            position.symbol = f"{position.symbol}_DB"
            
        return positions
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch positions from database: {str(e)}"
        )


@router.get("/", response_model=List[PositionDTO])
async def get_positions(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> List[PositionDTO]:
    """
    Get current portfolio positions.
    
    Returns positions from different sources based on configuration:
    - Mock data if USE_MOCK_DATA=true
    - Alpaca API if USE_MOCK_BROKER=false  
    - Database if USE_MOCK_BROKER=true and database available
    
    Requires authentication - returns 401 without valid token.
    """
    settings = get_settings()
    
    # Check USE_MOCK_DATA setting first
    use_mock_data = getattr(settings, 'USE_MOCK_DATA', False)
    if use_mock_data:
        return get_mock_positions()
    
    # Check USE_MOCK_BROKER setting
    use_mock_broker = getattr(settings, 'USE_MOCK_BROKER', True)
    
    if not use_mock_broker:
        # Use Alpaca API for real trading
        return await get_alpaca_positions()
    else:
        # Use database or fallback to mock
        try:
            return await get_database_positions()
        except HTTPException:
            # Fallback to mock data if database unavailable
            return get_mock_positions()
