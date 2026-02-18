from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.routes.signals import get_market_data_client
from backend.infra.security import get_current_user
from backend.services.auto_breakout_scanner import get_latest_breakout_scan, scan_breakouts


router = APIRouter(prefix="/auto-breakout", tags=["Auto Breakout Scanner"])


class RunBreakoutScanRequest(BaseModel):
    symbols: list[str] | None = Field(default=None, description="Optional symbol list override")
    timeframe: str = Field(default="1Day")
    limit: int = Field(default=25, ge=1, le=200)
    allow_short: bool = Field(default=False)
    min_price: float = Field(default=5.0, ge=0)
    max_price: float = Field(default=2000.0, ge=0)


class BreakoutCandidateResponse(BaseModel):
    symbol: str
    score: float
    direction: str
    close: float
    upper_trigger: float | None
    lower_trigger: float | None
    breakout_strength: float
    volume_ratio: float | None
    atr_ratio: float | None
    reason: str


class BreakoutScanResponse(BaseModel):
    candidates: list[BreakoutCandidateResponse]
    universe_size: int
    evaluated: int
    timestamp: str


@router.get("/latest", response_model=BreakoutScanResponse)
async def get_latest_scan(current_user: dict = Depends(get_current_user)):
    scan = get_latest_breakout_scan()
    if not scan:
        raise HTTPException(status_code=404, detail="No scan results available")
    return BreakoutScanResponse(
        candidates=[BreakoutCandidateResponse(**c.__dict__) for c in scan.candidates],
        universe_size=scan.universe_size,
        evaluated=scan.evaluated,
        timestamp=scan.timestamp,
    )


@router.post("/run-once", response_model=BreakoutScanResponse)
async def run_scan_once(payload: RunBreakoutScanRequest, current_user: dict = Depends(get_current_user)):
    data_client = get_market_data_client()
    scan = await scan_breakouts(
        data_client=data_client,
        symbols=payload.symbols,
        timeframe=payload.timeframe,
        limit=payload.limit,
        allow_short=payload.allow_short,
        min_price=payload.min_price,
        max_price=payload.max_price,
    )
    return BreakoutScanResponse(
        candidates=[BreakoutCandidateResponse(**c.__dict__) for c in scan.candidates],
        universe_size=scan.universe_size,
        evaluated=scan.evaluated,
        timestamp=scan.timestamp,
    )
