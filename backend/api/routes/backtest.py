"""
Backtest API routes.
Handles backtest execution, history retrieval, and result management.
"""

from datetime import date
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_session
from backend.infra.repositories.strategies import StrategyNotFoundError
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.models.backtest import (
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
)
from backend.services.backtest_service import BacktestService
from backend.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


async def get_user_uuid_from_username(db: AsyncSession, username: str) -> str:
    """
    Convert username to a UUID string for backtest ownership.
    
    The backtests table uses UUID for user_id (no FK to users table).
    We generate a deterministic UUID v5 from the username to maintain
    consistent user identification across backtests.
    """
    import uuid as uuid_module
    # Use a namespace UUID to generate deterministic UUIDs from usernames
    NAMESPACE = uuid_module.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace
    user_uuid = uuid_module.uuid5(NAMESPACE, username)
    return str(user_uuid)


async def get_backtest_service(
    session: AsyncSession = Depends(get_session),
) -> BacktestService:
    """Dependency to get BacktestService instance."""
    return BacktestService(session)


async def get_strategy_service(
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> StrategyService:
    """Dependency to get StrategyService instance."""
    return StrategyService(session, user_id=str(user.username))


@router.post(
    "/strategies/{strategy_id}/backtest",
    response_model=BacktestResult,
    status_code=200,
    summary="Run backtest on a strategy",
    description="Execute a backtest simulation on historical data for the specified strategy"
)
async def run_backtest(
    strategy_id: str,
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    backtest_service: BacktestService = Depends(get_backtest_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> BacktestResult:
    """
    Run a backtest on a strategy.

    Executes the strategy on historical data and returns comprehensive
    performance metrics including returns, Sharpe ratio, drawdown, and
    detailed trade log.

    Args:
        strategy_id: UUID of the strategy to backtest
        request: Backtest parameters (dates, capital, parameters)

    Returns:
        BacktestResult with complete metrics and trade history

    Raises:
        404: Strategy not found or not owned by user
        400: Invalid request parameters
        500: Backtest execution failed
    """
    logger.info(f"Backtest request for strategy {strategy_id} by user {user.username}")

    try:
        # Get strategy and verify ownership
        strategy = await strategy_service.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy {strategy_id} not found or not accessible"
            )

        # Validate date range
        if request.start_date >= request.end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before end_date"
            )

        if request.end_date > date.today():
            raise HTTPException(
                status_code=400,
                detail="end_date cannot be in the future"
            )

        # Check duration (max 5 years)
        duration_days = (request.end_date - request.start_date).days
        if duration_days > 1825:
            raise HTTPException(
                status_code=400,
                detail="Maximum backtest duration is 5 years (1825 days)"
            )

        # Convert strategy dict to object-like structure for service
        from types import SimpleNamespace
        strategy_obj = SimpleNamespace(**strategy)

        # Get integer user_id from username
        user_id = await get_user_uuid_from_username(db, user.username)

        # Execute backtest
        logger.info(
            f"Executing backtest: {request.start_date} to {request.end_date}, "
            f"capital=${request.initial_capital:,.2f}"
        )

        result = await backtest_service.run_backtest(
            strategy=strategy_obj,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            parameters=request.parameters,
            user_id=user_id,
        )

        logger.info(
            f"Backtest completed: {result.metrics.total_trades} trades, "
            f"return={result.metrics.total_return:.2f}%"
        )

        return result

    except StrategyNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Backtest execution failed: {str(e)}"
        )


@router.get(
    "/history",
    response_model=list[BacktestSummary],
    summary="Get backtest history",
    description="Retrieve list of past backtests with optional filtering"
)
async def get_backtest_history(
    strategy_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    skip: int = 0,  # Added for compatibility with frontend
    service: BacktestService = Depends(get_backtest_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_session),
) -> list[BacktestSummary]:
    """
    Get list of past backtests.

    Returns a paginated list of backtest summaries, optionally filtered
    by strategy.

    Args:
        strategy_id: Optional strategy ID to filter by
        limit: Maximum results to return (default 50, max 100)
        offset: Pagination offset (default 0)
        skip: Alias for offset (for backward compatibility)

    Returns:
        List of BacktestSummary objects

    Raises:
        400: Invalid pagination parameters
    """
    # Use skip if provided, otherwise use offset
    actual_offset = skip if skip > 0 else offset

    if limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum limit is 100"
        )

    if limit < 1:
        raise HTTPException(
            status_code=400,
            detail="Limit must be at least 1"
        )

    if actual_offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset must be non-negative"
        )

    try:
        user_id = await get_user_uuid_from_username(db, user.username)
        history = await service.get_backtest_history(
            user_id=user_id,
            strategy_id=strategy_id,
            limit=limit,
            offset=actual_offset,
        )

        logger.info(
            f"Retrieved {len(history)} backtests for user {user.username} "
            f"(limit={limit}, offset={actual_offset}, strategy_id={strategy_id})"
        )

        return history

    except Exception as e:
        logger.error(f"Failed to retrieve backtest history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backtest history: {str(e)}"
        )


