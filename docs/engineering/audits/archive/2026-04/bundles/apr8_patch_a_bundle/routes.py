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

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from backend.infra.schemas import Order
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


@router.post("/save")
async def force_save(
    request: Request,
    force: bool = Query(default=False),
    _admin=Depends(require_admin),
) -> dict:
    """Admin-only force-save endpoint: persist full brain bypassing the
    walk-forward gate.

    Requires explicit ``?force=true`` query parameter. Without it, returns
    HTTP 400. This is a recovery path for the case where the walk-forward
    gate has been blocking ML joblib persistence for an entire session.
    Calls ``LiveEngine.force_save_brain()`` on the live engine instance
    attached to ``app.state`` — never instantiates a new persistence object.
    """
    if not force:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "force=true query parameter required for /save",
                "hint": "Use POST /api/v1/organism/save?force=true",
            },
        )

    engine = _get_engine(request)
    if engine is None:
        raise HTTPException(
            status_code=409,
            detail="Live engine not active. Cannot force-save brain.",
        )

    result = await asyncio.to_thread(engine.force_save_brain)
    return result


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


@router.get("/analytics")
async def get_organism_analytics(request: Request):
    """Get enhanced analytics: sector exposure, regime timeline, signal confidence distribution."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    result: dict[str, Any] = {
        "sector_exposure": [],
        "regime_timeline": [],
        "confidence_distribution": [],
        "regime_kelly_stats": {},
        "calibration": {},
    }

    if engine is None:
        return result

    # Sector exposure from current positions
    try:
        from backend.organism.sector_map import get_sector
        positions = getattr(engine, "_last_positions", None)
        if positions is None:
            try:
                positions = await engine._positions_service.get_all_positions()
            except Exception:
                positions = {}
        sector_counts: dict[str, dict[str, Any]] = {}
        for sym, pos_data in (positions or {}).items():
            sector = get_sector(sym)
            if sector not in sector_counts:
                sector_counts[sector] = {"count": 0, "symbols": [], "total_value": 0.0}
            sector_counts[sector]["count"] += 1
            sector_counts[sector]["symbols"].append(sym)
            mkt_val = abs(float(pos_data.get("market_value", 0)))
            sector_counts[sector]["total_value"] += mkt_val
        result["sector_exposure"] = [
            {"sector": k, **v} for k, v in sector_counts.items()
        ]
    except Exception as e:
        logger.debug("Sector exposure failed: %s", e)

    # Regime timeline from tick history
    try:
        runs = getattr(engine, "_tick_history", [])
        timeline = []
        for run in runs[-100:]:
            r = run if isinstance(run, dict) else (run.to_dict() if hasattr(run, "to_dict") else {})
            if r.get("regime") and r.get("timestamp"):
                timeline.append({"regime": r["regime"], "timestamp": r["timestamp"]})
        result["regime_timeline"] = timeline
    except Exception as e:
        logger.debug("Regime timeline failed: %s", e)

    # ML confidence distribution from recent signals
    try:
        cal = engine.signal_gen.calibration_to_dict()
        result["calibration"] = cal
        bins = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
        result["confidence_distribution"] = [
            {"bin": bins[i], "correct": cal["counts"][i][0], "total": cal["counts"][i][1]}
            for i in range(5)
        ]
    except Exception as e:
        logger.debug("Confidence distribution failed: %s", e)

    # Regime Kelly stats
    try:
        result["regime_kelly_stats"] = engine.kelly_sizer.regime_stats_to_dict()
    except Exception as e:
        logger.debug("Regime Kelly stats failed: %s", e)

    return result


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


# ── Organism Orders Endpoint ──────────────────────────────────────

def _decimal_to_float(val: Decimal | None) -> float | None:
    if val is None:
        return None
    return float(val)


@router.get("/orders")
async def get_organism_orders(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    status: str = Query(default="all"),
):
    """Get organism-submitted orders from the orders table."""
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=503, detail="Database not available")

    async with sessionmaker() as session:
        stmt = select(Order).where(
            text("attributes->>'source' = 'organism'")
        )

        if status != "all":
            stmt = stmt.where(Order.status == status)

        stmt = stmt.order_by(Order.submitted_at.desc()).limit(limit)

        result = await session.execute(stmt)
        orders = list(result.scalars().all())

    rows = []
    for o in orders:
        attrs = o.attributes or {}
        rows.append({
            "order_id": str(o.id),
            "symbol": o.symbol,
            "side": o.side,
            "qty": _decimal_to_float(o.qty),
            "filled_qty": _decimal_to_float(o.filled_qty),
            "order_type": o.order_type,
            "tif": o.tif,
            "status": o.status,
            "avg_fill_price": _decimal_to_float(o.avg_fill_price),
            "limit_price": _decimal_to_float(o.limit_price),
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            "reason": attrs.get("reason"),
            "confidence": attrs.get("confidence"),
            "tick": attrs.get("tick"),
            "broker_order_id": o.broker_order_id,
        })

    return {"orders": rows, "total": len(rows)}


# ── Admin Maintenance Endpoints ───────────────────────────────────


@router.post("/close-shorts")
async def close_legacy_shorts(request: Request, _admin=Depends(require_admin)):
    """Close legacy short positions that violate LONG_ONLY mode.

    Fetches all positions from Alpaca, identifies any with negative quantity,
    and submits buy-to-cover market orders directly via the broker client.
    Idempotent — returns empty list if no shorts exist.
    """
    import os
    long_only = os.getenv("ORGANISM_LONG_ONLY", "true").lower() in ("1", "true", "yes")
    if not long_only:
        raise HTTPException(
            status_code=400,
            detail="LONG_ONLY is not enabled — short positions are allowed",
        )

    from backend.integrations.alpaca_broker import get_alpaca_broker_client
    broker = get_alpaca_broker_client()

    try:
        positions = await broker.get_positions()
    except Exception as e:
        logger.error("Failed to fetch positions from Alpaca: %s", e)
        raise HTTPException(status_code=502, detail=f"Alpaca positions fetch failed: {e}")

    closed = []
    errors = []
    for pos in (positions or []):
        qty = float(pos.get("qty", 0))
        if qty >= 0:
            continue  # long or flat — skip

        sym = pos.get("symbol", "UNKNOWN")
        abs_qty = abs(int(qty))
        logger.warning("Closing legacy short: %s qty=%d", sym, qty)

        try:
            result = await broker.place_order(
                symbol=sym,
                side="buy",
                qty=abs_qty,
                type="market",
                tif="day",
            )
            closed.append({
                "symbol": sym,
                "qty_covered": abs_qty,
                "broker_order_id": result.get("id"),
                "status": result.get("status"),
            })
            logger.info("Short cover submitted for %s: %s", sym, result.get("id"))
        except Exception as e:
            logger.error("Failed to close short %s: %s", sym, e)
            errors.append({"symbol": sym, "qty": abs_qty, "error": str(e)})

    return {
        "long_only": True,
        "shorts_found": len(closed) + len(errors),
        "closed": closed,
        "errors": errors,
    }


@router.post("/cleanup-orders")
async def cleanup_stuck_orders(request: Request, _admin=Depends(require_admin)):
    """Expire stuck 'accepted' orders that have no broker_order_id.

    These orders were created in the DB but never confirmed by the broker.
    The trade stream can never update them, so they are zombie records.
    Only touches orders older than 1 hour with status='accepted' and
    broker_order_id IS NULL.
    """
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=503, detail="Database not available")

    cutoff = datetime.now(UTC) - timedelta(hours=1)

    async with sessionmaker() as session:
        # Count first
        count_result = await session.execute(
            text(
                "SELECT COUNT(*) FROM orders "
                "WHERE status = 'accepted' "
                "AND broker_order_id IS NULL "
                "AND submitted_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        total = count_result.scalar() or 0

        if total == 0:
            return {"cleaned": 0, "message": "No stuck orders found"}

        # Update to expired
        await session.execute(
            text(
                "UPDATE orders "
                "SET status = 'expired', updated_at = :now "
                "WHERE status = 'accepted' "
                "AND broker_order_id IS NULL "
                "AND submitted_at < :cutoff"
            ),
            {"cutoff": cutoff, "now": datetime.now(UTC)},
        )
        await session.commit()

    logger.info("Cleaned up %d stuck 'accepted' orders (no broker_order_id, older than 1h)", total)
    return {"cleaned": total, "message": f"Expired {total} stuck orders"}


# ── Decision Telemetry Endpoints ──────────────────────────────────

def _get_engine(request: Request):
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    return getattr(scheduler, "_engine", None) if scheduler else None


@router.get("/decisions")
async def get_decisions(request: Request):
    """Latest full decision snapshot — all symbols scored, all exit proximities."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "snapshot": None}

    telemetry = getattr(engine, "_telemetry", None)
    if telemetry is None:
        return {"active": True, "snapshot": None}

    snap = telemetry.latest
    if snap is None:
        return {"active": True, "snapshot": None}

    return {"active": True, "snapshot": snap.to_dict()}


