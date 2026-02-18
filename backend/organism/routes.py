"""
Organism API Routes.

Provides visibility and control endpoints for the living organism:
- GET  /organism/status        — current regime, governance, promotion state
- GET  /organism/attribution   — latest attribution report
- GET  /organism/policy        — current living policy snapshot
- POST /organism/train         — trigger a manual training run
- POST /organism/freeze        — freeze all adaptation
- POST /organism/unfreeze      — unfreeze adaptation
- POST /organism/halt          — halt all trading
- POST /organism/resume        — resume trading
- POST /organism/promote       — advance promotion stage
- POST /organism/rollback      — force rollback
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.infra.security import require_admin
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/organism", tags=["Living Organism"])


# ── Response models ──────────────────────────────────────────────────

class OrganismStatusResponse(BaseModel):
    enabled: bool = True
    governance: dict[str, Any] = {}
    regime: dict[str, Any] | None = None
    promotion: dict[str, Any] | None = None
    policy_weights: dict[str, float] = {}
    tick_count: int = 0
    live_engine: dict[str, Any] | None = None  # Phase 3.4


class AttributionResponse(BaseModel):
    attribution: dict[str, Any] | None = None


class TrainRequest(BaseModel):
    source: str = Field(default="manual")


class TrainResponse(BaseModel):
    result: dict[str, Any] = {}


class OrganismRunsResponse(BaseModel):
    enabled: bool = True
    running: bool = False
    tick_interval_s: int | None = None
    runs: list[dict[str, Any]] = []
    engine: dict[str, Any] | None = None


class ScannerStatusResponse(BaseModel):
    enabled: bool = False
    scan_count: int = 0
    last_scan_time: str | None = None
    candidate_count: int = 0
    candidates: list[dict[str, Any]] = []  # ScannedStock.to_dict() items


class UniverseStatusResponse(BaseModel):
    active_symbols: list[str] = []
    universe_size: int = 0
    fitness_table: list[dict[str, Any]] = []
    scanner_candidates: list[str] = []
    rotation_count: int = 0
    config: dict[str, Any] = {}


# ── Helpers ──────────────────────────────────────────────────────────

def _get_governance(request: Request):
    gov = getattr(request.app.state, "organism_governance", None)
    if gov is None:
        raise HTTPException(status_code=503, detail="Organism not enabled — set ORGANISM_ENABLED=1")
    return gov


def _get_promotion(request: Request):
    return getattr(request.app.state, "organism_promotion", None)


def _get_runner(request: Request):
    return getattr(request.app.state, "organism_runner", None)


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/status", response_model=OrganismStatusResponse)
async def get_organism_status(request: Request):
    """Get full organism status: governance, regime, promotion, weights, live engine."""
    gov = getattr(request.app.state, "organism_governance", None)
    if gov is None:
        # Organism not enabled — return clean 200 with enabled=false
        return OrganismStatusResponse(enabled=False)

    runner = _get_runner(request)
    promotion = _get_promotion(request)
    policy = getattr(request.app.state, "living_policy", None)

    status = OrganismStatusResponse(
        governance=gov.to_dict(),
        policy_weights=policy.get_weights() if policy else {},
        tick_count=runner._tick_count if runner else 0,
    )

    if runner:
        status.regime = {"last_regime": runner._last_regime}

    if promotion and promotion._state:
        status.promotion = promotion._state.to_dict()

    # Phase 3.4: Include live engine + scheduler status
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    if scheduler:
        status.live_engine = scheduler.state()

    return status


@router.get("/attribution", response_model=AttributionResponse)
async def get_latest_attribution(request: Request):
    """Get the latest fill-based attribution report."""
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if not sessionmaker:
        return AttributionResponse(attribution=None)

    from backend.organism.attribution import AttributionService
    svc = AttributionService(sessionmaker)
    result = await svc.get_latest_attribution()
    return AttributionResponse(attribution=result.to_dict() if result else None)


@router.get("/policy")
async def get_policy_snapshot(request: Request):
    """Get current living policy weights and scores."""
    policy = getattr(request.app.state, "living_policy", None)
    if not policy:
        return {"enabled": False}

    return {
        "enabled": True,
        "weights": policy.get_weights(),
        "scores": dict(policy.scores),
        "mode": policy._mode,
    }


@router.get("/runs", response_model=OrganismRunsResponse)
async def get_organism_runs(request: Request, limit: int = Query(default=50, ge=1, le=500)):
    """Get recent organism run history from live scheduler state."""
    gov = getattr(request.app.state, "organism_governance", None)
    if gov is None:
        return OrganismRunsResponse(enabled=False)

    scheduler = getattr(request.app.state, "organism_scheduler", None)
    if not scheduler:
        return OrganismRunsResponse(enabled=True, running=False, runs=[])

    state = scheduler.state()
    runs = state.get("tick_history") or []
    if limit and len(runs) > limit:
        runs = runs[-limit:]

    return OrganismRunsResponse(
        enabled=True,
        running=bool(state.get("running")),
        tick_interval_s=state.get("tick_interval_s"),
        runs=runs,
        engine=state.get("engine"),
    )


@router.post("/train", response_model=TrainResponse)
async def trigger_training(request: Request, payload: TrainRequest | None = None, _admin=Depends(require_admin)):
    """Manually trigger a training run."""
    from backend.organism.nightly_scheduler import _run_nightly_tick
    result = await _run_nightly_tick(request.app)
    return TrainResponse(result=result)


@router.post("/freeze")
async def freeze_adaptation(request: Request, _admin=Depends(require_admin)):
    """Freeze all organism adaptation (weights/params stay fixed)."""
    gov = _get_governance(request)
    gov.freeze()
    return {"status": "frozen", "governance": gov.to_dict()}


@router.post("/unfreeze")
async def unfreeze_adaptation(request: Request, _admin=Depends(require_admin)):
    """Unfreeze organism adaptation."""
    gov = _get_governance(request)
    gov.unfreeze()
    return {"status": "unfrozen", "governance": gov.to_dict()}


@router.post("/halt")
async def halt_trading(request: Request, _admin=Depends(require_admin)):
    """Halt all trading immediately."""
    gov = _get_governance(request)
    gov.halt_trading()
    return {"status": "halted", "governance": gov.to_dict()}


@router.post("/resume")
async def resume_trading(request: Request, _admin=Depends(require_admin)):
    """Resume trading after a halt."""
    gov = _get_governance(request)
    gov.resume_trading()
    return {"status": "resumed", "governance": gov.to_dict()}


@router.post("/promote")
async def advance_promotion(request: Request, _admin=Depends(require_admin)):
    """Manually advance the promotion stage."""
    promotion = _get_promotion(request)
    if not promotion:
        raise HTTPException(status_code=503, detail="Promotion controller not initialized")
    if not promotion._state:
        raise HTTPException(status_code=404, detail="No candidate in promotion pipeline")

    # Pass empty metrics to skip rollback checks during manual advance
    state = await promotion.evaluate_and_advance({})
    return {"state": state.to_dict() if state else None}


@router.post("/rollback")
async def force_rollback(request: Request, _admin=Depends(require_admin)):
    """Force a rollback to last-known-good policy."""
    promotion = _get_promotion(request)
    if not promotion:
        raise HTTPException(status_code=503, detail="Promotion controller not initialized")
    if not promotion._state:
        raise HTTPException(status_code=404, detail="No candidate in promotion pipeline")

    from backend.organism.promotion import RollbackTrigger
    trigger = RollbackTrigger(
        reason="Manual rollback",
        metric_name="manual",
        metric_value=0.0,
        threshold=0.0,
        timestamp=datetime.now(UTC).isoformat(),
    )
    state = await promotion.rollback(trigger)
    return {"state": state.to_dict() if state else None}


@router.post("/compute-attribution")
async def compute_attribution(request: Request, _admin=Depends(require_admin)):
    """Trigger fresh attribution computation for the last 7 days."""
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=503, detail="Database not available")

    from backend.organism.attribution import AttributionService
    svc = AttributionService(sessionmaker)
    now = datetime.now(UTC)
    result = await svc.compute_attribution(
        window_start=now - timedelta(days=7),
        window_end=now,
        persist=True,
    )
    return result.to_dict()


# ── Phase 3.4: Live Engine brain & tick endpoints ────────────────

@router.get("/brain")
async def get_brain_status(request: Request):
    """Return brain manifest and validation warnings."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None
    if engine is None:
        return {"active": False, "detail": "Live engine not active", "validation_warnings": []}

    brain = engine.brain
    manifest = dict(brain._manifest)
    manifest["active"] = True
    manifest["validation_warnings"] = brain.validate_brain()
    return manifest


