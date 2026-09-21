"""
Risk Management API Routes
Comprehensive endpoints for risk metrics, violations, limits, and emergency stops.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user, require_admin
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


class OperatorEmergencyStopResponse(EmergencyStop):
    """Existing audit record plus explicit halt and entry-cancellation outcome."""

    control: dict


@router.post("/emergency-stop", response_model=OperatorEmergencyStopResponse)
async def trigger_emergency_stop(
    request: TriggerEmergencyStopRequest,
    http_request: Request,
    user: AuthenticatedUser = Depends(require_admin),
):
    """Halt new organism entries and cancel attributed pending entries only.

    Protective exits continue. Unverified cancellation, in-flight fills or
    persistence failures return 503 with the halt retained and an audit ID when
    available. This operation neither flattens positions nor cancels all orders.
    """
    from backend.organism.operator_controls import (
        halt_entries, OperatorControlError, operation_lock, control_status, live_engine,
    )
    from backend.organism.operator_cancellation import cancel_entry_orders

    # Authorization precedes all side effects. DB is deliberately opened below:
    # dependency initialization/query failure must not precede the safety latch.
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only administrators can trigger emergency stop")
    halt_ok = False
    try:
        control = await halt_entries(http_request.app)
        halt_ok = True
    except OperatorControlError as exc:
        control = dict(exc.result)
    except Exception:  # noqa: BLE001 - Preserve the latch and sanitize operational failures.
        control = {"operator_halted": None, "entries_halted": None, "drained": False,
                   "issue": "operator_halt_unverified"}
    control["cancellation"] = {"scope": "attributed_organism_entries", "status": "incomplete",
                               "confirmed_cancelled": 0, "issues": ["halt_not_confirmed"],
                               "protective_exits_preserved": True, "db_order_statuses_modified": False}
    audit = None
    issues = []
    def same_verified_halt(fresh):
        return (fresh.get("operator_halted") is True and fresh.get("entries_halted") is True
                and fresh.get("runtime_ready") is True and fresh.get("protective_exits_active") is True
                and fresh.get("halt_epoch") == control.get("halt_epoch")
                and fresh.get("governance", {}).get("operator_control_fault") is False
                and fresh.get("persistence", {}).get("configured") is True
                and fresh.get("persistence", {}).get("persistence") == "verified")
    try:
        # Serialize only operator actions while cancellation/audit runs. The
        # engine tick lock is released, so protective exits remain responsive.
        async with asyncio.timeout(20.0), operation_lock(http_request.app):
            if halt_ok:
                fresh = control_status(http_request.app)
                if not same_verified_halt(fresh):
                    raise ValueError("operator_halt_changed")
            async with asynccontextmanager(get_db_session)() as db:
                user_id = await get_user_id_from_username(db, user.username)
                if halt_ok:
                    control["cancellation"] = await cancel_entry_orders(live_engine(http_request.app), db, control)
                audit = await RiskManager(db).trigger_emergency_stop(
                    user_id=user_id, request=request, triggered_by=user_id, control_result=control)
            if halt_ok:
                fresh = control_status(http_request.app)
                if not same_verified_halt(fresh):
                    issues.append("operator_halt_changed_or_unverified")
                control = {**control, **fresh}
    except Exception:  # noqa: BLE001 - Preserve the latch and sanitize operational failures.
        # Failure to write an audit does not release the independent operator
        # latch, and private DB/broker exception bodies must not reach clients.
        issues.append("emergency_audit_unavailable")
    if not halt_ok or control["cancellation"]["status"] != "complete" or issues:
        raise HTTPException(status_code=503, detail={
            "status": "incomplete", "control": control,
            "audit_id": str(audit.id) if audit is not None else None,
            "issues": issues or ["operator_stop_requires_attention"],
        })
    return {**audit.model_dump(), "control": control}


@router.post("/emergency-stop/{stop_id}/resolve", response_model=EmergencyStop)
async def resolve_emergency_stop(
    stop_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Resolve an emergency stop audit record only.

    This does not resume the durable operator entry halt or restart strategies.
    Operator entry resume is a separate reviewed control action.

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
    http_request: Request, user: AuthenticatedUser = Depends(get_authenticated_user)
):
    """Read the actual operator entry halt/fault, not historical audit records.

    Automatic risk halts are separate. Unknown authority is unavailable, never
    interpreted as a resumed engine; an observed control fault is an active halt.
    """
    from backend.organism.operator_controls import control_status, live_engine

    try:
        engine = live_engine(http_request.app)
        if engine is None or getattr(engine, "governance", None) is None:
            raise ValueError("Engine control unavailable")
        control = control_status(http_request.app)
        halted = control.get("operator_halted")
        fault = control.get("governance", {}).get("operator_control_fault")
        if control.get("available") is not True or type(halted) is not bool or type(fault) is not bool:
            raise ValueError("Engine control unverified")
        if halted or fault:
            return True
        persistence = control.get("persistence", {})
        if persistence.get("configured") is not True or persistence.get("persistence") != "verified":
            raise ValueError("Durable control unverified")
        return False
    except Exception as exc:  # noqa: BLE001 - Unknown authority must fail closed without private exception text.
        raise HTTPException(status_code=503, detail={
            "status": "unavailable", "error": "operator_control_unverified",
        }) from exc
