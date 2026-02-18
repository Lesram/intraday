"""
Strategy Service - handles strategy management business logic.
Implements status transitions, performance tracking, WebSocket integration,
and strategy versioning (M-41).
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..api.socketio_server import broadcast_strategy_update
from ..infra.repositories.strategies import (
    DuplicateStrategyError,
    InvalidStatusTransitionError,
    StrategyNotFoundError,
    StrategyRepo,
)
from ..infra.schemas import Strategy
from ..strategies.versioning import (
    StrategyVersionManager,
    VersionChangeType,
    get_version_manager,
)

logger = logging.getLogger(__name__)


def _transform_for_broadcast(strategy_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Transform strategy dict to frontend format for WebSocket broadcasts.

    Converts snake_case to camelCase and adds strategyType field.

    Args:
        strategy_dict: Strategy dict with snake_case keys from _strategy_to_dict

    Returns:
        Transformed dict with camelCase keys for frontend
    """
    return {
        "strategyId": strategy_dict["id"],
        "name": strategy_dict["name"],
        "description": strategy_dict.get("description"),
        "strategyType": strategy_dict.get("strategy_type"),
        "status": "stopped" if strategy_dict["status"] == "inactive" else strategy_dict["status"],
        "symbols": strategy_dict.get("symbols", []),
        "parameters": strategy_dict.get("parameters", {}),
        "performance": {
            "totalTrades": strategy_dict.get("total_trades", 0),
            "winRate": strategy_dict.get("win_rate", 0.0),
            "totalPnL": strategy_dict.get("total_pnl", 0.0),
            "sharpeRatio": 0.0,
            "maxDrawdown": strategy_dict.get("max_drawdown_pct", 0.0),
        },
        "createdAt": strategy_dict.get("created_at"),
        "updatedAt": strategy_dict.get("updated_at"),
        "lastExecutedAt": strategy_dict.get("last_executed_at"),
        "startedAt": strategy_dict.get("started_at"),
        "stoppedAt": strategy_dict.get("stopped_at"),
    }


# Valid status values
VALID_STATUSES = ["active", "inactive", "paused", "error"]

# Valid strategy types
# Implementation types (algorithmic approach)
IMPLEMENTATION_TYPES = [
    "momentum",
    "mean_reversion",
    "ensemble",
    "ensemble_model",  # Template uses this
    "stat_arb",
    "statistical_arbitrage",  # Template uses this
    "optuna_meta",
]
# Classification types (trading philosophy)
CLASSIFICATION_TYPES = [
    "technical",
    "technical_analysis",  # Template uses this
    "fundamental",
    "fundamental_analysis",  # Template uses this
    "quantitative",
    "hybrid",
    "hybrid_strategy",  # Template uses this
]
# All valid types (combined)
VALID_STRATEGY_TYPES = IMPLEMENTATION_TYPES + CLASSIFICATION_TYPES


