"""
Test endpoint for WebSocket broadcasting.
Only available in development/testing environments.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.socketio_server import broadcast_portfolio_update
from backend.infra.security import get_current_user

router = APIRouter(prefix="/test", tags=["testing"])


class BroadcastPortfolioResponse(BaseModel):
    """Response for portfolio broadcast endpoint."""
    message: str
    user_id: str
    data: dict[str, Any]


@router.post("/broadcast-portfolio", response_model=BroadcastPortfolioResponse)
async def test_broadcast_portfolio(
    portfolio_data: dict[str, Any],
    current_user: dict = Depends(get_current_user)
) -> BroadcastPortfolioResponse:
    """
    Test endpoint to manually trigger a portfolio WebSocket broadcast.

    Args:
        portfolio_data: Portfolio data to broadcast
        current_user: Authenticated user from JWT

    Returns:
        Confirmation message
    """
    user_id = current_user.get("sub", "unknown")

    # Add timestamp if not present
    if "lastUpdate" not in portfolio_data:
        portfolio_data["lastUpdate"] = datetime.now(UTC).isoformat()

    # Broadcast to user
    await broadcast_portfolio_update(user_id, portfolio_data)

    return BroadcastPortfolioResponse(
        message="Portfolio update broadcasted",
        user_id=user_id,
        data=portfolio_data
    )
