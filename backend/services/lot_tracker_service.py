"""
Lot Tracker Service - Manages position lots and realized trade tracking.

This service implements accurate cost basis tracking using FIFO (First-In-First-Out)
lot matching. It creates position lots on buy orders and matches them with sell orders
to calculate realized P&L.

Key Features:
- FIFO lot matching for accurate cost basis
- Supports partial lot closes
- Creates realized trade records for closed positions
- Handles imported historical orders correctly
- Enables tax-loss harvesting and wash sale detection
"""

from datetime import datetime
from decimal import Decimal
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import PositionLot, RealizedTrade

logger = logging.getLogger(__name__)


class LotTracker:
    """Service for tracking position lots and realized trades."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_lot(
        self,
        user_id: str,
        symbol: str,
        qty: Decimal,
        cost_basis: Decimal,
        order_id: uuid.UUID,
        open_date: datetime,
    ) -> PositionLot:
        """
        Create a new position lot when a buy order is filled.

        Args:
            user_id: User identifier
            symbol: Stock symbol
            qty: Quantity purchased
            cost_basis: Cost per share
            order_id: ID of the buy order
            open_date: Order fill timestamp

        Returns:
            PositionLot: The newly created lot
        """
        lot = PositionLot(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol=symbol,
            qty=qty,
            remaining_qty=qty,
            cost_basis=cost_basis,
            order_id=order_id,
            open_date=open_date,
            status="open",
        )

        self.session.add(lot)
        await self.session.flush()

        logger.info(
            "Created position lot",
            extra={
                "lot_id": str(lot.id),
                "user_id": user_id,
                "symbol": symbol,
                "qty": float(qty),
                "cost_basis": float(cost_basis),
            },
        )

        return lot

    async def close_lots_fifo(
        self,
        user_id: str,
        symbol: str,
        qty_to_close: Decimal,
        close_price: Decimal,
        close_order_id: uuid.UUID,
        close_date: datetime,
    ) -> list[RealizedTrade]:
        """
        Close position lots using FIFO (First-In-First-Out) matching.

        Args:
            user_id: User identifier
            symbol: Stock symbol
            qty_to_close: Quantity to close (sell)
            close_price: Sale price per share
            close_order_id: ID of the sell order
            close_date: Order fill timestamp

        Returns:
            list[RealizedTrade]: List of realized trades created

        Raises:
            ValueError: If insufficient lots available to close
        """
        # Get all open lots for this symbol (FIFO order: oldest first).
        # V4 N-H-2 (2026-05-02): SELECT FOR UPDATE serializes concurrent
        # close paths (alpaca-stream WS fill vs the position-reconcile
        # loop). Without the row lock both readers see the same
        # remaining_qty, both compute closures, and the second commit
        # produces a lost update — only the per-row CHECK constraint
        # eventually catches it (sometimes with a partial close already
        # written). The lock is released on session commit/rollback.
        stmt = (
            select(PositionLot)
            .where(
                PositionLot.user_id == user_id,
                PositionLot.symbol == symbol,
                PositionLot.status == "open",
                PositionLot.remaining_qty > 0,
            )
            .order_by(PositionLot.open_date.asc())  # FIFO: oldest first
            .with_for_update()
        )

        result = await self.session.execute(stmt)
        open_lots = result.scalars().all()

        if not open_lots:
            raise ValueError(
                f"No open lots found for {user_id}/{symbol} to close {qty_to_close} shares"
            )

        # Calculate total available quantity
        total_available = sum(lot.remaining_qty for lot in open_lots)
        if total_available < qty_to_close:
            raise ValueError(
                f"Insufficient lots for {user_id}/{symbol}: "
                f"need {qty_to_close}, available {total_available}"
            )

        # Match lots in FIFO order
        remaining_to_close = qty_to_close
        realized_trades = []

        for lot in open_lots:
            if remaining_to_close <= 0:
                break

            # Determine how much to close from this lot
            qty_from_lot = min(lot.remaining_qty, remaining_to_close)

            # Calculate realized P&L
            realized_pnl = qty_from_lot * (close_price - lot.cost_basis)
            realized_pnl_percent = (
                ((close_price - lot.cost_basis) / lot.cost_basis * 100)
                if lot.cost_basis != 0
                else Decimal(0)
            )

            # Create realized trade record
            realized_trade = RealizedTrade(
                id=uuid.uuid4(),
                user_id=user_id,
                symbol=symbol,
                qty=qty_from_lot,
                open_price=lot.cost_basis,
                close_price=close_price,
                realized_pnl=realized_pnl,
                realized_pnl_percent=realized_pnl_percent,
                open_order_id=lot.order_id,
                close_order_id=close_order_id,
                lot_id=lot.id,
                open_date=lot.open_date,
                close_date=close_date,
                attributes={},
            )

            self.session.add(realized_trade)
            realized_trades.append(realized_trade)

            # Update lot remaining quantity
            lot.remaining_qty -= qty_from_lot
            if lot.remaining_qty == 0:
                lot.status = "closed"

            remaining_to_close -= qty_from_lot

            logger.info(
                "Closed lot partially/fully",
                extra={
                    "lot_id": str(lot.id),
                    "symbol": symbol,
                    "qty_closed": float(qty_from_lot),
                    "remaining_qty": float(lot.remaining_qty),
                    "realized_pnl": float(realized_pnl),
                },
            )

        await self.session.flush()

        logger.info(
            f"Closed {len(realized_trades)} lots for {symbol}",
            extra={
                "user_id": user_id,
                "symbol": symbol,
                "total_qty_closed": float(qty_to_close),
                "total_realized_pnl": float(
                    sum(t.realized_pnl for t in realized_trades)
                ),
            },
        )

        return realized_trades

    async def get_open_lots(
        self, user_id: str, symbol: str | None = None
    ) -> list[PositionLot]:
        """
        Get all open lots for a user, optionally filtered by symbol.

        Args:
            user_id: User identifier
            symbol: Optional symbol filter

        Returns:
            list[PositionLot]: List of open position lots
        """
        stmt = select(PositionLot).where(
            PositionLot.user_id == user_id,
            PositionLot.status == "open",
            PositionLot.remaining_qty > 0,
        )

        if symbol:
            stmt = stmt.where(PositionLot.symbol == symbol)

        stmt = stmt.order_by(PositionLot.open_date.asc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_realized_trades(
        self,
        user_id: str,
        symbol: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[RealizedTrade]:
        """
        Get realized trades for a user with optional filters.

        Args:
            user_id: User identifier
            symbol: Optional symbol filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            list[RealizedTrade]: List of realized trades
        """
        stmt = select(RealizedTrade).where(RealizedTrade.user_id == user_id)

        if symbol:
            stmt = stmt.where(RealizedTrade.symbol == symbol)
        if start_date:
            stmt = stmt.where(RealizedTrade.close_date >= start_date)
        if end_date:
            stmt = stmt.where(RealizedTrade.close_date <= end_date)

        stmt = stmt.order_by(RealizedTrade.close_date.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cost_basis(self, user_id: str, symbol: str) -> Decimal:
        """
        Calculate the weighted average cost basis for all open lots of a symbol.

        Args:
            user_id: User identifier
            symbol: Stock symbol

        Returns:
            Decimal: Weighted average cost basis per share
        """
        open_lots = await self.get_open_lots(user_id, symbol)

        if not open_lots:
            return Decimal(0)

        total_cost = sum(lot.remaining_qty * lot.cost_basis for lot in open_lots)
        total_qty = sum(lot.remaining_qty for lot in open_lots)

        if total_qty == 0:
            return Decimal(0)

        return total_cost / total_qty

    async def get_unrealized_pnl(
        self, user_id: str, symbol: str, current_price: Decimal
    ) -> Decimal:
        """
        Calculate unrealized P&L for all open lots of a symbol.

        Args:
            user_id: User identifier
            symbol: Stock symbol
            current_price: Current market price

        Returns:
            Decimal: Total unrealized P&L
        """
        open_lots = await self.get_open_lots(user_id, symbol)

        if not open_lots:
            return Decimal(0)

        unrealized_pnl = sum(
            lot.remaining_qty * (current_price - lot.cost_basis) for lot in open_lots
        )

        return unrealized_pnl
