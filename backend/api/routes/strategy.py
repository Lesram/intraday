"""
Strategy API routes.
Handles strategy management, feature ingestion, and signal batch operations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.socketio_server import broadcast_strategy_update
from backend.infra.db import get_session
from backend.infra.repositories.strategies import DuplicateStrategyError, StrategyNotFoundError
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.services.strategy_service import InvalidStatusTransitionError, StrategyService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/strategies", tags=["Strategy"])


def transform_strategy_response(strategy: dict) -> dict:
    """Transform strategy dict from service to API response format.

    Converts snake_case to camelCase and restructures performance fields.
    Maps 'inactive' status to 'stopped' for frontend compatibility.

    Args:
        strategy: Strategy dict from StrategyService

    Returns:
        Transformed dict with camelCase keys and nested performance
    """
    return {
        "strategyId": strategy["id"],
        "name": strategy["name"],
        "description": strategy.get("description"),
        "strategyType": strategy.get("strategy_type"),
        "status": "stopped" if strategy["status"] == "inactive" else strategy["status"],
        "symbols": strategy.get("symbols", []),
        "parameters": strategy.get("parameters", {}),
        "performance": {
            "totalTrades": strategy.get("total_trades", 0),
            "winRate": strategy.get("win_rate", 0.0),
            "totalPnL": strategy.get("total_pnl", 0.0),
            "sharpeRatio": 0.0,  # Not stored in DB, would need calculation
            "maxDrawdown": strategy.get("max_drawdown_pct", 0.0),  # Read from max_drawdown_pct
        },
        "createdAt": strategy["created_at"],
        "updatedAt": strategy["updated_at"],
        "lastExecutedAt": strategy.get("last_executed_at"),
    }


class StrategyCreate(BaseModel):
    """Strategy creation request."""
    name: str = Field(..., min_length=1, max_length=100, description="Strategy name (1-100 characters)")
    description: str | None = Field(None, max_length=1000, description="Strategy description (max 1000 characters)")
    strategy_type: str = Field(
        ...,
        description="Strategy type. Implementation types: momentum, mean_reversion, ensemble, stat_arb. Classification types: technical, fundamental, quantitative, hybrid"
    )
    symbols: list[str] = Field(..., min_length=1, description="At least one symbol required")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")

    @field_validator('name')
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty or only whitespace."""
        if not v or not v.strip():
            raise ValueError('Strategy name cannot be empty or only whitespace')
        return v.strip()

    @field_validator('parameters')
    @classmethod
    def validate_risk_parameters(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate risk and size parameters are positive when present."""
        # Risk/limit fields that should be positive
        positive_fields = [
            'maxDailyLoss', 'maxDrawdownPct', 'max_daily_loss', 'max_drawdown_pct',
            'maxPositionSize', 'max_position_size', 'stopLoss', 'stop_loss',
            'takeProfit', 'take_profit', 'riskPerTrade', 'risk_per_trade'
        ]

        for field in positive_fields:
            if field in v and v[field] is not None:
                try:
                    value = float(v[field])
                    if value < 0:
                        raise ValueError(f'{field} must be a positive number, got {value}')
                except TypeError:
                    # Only catch TypeError for invalid number conversion
                    raise ValueError(f'{field} must be a valid number')
        return v


class StrategyUpdate(BaseModel):
    """Strategy update request."""
    name: str | None = None
    description: str | None = None
    symbols: list[str] | None = None
    parameters: dict[str, Any] | None = None
    status: str | None = None


class StrategyPerformanceResponse(BaseModel):
    """Strategy performance metrics."""
    totalTrades: int = Field(default=0, alias="totalTrades")
    winRate: float = Field(default=0.0, alias="winRate")
    totalPnL: float = Field(default=0.0, alias="totalPnL")
    sharpeRatio: float = Field(default=0.0, alias="sharpeRatio")
    maxDrawdown: float = Field(default=0.0, alias="maxDrawdown")

    model_config = ConfigDict(populate_by_name=True)


class StrategyResponse(BaseModel):
    """Strategy response model with camelCase aliases for frontend compatibility."""
    id: str
    name: str
    description: str | None = None
    strategyType: str | None = Field(default=None, alias="strategyType")
    status: str
    symbols: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    performance: StrategyPerformanceResponse | None = None
    createdAt: str | None = Field(default=None, alias="createdAt")
    updatedAt: str | None = Field(default=None, alias="updatedAt")
    lastExecutedAt: str | None = Field(default=None, alias="lastExecutedAt")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================================
# STRATEGY TEMPLATES ENDPOINTS (Phase 3.1: Strategy Builder)
# ============================================================================

@router.get("/templates", response_model=list[dict[str, Any]])
async def get_strategy_templates(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> list[dict[str, Any]]:
    """
    Get all strategy templates with parameter definitions.
    Used by strategy builder wizard to provide defaults and validation.

    Returns list of all 8 strategy templates with:
    - Parameter definitions (name, type, default, min, max, description)
    - Default risk limits
    - Strategy metadata (name, description, icon, category)

    Returns:
        List of strategy templates
    """
    try:
        from backend.data.strategy_templates import get_all_templates

        templates = get_all_templates()
        # Convert Pydantic models to dicts with camelCase
        return [template.model_dump(by_alias=True) for template in templates]

    except Exception as e:
        logger.error(f"Failed to get strategy templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get strategy templates")


@router.get("/templates/{strategy_type}", response_model=dict[str, Any])
async def get_strategy_template(
    strategy_type: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """
    Get specific strategy template by type.
    Returns parameter definitions and default values for a strategy type.

    Args:
        strategy_type: Strategy type (technical_analysis, fundamental_analysis, etc.)

    Returns:
        Strategy template with parameters and defaults

    Raises:
        HTTPException: 404 if template not found for strategy type
    """
    try:
        from backend.data.strategy_templates import get_template

        template = get_template(strategy_type)
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found for strategy type: {strategy_type}"
            )

        return template.model_dump(by_alias=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template for {strategy_type}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get strategy template")


# ============================================================================
# STRATEGY STATUS ENDPOINT (must be before /{strategy_id} to avoid shadowing)
# ============================================================================

@router.get("/status")
async def get_strategy_status():
    """Get strategy system status."""
    return {
        "status": "operational",
        "active_strategies": 3,
        "last_update": datetime.now().isoformat(),
        "features_processed": 12500,
        "signals_generated": 450
    }


# ============================================================================
# STRATEGY CRUD ENDPOINTS
# ============================================================================

@router.get("/", response_model=list[dict[str, Any]])
async def get_strategies(
    status: str | None = None,
    strategy_type: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> list[dict[str, Any]]:
    """Get list of available strategies.

    Args:
        status: Optional status filter ('active', 'inactive', 'paused', 'error')
        strategy_type: Optional type filter (momentum, mean_reversion, ensemble, stat_arb, technical, fundamental, quantitative, hybrid)
        session: Database session
        current_user: Authenticated user

    Returns:
        List of strategies with transformed field names
    """
    try:
        service = StrategyService(session, current_user.username)
        strategies = await service.list_strategies(status=status, strategy_type=strategy_type)

        # Transform each strategy to frontend format
        return [transform_strategy_response(s) for s in strategies]

    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail="Failed to list strategies")


@router.get("/{strategy_id}", response_model=dict[str, Any])
async def get_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Get single strategy by ID.

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        Strategy with transformed field names

    Raises:
        HTTPException: 404 if strategy not found
    """
    try:
        service = StrategyService(session, current_user.username)
        strategy = await service.get_strategy(strategy_id)
        return transform_strategy_response(strategy)

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get strategy")


@router.post("/", response_model=dict[str, Any], status_code=201)
async def create_strategy(
    strategy: StrategyCreate,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Create a new strategy.

    Args:
        strategy: Strategy creation data
        session: Database session
        current_user: Authenticated user

    Returns:
        Created strategy with transformed field names

    Raises:
        HTTPException: 409 if strategy name already exists, 400 if validation fails
    """
    try:
        service = StrategyService(session, current_user.username)

        # Build strategy data dict
        strategy_data = {
            "name": strategy.name,
            "description": strategy.description,
            "strategy_type": strategy.strategy_type,
            "symbols": strategy.symbols,
            "parameters": strategy.parameters,
        }

        created = await service.create_strategy(strategy_data)
        logger.info(f"Strategy created: {created['name']} (ID: {created['id']})")

        return transform_strategy_response(created)

    except DuplicateStrategyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Strategy creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strategy creation failed: {type(e).__name__}: {str(e)}")


@router.patch("/{strategy_id}", response_model=dict[str, Any])
async def update_strategy(
    strategy_id: str,
    updates: StrategyUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Update an existing strategy.

    Args:
        strategy_id: Strategy UUID
        updates: Fields to update
        session: Database session
        current_user: Authenticated user

    Returns:
        Updated strategy with transformed field names

    Raises:
        HTTPException: 404 if not found, 409 if name conflict, 400 if validation fails
    """
    try:
        service = StrategyService(session, current_user.username)

        # Build update dict (only include provided fields)
        update_data = {}
        if updates.name is not None:
            update_data["name"] = updates.name
        if updates.description is not None:
            update_data["description"] = updates.description
        if updates.symbols is not None:
            update_data["symbols"] = updates.symbols
        if updates.parameters is not None:
            update_data["parameters"] = updates.parameters
        # Note: status updates should use start/stop/pause endpoints

        updated = await service.update_strategy(strategy_id, update_data)
        logger.info(f"Strategy updated: {strategy_id}")

        return transform_strategy_response(updated)

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateStrategyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Strategy update failed: {e}")
        raise HTTPException(status_code=500, detail="Strategy update failed")


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> None:
    """Delete a strategy.

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        None (204 No Content on success)

    Raises:
        HTTPException: 404 if not found
    """
    try:
        service = StrategyService(session, current_user.username)
        await service.delete_strategy(strategy_id)
        logger.info(f"Strategy deleted: {strategy_id}")

        # Broadcast deletion to WebSocket clients
        await broadcast_strategy_update('strategies', {
            'action': 'deleted',
            'strategyId': strategy_id
        })

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Strategy deletion failed: {e}")
        raise HTTPException(status_code=500, detail="Strategy deletion failed")


class FeatureBatch(BaseModel):
    """Feature batch for strategy processing."""
    features: list[dict[str, Any]] = Field(..., description="List of feature vectors")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalBatch(BaseModel):
    """Signal batch for strategy processing."""
    signals: list[dict[str, Any]] = Field(..., description="List of signals")
    strategy_id: str = Field(..., description="Strategy identifier")
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/{strategy_id}/start", response_model=dict[str, Any])
async def start_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Start a strategy (transition to 'active' status).

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        Updated strategy with transformed field names

    Raises:
        HTTPException: 404 if not found, 400 if invalid transition
    """
    try:
        service = StrategyService(session, current_user.username)
        started = await service.start_strategy(strategy_id)
        logger.info(f"Strategy started: {strategy_id}")

        response = transform_strategy_response(started)

        # Broadcast update to WebSocket clients
        await broadcast_strategy_update('strategies', {
            'action': 'updated',
            'strategy': response
        })

        return response

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start strategy: {e}")
        raise HTTPException(status_code=500, detail="Failed to start strategy")


@router.post("/{strategy_id}/stop", response_model=dict[str, Any])
async def stop_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Stop a strategy (transition to 'inactive' status).

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        Updated strategy with transformed field names

    Raises:
        HTTPException: 404 if not found, 400 if invalid transition
    """
    try:
        service = StrategyService(session, current_user.username)
        stopped = await service.stop_strategy(strategy_id)
        logger.info(f"Strategy stopped: {strategy_id}")

        response = transform_strategy_response(stopped)

        # Broadcast update to WebSocket clients
        await broadcast_strategy_update('strategies', {
            'action': 'updated',
            'strategy': response
        })

        return response

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop strategy: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop strategy")


@router.post("/{strategy_id}/pause", response_model=dict[str, Any])
async def pause_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Pause a strategy (transition to 'paused' status).

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        Updated strategy with transformed field names

    Raises:
        HTTPException: 404 if not found, 400 if invalid transition
    """
    try:
        service = StrategyService(session, current_user.username)
        paused = await service.pause_strategy(strategy_id)
        logger.info(f"Strategy paused: {strategy_id}")

        response = transform_strategy_response(paused)

        # Broadcast update to WebSocket clients
        await broadcast_strategy_update('strategies', {
            'action': 'updated',
            'strategy': response
        })

        return response

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to pause strategy: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause strategy")


@router.get("/{strategy_id}/performance")
async def get_strategy_performance(
    strategy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Get strategy performance metrics.

    Args:
        strategy_id: Strategy UUID
        session: Database session
        current_user: Authenticated user

    Returns:
        Performance metrics in camelCase format

    Raises:
        HTTPException: 404 if strategy not found
    """
    try:
        service = StrategyService(session, current_user.username)
        metrics = await service.get_strategy_performance(strategy_id)

        # Transform performance metrics to camelCase
        return {
            "strategyId": strategy_id,
            "totalTrades": metrics.get("total_trades", 0),
            "winRate": metrics.get("win_rate", 0.0),
            "totalPnL": metrics.get("total_pnl", 0.0),
            "sharpeRatio": 0.0,  # Not stored in DB
            "maxDrawdown": metrics.get("max_drawdown_pct", 0.0)
        }

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get strategy performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to get strategy performance")


class PerformanceUpdate(BaseModel):
    """Performance metrics update."""
    totalTrades: int = Field(ge=0, description="Total number of trades")
    winRate: float = Field(ge=0.0, le=1.0, description="Win rate (0.0-1.0)")
    totalPnL: float = Field(description="Total profit/loss")
    sharpeRatio: float = Field(description="Sharpe ratio (not stored, for display only)")
    maxDrawdown: float = Field(ge=-1.0, le=0.0, description="Maximum drawdown as decimal (-0.50 for -50%)")


@router.put("/{strategy_id}/performance", response_model=dict[str, Any])
async def update_strategy_performance(
    strategy_id: str,
    metrics: PerformanceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """Update strategy performance metrics.

    Args:
        strategy_id: Strategy UUID
        metrics: Performance metrics to update
        session: Database session
        current_user: Authenticated user

    Returns:
        Updated strategy with transformed field names

    Raises:
        HTTPException: 404 if strategy not found
    """
    try:
        service = StrategyService(session, current_user.username)

        # Convert camelCase to snake_case for service
        # Note: sharpe_ratio not stored in DB, can be calculated on-the-fly
        # maxDrawdown becomes max_drawdown_pct (stored as percentage in DB)
        metrics_data = {
            "total_trades": metrics.totalTrades,
            "win_rate": metrics.winRate,
            "total_pnl": metrics.totalPnL,
            "max_drawdown_pct": metrics.maxDrawdown,  # Fixed: use max_drawdown_pct
            # sharpe_ratio excluded - not a DB column
        }

        updated = await service.update_performance_metrics(strategy_id, metrics_data)
        logger.info(f"Performance updated for strategy: {strategy_id}")

        return transform_strategy_response(updated)

    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update strategy performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update strategy performance: {str(e)}")


@router.post("/features/ingest")
async def ingest_features(request: Request, batch: FeatureBatch):
    """Ingest feature batch for strategy processing."""
    try:
        # Mock feature processing
        processed_count = len(batch.features)

        logger.info(f"Ingested {processed_count} features for strategy processing")

        return {
            "status": "accepted",
            "processed_count": processed_count,
            "batch_id": f"batch_{abs(hash(str(batch.features))) % 10000}",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Feature ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="Feature ingestion failed")


@router.post("/signals/batch")
async def process_signal_batch(request: Request, batch: SignalBatch):
    """Process a batch of signals for strategy execution."""
    try:
        processed_signals = []

        for signal in batch.signals:
            # Mock signal processing
            processed_signal = {
                "signal_id": f"sig_{abs(hash(str(signal))) % 10000}",
                "original": signal,
                "status": "processed",
                "timestamp": datetime.now().isoformat()
            }
            processed_signals.append(processed_signal)

        return {
            "status": "completed",
            "strategy_id": batch.strategy_id,
            "processed_count": len(processed_signals),
            "signals": processed_signals,
            "batch_timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Signal batch processing failed: {e}")
        raise HTTPException(status_code=500, detail="Signal batch processing failed")


@router.post("/signals/submit")
async def submit_strategy_signal(request: Request):
    """Submit a single signal for strategy processing."""
    try:
        body = await request.json()

        # Mock single signal processing
        signal_id = f"sig_{abs(hash(str(body))) % 10000}"

        return {
            "signal_id": signal_id,
            "status": "submitted",
            "strategy": "default",
            "timestamp": datetime.now().isoformat(),
            "data": body
        }

    except Exception as e:
        logger.error(f"Signal submission failed: {e}")
        raise HTTPException(status_code=500, detail="Signal submission failed")