@router.get(
    "/{backtest_id}",
    response_model=BacktestResult,
    summary="Get backtest result",
    description="Retrieve detailed results for a specific backtest"
)
async def get_backtest_result(
    backtest_id: str,
    db: AsyncSession = Depends(get_session),
    service: BacktestService = Depends(get_backtest_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> BacktestResult:
    """
    Get detailed backtest result.

    Returns complete backtest results including equity curve, trade log,
    and all performance metrics.

    Args:
        backtest_id: UUID of the backtest

    Returns:
        BacktestResult with complete details

    Raises:
        404: Backtest not found or not owned by user
    """
    try:
        user_id = await get_user_uuid_from_username(db, user.username)
        result = await service.get_backtest_result(
            backtest_id=backtest_id,
            user_id=user_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Backtest {backtest_id} not found or not accessible"
            )

        logger.info(f"Retrieved backtest {backtest_id} for user {user.username}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve backtest result: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backtest result: {str(e)}"
        )


@router.delete(
    "/{backtest_id}",
    status_code=204,
    summary="Delete backtest",
    description="Delete a backtest and all its data"
)
async def delete_backtest(
    backtest_id: str,
    db: AsyncSession = Depends(get_session),
    service: BacktestService = Depends(get_backtest_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Response:
    """
    Delete a backtest.

    Permanently removes the backtest record and all associated data.

    Args:
        backtest_id: UUID of the backtest to delete

    Returns:
        204 No Content on success

    Raises:
        404: Backtest not found or not owned by user
    """
    try:
        user_id = await get_user_uuid_from_username(db, user.username)
        deleted = await service.delete_backtest(
            backtest_id=backtest_id,
            user_id=user_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Backtest {backtest_id} not found or not accessible"
            )

        logger.info(f"Deleted backtest {backtest_id} for user {user.username}")

        return Response(status_code=204)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backtest: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete backtest: {str(e)}"
        )


@router.get(
    "/{backtest_id}/export",
    summary="Export backtest results",
    description="Export backtest results to CSV or JSON format"
)
async def export_backtest(
    backtest_id: str,
    format: str = "csv",
    db: AsyncSession = Depends(get_session),
    service: BacktestService = Depends(get_backtest_service),
    user: AuthenticatedUser = Depends(get_authenticated_user),
):
    """
    Export backtest results.

    Exports the trade log and results to CSV or JSON format for
    external analysis.

    Args:
        backtest_id: UUID of the backtest
        format: Export format ('csv' or 'json')

    Returns:
        File download

    Raises:
        404: Backtest not found or not owned by user
        400: Invalid format
    """
    if format not in ["csv", "json"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Use 'csv' or 'json'"
        )

    try:
        user_id = await get_user_uuid_from_username(db, user.username)
        result = await service.get_backtest_result(
            backtest_id=backtest_id,
            user_id=user_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Backtest {backtest_id} not found or not accessible"
            )

        if format == "csv":
            # Convert trade log to CSV
            import csv
            import io

            output = io.StringIO()
            if result.trade_log:
                fieldnames = [
                    "symbol", "side", "quantity", "entry_date", "entry_price",
                    "exit_date", "exit_price", "pnl", "pnl_percent",
                    "duration_days", "commission"
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()

                for trade in result.trade_log:
                    writer.writerow({
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "quantity": trade.quantity,
                        "entry_date": trade.entry_date,
                        "entry_price": trade.entry_price,
                        "exit_date": trade.exit_date,
                        "exit_price": trade.exit_price,
                        "pnl": trade.pnl,
                        "pnl_percent": trade.pnl_percent,
                        "duration_days": trade.duration_days,
                        "commission": trade.commission,
                    })

            csv_content = output.getvalue()

            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=backtest_{backtest_id}_trades.csv"
                }
            )

        else:  # json
            import json
            json_content = json.dumps(result.model_dump(), indent=2, default=str)

            return Response(
                content=json_content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=backtest_{backtest_id}_results.json"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export backtest: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export backtest: {str(e)}"
        )
