"""
Orders repository - handles order lifecycle and idempotency.
Implements async CRUD operations with proper error handling.
"""
from datetime import datetime
from decimal import Decimal
import logging
from typing import Any
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import Order

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    """Raised when an order is not found."""

    pass


class DuplicateOrderError(Exception):
    """Raised when attempting to create a duplicate order."""

    pass


class OrdersRepo:
    """Repository for order operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_by_idempotency(
        self,
        *,
        client_key: str,
        symbol: str,
        side: str,
        qty: Decimal,
        order_type: str,
        tif: str,
        attributes: dict[str, Any] | None = None,
    ) -> Order:
        """
        Create order with idempotency protection.

        If client_idempotency_key already exists, returns the existing order.
        Otherwise creates a new order with status='accepted'.

        Args:
            client_key: Client-provided idempotency key
            symbol: Trading symbol
            side: 'buy' or 'sell'
            qty: Order quantity
            order_type: Order type ('market', 'limit', etc.)
            tif: Time in force ('gtc', 'ioc', 'fok')
            attributes: Optional additional attributes

        Returns:
            Order: Either existing or newly created order
        """
        # First, try to find existing order
        stmt = select(Order).where(Order.client_idempotency_key == client_key)
        result = await self.session.execute(stmt)
        existing_order = result.scalar_one_or_none()

        if existing_order:
            logger.debug(
                "Order already exists for idempotency key",
                extra={
                    "client_key": client_key,
                    "order_id": str(existing_order.id),
                    "symbol": existing_order.symbol,
                    "status": existing_order.status,
                },
            )
            return existing_order

        # Create new order
        new_order = Order(
            client_idempotency_key=client_key,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            tif=tif,
            status="accepted",
            submitted_at=datetime.utcnow(),
            attributes=attributes or {},
        )

        try:
            self.session.add(new_order)
            await self.session.flush()  # Get the ID without committing

            logger.info(
                "New order created",
                extra={
                    "order_id": str(new_order.id),
                    "client_key": client_key,
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty),
                    "order_type": order_type,
                },
            )

            return new_order

        except IntegrityError as e:
            await self.session.rollback()
            # Handle race condition - another process may have created the order
            if "client_idempotency_key" in str(e):
                # Try to fetch the order that was just created by another process
                stmt = select(Order).where(Order.client_idempotency_key == client_key)
                result = await self.session.execute(stmt)
                existing_order = result.scalar_one_or_none()

                if existing_order:
                    logger.debug(
                        "Order created by another process",
                        extra={"client_key": client_key, "order_id": str(existing_order.id)},
                    )
                    return existing_order

            logger.error(
                "Failed to create order",
                extra={"client_key": client_key, "symbol": symbol, "error": str(e)},
            )
            raise DuplicateOrderError(f"Failed to create order with key {client_key}") from e

    async def set_status(self, order_id: uuid.UUID, status: str) -> None:
        """
        Update order status.

        Args:
            order_id: Order ID
            status: New status

        Raises:
            OrderNotFoundError: If order not found
        """
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(status=status, updated_at=datetime.utcnow())
            .returning(Order.id)
        )

        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()

        if not updated_id:
            raise OrderNotFoundError(f"Order {order_id} not found")

        logger.info("Order status updated", extra={"order_id": str(order_id), "status": status})

    async def attach_broker_result(
        self,
        order_id: uuid.UUID,
        *,
        broker_order_id: str | None = None,
        status: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """
        Update order with broker response.

        Args:
            order_id: Order ID
            broker_order_id: Broker's order ID
            status: New order status
            attributes: Additional attributes to merge

        Raises:
            OrderNotFoundError: If order not found
        """
        # Build update values
        values = {"updated_at": datetime.utcnow()}

        if broker_order_id is not None:
            values["broker_order_id"] = broker_order_id

        if status is not None:
            values["status"] = status

        # For attributes, we need to merge with existing attributes
        if attributes:
            # First fetch current attributes
            stmt = select(Order.attributes).where(Order.id == order_id)
            result = await self.session.execute(stmt)
            current_attrs = result.scalar_one_or_none()

            if current_attrs is None:
                raise OrderNotFoundError(f"Order {order_id} not found")

            # Merge attributes
            merged_attrs = {**(current_attrs or {}), **attributes}
            values["attributes"] = merged_attrs

        stmt = update(Order).where(Order.id == order_id).values(**values).returning(Order.id)

        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()

        if not updated_id:
            raise OrderNotFoundError(f"Order {order_id} not found")

        logger.info(
            "Order broker result attached",
            extra={
                "order_id": str(order_id),
                "broker_order_id": broker_order_id,
                "status": status,
                "attributes_updated": bool(attributes),
            },
        )

    async def get_by_client_key(self, client_key: str) -> Order | None:
        """
        Get order by client idempotency key.

        Args:
            client_key: Client idempotency key

        Returns:
            Order if found, None otherwise
        """
        stmt = select(Order).where(Order.client_idempotency_key == client_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        """
        Get order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order if found, None otherwise
        """
        stmt = select(Order).where(Order.id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_symbol(self, symbol: str, limit: int = 100) -> list[Order]:
        """
        Get orders by symbol.

        Args:
            symbol: Trading symbol
            limit: Maximum number of orders to return

        Returns:
            List of orders
        """
        stmt = (
            select(Order)
            .where(Order.symbol == symbol)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_orders(self, limit: int = 100) -> list[Order]:
        """
        Get active orders (not filled, cancelled, or rejected).

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of active orders
        """
        active_statuses = ["accepted", "submitting", "submitted", "partially_filled"]

        stmt = (
            select(Order)
            .where(Order.status.in_(active_statuses))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
