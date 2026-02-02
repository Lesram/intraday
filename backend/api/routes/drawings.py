"""
Drawing Tools API Endpoints

Provides REST API for saving, loading, and managing chart drawings (trendlines, shapes, annotations).

Features:
- Save/load drawings per symbol
- CRUD operations for drawings
- User-specific drawings with authentication
- Support for multiple drawing types

Phase 7 - Market Data & Charting
Created: October 16, 2025
"""

from datetime import datetime
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.infra.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drawings", tags=["drawings"])

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class Point(BaseModel):
    """Chart point with time and price"""
    time: int = Field(..., description="Unix timestamp in seconds")
    price: float = Field(..., description="Price value")

class DrawingStyle(BaseModel):
    """Drawing visual style"""
    color: str = Field(default="#2962FF", description="Line/shape color")
    line_width: int = Field(default=2, description="Line width in pixels")
    line_style: str = Field(default="solid", description="solid, dashed, or dotted")
    fill_color: str | None = Field(default=None, description="Fill color for shapes")
    fill_opacity: float = Field(default=0.2, description="Fill opacity 0-1")
    text_size: int = Field(default=12, description="Text size for annotations")

class DrawingCreate(BaseModel):
    """Request model for creating a drawing"""
    symbol: str = Field(..., description="Stock symbol")
    type: str = Field(..., description="Drawing type: trendline, horizontal, vertical, fibonacci, rectangle, ellipse, text")
    points: list[Point] = Field(..., description="Drawing points (1-2 depending on type)")
    style: DrawingStyle = Field(default_factory=DrawingStyle, description="Visual style")
    text: str | None = Field(default=None, description="Text content for annotations")
    timeframe: str = Field(default="1D", description="Chart timeframe")

class DrawingUpdate(BaseModel):
    """Request model for updating a drawing"""
    points: list[Point] | None = None
    style: DrawingStyle | None = None
    text: str | None = None

class DrawingResponse(BaseModel):
    """Response model for a drawing"""
    id: str
    symbol: str
    type: str
    points: list[Point]
    style: DrawingStyle
    text: str | None
    timeframe: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============================================================================
# IN-MEMORY STORAGE (for now - migrate to DB later)
# ============================================================================

# TODO: Replace with database table
# Format: {user_id: {symbol: [drawings]}}
_drawings_store: dict = {}

def _username_to_id(username: str) -> int:
    """Convert username to stable integer ID for in-memory storage"""
    return abs(hash(username)) % (10 ** 8)  # 8-digit positive integer

def _get_user_drawings(user_id: int, symbol: str) -> list[dict]:
    """Get all drawings for a user and symbol"""
    if user_id not in _drawings_store:
        _drawings_store[user_id] = {}
    if symbol not in _drawings_store[user_id]:
        _drawings_store[user_id][symbol] = []
    return _drawings_store[user_id][symbol]

def _find_drawing(user_id: int, drawing_id: str) -> dict | None:
    """Find a drawing by ID"""
    if user_id not in _drawings_store:
        return None
    for symbol_drawings in _drawings_store[user_id].values():
        for drawing in symbol_drawings:
            if drawing['id'] == drawing_id:
                return drawing
    return None

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/{symbol}", response_model=list[DrawingResponse])
async def get_drawings(
    symbol: str,
    timeframe: str = "1D",
    current_user: dict = Depends(get_current_user)
):
    """
    Get all drawings for a symbol and timeframe

    Args:
        symbol: Stock symbol (e.g., AAPL)
        timeframe: Chart timeframe (1m, 5m, 15m, 1h, 4h, 1D, etc.)
        current_user: Authenticated user

    Returns:
        List of drawings for the symbol

    Example:
        GET /api/v1/drawings/AAPL?timeframe=1D

        Response:
        [
          {
            "id": "drawing_123",
            "symbol": "AAPL",
            "type": "trendline",
            "points": [
              {"time": 1704067200, "price": 180.0},
              {"time": 1704153600, "price": 185.0}
            ],
            "style": {
              "color": "#2962FF",
              "line_width": 2,
              "line_style": "solid"
            },
            "timeframe": "1D",
            "user_id": 1,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
          }
        ]
    """
    try:
        user_id = _username_to_id(current_user.username)
        drawings = _get_user_drawings(user_id, symbol)

        # Filter by timeframe
        filtered = [d for d in drawings if d.get('timeframe') == timeframe]

        logger.info(f"Retrieved {len(filtered)} drawings for {symbol} ({timeframe})")
        return filtered

    except Exception as e:
        logger.error(f"Failed to get drawings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve drawings: {str(e)}"
        )

