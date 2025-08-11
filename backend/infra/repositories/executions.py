"""
Executions repository - tracks order fills and trades.
Implements async CRUD operations with proper error handling.
"""
from datetime import datetime
from decimal import Decimal
import logging
from typing import Any
import uuid

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import Execution

logger = logging.getLogger(__name__)


class ExecutionNotFoundError(Exception):
    """Raised when an execution is not found."""

    pass


class DuplicateExecutionError(Exception):
    """Raised when attempting to create a duplicate execution."""

    pass


class ExecutionsRepo:
    """Repository for execution operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_execution(
        self,
        *,
        order_id: uuid.UUID,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        execution_id: str,  # Broker's execution ID
        timestamp: datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Execution:
        """
        Create a new execution record.

        Args:
            order_id: Associated order ID
            symbol: Trading symbol
            side: 'buy' or 'sell'
            qty: Executed quantity
            price: Execution price
            execution_id: Broker's execution/trade ID
            timestamp: Execution timestamp (defaults to now)
            attributes: Optional additional attributes

        Returns:
            Execution: Newly created execution

        Raises:
            DuplicateExecutionError: If execution_id already exists
        """
        new_execution = Execution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            execution_id=execution_id,
            timestamp=timestamp or datetime.utcnow(),
            attributes=attributes or {},
        )

        try:
            self.session.add(new_execution)
            await self.session.flush()  # Get the ID without committing

            logger.info(
                "New execution created",
                extra={
                    "execution_id": execution_id,
                    "order_id": str(order_id),
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty),
                    "price": str(price),
                    "notional": str(qty * price),
                },
            )

            return new_execution

        except IntegrityError as e:
            await self.session.rollback()
            if "execution_id" in str(e):
                logger.warning(
                    "Duplicate execution ID",
                    extra={"execution_id": execution_id, "order_id": str(order_id)},
                )
                raise DuplicateExecutionError(f"Execution {execution_id} already exists") from e

            logger.error(
                "Failed to create execution",
                extra={"execution_id": execution_id, "order_id": str(order_id), "error": str(e)},
            )
            raise

    async def upsert_by_execution_id(
        self,
        *,
        order_id: uuid.UUID,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        execution_id: str,
        timestamp: datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Execution:
        """
        Create execution with idempotency protection.

        If execution_id already exists, returns the existing execution.
        Otherwise creates a new execution.

        Args:
            order_id: Associated order ID
            symbol: Trading symbol
            side: 'buy' or 'sell'
            qty: Executed quantity
            price: Execution price
            execution_id: Broker's execution/trade ID
            timestamp: Execution timestamp (defaults to now)
            attributes: Optional additional attributes

        Returns:
            Execution: Either existing or newly created execution
        """
        # First, try to find existing execution
        stmt = select(Execution).where(Execution.execution_id == execution_id)
        result = await self.session.execute(stmt)
        existing_execution = result.scalar_one_or_none()

        if existing_execution:
            logger.debug(
                "Execution already exists",
                extra={
                    "execution_id": execution_id,
                    "order_id": str(existing_execution.order_id),
                    "symbol": existing_execution.symbol,
                    "qty": str(existing_execution.qty),
                    "price": str(existing_execution.price),
                },
            )
            return existing_execution

        # Create new execution
        return await self.create_execution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            execution_id=execution_id,
            timestamp=timestamp,
            attributes=attributes,
        )

    async def get_by_execution_id(self, execution_id: str) -> Execution | None:
        """
        Get execution by broker execution ID.

        Args:
            execution_id: Broker execution ID

        Returns:
            Execution if found, None otherwise
        """
        stmt = select(Execution).where(Execution.execution_id == execution_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, execution_uuid: uuid.UUID) -> Execution | None:
        """
        Get execution by internal UUID.

        Args:
            execution_uuid: Internal execution UUID

        Returns:
            Execution if found, None otherwise
        """
        stmt = select(Execution).where(Execution.id == execution_uuid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> list[Execution]:
        """
        Get all executions for an order.

        Args:
            order_id: Order ID

        Returns:
            List of executions for the order
        """
        stmt = (
            select(Execution)
            .where(Execution.order_id == order_id)
            .order_by(Execution.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_symbol(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        """
        Get executions by symbol within time range.

        Args:
            symbol: Trading symbol
            start_time: Start time filter (optional)
            end_time: End time filter (optional)
            limit: Maximum number of executions to return

        Returns:
            List of executions
        """
        conditions = [Execution.symbol == symbol]

        if start_time:
            conditions.append(Execution.timestamp >= start_time)

        if end_time:
            conditions.append(Execution.timestamp <= end_time)

        stmt = (
            select(Execution)
            .where(and_(*conditions))
            .order_by(Execution.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_filled_qty(self, order_id: uuid.UUID) -> Decimal:
        """
        Calculate total filled quantity for an order.

        Args:
            order_id: Order ID

        Returns:
            Total filled quantity
        """
        executions = await self.get_by_order_id(order_id)
        return sum(execution.qty for execution in executions)

    async def get_volume_weighted_avg_price(self, order_id: uuid.UUID) -> Decimal | None:
        """
        Calculate volume-weighted average price for an order.

        Args:
            order_id: Order ID

        Returns:
            VWAP if executions exist, None otherwise
        """
        executions = await self.get_by_order_id(order_id)

        if not executions:
            return None

        total_notional = sum(execution.qty * execution.price for execution in executions)
        total_qty = sum(execution.qty for execution in executions)

        if total_qty == 0:
            return None

        return total_notional / total_qty

    async def get_recent_executions(
        self, limit: int = 100, symbol: str | None = None
    ) -> list[Execution]:
        """
        Get recent executions.

        Args:
            limit: Maximum number of executions to return
            symbol: Optional symbol filter

        Returns:
            List of recent executions
        """
        stmt = select(Execution)

        if symbol:
            stmt = stmt.where(Execution.symbol == symbol)

        stmt = stmt.order_by(Execution.timestamp.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def calculate_pnl_impact(
        self, symbol: str, side: str, qty: Decimal, price: Decimal
    ) -> dict[str, Any]:
        """
        Calculate PnL impact of a potential execution.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            qty: Execution quantity
            price: Execution price

        Returns:
            Dictionary with PnL impact analysis
        """
        # Get recent executions for the symbol to calculate current position
        recent_executions = await self.get_by_symbol(symbol, limit=1000)

        # Calculate current position
        position_qty = Decimal("0")
        total_cost = Decimal("0")

        for execution in recent_executions:
            if execution.side == "buy":
                position_qty += execution.qty
                total_cost += execution.qty * execution.price
            else:  # sell
                position_qty -= execution.qty
                total_cost -= execution.qty * execution.price

        # Calculate current average cost
        avg_cost = None
        if position_qty != 0:
            avg_cost = abs(total_cost / position_qty)

        # Calculate impact of new execution
        new_notional = qty * price
        if side == "buy":
            new_position_qty = position_qty + qty
            new_total_cost = total_cost + new_notional
        else:  # sell
            new_position_qty = position_qty - qty
            new_total_cost = total_cost - new_notional

        # Calculate new average cost
        new_avg_cost = None
        if new_position_qty != 0:
            new_avg_cost = abs(new_total_cost / new_position_qty)

        # Calculate unrealized PnL change
        unrealized_pnl_change = None
        if avg_cost and new_avg_cost:
            current_market_value = position_qty * price
            current_unrealized = current_market_value - abs(total_cost)

            new_market_value = new_position_qty * price
            new_unrealized = new_market_value - abs(new_total_cost)

            unrealized_pnl_change = new_unrealized - current_unrealized

        return {
            "current_position_qty": position_qty,
            "current_avg_cost": avg_cost,
            "new_position_qty": new_position_qty,
            "new_avg_cost": new_avg_cost,
            "execution_notional": new_notional,
            "unrealized_pnl_change": unrealized_pnl_change,
        }
