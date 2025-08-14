"""
Portfolio API endpoints.
Handles position management and portfolio operations.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from decimal import Decimal
import logging
from backend.infra.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["portfolio"])

def get_portfolio_service():
    """Get portfolio service for dependency injection."""
    return type('PortfolioService', (), {
        'get_positions': lambda: [{"symbol": "AAPL", "quantity": 100}],
        'get_performance': lambda: {"total_return": 0.05, "sharpe_ratio": 1.2},
    })()

def get_portfolio_repo():
    """Get portfolio repository - minimal in-memory implementation for tests"""
    
    class InMemoryPortfolioRepo:
        def __init__(self):
            self._positions = {
                "AAPL": {
                    "symbol": "AAPL", 
                    "qty": Decimal("100"), 
                    "avg_price": Decimal("150.00"),
                    "market_value": Decimal("15000.00"),
                    "unrealized_pnl": Decimal("500.00")
                },
                "GOOGL": {
                    "symbol": "GOOGL",
                    "qty": Decimal("50"), 
                    "avg_price": Decimal("2500.00"),
                    "market_value": Decimal("125000.00"),
                    "unrealized_pnl": Decimal("-1000.00")
                }
            }
        
        def get_all_positions(self) -> List[Dict[str, Any]]:
            return list(self._positions.values())
    
    return InMemoryPortfolioRepo()


class PositionResponse(BaseModel):
    """Position response model."""
    symbol: str
    qty: Decimal
    avg_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    current_user=Depends(get_current_user),
    portfolio_repo=Depends(get_portfolio_repo)
) -> List[PositionResponse]:
    """
    Get current user's portfolio positions.
    
    Args:
        current_user: Current authenticated user
        portfolio_repo: Portfolio repository dependency
        
    Returns:
        List of position objects with symbol, qty, avg_price, market_value, unrealized_pnl
    """
    try:
        # In production, filter by current_user.user_id
        positions_data = portfolio_repo.get_all_positions()
        
        # Convert to response models
        positions = [
            PositionResponse(**pos_data) for pos_data in positions_data
        ]
        
        logger.info(f"Retrieved {len(positions)} positions for user {current_user.get('user_id', 'unknown')}")
        return positions
        
    except Exception as e:
        logger.error(f"Failed to retrieve positions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )
