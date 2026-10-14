"""Admin trading controls.

Provides runtime controls for order execution behavior.

Security:
- All endpoints require role: admin.

Audit 2026-10-05 A3-01: the runtime execution-mode override governs manual
orders only; the organism engine's own orders follow the configured mode. PUT
is refused with 423 while the research policy lock is on (the whole research
period) and with 409 whenever this process hosts an organism scheduler,
running or not; an unknown mode is a 422. GET reports whether a PUT would be
accepted (``override_allowed``).

The scheduler builds a new engine on every start (process start and POST
/settings/restart-engine), and the engine's risk-limit guard evaluates the
effective mode at that moment, so a stopped, restarting or crashed scheduler
must refuse the override as much as a running one.

The lock refusal is 423 here although /settings answers 403 for the same lock:
on this route 403 already means that the admin role gate refused the caller.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from backend.infra.security import AuthenticatedUser, require_admin
from backend.services.trading_execution_mode import (
    ExecutionModeOverrideRefused,
    TradingExecutionModeState,
    clear_trading_execution_mode_override,
    get_trading_execution_mode,
    normalize_trading_execution_mode,
    override_refusal,
    set_trading_execution_mode_override,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/trading", tags=["Admin - Trading"])

SCHEDULER_PRESENT_CODE = "organism_scheduler_present"
SCHEDULER_PRESENT_MESSAGE = (
    "The execution-mode override is refused while this process hosts the organism "
    "scheduler, running or not: the engine evaluates the execution mode whenever it "
    "is constructed, including on POST /api/v1/settings/restart-engine."
)


class TradingExecutionModeResponse(BaseModel):
    mode: str
    source: str
    default_mode: str
    overridden: bool
    override_set_by: str | None = None
    override_set_at: str | None = None
    allowed_modes: list[str]
    alpaca_paper: bool
    alpaca_base_url: str
    use_mock_broker: bool
    # Audit 2026-10-05 A3-01: whether PUT would be accepted right now.
    override_allowed: bool = True
    override_blocked_reason: str | None = None


class TradingExecutionModeUpdateRequest(BaseModel):
    mode: str = Field(..., description="One of: execute, shadow, dry_run")

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        # Unknown modes are a 422 (they used to surface as a 500).
        return normalize_trading_execution_mode(value)


def _organism_scheduler_present(request: Request) -> bool:
    """Whether this process hosts an organism scheduler, running or not.

    ``is_running`` is not enough: OrganismScheduler.start() constructs a new
    engine (POST /settings/restart-engine stops and starts it; a crashed task
    leaves the scheduler stopped but restartable), and the engine's startup
    risk-limit guard reads the effective mode, override included.
    """
    return getattr(request.app.state, "organism_scheduler", None) is not None


def _override_block(request: Request) -> tuple[int, str, str] | None:
    """(HTTP status, code, message) when PUT must be refused, else None."""
    refusal = override_refusal()
    if refusal is not None:
        return status.HTTP_423_LOCKED, refusal.code, refusal.message
    if _organism_scheduler_present(request):
        return status.HTTP_409_CONFLICT, SCHEDULER_PRESENT_CODE, SCHEDULER_PRESENT_MESSAGE
    return None


def _state_to_response(
    state: TradingExecutionModeState, request: Request
) -> TradingExecutionModeResponse:
    block = _override_block(request)
    return TradingExecutionModeResponse(
        mode=state.mode,
        source=state.source,
        default_mode=state.default_mode,
        overridden=state.overridden,
        override_set_by=state.override_set_by,
        override_set_at=state.override_set_at,
        allowed_modes=list(state.allowed_modes),
        alpaca_paper=state.alpaca_paper,
        alpaca_base_url=state.alpaca_base_url,
        use_mock_broker=state.use_mock_broker,
        override_allowed=block is None,
        override_blocked_reason=block[2] if block is not None else None,
    )


@router.get("/execution-mode", response_model=TradingExecutionModeResponse)
async def get_execution_mode(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin),
):
    state = get_trading_execution_mode()
    return _state_to_response(state, request)


@router.put("/execution-mode", response_model=TradingExecutionModeResponse)
async def set_execution_mode(
    body: TradingExecutionModeUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin),
):
    block = _override_block(request)
    if block is not None:
        http_status, code, message = block
        logger.warning(
            "Execution-mode override refused: actor=%s requested=%s reason=%s",
            current_user.username, body.mode, code,
        )
        raise HTTPException(status_code=http_status, detail={"code": code, "message": message})
    try:
        state = set_trading_execution_mode_override(body.mode, actor=current_user.username)
    except ExecutionModeOverrideRefused as refused:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"code": refused.code, "message": refused.message},
        ) from None
    return _state_to_response(state, request)


@router.delete("/execution-mode", response_model=TradingExecutionModeResponse)
async def clear_execution_mode_override(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_admin),
):
    state = clear_trading_execution_mode_override(actor=current_user.username)
    return _state_to_response(state, request)
