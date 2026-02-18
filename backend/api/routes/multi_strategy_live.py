from datetime import UTC, datetime
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.routes.signals import get_market_data_client, get_order_service
from backend.services.multi_strategy_live_runner import MultiStrategyLiveRunner
from backend.strategies.engine import StrategyEngine
from backend.services.auto_breakout_scanner import get_latest_breakout_scan


router = APIRouter(prefix="/multi-strategy-live", tags=["Multi-Strategy Live"])


class MultiStrategyRunOnceRequest(BaseModel):
    symbols: list[str] = Field(..., description="Symbols to evaluate")
    lookback: int = Field(default=200, ge=50, le=1000)
    timeframe: str = Field(default="1Day")
    idempotency_key: str | None = Field(default=None)


class MultiStrategyRunOnceResponse(BaseModel):
    symbols: list[str]
    engine_signals_count: int
    submitted: list[dict[str, Any]]
    timestamp: str


@router.post("/run-once", response_model=MultiStrategyRunOnceResponse)
async def run_multi_strategy_once(
    payload: MultiStrategyRunOnceRequest,
    request: Request,
    order_service=Depends(get_order_service),
):
    if not payload.symbols:
        raise HTTPException(status_code=400, detail="symbols cannot be empty")

    data_client = get_market_data_client()
    runner = MultiStrategyLiveRunner()

    # Use a default engine instance (risk + positions are handled internally)
    engine = StrategyEngine.create_default()

    # Optionally augment the universe with latest breakout candidates
    symbols = [s.strip().upper() for s in payload.symbols if s and s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols cannot be empty")

    scan = get_latest_breakout_scan()
    include_scan = (os.getenv("LIVING_STRATEGY_INCLUDE_BREAKOUT_CANDIDATES", "1").lower() in ("1", "true", "yes"))
    if include_scan and scan and getattr(scan, "candidates", None):
        limit = int(os.getenv("LIVING_STRATEGY_BREAKOUT_CANDIDATES_LIMIT", "20"))
        candidates = [c.symbol.strip().upper() for c in scan.candidates[: max(0, limit)]]
        for sym in candidates:
            if sym and sym not in symbols:
                symbols.append(sym)

    # Apply living policy weights (soft mixing) if enabled
    policy = getattr(request.app.state, "living_policy", None)
    breakout_syms = []
    if scan and getattr(scan, "candidates", None):
        breakout_syms = [c.symbol.strip().upper() for c in scan.candidates]
    if policy is not None:
        engine.strategy_weights.update(policy.get_weights())

    # ── Organism pre-execution hook ──────────────────────────────
    organism_runner = getattr(request.app.state, "organism_runner", None)
    if organism_runner is not None:
        base_w = dict(engine.strategy_weights)
        organism_pre = organism_runner.pre_execution_hook(base_weights=base_w)
        engine.strategy_weights.update(organism_pre["final_weights"])
        if not organism_pre["trading_allowed"]:
            return MultiStrategyRunOnceResponse(
                symbols=symbols,
                engine_signals_count=0,
                submitted=[],
                timestamp=datetime.now(UTC).isoformat(),
            )
    # ─────────────────────────────────────────────────────────────

    result = await runner.run_once(
        symbols=symbols,
        lookback=payload.lookback,
        timeframe=payload.timeframe,
        data_client=data_client,
        order_service=order_service,
        strategy_engine=engine,
        portfolio_state=None,
        idempotency_key=payload.idempotency_key,
    )

    # Update policy after the run
    if policy is not None:
        snap = policy.observe_signals(engine_signals=result.engine_signals, breakout_candidates=breakout_syms)
        await policy.maybe_persist_snapshot(snap)

    # ── Organism post-execution hook ────────────────────────────
    if organism_runner is not None:
        organism_runner.post_execution_hook(live_metrics={})
    # ─────────────────────────────────────────────────────────────

    return MultiStrategyRunOnceResponse(
        symbols=result.symbols,
        engine_signals_count=result.engine_signals_count,
        submitted=result.submitted,
        timestamp=result.timestamp or datetime.now(UTC).isoformat(),
    )