@router.post("/", response_model=DrawingResponse, status_code=status.HTTP_201_CREATED)
async def create_drawing(
    drawing: DrawingCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new drawing

    Args:
        drawing: Drawing data
        current_user: Authenticated user

    Returns:
        Created drawing with ID and timestamps

    Example:
        POST /api/v1/drawings/
        {
          "symbol": "AAPL",
          "type": "trendline",
          "points": [
            {"time": 1704067200, "price": 180.0},
            {"time": 1704153600, "price": 185.0}
          ],
          "style": {
            "color": "#2962FF",
            "line_width": 2,
            "line_style": "solid"
          },
          "timeframe": "1D"
        }
    """
    try:
        user_id = _username_to_id(current_user.username)

        # Validate drawing type
        valid_types = ['trendline', 'horizontal', 'vertical', 'fibonacci', 'rectangle', 'ellipse', 'text']
        if drawing.type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid drawing type. Must be one of: {valid_types}"
            )

        # Validate points
        required_points = {
            'trendline': 2,
            'horizontal': 1,
            'vertical': 1,
            'fibonacci': 2,
            'rectangle': 2,
            'ellipse': 2,
            'text': 1,
        }
        expected = required_points.get(drawing.type, 2)
        if len(drawing.points) != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Drawing type '{drawing.type}' requires {expected} points, got {len(drawing.points)}"
            )

        # Create drawing
        now = datetime.utcnow()
        new_drawing = {
            'id': f"drawing_{uuid4().hex[:12]}",
            'symbol': drawing.symbol.upper(),
            'type': drawing.type,
            'points': [p.dict() for p in drawing.points],
            'style': drawing.style.dict(),
            'text': drawing.text,
            'timeframe': drawing.timeframe,
            'user_id': user_id,
            'created_at': now,
            'updated_at': now,
        }

        # Store drawing
        drawings = _get_user_drawings(user_id, drawing.symbol.upper())
        drawings.append(new_drawing)

        logger.info(f"Created drawing {new_drawing['id']} for {drawing.symbol}")
        return new_drawing

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create drawing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create drawing: {str(e)}"
        )

@router.put("/{drawing_id}", response_model=DrawingResponse)
async def update_drawing(
    drawing_id: str,
    updates: DrawingUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing drawing

    Args:
        drawing_id: Drawing ID
        updates: Fields to update
        current_user: Authenticated user

    Returns:
        Updated drawing

    Example:
        PUT /api/v1/drawings/drawing_123
        {
          "style": {
            "color": "#FF0000",
            "line_width": 3
          }
        }
    """
    try:
        user_id = _username_to_id(current_user.username)
        drawing = _find_drawing(user_id, drawing_id)

        if not drawing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Drawing {drawing_id} not found"
            )

        # Update fields
        if updates.points is not None:
            drawing['points'] = [p.dict() for p in updates.points]
        if updates.style is not None:
            drawing['style'].update(updates.style.dict(exclude_unset=True))
        if updates.text is not None:
            drawing['text'] = updates.text

        drawing['updated_at'] = datetime.utcnow()

        logger.info(f"Updated drawing {drawing_id}")
        return drawing

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update drawing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update drawing: {str(e)}"
        )

@router.delete("/{drawing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drawing(
    drawing_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a drawing

    Args:
        drawing_id: Drawing ID
        current_user: Authenticated user

    Returns:
        204 No Content on success

    Example:
        DELETE /api/v1/drawings/drawing_123
    """
    try:
        user_id = _username_to_id(current_user.username)

        # Find and remove drawing
        if user_id in _drawings_store:
            for symbol_drawings in _drawings_store[user_id].values():
                for i, drawing in enumerate(symbol_drawings):
                    if drawing['id'] == drawing_id:
                        symbol_drawings.pop(i)
                        logger.info(f"Deleted drawing {drawing_id}")
                        return

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing {drawing_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete drawing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete drawing: {str(e)}"
        )

@router.delete("/symbol/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_drawings(
    symbol: str,
    timeframe: str = "1D",
    current_user: dict = Depends(get_current_user)
):
    """
    Delete all drawings for a symbol and timeframe

    Args:
        symbol: Stock symbol
        timeframe: Chart timeframe
        current_user: Authenticated user

    Returns:
        204 No Content on success

    Example:
        DELETE /api/v1/drawings/symbol/AAPL?timeframe=1D
    """
    try:
        user_id = _username_to_id(current_user.username)
        symbol = symbol.upper()

        if user_id in _drawings_store and symbol in _drawings_store[user_id]:
            # Remove only drawings matching timeframe
            _drawings_store[user_id][symbol] = [
                d for d in _drawings_store[user_id][symbol]
                if d.get('timeframe') != timeframe
            ]
            logger.info(f"Deleted all {timeframe} drawings for {symbol}")

        return

    except Exception as e:
        logger.error(f"Failed to delete drawings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete drawings: {str(e)}"
        )
