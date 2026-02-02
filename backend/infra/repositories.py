"""
Unified Repository Pattern - Proper ORM Access Layer

This module provides repository classes that replace all direct SQL usage.
Ensures consistent, transaction-safe database operations through SQLAlchemy ORM.
"""

from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import Order
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class BaseRepository:
    """Base repository with common CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session


class OrderRepository(BaseRepository):
    """
    Repository for Order operations.

    Replaces all direct SQL access to orders table with proper ORM operations.
    This is what outbox_worker.py should use instead of sqlite3.connect().
    """

    async def get_by_id(self, order_id: str | uuid.UUID) -> Order | None:
        """Get order by ID."""
        if isinstance(order_id, str):
            order_id = uuid.UUID(order_id)

        stmt = select(Order).where(Order.id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, order: Order) -> Order:
        """Update existing order."""
        order.updated_at = datetime.utcnow()
        await self.session.flush()

        logger.info("Order updated via repository",
                   order_id=str(order.id),
                   status=order.status)

        return order


def get_order_repository(session: AsyncSession) -> OrderRepository:
    """Get OrderRepository instance."""
    return OrderRepository(session)