@router.get("/decisions/history")
async def get_decision_history(
    request: Request, limit: int = Query(default=50, ge=1, le=360)
):
    """Recent decision snapshots for time-series analysis."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "snapshots": []}

    telemetry = getattr(engine, "_telemetry", None)
    if telemetry is None:
        return {"active": True, "snapshots": []}

    snaps = telemetry.history(limit=limit)
    return {
        "active": True,
        "count": len(snaps),
        "snapshots": [s.to_dict() for s in snaps],
    }


@router.get("/decisions/symbol/{symbol}")
async def get_decision_by_symbol(request: Request, symbol: str, limit: int = Query(default=50, ge=1, le=360)):
    """Per-symbol timeline of alpha/breakout/exit/kelly data across recent ticks."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "symbol": symbol, "history": []}

    telemetry = getattr(engine, "_telemetry", None)
    if telemetry is None:
        return {"active": True, "symbol": symbol, "history": []}

    history = telemetry.symbol_history(symbol.upper(), limit=limit)
    return {
        "active": True,
        "symbol": symbol.upper(),
        "count": len(history),
        "history": history,
    }


@router.get("/decisions/exits")
async def get_exit_proximity(request: Request):
    """Exit proximity for all current positions — distances to each exit condition."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "exits": []}

    telemetry = getattr(engine, "_telemetry", None)
    if telemetry is None:
        return {"active": True, "exits": []}

    return {
        "active": True,
        "exits": telemetry.exits_snapshot(),
    }


@router.get("/evolution/history")
async def get_evolution_history(request: Request, limit: int = Query(default=50, ge=1, le=360)):
    """Evolution parameter change history across recent ticks."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "history": []}

    telemetry = getattr(engine, "_telemetry", None)
    if telemetry is None:
        return {"active": True, "history": []}

    snaps = telemetry.history(limit=limit)
    history = []
    for s in snaps:
        history.append({
            "tick_number": s.tick_number,
            "timestamp": s.timestamp,
            "generation": s.evolution_generation,
            "regime": s.regime,
            "equity": round(s.equity, 2),
            "drawdown_pct": round(s.drawdown_pct, 4),
            "params": s.evolved_params_summary,
        })
    return {
        "active": True,
        "count": len(history),
        "history": history,
    }


