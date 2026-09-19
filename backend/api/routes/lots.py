"""
Position Lots & Realized Trades API Routes

Endpoints for querying position lots (cost basis tracking) and realized trades.
"""

from datetime import datetime
from decimal import Decimal
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.services.lot_tracker_service import LotTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lots", tags=["lots"])


# ============================================================================
# Pydantic Models
# ============================================================================


class PositionLotResponse(BaseModel):
    """Position lot response model"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    symbol: str
    qty: float
    remaining_qty: float
    cost_basis: float
    order_id: str
    open_date: datetime
    status: str
    created_at: datetime
    updated_at: datetime


class RealizedTradeResponse(BaseModel):
    """Realized trade response model"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    symbol: str
    qty: float
    open_price: float
    close_price: float
    realized_pnl: float
    realized_pnl_percent: float
    open_order_id: str
    close_order_id: str
    lot_id: str
    open_date: datetime
    close_date: datetime
    created_at: datetime


class CostBasisResponse(BaseModel):
    """Cost basis response model.

    Audit-I finding I-12 (2026-05-02): the response carries a
    `has_position: bool` flag so consumers can distinguish "user has
    no open lots in this symbol" from any other zero state. Previously
    cost_basis=0/total_qty=0 was indistinguishable from a real flat.
    """

    symbol: str
    weighted_avg_cost: float
    total_qty: float
    total_cost: float
    open_lots: int
    has_position: bool = False


class UnrealizedPnLResponse(BaseModel):
    """Unrealized P&L response model"""

    symbol: str
    current_price: float
    total_qty: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/open", response_model=list[PositionLotResponse])
async def get_open_lots(
    symbol: str | None = Query(None, description="Filter by symbol"),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[PositionLotResponse]:
    """
    Get all open position lots for a user.

    Open lots represent current positions with their cost basis.
    Used for calculating unrealized P&L and tracking cost basis.
    """
    user_id = current_user.username
    try:
        lot_tracker = LotTracker(db)
        lots = await lot_tracker.get_open_lots(user_id, symbol)

        return [
            PositionLotResponse(
                id=str(lot.id),
                user_id=lot.user_id,
                symbol=lot.symbol,
                qty=float(lot.qty),
                remaining_qty=float(lot.remaining_qty),
                cost_basis=float(lot.cost_basis),
                order_id=str(lot.order_id),
                open_date=lot.open_date,
                status=lot.status,
                created_at=lot.created_at,
                updated_at=lot.updated_at,
            )
            for lot in lots
        ]

    except Exception as e:
        logger.error(f"Error fetching open lots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch open lots: {str(e)}")


@router.get("/realized", response_model=list[RealizedTradeResponse])
async def get_realized_trades(
    symbol: str | None = Query(None, description="Filter by symbol"),
    start_date: datetime | None = Query(None, description="Start date filter"),
    end_date: datetime | None = Query(None, description="End date filter"),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[RealizedTradeResponse]:
    """
    Get realized trades (closed positions) for a user.

    Realized trades are completed buy→sell cycles with accurate P&L.
    Used for historical performance analysis and tax reporting.
    """
    user_id = current_user.username
    try:
        lot_tracker = LotTracker(db)
        trades = await lot_tracker.get_realized_trades(
            user_id, symbol, start_date, end_date
        )

        return [
            RealizedTradeResponse(
                id=str(trade.id),
                user_id=trade.user_id,
                symbol=trade.symbol,
                qty=float(trade.qty),
                open_price=float(trade.open_price),
                close_price=float(trade.close_price),
                realized_pnl=float(trade.realized_pnl),
                realized_pnl_percent=float(trade.realized_pnl_percent),
                open_order_id=str(trade.open_order_id),
                close_order_id=str(trade.close_order_id),
                lot_id=str(trade.lot_id),
                open_date=trade.open_date,
                close_date=trade.close_date,
                created_at=trade.created_at,
            )
            for trade in trades
        ]

    except Exception as e:
        logger.error(f"Error fetching realized trades: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch realized trades: {str(e)}")


@router.get("/{symbol}/cost-basis", response_model=CostBasisResponse)
async def get_cost_basis(
    symbol: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
) -> CostBasisResponse:
    """
    Get weighted average cost basis for a symbol.

    Calculates the cost basis across all open lots for accurate
    unrealized P&L calculation and tax reporting.
    """
    user_id = current_user.username
    try:
        lot_tracker = LotTracker(db)

        # Get open lots and calculate cost basis
        open_lots = await lot_tracker.get_open_lots(user_id, symbol)

        if not open_lots:
            return CostBasisResponse(
                symbol=symbol,
                weighted_avg_cost=0.0,
                total_qty=0.0,
                total_cost=0.0,
                open_lots=0,
                has_position=False,
            )

        total_qty = sum(lot.remaining_qty for lot in open_lots)
        total_cost = sum(lot.remaining_qty * lot.cost_basis for lot in open_lots)
        weighted_avg_cost = total_cost / total_qty if total_qty > 0 else Decimal(0)

        return CostBasisResponse(
            symbol=symbol,
            weighted_avg_cost=float(weighted_avg_cost),
            total_qty=float(total_qty),
            total_cost=float(total_cost),
            open_lots=len(open_lots),
            has_position=True,
        )

    except Exception as e:
        logger.error(f"Error calculating cost basis for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate cost basis: {str(e)}"
        )


@router.get("/{symbol}/unrealized-pnl", response_model=UnrealizedPnLResponse)
async def get_unrealized_pnl(
    symbol: str,
    current_price: float = Query(..., description="Current market price"),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
) -> UnrealizedPnLResponse:
    """
    Get unrealized P&L for a symbol at current market price.

    Calculates the profit/loss if all open lots were closed at current price.
    """
    user_id = current_user.username
    try:
        lot_tracker = LotTracker(db)

        # Get cost basis and unrealized P&L
        cost_basis = await lot_tracker.get_cost_basis(user_id, symbol)
        unrealized_pnl = await lot_tracker.get_unrealized_pnl(
            user_id, symbol, Decimal(str(current_price))
        )

        # Get total quantity
        open_lots = await lot_tracker.get_open_lots(user_id, symbol)
        total_qty = sum(lot.remaining_qty for lot in open_lots)

        # Calculate percent
        unrealized_pnl_percent = (
            ((Decimal(str(current_price)) - cost_basis) / cost_basis * 100)
            if cost_basis > 0
            else Decimal(0)
        )

        return UnrealizedPnLResponse(
            symbol=symbol,
            current_price=current_price,
            total_qty=float(total_qty),
            cost_basis=float(cost_basis),
            unrealized_pnl=float(unrealized_pnl),
            unrealized_pnl_percent=float(unrealized_pnl_percent),
        )

    except Exception as e:
        logger.error(f"Error calculating unrealized P&L for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate unrealized P&L: {str(e)}"
        )
