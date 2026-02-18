"""
Orders repository - handles order lifecycle and idempotency.
Implements async CRUD operations with proper error handling.
"""

from datetime import UTC, datetime
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
        user_id: str = "system",
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
            user_id: User ID for ownership tracking (default: 'system')

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
            user_id=user_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            tif=tif,
            status="accepted",
            submitted_at=datetime.now(UTC),
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
                        extra={
                            "client_key": client_key,
                            "order_id": str(existing_order.id),
                        },
                    )
                    return existing_order

            logger.error(
                "Failed to create order",
                extra={"client_key": client_key, "symbol": symbol, "error": str(e)},
            )
            raise DuplicateOrderError(
                f"Failed to create order with key {client_key}"
            ) from e

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
            .values(status=status, updated_at=datetime.now(UTC))
            .returning(Order.id)
        )

        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()

        if not updated_id:
            raise OrderNotFoundError(f"Order {order_id} not found")

        logger.info(
            "Order status updated", extra={"order_id": str(order_id), "status": status}
        )

    async def update_status(self, order_id: uuid.UUID, status: str) -> Order | None:
        """
        Update order status and return the updated order.
        Alias for set_status that returns the order instead of None.

        Args:
            order_id: Order ID
            status: New status

        Returns:
            Updated order or None if not found

        Raises:
            OrderNotFoundError: If order not found
        """
        await self.set_status(order_id, status)
        return await self.get_by_id(order_id)

    async def create_order(self, order_data: dict[str, Any]) -> Order:
        """
        Create a new order.
        Alias for upsert_by_idempotency that matches test expectations.

        Args:
            order_data: Order data dictionary

        Returns:
            Created order
        """
        # Extract client_key or generate one
        client_key = order_data.get("client_key", str(uuid.uuid4()))

        # Convert dict to Order model fields
        return await self.upsert_by_idempotency(
            client_key=client_key,
            symbol=order_data.get("symbol"),
            side=order_data.get("side"),
            qty=order_data.get("quantity", Decimal("0")),
            order_type=order_data.get("order_type", "market"),
            tif=order_data.get("time_in_force", "gtc"),
            attributes=order_data.get("attributes", {})
        )

    async def attach_broker_result(
        self,
        order_id: uuid.UUID,
        *,
        broker_order_id: str | None = None,
        status: str | None = None,
        attributes: dict[str, Any] | None = None,
        filled_qty: Decimal | None = None,
        avg_fill_price: Decimal | None = None,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> None:
        """
        Update order with broker response.

        Args:
            order_id: Order ID
            broker_order_id: Broker's order ID
            status: New order status
            attributes: Additional attributes to merge
            filled_qty: Filled quantity from broker
            avg_fill_price: Average fill price from broker
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)

        Raises:
            OrderNotFoundError: If order not found
        """
        # Build update values
        values = {"updated_at": datetime.now(UTC)}

        if broker_order_id is not None:
            values["broker_order_id"] = broker_order_id

        if status is not None:
            values["status"] = status

        # Update price and fill fields if provided
        if filled_qty is not None:
            values["filled_qty"] = filled_qty

        if avg_fill_price is not None:
            values["avg_fill_price"] = avg_fill_price

        if limit_price is not None:
            values["limit_price"] = limit_price

        if stop_price is not None:
            values["stop_price"] = stop_price

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

        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(**values)
            .returning(Order.id)
        )

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
                "filled_qty": str(filled_qty) if filled_qty else None,
                "avg_fill_price": str(avg_fill_price) if avg_fill_price else None,
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

    async def get_by_broker_order_id(self, broker_order_id: str) -> Order | None:
        """
        Get order by broker order ID.

        Args:
            broker_order_id: Broker-assigned order ID

        Returns:
            Order if found, None otherwise
        """
        stmt = select(Order).where(Order.broker_order_id == broker_order_id)
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

    # ==========================================================================
    # BATCH OPERATIONS (M-25: HFT optimization)
    # ==========================================================================

    async def batch_create_orders(
        self,
        orders_data: list[dict[str, Any]],
        *,
        skip_duplicates: bool = True,
    ) -> tuple[list[Order], list[str]]:
        """
        Batch create multiple orders efficiently for HFT scenarios.

        Uses SQLAlchemy bulk insert for optimal performance.
        Orders with duplicate idempotency keys are skipped if skip_duplicates=True.

        Args:
            orders_data: List of order dictionaries with required fields:
                - client_key: Idempotency key
                - symbol: Trading symbol
                - side: 'buy' or 'sell'
                - qty: Order quantity (Decimal)
                - order_type: 'market', 'limit', etc.
                - tif: Time in force
                - user_id: Optional user ID (default: 'admin')
            skip_duplicates: If True, skip orders with existing idempotency keys

        Returns:
            Tuple of (created_orders, skipped_keys)
        """
        if not orders_data:
            return [], []

        # Check for existing idempotency keys
        client_keys = [o.get("client_key") for o in orders_data if o.get("client_key")]
        existing_keys: set[str] = set()

        if client_keys and skip_duplicates:
            stmt = select(Order.client_idempotency_key).where(
                Order.client_idempotency_key.in_(client_keys)
            )
            result = await self.session.execute(stmt)
            existing_keys = {row[0] for row in result.fetchall()}

        # Filter and prepare orders
        orders_to_create: list[Order] = []
        skipped_keys: list[str] = list(existing_keys)
        now = datetime.now(UTC)

        for order_data in orders_data:
            client_key = order_data.get("client_key")
            if client_key in existing_keys:
                continue

            order = Order(
                id=uuid.uuid4(),
                client_idempotency_key=client_key or str(uuid.uuid4()),
                broker_order_id="",
                symbol=order_data["symbol"],
                side=order_data["side"],
                qty=Decimal(str(order_data["qty"])),
                filled_qty=Decimal("0"),
                avg_fill_price=None,
                status="accepted",
                order_type=order_data["order_type"],
                tif=order_data.get("tif", "gtc"),
                limit_price=order_data.get("limit_price"),
                stop_price=order_data.get("stop_price"),
                attributes=order_data.get("attributes", {}),
                user_id=order_data.get("user_id", "admin"),
                submitted_at=now,
                created_at=now,
                updated_at=now,
            )
            orders_to_create.append(order)

        # Bulk add all orders
        if orders_to_create:
            self.session.add_all(orders_to_create)
            await self.session.flush()

            logger.info(
                "Batch order creation completed",
                extra={
                    "created_count": len(orders_to_create),
                    "skipped_count": len(skipped_keys),
                },
            )

        return orders_to_create, skipped_keys

    async def batch_update_status(
        self,
        updates: list[dict[str, Any]],
    ) -> int:
        """
        Batch update order statuses for HFT fill processing.

        Args:
            updates: List of dicts with 'order_id', 'status', and optional
                     'filled_qty', 'avg_fill_price', 'broker_order_id'

        Returns:
            Number of orders updated
        """
        if not updates:
            return 0

        updated_count = 0
        now = datetime.now(UTC)

        for upd in updates:
            order_id = upd.get("order_id")
            if not order_id:
                continue

            try:
                order_uuid = uuid.UUID(str(order_id))
            except (ValueError, TypeError):
                logger.warning(f"Invalid order_id in batch update: {order_id}")
                continue

            update_data: dict[str, Any] = {"updated_at": now}

            if "status" in upd:
                update_data["status"] = upd["status"]
            if "filled_qty" in upd:
                update_data["filled_qty"] = Decimal(str(upd["filled_qty"]))
            if "avg_fill_price" in upd:
                update_data["avg_fill_price"] = Decimal(str(upd["avg_fill_price"]))
            if "broker_order_id" in upd:
                update_data["broker_order_id"] = upd["broker_order_id"]

            stmt = update(Order).where(Order.id == order_uuid).values(**update_data)
            result = await self.session.execute(stmt)
            updated_count += result.rowcount

        await self.session.flush()

        logger.info(
            "Batch status update completed",
            extra={"updated_count": updated_count, "requested_count": len(updates)},
        )

        return updated_count

    async def batch_get_by_ids(self, order_ids: list[str]) -> list[Order]:
        """
        Batch fetch orders by IDs for efficient HFT lookups.

        Args:
            order_ids: List of order UUIDs (as strings)

        Returns:
            List of found orders
        """
        if not order_ids:
            return []

        valid_uuids = []
        for oid in order_ids:
            try:
                valid_uuids.append(uuid.UUID(str(oid)))
            except (ValueError, TypeError):
                continue

        if not valid_uuids:
            return []

        stmt = select(Order).where(Order.id.in_(valid_uuids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
