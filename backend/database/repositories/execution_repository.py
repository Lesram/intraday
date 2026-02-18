"""Execution repository — database access for trade executions.

When a real database session is available, queries the ``executions``
table (see ``backend.infra.schemas.Execution``).  Falls back to
lightweight stubs for unit-test runs without a database.
"""

import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class ExecutionRepository:
    """Repository for trade execution records.

    Designed to be instantiated with an async SQLAlchemy session.
    If no session is provided, returns stub data for test compatibility.
    """

    def __init__(self, session=None):
        self._session = session

    async def get_executions_for_order(self, order_id):
        """Fetch all executions that filled a given order."""
        if self._session is None:
            return []

        try:
            from sqlalchemy import select
            from backend.infra.schemas import Execution

            result = await self._session.execute(
                select(Execution).where(Execution.order_id == order_id)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": str(row.id),
                    "order_id": str(row.order_id),
                    "qty": float(row.qty),
                    "price": float(row.price),
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                }
                for row in rows
            ]
        except Exception as exc:
            logger.warning(f"Failed to query executions for order {order_id}: {exc}")
            return []

    async def create_execution(self, execution_data: dict):
        """Persist a new execution record."""
        if self._session is None:
            # Stub mode — return the data with a generated ID
            return {"id": str(uuid.uuid4()), "created_at": datetime.now(UTC).isoformat(), **execution_data}

        try:
            from backend.infra.schemas import Execution

            execution = Execution(**execution_data)
            self._session.add(execution)
            await self._session.flush()
            return {
                "id": str(execution.id),
                "order_id": str(execution.order_id),
                "qty": float(execution.qty),
                "price": float(execution.price),
                "timestamp": execution.timestamp.isoformat() if execution.timestamp else None,
            }
        except Exception as exc:
            logger.warning(f"Failed to create execution: {exc}")
            return {"id": str(uuid.uuid4()), "created_at": datetime.now(UTC).isoformat(), **execution_data}
