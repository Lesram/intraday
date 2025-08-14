"""
Position management API routes.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.api.auth import get_current_user
from backend.services.positions_service import PositionsService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])

class PositionResponse(BaseModel):
    """Position response model."""
    symbol: str
    quantity: float
    avg_price: float
    market_value: float
    unrealized_pnl: float
    position_type: str = "long"

class PositionRequest(BaseModel):
    """Position request model."""
    symbol: str
    quantity: float
    price: float
    position_type: str = "long"

@router.get("/", response_model=List[PositionResponse])
async def get_positions(current_user: dict = Depends(get_current_user)):
    """Get all positions for the current user."""
    try:
        positions_service = PositionsService()
        positions = await positions_service.get_user_positions(current_user["user_id"])
        
        return [
            PositionResponse(
                symbol=pos.get("symbol", ""),
                quantity=pos.get("quantity", 0.0),
                avg_price=pos.get("avg_price", 0.0),
                market_value=pos.get("market_value", 0.0),
                unrealized_pnl=pos.get("unrealized_pnl", 0.0),
                position_type=pos.get("position_type", "long")
            )
            for pos in positions
        ]
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve positions")

@router.get("/{symbol}", response_model=PositionResponse)
async def get_position(symbol: str, current_user: dict = Depends(get_current_user)):
    """Get position for a specific symbol."""
    try:
        positions_service = PositionsService()
        position = await positions_service.get_position(current_user["user_id"], symbol)
        
        if not position:
            raise HTTPException(status_code=404, detail=f"Position not found for symbol {symbol}")
        
        return PositionResponse(
            symbol=position.get("symbol", symbol),
            quantity=position.get("quantity", 0.0),
            avg_price=position.get("avg_price", 0.0),
            market_value=position.get("market_value", 0.0),
            unrealized_pnl=position.get("unrealized_pnl", 0.0),
            position_type=position.get("position_type", "long")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get position for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve position")

@router.post("/", response_model=Dict[str, Any])
async def create_position(
    position: PositionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new position."""
    try:
        positions_service = PositionsService()
        result = await positions_service.create_position(
            user_id=current_user["user_id"],
            symbol=position.symbol,
            quantity=position.quantity,
            price=position.price,
            position_type=position.position_type
        )
        
        return {"success": True, "position_id": result.get("position_id")}
    except Exception as e:
        logger.error(f"Failed to create position: {e}")
        raise HTTPException(status_code=500, detail="Failed to create position")

@router.put("/{symbol}", response_model=Dict[str, Any])
async def update_position(
    symbol: str,
    position: PositionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing position."""
    try:
        positions_service = PositionsService()
        result = await positions_service.update_position(
            user_id=current_user["user_id"],
            symbol=symbol,
            quantity=position.quantity,
            price=position.price
        )
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Position not found for symbol {symbol}")
        
        return {"success": True, "message": "Position updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update position {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update position")

@router.delete("/{symbol}", response_model=Dict[str, Any])
async def delete_position(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """Close/delete a position."""
    try:
        positions_service = PositionsService()
        result = await positions_service.close_position(
            user_id=current_user["user_id"],
            symbol=symbol
        )
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Position not found for symbol {symbol}")
        
        return {"success": True, "message": "Position closed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close position {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to close position")
