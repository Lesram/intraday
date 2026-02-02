"""
Strategy repository - handles strategy lifecycle and CRUD operations.
Implements async database operations with proper error handling.
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import Strategy

logger = logging.getLogger(__name__)


class StrategyNotFoundError(Exception):
    """Raised when a strategy is not found."""
    pass


class DuplicateStrategyError(Exception):
    """Raised when attempting to create a strategy with a duplicate name."""
    pass


class InvalidStatusTransitionError(Exception):
    """Raised when attempting an invalid status transition."""
    pass


class StrategyRepo:
    """Repository for strategy operations."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_all(self) -> list[Strategy]:
        """
        Get all strategies ordered by updated_at descending.

        Returns:
            List of all Strategy objects
        """
        try:
            stmt = select(Strategy).order_by(Strategy.updated_at.desc())
            result = await self.session.execute(stmt)
            strategies = result.scalars().all()

            logger.info(
                "Retrieved all strategies",
                extra={"count": len(strategies)}
            )

            return list(strategies)

        except Exception as e:
            logger.error(f"Failed to get all strategies: {e}")
            raise

    async def get_by_id(self, strategy_id: uuid.UUID) -> Strategy:
        """
        Get strategy by ID.

        Args:
            strategy_id: Strategy UUID

        Returns:
            Strategy object

        Raises:
            StrategyNotFoundError: If strategy not found
        """
        try:
            stmt = select(Strategy).where(Strategy.id == strategy_id)
            result = await self.session.execute(stmt)
            strategy = result.scalar_one_or_none()

            if not strategy:
                raise StrategyNotFoundError(f"Strategy {strategy_id} not found")

            logger.debug(
                "Retrieved strategy by ID",
                extra={"strategy_id": str(strategy_id), "strategy_name": strategy.name}
            )

            return strategy

        except StrategyNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get strategy by ID",
                extra={"strategy_id": str(strategy_id), "error": str(e)}
            )
            raise

    async def get_by_status(self, status: str) -> list[Strategy]:
        """
        Get all strategies with specified status.

        Args:
            status: Strategy status ('active', 'inactive', 'paused', 'error')

        Returns:
            List of Strategy objects matching status
        """
        try:
            stmt = (
                select(Strategy)
                .where(Strategy.status == status)
                .order_by(Strategy.updated_at.desc())
            )
            result = await self.session.execute(stmt)
            strategies = result.scalars().all()

            logger.info(
                "Retrieved strategies by status",
                extra={"status": status, "count": len(strategies)}
            )

            return list(strategies)

        except Exception as e:
            logger.error(
                "Failed to get strategies by status",
                extra={"status": status, "error": str(e)}
            )
            raise

    async def get_by_strategy_type(self, strategy_type: str) -> list[Strategy]:
        """
        Get all strategies with specified type.

        Args:
            strategy_type: Strategy type ('momentum', 'mean_reversion', 'ensemble', 'stat_arb')

        Returns:
            List of Strategy objects matching type
        """
        try:
            stmt = (
                select(Strategy)
                .where(Strategy.strategy_type == strategy_type)
                .order_by(Strategy.updated_at.desc())
            )
            result = await self.session.execute(stmt)
            strategies = result.scalars().all()

            logger.info(
                "Retrieved strategies by type",
                extra={"strategy_type": strategy_type, "count": len(strategies)}
            )

            return list(strategies)

        except Exception as e:
            logger.error(
                "Failed to get strategies by type",
                extra={"strategy_type": strategy_type, "error": str(e)}
            )
            raise

    async def create(self, strategy_data: dict[str, Any]) -> Strategy:
        """
        Create a new strategy.

        Args:
            strategy_data: Dictionary containing strategy fields

        Returns:
            Created Strategy object

        Raises:
            DuplicateStrategyError: If strategy name already exists
        """
        try:
            # Create new strategy instance
            new_strategy = Strategy(
                name=strategy_data["name"],
                strategy_type=strategy_data["strategy_type"],
                description=strategy_data.get("description"),
                status=strategy_data.get("status", "inactive"),
                symbols=strategy_data.get("symbols", []),
                parameters=strategy_data.get("parameters", {}),
                total_pnl=strategy_data.get("total_pnl", Decimal("0.0")),
                total_trades=strategy_data.get("total_trades", 0),
                winning_trades=strategy_data.get("winning_trades", 0),
                losing_trades=strategy_data.get("losing_trades", 0),
                win_rate=strategy_data.get("win_rate", Decimal("0.0")),
                max_position_size=strategy_data.get("max_position_size"),
                max_daily_loss=strategy_data.get("max_daily_loss"),
                max_drawdown_pct=strategy_data.get("max_drawdown_pct"),
                model_id=strategy_data.get("model_id"),
            )

            self.session.add(new_strategy)
            await self.session.flush()  # Get the ID without committing

            logger.info(
                "Strategy created",
                extra={
                    "strategy_id": str(new_strategy.id),
                    "strategy_name": new_strategy.name,
                    "strategy_type": new_strategy.strategy_type,
                    "status": new_strategy.status,
                }
            )

            return new_strategy

        except IntegrityError as e:
            await self.session.rollback()

            # Check if it's a duplicate name error
            if "uq_strategies_name" in str(e) or "name" in str(e).lower():
                logger.warning(
                    "Duplicate strategy name",
                    extra={"strategy_name": strategy_data.get("name")}
                )
                raise DuplicateStrategyError(
                    f"Strategy with name '{strategy_data.get('name')}' already exists"
                ) from e

            logger.error(
                "Failed to create strategy",
                extra={"strategy_data": strategy_data, "error": str(e)}
            )
            raise

        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to create strategy",
                extra={"strategy_data": strategy_data, "error": str(e)}
            )
            raise

    async def update(
        self, strategy_id: uuid.UUID, update_data: dict[str, Any]
    ) -> Strategy:
        """
        Update strategy fields.

        Args:
            strategy_id: Strategy UUID
            update_data: Dictionary of fields to update

        Returns:
            Updated Strategy object

        Raises:
            StrategyNotFoundError: If strategy not found
            DuplicateStrategyError: If new name conflicts with existing strategy
        """
        try:
            # First, check if strategy exists
            await self.get_by_id(strategy_id)

            # Build update statement
            values = {**update_data, "updated_at": datetime.now(UTC)}

            stmt = (
                update(Strategy)
                .where(Strategy.id == strategy_id)
                .values(**values)
                .returning(Strategy)
            )

            result = await self.session.execute(stmt)
            updated_strategy = result.scalar_one()

            logger.info(
                "Strategy updated",
                extra={
                    "strategy_id": str(strategy_id),
                    "updated_fields": list(update_data.keys()),
                }
            )

            return updated_strategy

        except StrategyNotFoundError:
            raise
        except IntegrityError as e:
            await self.session.rollback()

            if "uq_strategies_name" in str(e) or "name" in str(e).lower():
                logger.warning(
                    "Duplicate strategy name on update",
                    extra={"strategy_id": str(strategy_id), "strategy_name": update_data.get("name")}
                )
                raise DuplicateStrategyError(
                    f"Strategy with name '{update_data.get('name')}' already exists"
                ) from e

            logger.error(
                "Failed to update strategy",
                extra={"strategy_id": str(strategy_id), "error": str(e)}
            )
            raise

        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to update strategy",
                extra={"strategy_id": str(strategy_id), "error": str(e)}
            )
            raise

    async def update_status(
        self,
        strategy_id: uuid.UUID,
        status: str,
        started_at: datetime | None = None,
        stopped_at: datetime | None = None,
    ) -> Strategy:
        """
        Update strategy status and related timestamps.

        Args:
            strategy_id: Strategy UUID
            status: New status value
            started_at: Optional started_at timestamp
            stopped_at: Optional stopped_at timestamp

        Returns:
            Updated Strategy object

        Raises:
            StrategyNotFoundError: If strategy not found
        """
        try:
            # Build update values
            values = {
                "status": status,
                "updated_at": datetime.now(UTC),
            }

            if started_at is not None:
                values["started_at"] = started_at

            if stopped_at is not None:
                values["stopped_at"] = stopped_at

            stmt = (
                update(Strategy)
                .where(Strategy.id == strategy_id)
                .values(**values)
                .returning(Strategy)
            )

            result = await self.session.execute(stmt)
            updated_strategy = result.scalar_one_or_none()

            if not updated_strategy:
                raise StrategyNotFoundError(f"Strategy {strategy_id} not found")

            logger.info(
                "Strategy status updated",
                extra={
                    "strategy_id": str(strategy_id),
                    "status": status,
                    "started_at": started_at,
                    "stopped_at": stopped_at,
                }
            )

            return updated_strategy

        except StrategyNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to update strategy status",
                extra={"strategy_id": str(strategy_id), "status": status, "error": str(e)}
            )
            raise

    async def update_performance(
        self, strategy_id: uuid.UUID, metrics: dict[str, Any]
    ) -> Strategy:
        """
        Update strategy performance metrics.

        Args:
            strategy_id: Strategy UUID
            metrics: Dictionary of performance fields to update
                    (total_pnl, total_trades, winning_trades, losing_trades, win_rate, etc.)

        Returns:
            Updated Strategy object

        Raises:
            StrategyNotFoundError: If strategy not found
        """
        try:
            # Build update values
            values = {**metrics, "updated_at": datetime.now(UTC)}

            # Set last_executed_at if not provided
            if "last_executed_at" not in values:
                values["last_executed_at"] = datetime.now(UTC)

            stmt = (
                update(Strategy)
                .where(Strategy.id == strategy_id)
                .values(**values)
                .returning(Strategy)
            )

            result = await self.session.execute(stmt)
            updated_strategy = result.scalar_one_or_none()

            if not updated_strategy:
                raise StrategyNotFoundError(f"Strategy {strategy_id} not found")

            logger.info(
                "Strategy performance updated",
                extra={
                    "strategy_id": str(strategy_id),
                    "updated_metrics": list(metrics.keys()),
                }
            )

            return updated_strategy

        except StrategyNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to update strategy performance",
                extra={"strategy_id": str(strategy_id), "error": str(e)}
            )
            raise

    async def delete(self, strategy_id: uuid.UUID) -> None:
        """
        Delete a strategy.

        Args:
            strategy_id: Strategy UUID

        Raises:
            StrategyNotFoundError: If strategy not found
        """
        try:
            # First, check if strategy exists
            await self.get_by_id(strategy_id)

            stmt = delete(Strategy).where(Strategy.id == strategy_id)
            await self.session.execute(stmt)

            logger.info(
                "Strategy deleted",
                extra={"strategy_id": str(strategy_id)}
            )

        except StrategyNotFoundError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to delete strategy",
                extra={"strategy_id": str(strategy_id), "error": str(e)}
            )
            raise