@router.post("/tick")
async def manual_tick(request: Request, _admin=Depends(require_admin)):
    """Manually trigger one organism live tick (admin only)."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None
    if engine is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Live engine not active. The organism scheduler requires "
                "ENABLE_ORGANISM_SCHEDULER=1 plus active Alpaca data/order/positions services. "
                "Check backend logs for 'Organism scheduler skipped' or 'Organism live engine scheduler enabled'."
            ),
        )

    result = await engine.live_tick()
    result_dict = result.to_dict()

    # Broadcast to WebSocket subscribers
    try:
        from backend.websocket import get_websocket_manager
        manager = get_websocket_manager()
        await manager.broadcast_to_topic(
            "organism",
            {
                "type": "organism_tick",
                "data": result_dict,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        pass  # WebSocket not available — that's fine

    return result_dict


# ── Phase 5: Scanner & Universe Endpoints ────────────────────────────


@router.get("/scanner", response_model=ScannerStatusResponse)
async def get_scanner_status(request: Request):
    """Get Phase 5 Market Scanner status — discovered stocks, tension scores."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None or engine.market_scanner is None:
        return ScannerStatusResponse(enabled=False)

    scanner = engine.market_scanner

    last_time = None
    if scanner.last_scan_time > 0:
        last_time = datetime.fromtimestamp(scanner.last_scan_time, tz=UTC).isoformat()

    return ScannerStatusResponse(
        enabled=True,
        scan_count=scanner.scan_count,
        last_scan_time=last_time,
        candidate_count=len(scanner.candidates),
        candidates=[s.to_dict() for s in scanner.scanned_stocks],
    )


