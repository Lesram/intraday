"""V12 W71 (EXT-1): /api/v1/health/strategy — strategy expectancy gate.

Auditor's #1 finding from V11 external review: 11 internal audits
validated software-correctness without ever computing realized PnL,
Sharpe, win-rate, or max-drawdown.  This endpoint surfaces those
numbers from the live brain so operators (and the next external
auditor) can see whether the brain is profitable at a glance.

Auth: protected (mounted under the JWT-required prefix in
``routes_setup.py``).  Exposing live PnL/Sharpe to unauthenticated
clients would be an information-disclosure risk.

Behavior:
- Reads ``organism_brain/manifest.json`` for the at-rest snapshot
  (set by ``brain_persistence._apply_live_manifest_fields``).
- Falls back to recomputing from ``organism_brain/trade_history.csv``
  if the manifest hasn't been updated by the new V12 W71 path yet
  (e.g. on first deploy before the next save).
- Single helper ``backend.organism.strategy_expectancy.compute_from_trades``
  drives both the manifest writer and this endpoint, so the schema
  stays consistent.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.organism import strategy_expectancy as _sx
from backend.organism import strategy_attribution as _attr


router = APIRouter(prefix="/health", tags=["Health"])


def _resolve_brain_dir() -> Path:
    """Best-effort resolution of the brain directory.

    Container path is ``/app/organism_brain``; local dev is
    ``./organism_brain``.  Try the env override first, then the live
    engine reference, then the conventional paths.
    """
    env = os.environ.get("ORGANISM_BRAIN_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # Live engine ref (set by lifespan when the engine is up).
    try:
        from backend.api import lifespan as _lifespan_mod
        engine = getattr(_lifespan_mod, "_LIVE_ENGINE_REF", None)
        if engine is not None:
            brain = getattr(engine, "brain", None)
            if brain is not None:
                bd = getattr(brain, "brain_dir", None)
                if bd is not None and Path(bd).is_dir():
                    return Path(bd)
    except Exception:
        pass
    for candidate in ("organism_brain", "/app/organism_brain"):
        p = Path(candidate)
        if p.is_dir():
            return p
    return Path("organism_brain")


def _read_manifest_expectancy(brain_dir: Path) -> dict[str, Any] | None:
    """Return the manifest's ``strategy_expectancy`` block if present."""
    mpath = brain_dir / "manifest.json"
    if not mpath.is_file():
        return None
    try:
        m = json.loads(mpath.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    sx = m.get("strategy_expectancy")
    if isinstance(sx, dict) and "n_trades" in sx:
        return sx
    return None


def _read_manifest_attribution(brain_dir: Path) -> dict[str, Any] | None:
    """Return the manifest's ``strategy_attribution`` block if present."""
    mpath = brain_dir / "manifest.json"
    if not mpath.is_file():
        return None
    try:
        m = json.loads(mpath.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    attr = m.get("strategy_attribution")
    if isinstance(attr, dict) and "segments" in attr:
        return attr
    return None


def _read_csv_rows(brain_dir: Path) -> list[dict[str, Any]] | None:
    """Read trade_history.csv rows for fallback computations."""
    csv_path = brain_dir / "trade_history.csv"
    if not csv_path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))
    return rows


def _compute_from_csv(brain_dir: Path) -> dict[str, Any] | None:
    """Recompute expectancy from trade_history.csv (fallback)."""
    rows = _read_csv_rows(brain_dir)
    if rows is None:
        return None
    pnls: list[float] = []
    for row in rows:
        try:
            pnls.append(float(row.get("pnl", 0)))
        except (TypeError, ValueError):
            continue
    return _sx.compute_from_pnls(pnls)


def _compute_attribution_from_csv(brain_dir: Path) -> dict[str, Any] | None:
    rows = _read_csv_rows(brain_dir)
    if rows is None:
        return None
    return _attr.compute_from_trades(rows)


_ALLOWED_WINDOWS = {"last_25", "last_50"}
_ALLOWED_DETAILS = {"attribution"}


@router.get("/strategy")
async def strategy_health(
    window: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """V12 W71: live strategy-expectancy snapshot.

    Returns the full expectancy payload (n_trades, total_pnl, win_rate,
    sharpe_ratio_per_trade, max_drawdown, mean/median, last 25/50
    windows) plus provenance fields so operators can tell whether they
    are reading the manifest or a recomputation.

    V13 W94: ``?window=last_50`` (or ``last_25``) projects the payload
    down to just that window's fields plus the provenance fields.
    Useful for dashboard panels that only care about the rolling slice.

    Status code is always 200 even if the brain is unprofitable — this
    is an *informational* endpoint, not a readiness gate.  Use the
    ``is_profitable`` boolean for at-a-glance assessment.
    """
    if window is not None and window not in _ALLOWED_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail=f"window must be one of {sorted(_ALLOWED_WINDOWS)}",
        )
    if detail is not None and detail not in _ALLOWED_DETAILS:
        raise HTTPException(
            status_code=400,
            detail=f"detail must be one of {sorted(_ALLOWED_DETAILS)}",
        )
    brain_dir = _resolve_brain_dir()

    payload: dict[str, Any] = {
        "source": "manifest",
        "brain_dir": str(brain_dir),
    }
    manifest_sx = _read_manifest_expectancy(brain_dir)
    if manifest_sx is not None:
        payload.update(manifest_sx)
    else:
        # Fallback: recompute from CSV.  This path is hit only before
        # the V12 W71 manifest writer has run for the first time.
        recomputed = _compute_from_csv(brain_dir)
        if recomputed is None:
            raise HTTPException(
                status_code=503,
                detail="strategy_expectancy unavailable: no manifest, no CSV",
            )
        payload["source"] = "trade_history_csv"
        payload.update(recomputed)

    # Convenience boolean for operators.  Auditor's framing:
    # "code-correct ≠ profitable".  This makes the gap visible.
    payload["is_profitable"] = bool(payload.get("total_pnl", 0) > 0)

    csv_path = brain_dir / "trade_history.csv"
    if csv_path.is_file():
        payload["csv_mtime"] = os.path.getmtime(csv_path)

    if detail == "attribution":
        attribution = _read_manifest_attribution(brain_dir)
        if attribution is None:
            attribution = _compute_attribution_from_csv(brain_dir)
        if attribution is not None:
            payload["strategy_attribution"] = attribution

    # V13 W94: windowed projection.
    if window is not None:
        prefix = f"{window}_"
        slim: dict[str, Any] = {
            "source": payload.get("source"),
            "brain_dir": payload.get("brain_dir"),
            "window": window,
            "n_trades": payload.get("n_trades"),
            "csv_mtime": payload.get("csv_mtime"),
        }
        for k, v in payload.items():
            if k.startswith(prefix):
                slim[k] = v
        if detail == "attribution" and "strategy_attribution" in payload:
            window_attr = (
                payload["strategy_attribution"]
                .get("windows", {})
                .get(window)
            )
            if window_attr is not None:
                slim["strategy_attribution"] = window_attr
        return slim

    return payload
