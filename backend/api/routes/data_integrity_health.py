"""V13 W95 (Lens 4: Data Integrity) — reconciliation endpoint.

V12 EXT-3 documented the realized_trades-vs-brain.total_trades
divergence "by design" without a programmatic surface that operators
could query.  W95 ships:

    GET /api/v1/health/data-integrity

The endpoint reads:
- ``realized_trades`` row count from Postgres (source of truth for
  realized PnL — audited rows).
- ``manifest.json::total_trades`` from the brain dir, with backward
  compatibility for the older nested ``brain_state.total_trades`` shape.

Response surfaces:
- Both counts.
- Variance + variance percentage.
- A boolean ``within_tolerance`` (default 5%).
- Order, execution, lot, realized-trade, and tick-telemetry row counts.
- A machine-readable ``accounting_status`` so by-design fill-vs-
  round-trip semantics are not confused with missing persistence.

Auth: protected (mounted under /api/v1).  The endpoint is
informational; status code is always 200 when the data is readable,
503 when the brain dir is missing entirely.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.security import AuthenticatedUser, require_admin

router = APIRouter(prefix="/health", tags=["Health"])


_DEFAULT_TOLERANCE_PCT = float(os.environ.get(
    "DATA_INTEGRITY_VARIANCE_TOLERANCE_PCT", "5.0",
))


def _resolve_brain_dir() -> Path:
    env = os.environ.get("ORGANISM_BRAIN_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    for c in ("organism_brain", "/app/organism_brain"):
        p = Path(c)
        if p.is_dir():
            return p
    return Path("organism_brain")


def _read_brain_total_trades(brain_dir: Path) -> int | None:
    mpath = brain_dir / "manifest.json"
    if not mpath.is_file():
        return None
    try:
        m = json.loads(mpath.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    candidates = [
        m.get("total_trades"),
        (m.get("brain_state") or {}).get("total_trades"),
        (m.get("strategy_expectancy") or {}).get("n_trades"),
    ]
    for val in candidates:
        if val is None:
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    return None


async def _count_model_rows(session: AsyncSession, model: type[Any]) -> int | None:
    from sqlalchemy.exc import SQLAlchemyError
    try:
        stmt = select(func.count()).select_from(model)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)
    except SQLAlchemyError:
        return None


async def _count_realized_trades(session: AsyncSession) -> int | None:
    try:
        from backend.infra.schemas import RealizedTrade
    except ImportError:
        return None
    return await _count_model_rows(session, RealizedTrade)


def _compute_variance(realized: int | None, brain: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "realized_trades": realized,
        "brain_total_trades": brain,
        "tolerance_pct": _DEFAULT_TOLERANCE_PCT,
    }
    if realized is None or brain is None:
        out["within_tolerance"] = None
        out["variance_pct"] = None
        out["variance_abs"] = None
        return out
    abs_var = abs(brain - realized)
    base = max(brain, realized, 1)
    var_pct = (abs_var / base) * 100.0
    out["variance_abs"] = abs_var
    out["variance_pct"] = round(var_pct, 4)
    out["within_tolerance"] = var_pct <= _DEFAULT_TOLERANCE_PCT
    return out


def _round_trip_variance(realized: int | None, brain: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "expected_brain_total_trades_from_realized": None,
        "round_trip_variance_abs": None,
        "round_trip_variance_pct": None,
        "round_trip_within_tolerance": None,
    }
    if realized is None or brain is None:
        return out
    expected = realized * 2
    out["expected_brain_total_trades_from_realized"] = expected
    abs_var = abs(brain - expected)
    base = max(brain, expected, 1)
    pct = (abs_var / base) * 100.0
    out["round_trip_variance_abs"] = abs_var
    out["round_trip_variance_pct"] = round(pct, 4)
    out["round_trip_within_tolerance"] = pct <= _DEFAULT_TOLERANCE_PCT
    return out


def _classify_accounting_status(
    *,
    brain: int | None,
    realized: int | None,
    orders: int | None,
    executions: int | None,
    position_lots: int | None,
    tick_telemetry: int | None,
) -> dict[str, Any]:
    """Classify accounting health without mutating any production data."""
    reasons: list[str] = []

    if brain is None or realized is None:
        return {
            "accounting_status": "unavailable",
            "reasons": ["brain_or_realized_source_unreadable"],
        }

    if brain > 0 and realized == 0:
        reasons.append("brain_has_trades_but_realized_trades_empty")
    if (orders or 0) > 0 and executions == 0:
        reasons.append("orders_exist_but_executions_empty")
    if (orders or 0) > 0 and brain > 0 and position_lots == 0:
        reasons.append("orders_and_brain_trades_exist_but_position_lots_empty")
    if (orders or 0) > 0 and tick_telemetry == 0:
        reasons.append("orders_exist_but_tick_telemetry_empty")

    rt = _round_trip_variance(realized, brain)
    if (
        rt["round_trip_within_tolerance"] is False
        and "brain_has_trades_but_realized_trades_empty" not in reasons
    ):
        reasons.append("brain_vs_realized_round_trip_ratio_outside_tolerance")

    if reasons:
        severity = "critical" if any(
            r in reasons
            for r in (
                "brain_has_trades_but_realized_trades_empty",
                "orders_exist_but_executions_empty",
                "orders_and_brain_trades_exist_but_position_lots_empty",
            )
        ) else "warning"
        return {"accounting_status": severity, "reasons": reasons}

    return {"accounting_status": "ok", "reasons": []}


@router.get("/data-integrity")
async def data_integrity(
    request: Request,
    _current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """V13 W95: realized_trades vs brain.total_trades reconciliation.

    Surfaces the V12 EXT-3 divergence with a programmatic answer.

    Default tolerance is ±5%; override via env
    ``DATA_INTEGRITY_VARIANCE_TOLERANCE_PCT``.

    Returns 200 with the reconciliation payload, or 503 if neither
    source is readable.
    """
    brain_dir = _resolve_brain_dir()
    brain = _read_brain_total_trades(brain_dir)

    realized: int | None = None
    table_counts: dict[str, int | None] = {
        "orders": None,
        "executions": None,
        "realized_trades": None,
        "position_lots": None,
        "tick_telemetry": None,
    }
    sm = getattr(request.app.state, "sessionmaker", None)
    if sm is not None:
        async with sm() as session:
            from backend.infra.schemas import Execution, Order, PositionLot, TickTelemetry

            realized = await _count_realized_trades(session)
            table_counts["orders"] = await _count_model_rows(session, Order)
            table_counts["executions"] = await _count_model_rows(session, Execution)
            table_counts["realized_trades"] = realized
            table_counts["position_lots"] = await _count_model_rows(session, PositionLot)
            table_counts["tick_telemetry"] = await _count_model_rows(session, TickTelemetry)

    if brain is None and realized is None:
        raise HTTPException(
            status_code=503,
            detail="data-integrity: neither manifest.json nor realized_trades readable",
        )

    payload = _compute_variance(realized, brain)
    payload.update(_round_trip_variance(realized, brain))
    payload.update(_classify_accounting_status(
        brain=brain,
        realized=realized,
        orders=table_counts["orders"],
        executions=table_counts["executions"],
        position_lots=table_counts["position_lots"],
        tick_telemetry=table_counts["tick_telemetry"],
    ))
    payload["table_counts"] = table_counts
    payload["brain_dir"] = str(brain_dir)
    payload["explanation"] = (
        "brain.total_trades increments at fill (entry + exit each count); "
        "realized_trades stores ONE row per closed round-trip, so a clean "
        "run should be approximately brain.total_trades = 2 * realized_trades. "
        "If brain/orders exist while executions, realized_trades, or position_lots remain "
        "empty, the endpoint reports critical accounting drift rather than "
        "treating the divergence as by-design."
    )
    return payload
