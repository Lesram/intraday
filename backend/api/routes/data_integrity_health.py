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
import csv
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


def _read_brain_trade_history_summary(brain_dir: Path) -> dict[str, Any]:
    """Return cheap CSV scope metadata for operator reconciliation."""
    path = brain_dir / "trade_history.csv"
    out: dict[str, Any] = {
        "rows": None,
        "closed_rows": None,
        "first_closed_at": None,
        "last_closed_at": None,
        "path": str(path),
    }
    if not path.is_file():
        return out

    rows = 0
    closed: list[str] = []
    try:
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                rows += 1
                closed_at = (row.get("closed_at") or "").strip()
                if closed_at:
                    closed.append(closed_at)
    except OSError:
        return out

    out["rows"] = rows
    out["closed_rows"] = len(closed)
    if closed:
        out["first_closed_at"] = min(closed)
        out["last_closed_at"] = max(closed)
    return out


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


async def _realized_trade_summary(session: AsyncSession) -> dict[str, Any]:
    """Summarize realized accounting at the same semantic level as the DB.

    ``realized_trades`` is a lot-accounting table. A single close order can
    create multiple rows when it closes multiple FIFO lots, so raw row count is
    intentionally not comparable to brain trade-history rows.
    """
    out: dict[str, Any] = {
        "lot_rows": None,
        "distinct_close_orders": None,
        "distinct_open_orders": None,
        "distinct_lots": None,
        "first_close_date": None,
        "last_close_date": None,
    }
    try:
        from backend.infra.schemas import RealizedTrade
    except ImportError:
        return out

    from sqlalchemy.exc import SQLAlchemyError
    try:
        stmt = select(
            func.count(RealizedTrade.id),
            func.count(func.distinct(RealizedTrade.close_order_id)),
            func.count(func.distinct(RealizedTrade.open_order_id)),
            func.count(func.distinct(RealizedTrade.lot_id)),
            func.min(RealizedTrade.close_date),
            func.max(RealizedTrade.close_date),
        )
        result = await session.execute(stmt)
        row = result.one()
    except SQLAlchemyError:
        return out

    out["lot_rows"] = int(row[0] or 0)
    out["distinct_close_orders"] = int(row[1] or 0)
    out["distinct_open_orders"] = int(row[2] or 0)
    out["distinct_lots"] = int(row[3] or 0)
    if row[4] is not None:
        out["first_close_date"] = row[4].isoformat()
    if row[5] is not None:
        out["last_close_date"] = row[5].isoformat()
    return out


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


def _compute_count_variance(left: int | None, right: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "variance_abs": None,
        "variance_pct": None,
        "within_tolerance": None,
    }
    if left is None or right is None:
        return out
    abs_var = abs(left - right)
    base = max(left, right, 1)
    pct = (abs_var / base) * 100.0
    out["variance_abs"] = abs_var
    out["variance_pct"] = round(pct, 4)
    out["within_tolerance"] = pct <= _DEFAULT_TOLERANCE_PCT
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


def _classify_scope_status(
    *,
    brain_history: dict[str, Any],
    realized_summary: dict[str, Any],
) -> dict[str, Any]:
    """Describe whether brain history and DB accounting share a scope."""
    notes: list[str] = []
    brain_rows = brain_history.get("rows")
    db_close_orders = realized_summary.get("distinct_close_orders")
    brain_first = brain_history.get("first_closed_at")
    db_first = realized_summary.get("first_close_date")

    if brain_first and db_first and str(db_first) < str(brain_first):
        notes.append("db_history_starts_before_brain_history")
    if (
        isinstance(db_close_orders, int)
        and isinstance(brain_rows, int)
        and db_close_orders > brain_rows
        and _compute_count_variance(db_close_orders, brain_rows)["within_tolerance"] is False
    ):
        notes.append("db_close_orders_exceed_brain_history_rows")

    if notes:
        return {
            "scope_status": "not_comparable_db_superset",
            "scope_notes": notes,
        }
    if brain_rows is None or db_close_orders is None:
        return {
            "scope_status": "unknown",
            "scope_notes": ["brain_or_db_scope_unreadable"],
        }
    return {"scope_status": "comparable", "scope_notes": []}


def _classify_accounting_status(
    *,
    brain: int | None,
    realized: int | None,
    orders: int | None,
    executions: int | None,
    position_lots: int | None,
    tick_telemetry: int | None,
    scope_status: str = "comparable",
    realized_close_orders: int | None = None,
    brain_history_rows: int | None = None,
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

    if scope_status == "comparable":
        if realized_close_orders is not None and brain_history_rows is not None:
            scoped = _compute_count_variance(realized_close_orders, brain_history_rows)
            if scoped["within_tolerance"] is False:
                reasons.append("brain_history_vs_db_close_orders_outside_tolerance")
        else:
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
    brain_history = _read_brain_trade_history_summary(brain_dir)

    realized: int | None = None
    realized_summary: dict[str, Any] = {
        "lot_rows": None,
        "distinct_close_orders": None,
        "distinct_open_orders": None,
        "distinct_lots": None,
        "first_close_date": None,
        "last_close_date": None,
    }
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
            realized_summary = await _realized_trade_summary(session)
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
    scope = _classify_scope_status(
        brain_history=brain_history,
        realized_summary=realized_summary,
    )
    payload.update(_classify_accounting_status(
        brain=brain,
        realized=realized,
        orders=table_counts["orders"],
        executions=table_counts["executions"],
        position_lots=table_counts["position_lots"],
        tick_telemetry=table_counts["tick_telemetry"],
        scope_status=scope["scope_status"],
        realized_close_orders=realized_summary.get("distinct_close_orders"),
        brain_history_rows=brain_history.get("rows"),
    ))
    payload["table_counts"] = table_counts
    payload["realized_trade_summary"] = realized_summary
    payload["brain_trade_history"] = brain_history
    payload.update(scope)
    payload["brain_dir"] = str(brain_dir)
    payload["explanation"] = (
        "realized_trades is a lot-accounting table: one close order can "
        "create multiple realized rows when it closes multiple FIFO lots. "
        "The brain manifest/trade_history is strategy history and may have "
        "a shorter scope than the cumulative DB ledger. The endpoint only "
        "uses count comparisons for warning status when the scopes are "
        "comparable; otherwise it reports the scope note and verifies that "
        "orders, executions, lots, realized rows, and tick telemetry exist. "
        "If brain/orders exist while executions, realized_trades, or position_lots remain "
        "empty, the endpoint reports critical accounting drift rather than "
        "treating the divergence as by-design."
    )
    return payload
