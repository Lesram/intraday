"""
Trading history API routes.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from datetime import datetime, timedelta

from backend.infra.security import get_current_user, get_authenticated_user
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/trades", tags=["trades"])

class TradeHistory(BaseModel):
    """Trade history response model."""
    trade_id: str
    symbol: str
    quantity: float
    price: float
    side: str  # "buy" or "sell"
    timestamp: datetime
    order_type: str = "market"
    fees: float = 0.0
    pnl: float = 0.0

class TradeHistoryResponse(BaseModel):
    """Trade history list response."""
    trades: List[TradeHistory]
    total_count: int
    page: int
    page_size: int

@router.get("/history", response_model=TradeHistoryResponse)
async def get_trade_history(
    current_user = Depends(get_authenticated_user),
    symbol: str = Query(None, description="Filter by symbol"),
    start_date: datetime = Query(None, description="Start date filter"),
    end_date: datetime = Query(None, description="End date filter"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Page size")
):
    """Get trading history for the current user."""
    # Check user has trading access
    user_roles = current_user.roles if hasattr(current_user, 'roles') else []
    if "read-only" in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    
    try:
        # Mock data for now - in production this would query the trades repository
        mock_trades = [
            TradeHistory(
                trade_id="trade_001",
                symbol="AAPL",
                quantity=100,
                price=150.25,
                side="buy",
                timestamp=datetime.now() - timedelta(days=1),
                order_type="market",
                fees=1.50,
                pnl=0.0
            ),
            TradeHistory(
                trade_id="trade_002",
                symbol="AAPL",
                quantity=50,
                price=152.10,
                side="sell",
                timestamp=datetime.now() - timedelta(hours=12),
                order_type="limit",
                fees=0.75,
                pnl=92.50
            ),
            TradeHistory(
                trade_id="trade_003",
                symbol="MSFT",
                quantity=25,
                price=300.50,
                side="buy",
                timestamp=datetime.now() - timedelta(hours=6),
                order_type="market",
                fees=0.75,
                pnl=0.0
            )
        ]
        
        # Apply symbol filter if provided
        if symbol:
            mock_trades = [t for t in mock_trades if t.symbol == symbol]
        
        # Apply date filters if provided
        if start_date:
            mock_trades = [t for t in mock_trades if t.timestamp >= start_date]
        if end_date:
            mock_trades = [t for t in mock_trades if t.timestamp <= end_date]
        
        # Simple pagination
        total_count = len(mock_trades)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_trades = mock_trades[start_idx:end_idx]
        
        return TradeHistoryResponse(
            trades=paginated_trades,
            total_count=total_count,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to get trade history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trade history")

@router.get("/history/{trade_id}", response_model=TradeHistory)
async def get_trade_detail(
    trade_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details for a specific trade."""
    try:
        # Mock implementation - return a sample trade
        trade = TradeHistory(
            trade_id=trade_id,
            symbol="AAPL",
            quantity=100,
            price=150.25,
            side="buy",
            timestamp=datetime.now() - timedelta(days=1),
            order_type="market",
            fees=1.50,
            pnl=0.0
        )
        
        return trade
        
    except Exception as e:
        logger.error(f"Failed to get trade detail for {trade_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trade detail")

@router.get("/stats", response_model=Dict[str, Any])
async def get_trading_stats(
    current_user: dict = Depends(get_current_user),
    start_date: datetime = Query(None, description="Start date for stats"),
    end_date: datetime = Query(None, description="End date for stats")
):
    """Get trading statistics for the current user."""
    try:
        # Mock statistics - in production this would calculate from actual trades
        stats = {
            "total_trades": 15,
            "profitable_trades": 9,
            "losing_trades": 6,
            "win_rate": 60.0,
            "total_pnl": 1250.75,
            "total_fees": 45.25,
            "net_pnl": 1205.50,
            "avg_trade_pnl": 80.37,
            "best_trade": 450.00,
            "worst_trade": -125.50,
            "total_volume": 125000.00
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get trading stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trading statistics")


class TradeExecutionRequest(BaseModel):
    """Trade execution request model."""
    symbol: str
    quantity: float
    side: str  # "buy" or "sell"
    order_type: str = "market"


@router.post("/execute")
async def execute_trade(
    trade_request: TradeExecutionRequest,
    current_user = Depends(get_authenticated_user)
):
    """Execute a trade order."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if user has trading privileges
    user_roles = current_user.roles if hasattr(current_user, 'roles') else []
    if "trader" not in user_roles and "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="Trading privileges required")
    
    try:
        # Mock trade execution
        import uuid
        from datetime import datetime
        
        trade_id = str(uuid.uuid4())
        mock_price = 150.00  # Mock price
        
        return {
            "trade_id": trade_id,
            "symbol": trade_request.symbol,
            "quantity": trade_request.quantity,
            "side": trade_request.side,
            "order_type": trade_request.order_type,
            "price": mock_price,
            "timestamp": datetime.now(),
            "status": "executed"
        }
        
    except Exception as e:
        logger.error(f"Failed to execute trade: {e}")
        raise HTTPException(status_code=500, detail="Trade execution failed")
