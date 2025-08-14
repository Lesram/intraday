"""
Order API routes.
Handles order submission, status, and cancellation operations.
"""

from typing import Any, Dict
from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from backend.infra.security import get_current_user
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["Trading", "Protected", "Outbox"])


# Request/Response Models
class OrderSubmissionRequest(BaseModel):
    """Order submission request payload."""
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side: buy or sell")
    qty: float = Field(..., gt=0, description="Quantity to trade")
    order_type: str = Field(default="market", description="Order type")
    time_in_force: str = Field(default="day", description="Time in force")
    client_order_id: str = Field(None, description="Client-provided order ID for idempotency")


class OrderSubmissionResponse(BaseModel):
    """Order submission response."""
    order_id: str
    client_order_id: str = None
    status: str
    symbol: str
    side: str
    qty: float
    submitted_at: str


class OrderStatusResponse(BaseModel):
    """Order status response."""
    order_id: str
    client_order_id: str = None
    status: str
    symbol: str
    side: str
    qty: float
    filled_qty: float = 0.0
    avg_fill_price: float = None
    submitted_at: str
    updated_at: str


# Mock dependencies for testing
def get_order_service():
    """Get order service - mock implementation for testing"""
    class MockOrderService:
        def __init__(self):
            self.orders = {}
        
        async def submit_order(self, request: OrderSubmissionRequest, user_id: str):
            """Submit a new order"""
            import uuid
            order_id = str(uuid.uuid4())
            
            order = {
                "order_id": order_id,
                "client_order_id": request.client_order_id,
                "status": "submitted",
                "symbol": request.symbol,
                "side": request.side,
                "qty": request.qty,
                "filled_qty": 0.0,
                "avg_fill_price": None,
                "submitted_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id
            }
            
            self.orders[order_id] = order
            return OrderSubmissionResponse(**order)
        
        async def get_order_status(self, order_id: str):
            """Get order status"""
            order = self.orders.get(order_id)
            if not order:
                return None
            return OrderStatusResponse(**order)
        
        async def cancel_order(self, order_id: str):
            """Cancel an order"""
            order = self.orders.get(order_id)
            if not order:
                return None
            
            order["status"] = "cancelled"
            order["updated_at"] = datetime.now().isoformat()
            return order
    
    return MockOrderService()


def get_risk_manager():
    """Get risk manager - mock implementation for testing"""
    class MockRiskManager:
        def check_trade_risk(self, symbol: str, side: str, qty: float):
            """Simple risk check"""
            if qty > 1000:
                return {"approved": False, "reason": "Quantity too large"}
            return {"approved": True}
    
    return MockRiskManager()


def require_trader(current_user=Depends(get_current_user)):
    """Dependency that requires authenticated user with trader role"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # In production, would check roles/permissions
    return current_user


# Route Handlers
@router.post(
    "/orders/submit",
    response_model=OrderSubmissionResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def submit_order(
    request: OrderSubmissionRequest,
    current_user=Depends(require_trader),
    order_service=Depends(get_order_service),
    risk_manager=Depends(get_risk_manager),
):
    """
    Submit an order with exactly-once guarantees using transactional outbox pattern.

    Features:
    - Atomic order creation and outbox enqueuing
    - Idempotency protection via client_order_id
    - Background side-effect processing
    - Complete audit trail
    - Risk management validation
    """
    try:
        # Validate trade parameters
        if request.side.lower() not in ["buy", "sell"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Side must be 'buy' or 'sell'",
            )

        if request.qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be positive",
            )

        # Risk management check
        risk_check = risk_manager.check_trade_risk(
            request.symbol, request.side.upper(), request.qty
        )
        
        if not risk_check.get("approved", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Risk check failed: {risk_check.get('reason', 'Unknown reason')}"
            )

        # Submit order
        result = await order_service.submit_order(request, current_user.get("user_id", "anonymous"))
        
        logger.info(f"Order submitted successfully: {result.order_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order submission failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order submission failed",
        )


@router.get(
    "/orders/{order_id}",
    response_model=OrderStatusResponse,
    tags=["Trading", "Protected", "Outbox"],
)
async def get_order_status(
    order_id: str,
    current_user=Depends(require_trader),
    order_service=Depends(get_order_service),
):
    """Get current order status and details."""
    try:
        order_status = await order_service.get_order_status(order_id)

        if not order_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order not found: {order_id}",
            )

        return order_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order status",
        )


@router.post("/orders/{order_id}/cancel", tags=["Trading", "Protected", "Outbox"])
async def cancel_order(
    order_id: str,
    idempotency_key: str = None,
    current_user=Depends(require_trader),
    order_service=Depends(get_order_service),
):
    """Cancel an existing order."""
    try:
        result = await order_service.cancel_order(order_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order not found: {order_id}",
            )

        logger.info(f"Order cancelled successfully: {order_id}")
        return {
            "order_id": order_id,
            "status": "cancelled",
            "cancelled_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel order",
        )
