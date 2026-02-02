"""Admin trading controls.

Provides runtime controls for order execution behavior.

Security:
- All endpoints require role: admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.infra.security import AuthenticatedUser, require_admin
from backend.services.trading_execution_mode import (
    TradingExecutionModeState,
    clear_trading_execution_mode_override,
    get_trading_execution_mode,
    set_trading_execution_mode_override,
)

router = APIRouter(prefix="/admin/trading", tags=["Admin - Trading"])


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


class TradingExecutionModeUpdateRequest(BaseModel):
    mode: str = Field(..., description="One of: execute, shadow, dry_run")


def _state_to_response(state: TradingExecutionModeState) -> TradingExecutionModeResponse:
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
    )


@router.get("/execution-mode", response_model=TradingExecutionModeResponse)
async def get_execution_mode(
    current_user: AuthenticatedUser = Depends(require_admin()),
):
    state = get_trading_execution_mode()
    return _state_to_response(state)


@router.put("/execution-mode", response_model=TradingExecutionModeResponse)
async def set_execution_mode(
    request: TradingExecutionModeUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_admin()),
):
    state = set_trading_execution_mode_override(request.mode, actor=current_user.username)
    return _state_to_response(state)


@router.delete("/execution-mode", response_model=TradingExecutionModeResponse)
async def clear_execution_mode_override(
    current_user: AuthenticatedUser = Depends(require_admin()),
):
    state = clear_trading_execution_mode_override(actor=current_user.username)
    return _state_to_response(state)