# ── System Diagnostics Endpoints ─────────────────────────────────


@router.get("/diagnostics")
async def get_diagnostics(request: Request):
    """Return the latest diagnostic report (preflight or continuous)."""
    engine = _get_engine(request)
    if engine is None:
        return {"active": False, "report": None}

    report = getattr(engine, "_last_diagnostic_report", None)
    if report is None:
        return {"active": True, "report": None}

    return {"active": True, "report": report.to_dict()}


@router.get("/diagnostics/history")
async def get_diagnostics_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    trigger: str = Query(default="all"),
):
    """Return diagnostic report history with optional trigger filter."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    store = getattr(scheduler, "_diag_store", None) if scheduler else None

    if store is None:
        return {"active": False, "count": 0, "reports": []}

    trigger_filter = trigger if trigger != "all" else None
    reports = store.history(limit=limit, trigger=trigger_filter)
    return {
        "active": True,
        "count": len(reports),
        "reports": reports,
    }


@router.post("/diagnostics/run")
async def run_deep_diagnostics(request: Request, _admin=Depends(require_admin)):
    """Run a full deep diagnostic scan (admin only)."""
    engine = _get_engine(request)
    if engine is None:
        raise HTTPException(status_code=409, detail="Live engine not active")

    from backend.organism.diagnostics import diagnostics as _diag, CheckMode
    import backend.organism.diagnostic_checks  # noqa: F401

    report = await _diag.run(CheckMode.DEEP, engine=engine, app=request.app)
    engine._last_diagnostic_report = report

    # Persist manual run to diagnostic store
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    store = getattr(scheduler, "_diag_store", None) if scheduler else None
    if store:
        await store.append(report, trigger="manual")

    return {"active": True, "report": report.to_dict()}