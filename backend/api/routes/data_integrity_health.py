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
- An operator-readable explanation of the divergence (W95 design
  decision: this is *expected* drift, not a bug).

Auth: protected (mounted under /api/v1).  The endpoint is
informational; status code is always 200 when the data is readable,
503 when the brain dir is missing entirely.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _count_realized_trades(session: AsyncSession) -> int | None:
    from sqlalchemy.exc import SQLAlchemyError
    try:
        from backend.infra.schemas import RealizedTrade
        stmt = select(func.count()).select_from(RealizedTrade)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)
    except SQLAlchemyError:
        return None
    except ImportError:
        return None


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


@router.get("/data-integrity")
async def data_integrity(request: Request) -> dict[str, Any]:
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
    sm = getattr(request.app.state, "sessionmaker", None)
    if sm is not None:
        async with sm() as session:
            realized = await _count_realized_trades(session)

    if brain is None and realized is None:
        raise HTTPException(
            status_code=503,
            detail="data-integrity: neither manifest.json nor realized_trades readable",
        )

    payload = _compute_variance(realized, brain)
    payload["brain_dir"] = str(brain_dir)
    payload["explanation"] = (
        "brain.total_trades increments at fill (entry + exit each count); "
        "realized_trades stores ONE row per closed round-trip.  An expected "
        "by-design ratio is roughly 2× realized = brain when running cleanly.  "
        "W95 surfaces the variance so operators see drift without parsing logs."
    )
    return payload