class StrategyService:
    """Service for strategy management operations with versioning support."""

    def __init__(self, session: AsyncSession, user_id: str) -> None:
        """
        Initialize service with database session and user context.

        Args:
            session: Async SQLAlchemy session
            user_id: User ID for WebSocket broadcasts
        """
        self.repo = StrategyRepo(session)
        self.user_id = user_id
        self.session = session
        self._version_manager = get_version_manager()

    def _strategy_to_dict(self, strategy: Strategy) -> dict[str, Any]:
        """
        Convert Strategy object to dictionary with proper type conversions.

        Args:
            strategy: Strategy SQLAlchemy object

        Returns:
            Dictionary with snake_case keys and converted types
        """
        return {
            "id": str(strategy.id),
            "name": strategy.name,
            "strategy_type": strategy.strategy_type,
            "description": strategy.description,
            "status": strategy.status,
            "symbols": strategy.symbols,
            "parameters": strategy.parameters,
            "total_pnl": float(strategy.total_pnl),
            "total_trades": strategy.total_trades,
            "winning_trades": strategy.winning_trades,
            "losing_trades": strategy.losing_trades,
            "win_rate": float(strategy.win_rate),
            "max_position_size": float(strategy.max_position_size) if strategy.max_position_size else None,
            "max_daily_loss": float(strategy.max_daily_loss) if strategy.max_daily_loss else None,
            "max_drawdown_pct": float(strategy.max_drawdown_pct) if strategy.max_drawdown_pct else None,
            "last_executed_at": strategy.last_executed_at.isoformat() if strategy.last_executed_at else None,
            "last_signal_at": strategy.last_signal_at.isoformat() if strategy.last_signal_at else None,
            "error_message": strategy.error_message,
            "error_count": strategy.error_count,
            "model_id": str(strategy.model_id) if strategy.model_id else None,
            "created_at": strategy.created_at.isoformat(),
            "updated_at": strategy.updated_at.isoformat(),
            "started_at": strategy.started_at.isoformat() if strategy.started_at else None,
            "stopped_at": strategy.stopped_at.isoformat() if strategy.stopped_at else None,
        }

    def _validate_status_transition(self, current_status: str, new_status: str) -> None:
        """
        Validate status transition is allowed.

        Valid transitions:
        - inactive → active (start)
        - active → paused (pause)
        - paused → active (resume)
        - active → inactive (stop)
        - paused → inactive (stop)
        - any → error (on exception)

        Invalid transitions:
        - inactive → paused (must be active first)
        - error → active (manual intervention required)

        Args:
            current_status: Current strategy status
            new_status: Desired new status

        Raises:
            InvalidStatusTransitionError: If transition is not allowed
        """
        # Allow any status to transition to itself (no-op)
        if current_status == new_status:
            return

        # Allow any status to transition to error
        if new_status == "error":
            return

        # Define valid transitions
        valid_transitions = {
            "inactive": ["active"],
            "active": ["paused", "inactive"],
            "paused": ["active", "inactive"],
            "error": [],  # Cannot transition out of error automatically
        }

        if new_status not in valid_transitions.get(current_status, []):
            raise InvalidStatusTransitionError(
                f"Invalid status transition: {current_status} → {new_status}"
            )

    async def list_strategies(
        self, status: str | None = None, strategy_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        List all strategies with optional filtering.

        Args:
            status: Optional status filter
            strategy_type: Optional type filter

        Returns:
            List of strategy dictionaries
        """
        try:
            if status and strategy_type:
                # Need to filter by both - get all and filter in memory
                strategies = await self.repo.get_all()
                strategies = [
                    s for s in strategies
                    if s.status == status and s.strategy_type == strategy_type
                ]
            elif status:
                strategies = await self.repo.get_by_status(status)
            elif strategy_type:
                strategies = await self.repo.get_by_strategy_type(strategy_type)
            else:
                strategies = await self.repo.get_all()

            result = [self._strategy_to_dict(s) for s in strategies]

            logger.info(
                "Listed strategies",
                extra={
                    "count": len(result),
                    "status_filter": status,
                    "type_filter": strategy_type,
                }
            )

            return result

        except Exception as e:
            logger.error(f"Failed to list strategies: {e}")
            raise

    async def get_strategy(self, strategy_id: str) -> dict[str, Any]:
        """
        Get single strategy by ID.

        Args:
            strategy_id: Strategy UUID as string

        Returns:
            Strategy dictionary

        Raises:
            StrategyNotFoundError: If strategy not found
        """
        try:
            try:
                strategy_uuid = UUID(strategy_id)
            except (ValueError, AttributeError):
                # Invalid UUID format - treat as not found
                logger.warning(f"Invalid UUID format for strategy_id: {strategy_id}")
                raise StrategyNotFoundError("Invalid strategy ID format")

            strategy = await self.repo.get_by_id(strategy_uuid)
            result = self._strategy_to_dict(strategy)

            logger.info("Retrieved strategy", extra={"strategy_id": strategy_id})

            return result

        except StrategyNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get strategy: {e}", extra={"strategy_id": strategy_id})
            raise

    async def get_strategy_performance(self, strategy_id: str) -> dict[str, Any]:
        """
        Get strategy performance metrics only.

        Args:
            strategy_id: Strategy UUID as string

        Returns:
            Dictionary with performance fields
        """
        try:
            strategy = await self.repo.get_by_id(UUID(strategy_id))

            result = {
                "strategy_id": str(strategy.id),
                "name": strategy.name,
                "total_pnl": float(strategy.total_pnl),
                "total_trades": strategy.total_trades,
                "winning_trades": strategy.winning_trades,
                "losing_trades": strategy.losing_trades,
                "win_rate": float(strategy.win_rate),
                "max_drawdown_pct": float(strategy.max_drawdown_pct) if strategy.max_drawdown_pct is not None else 0.0,
                "last_executed_at": strategy.last_executed_at.isoformat() if strategy.last_executed_at else None,
                "generated_at": datetime.now(UTC).isoformat(),
            }

            logger.info(
                "Retrieved strategy performance",
                extra={"strategy_id": strategy_id}
            )

            return result

        except StrategyNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get strategy performance: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def create_strategy(self, strategy_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new strategy with validation.

        Args:
            strategy_data: Strategy configuration

        Returns:
            Created strategy dictionary

        Raises:
            ValueError: If validation fails
            DuplicateStrategyError: If name already exists
        """
        try:
            # Validate required fields
            if not strategy_data.get("name"):
                raise ValueError("Strategy name is required")

            if not strategy_data.get("strategy_type"):
                raise ValueError("Strategy type is required")

            if strategy_data["strategy_type"] not in VALID_STRATEGY_TYPES:
                raise ValueError(
                    f"Invalid strategy type: {strategy_data['strategy_type']}. "
                    f"Must be one of {VALID_STRATEGY_TYPES}"
                )

            # Validate symbols list
            symbols = strategy_data.get("symbols", [])
            if not isinstance(symbols, list):
                raise ValueError("Symbols must be a list")

            if not symbols:
                logger.warning("Creating strategy with empty symbols list")

            # Validate parameters dict
            parameters = strategy_data.get("parameters", {})
            if not isinstance(parameters, dict):
                raise ValueError("Parameters must be a dictionary")

            # Default creation origin for UI-created strategies
            if "_origin" not in parameters:
                parameters["_origin"] = "ui"
            strategy_data["parameters"] = parameters

            # Set default status if not provided
            if "status" not in strategy_data:
                strategy_data["status"] = "inactive"

            # Validate status if provided
            if strategy_data["status"] not in VALID_STATUSES:
                raise ValueError(
                    f"Invalid status: {strategy_data['status']}. "
                    f"Must be one of {VALID_STATUSES}"
                )

            # Create strategy
            strategy = await self.repo.create(strategy_data)
            await self.session.commit()

            result = self._strategy_to_dict(strategy)

            logger.info(
                "Strategy created",
                extra={
                    "strategy_id": str(strategy.id),
                    "strategy_name": strategy.name,
                    "type": strategy.strategy_type,
                }
            )

            # No WebSocket broadcast for creation (strategy not started yet)

            return result

        except (ValueError, DuplicateStrategyError):
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create strategy: {e}")
            raise

    async def start_strategy(self, strategy_id: str) -> dict[str, Any]:
        """
        Start a strategy (transition to active status).

        Args:
            strategy_id: Strategy UUID as string

        Returns:
            Updated strategy dictionary
        """
        try:
            # Get current strategy
            strategy = await self.repo.get_by_id(UUID(strategy_id))

            # Validate status transition
            self._validate_status_transition(strategy.status, "active")

            # If already active, return as-is (no-op)
            if strategy.status == "active":
                logger.info("Strategy already active", extra={"strategy_id": strategy_id})
                return self._strategy_to_dict(strategy)

            # Update status to active with started_at timestamp
            updated_strategy = await self.repo.update_status(
                UUID(strategy_id),
                status="active",
                started_at=datetime.now(UTC),
                stopped_at=None,  # Clear stopped_at when starting
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            logger.info(
                "Strategy started",
                extra={"strategy_id": strategy_id, "strategy_name": updated_strategy.name}
            )

            # Broadcast WebSocket event (transform to frontend format)
            try:
                transformed_data = _transform_for_broadcast(result)
                await broadcast_strategy_update(
                    topic='strategies',
                    strategy_data=transformed_data
                )
            except Exception as e:
                logger.error(f"Failed to broadcast strategy start: {e}")
                # Don't fail the operation if broadcast fails

            return result

        except (StrategyNotFoundError, InvalidStatusTransitionError):
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to start strategy: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def stop_strategy(self, strategy_id: str) -> dict[str, Any]:
        """
        Stop a strategy (transition to inactive status).

        Args:
            strategy_id: Strategy UUID as string

        Returns:
            Updated strategy dictionary
        """
        try:
            # Get current strategy
            strategy = await self.repo.get_by_id(UUID(strategy_id))

            # Validate status transition
            self._validate_status_transition(strategy.status, "inactive")

            # If already inactive, return as-is (no-op)
            if strategy.status == "inactive":
                logger.info("Strategy already inactive", extra={"strategy_id": strategy_id})
                return self._strategy_to_dict(strategy)

            # Update status to inactive with stopped_at timestamp
            updated_strategy = await self.repo.update_status(
                UUID(strategy_id),
                status="inactive",
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            logger.info(
                "Strategy stopped",
                extra={"strategy_id": strategy_id, "strategy_name": updated_strategy.name}
            )

            # Broadcast WebSocket event (transform to frontend format)
            try:
                transformed_data = _transform_for_broadcast(result)
                await broadcast_strategy_update(
                    topic='strategies',
                    strategy_data=transformed_data
                )
            except Exception as e:
                logger.error(f"Failed to broadcast strategy stop: {e}")

            return result

        except (StrategyNotFoundError, InvalidStatusTransitionError):
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to stop strategy: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def pause_strategy(self, strategy_id: str) -> dict[str, Any]:
        """
        Pause a strategy (transition to paused status).

        Args:
            strategy_id: Strategy UUID as string

        Returns:
            Updated strategy dictionary
        """
        try:
            # Get current strategy
            strategy = await self.repo.get_by_id(UUID(strategy_id))

            # Validate status transition
            self._validate_status_transition(strategy.status, "paused")

            # If already paused, return as-is (no-op)
            if strategy.status == "paused":
                logger.info("Strategy already paused", extra={"strategy_id": strategy_id})
                return self._strategy_to_dict(strategy)

            # Update status to paused
            updated_strategy = await self.repo.update_status(
                UUID(strategy_id),
                status="paused",
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            logger.info(
                "Strategy paused",
                extra={"strategy_id": strategy_id, "strategy_name": updated_strategy.name}
            )

            # Broadcast WebSocket event (transform to frontend format)
            try:
                transformed_data = _transform_for_broadcast(result)
                await broadcast_strategy_update(
                    topic='strategies',
                    strategy_data=transformed_data
                )
            except Exception as e:
                logger.error(f"Failed to broadcast strategy pause: {e}")

            return result

        except (StrategyNotFoundError, InvalidStatusTransitionError):
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to pause strategy: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def update_performance_metrics(
        self, strategy_id: str, metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update strategy performance metrics.

        Args:
            strategy_id: Strategy UUID as string
            metrics: Dictionary with performance fields (total_pnl, total_trades, etc.)

        Returns:
            Updated strategy dictionary
        """
        try:
            # Calculate win rate if trade counts provided
            if "total_trades" in metrics and "winning_trades" in metrics:
                total_trades = metrics["total_trades"]
                winning_trades = metrics["winning_trades"]

                if total_trades > 0:
                    win_rate = Decimal(winning_trades) / Decimal(total_trades)
                    metrics["win_rate"] = win_rate
                else:
                    metrics["win_rate"] = Decimal("0.0")

            # Convert float values to Decimal for database
            if "total_pnl" in metrics and not isinstance(metrics["total_pnl"], Decimal):
                metrics["total_pnl"] = Decimal(str(metrics["total_pnl"]))

            if "win_rate" in metrics and not isinstance(metrics["win_rate"], Decimal):
                metrics["win_rate"] = Decimal(str(metrics["win_rate"]))

            # Update performance metrics
            updated_strategy = await self.repo.update_performance(
                UUID(strategy_id),
                metrics
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            logger.info(
                "Strategy performance updated",
                extra={
                    "strategy_id": strategy_id,
                    "total_pnl": float(updated_strategy.total_pnl),
                    "total_trades": updated_strategy.total_trades,
                    "win_rate": float(updated_strategy.win_rate),
                }
            )

            # Broadcast WebSocket event (transform to frontend format)
            try:
                transformed_data = _transform_for_broadcast(result)
                await broadcast_strategy_update(
                    topic='strategies',
                    strategy_data=transformed_data
                )
            except Exception as e:
                logger.error(f"Failed to broadcast strategy performance update: {e}")

            return result

        except StrategyNotFoundError:
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to update strategy performance: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def update_strategy(
        self, strategy_id: str, update_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update strategy configuration fields.

        Args:
            strategy_id: Strategy UUID as string
            update_data: Dictionary of fields to update

        Returns:
            Updated strategy dictionary
        """
        try:
            # Validate strategy type if being updated
            if "strategy_type" in update_data:
                if update_data["strategy_type"] not in VALID_STRATEGY_TYPES:
                    raise ValueError(
                        f"Invalid strategy type: {update_data['strategy_type']}"
                    )

            # Validate status if being updated
            if "status" in update_data:
                if update_data["status"] not in VALID_STATUSES:
                    raise ValueError(f"Invalid status: {update_data['status']}")

                # Get current strategy to validate transition
                strategy = await self.repo.get_by_id(UUID(strategy_id))
                self._validate_status_transition(strategy.status, update_data["status"])

            # Update strategy
            updated_strategy = await self.repo.update(
                UUID(strategy_id),
                update_data
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            logger.info(
                "Strategy updated",
                extra={
                    "strategy_id": strategy_id,
                    "updated_fields": list(update_data.keys()),
                }
            )

            return result

        except (StrategyNotFoundError, DuplicateStrategyError, InvalidStatusTransitionError, ValueError):
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to update strategy: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def delete_strategy(self, strategy_id: str) -> None:
        """
        Delete a strategy.

        Args:
            strategy_id: Strategy UUID as string
        """
        try:
            await self.repo.delete(UUID(strategy_id))
            await self.session.commit()

            logger.info("Strategy deleted", extra={"strategy_id": strategy_id})

        except StrategyNotFoundError:
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to delete strategy: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise
    # ==================== VERSIONING METHODS (M-41) ====================

    async def create_version_snapshot(
        self,
        strategy_id: str,
        change_description: str = "",
    ) -> dict[str, Any]:
        """
        Create a version snapshot of a strategy.

        Args:
            strategy_id: Strategy UUID as string
            change_description: Description of the change

        Returns:
            Version information dictionary
        """
        try:
            strategy = await self.repo.get_by_id(UUID(strategy_id))
            strategy_dict = self._strategy_to_dict(strategy)

            version = self._version_manager.create_version(
                strategy_dict,
                VersionChangeType.MANUAL_SNAPSHOT,
                change_description=change_description or "Manual snapshot",
                created_by=self.user_id,
            )

            logger.info(
                "Strategy version snapshot created",
                extra={
                    "strategy_id": strategy_id,
                    "version_id": version.version_id,
                    "version_number": version.version_number,
                }
            )

            return self._version_manager.to_dict(version)

        except StrategyNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to create version snapshot: {e}",
                extra={"strategy_id": strategy_id}
            )
            raise

    async def get_version_history(
        self,
        strategy_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get version history for a strategy.

        Args:
            strategy_id: Strategy UUID as string
            limit: Optional limit on versions to return

        Returns:
            List of version dictionaries, newest first
        """
        versions = self._version_manager.get_version_history(strategy_id, limit)
        return [self._version_manager.to_dict(v) for v in versions]

    async def compare_versions(
        self,
        version_a_id: str,
        version_b_id: str,
    ) -> dict[str, Any]:
        """
        Compare two strategy versions.

        Args:
            version_a_id: First version ID
            version_b_id: Second version ID

        Returns:
            Comparison results dictionary
        """
        comparison = self._version_manager.compare_versions(version_a_id, version_b_id)

        return {
            "version_a": comparison.version_a,
            "version_b": comparison.version_b,
            "has_changes": comparison.has_changes,
            "parameters_changed": comparison.parameters_changed,
            "symbols_added": comparison.symbols_added,
            "symbols_removed": comparison.symbols_removed,
            "risk_limits_changed": comparison.risk_limits_changed,
            "performance_delta": comparison.performance_delta,
        }

    async def rollback_to_version(
        self,
        strategy_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        """
        Rollback a strategy to a previous version.

        Args:
            strategy_id: Strategy UUID as string
            version_id: Version ID to rollback to

        Returns:
            Updated strategy dictionary
        """
        try:
            # Get rollback config
            rollback_config = self._version_manager.get_rollback_config(version_id)

            # Filter out None values and only include updateable fields
            update_data = {
                k: v for k, v in rollback_config.items()
                if v is not None and k in ["symbols", "parameters"]
            }

            # Update strategy
            updated_strategy = await self.repo.update(
                UUID(strategy_id),
                update_data
            )
            await self.session.commit()

            result = self._strategy_to_dict(updated_strategy)

            # Create new version recording the rollback
            self._version_manager.create_version(
                result,
                VersionChangeType.PARAMETERS_CHANGED,
                change_description=f"Rollback to version {version_id}",
                created_by=self.user_id,
            )

            logger.info(
                "Strategy rolled back",
                extra={
                    "strategy_id": strategy_id,
                    "rollback_version_id": version_id,
                }
            )

            return result

        except StrategyNotFoundError:
            await self.session.rollback()
            raise
        except ValueError as e:
            await self.session.rollback()
            raise ValueError(f"Invalid version for rollback: {e}")
        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to rollback strategy: {e}",
                extra={"strategy_id": strategy_id, "version_id": version_id}
            )
            raise