@router.get("/universe", response_model=UniverseStatusResponse)
async def get_universe_status(request: Request):
    """Get Dynamic Universe Selector status — active symbols, fitness, rotation."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None:
        return UniverseStatusResponse()

    selector = getattr(engine, "universe_selector", None)
    if selector is None:
        return UniverseStatusResponse()
    fitness_list = [
        sf.to_dict()
        for sf in sorted(
            selector.fitness_table.values(),
            key=lambda sf: sf.fitness,
            reverse=True,
        )
    ]

    return UniverseStatusResponse(
        active_symbols=list(engine._universe),
        universe_size=len(engine._universe),
        fitness_table=fitness_list,
        scanner_candidates=engine._scanner_candidates,
        rotation_count=selector._rotation_count,
        config={
            "min_universe": selector._min,
            "max_universe": selector._max,
        },
    )


@router.get("/scanner/history")
async def get_scanner_history(request: Request):
    """Get the raw list of scanned stock details (latest scan only)."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None or engine.market_scanner is None:
        return {"stocks": [], "scan_count": 0}

    scanner = engine.market_scanner
    return {
        "stocks": [s.to_dict() for s in scanner.scanned_stocks],
        "scan_count": scanner.scan_count,
        "last_scan_time": scanner.last_scan_time,
    }