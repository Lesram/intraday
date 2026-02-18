"""
Risk Management API Routes
Comprehensive endpoints for risk metrics, violations, limits, and emergency stops.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.models.risk import (
    EmergencyStop,
    RiskDashboardData,
    RiskLimit,
    RiskMetric,
    RiskViolation,
    TriggerEmergencyStopRequest,
    UpdateRiskLimitRequest,
)
from backend.services.risk_manager import RiskManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


async def get_user_id_from_username(db: AsyncSession, username: str) -> int:
    """Get user ID from username."""
    result = await db.execute(
        text("SELECT id FROM users WHERE username = :username"),
        {"username": username}
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found"
        )
    return row[0]


# ===========================
# DASHBOARD & METRICS
# ===========================


@router.get("/dashboard", response_model=RiskDashboardData)
async def get_risk_dashboard(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get complete risk dashboard data.

    Returns:
    - All current risk metrics
    - Recent violations (last 24 hours)
    - Risk limit configurations
    - Emergency stop status
    """
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        dashboard_data = await risk_mgr.get_dashboard_data(user_id)
        return dashboard_data
    except Exception as e:
        logger.error(f"Error fetching risk dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch risk dashboard: {str(e)}",
        )


@router.get("/metrics", response_model=list[RiskMetric])
async def get_risk_metrics(
    user: AuthenticatedUser = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db_session)
):
    """
    Get all current risk metrics for user.

    Returns metrics for:
    - Daily loss
    - Max drawdown
    - Position count
    - Total exposure
    - Daily order count
    - Buying power used
    """
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        metrics = await risk_mgr.get_current_metrics(user_id)
        return metrics
    except Exception as e:
        logger.error(f"Error fetching risk metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch risk metrics: {str(e)}",
        )


@router.post("/metrics/calculate", response_model=list[RiskMetric])
async def calculate_risk_metrics(
    user: AuthenticatedUser = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db_session)
):
    """
    Calculate and update all risk metrics for user.

    This endpoint should be called:
    - After each trade execution
    - On demand when viewing risk dashboard
    - Periodically by background task
    """
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        metrics = await risk_mgr.calculate_and_update_metrics(user_id)
        return metrics
    except Exception as e:
        logger.error(f"Error calculating risk metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate risk metrics: {str(e)}",
        )


# ===========================
# VIOLATIONS
# ===========================


@router.get("/violations", response_model=list[RiskViolation])
async def get_risk_violations(
    hours: int = 24,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get recent risk violations.

    Args:
        hours: Number of hours to look back (default: 24)

    Returns violations that are either:
    - Unresolved (regardless of age)
    - Created within the specified time window
    """
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        violations = await risk_mgr.get_recent_violations(user_id, hours=hours)
        return violations
    except Exception as e:
        logger.error(f"Error fetching risk violations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch risk violations: {str(e)}",
        )


# ===========================
# RISK LIMITS
# ===========================


@router.get("/limits", response_model=list[RiskLimit])
async def get_risk_limits(
    user: AuthenticatedUser = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db_session)
):
    """Get all risk limit configurations for user."""
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        limits = await risk_mgr.get_risk_limits(user_id)
        return limits
    except Exception as e:
        logger.error(f"Error fetching risk limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch risk limits: {str(e)}",
        )


@router.put("/limits/{limit_name}", response_model=RiskLimit)
async def update_risk_limit(
    limit_name: str,
    request: UpdateRiskLimitRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Update or create a risk limit configuration.

    Args:
        limit_name: Name of the limit to update (e.g., 'daily_loss', 'max_drawdown')
        request: Limit configuration with value and thresholds

    Admin-only endpoint.
    """
    # Check admin privileges
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to update risk limits",
        )

    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        limit = await risk_mgr.update_risk_limit(
            user_id=user_id,
            limit_name=limit_name,
            request=request,
            updated_by=user_id,
        )
        return limit
    except Exception as e:
        logger.error(f"Error updating risk limit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update risk limit: {str(e)}",
        )


@router.delete("/limits/{limit_id}")
async def delete_risk_limit(
    limit_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a risk limit by ID."""
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        await risk_mgr.delete_risk_limit(user_id=user_id, limit_id=limit_id)
        return {"message": "Risk limit deleted successfully", "limit_id": limit_id}
    except Exception as e:
        logger.error(f"Error deleting risk limit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete risk limit: {str(e)}",
        )


# ===========================
# EMERGENCY STOP
# ===========================


@router.post("/emergency-stop", response_model=EmergencyStop)
async def trigger_emergency_stop(
    request: TriggerEmergencyStopRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    CRITICAL: Trigger emergency stop (kill-switch).

    This will:
    1. Stop all active strategies
    2. Cancel all open orders
    3. Create emergency stop record

    Use only when immediate trading halt is required.
    """
    # Only admin users can trigger emergency stop
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger emergency stop"
        )
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        emergency_stop = await risk_mgr.trigger_emergency_stop(
            user_id=user_id, request=request, triggered_by=user_id
        )

        logger.critical(
            f"EMERGENCY STOP triggered: user={user_id}, "
            f"strategies_stopped={emergency_stop.strategies_stopped}, "
            f"orders_cancelled={emergency_stop.orders_cancelled}"
        )

        return emergency_stop
    except Exception as e:
        logger.error(f"Error triggering emergency stop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger emergency stop: {str(e)}",
        )


@router.post("/emergency-stop/{stop_id}/resolve", response_model=EmergencyStop)
async def resolve_emergency_stop(
    stop_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Resolve an active emergency stop.

    This marks the emergency stop as resolved but does NOT
    automatically restart strategies. Strategies must be
    manually restarted after review.

    Admin-only endpoint.
    """
    # Check admin privileges
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to resolve emergency stop",
        )

    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        emergency_stop = await risk_mgr.resolve_emergency_stop(
            stop_id=stop_id, user_id=user_id, resolved_by=user_id
        )

        logger.info(f"Emergency stop {stop_id} resolved by user {user_id}")

        return emergency_stop
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error resolving emergency stop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve emergency stop: {str(e)}",
        )


@router.get("/emergency-stop/active", response_model=bool)
async def check_emergency_stop_active(
    user: AuthenticatedUser = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db_session)
):
    """Check if an emergency stop is currently active for user."""
    user_id = await get_user_id_from_username(db, user.username)
    risk_mgr = RiskManager(db)

    try:
        is_active = await risk_mgr.is_emergency_stop_active(user_id)
        return is_active
    except Exception as e:
        logger.error(f"Error checking emergency stop status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check emergency stop status: {str(e)}",
        )

