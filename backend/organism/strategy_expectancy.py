"""V12 W71 (EXT-1): strategy expectancy gate.

The auditor's #1 finding from the V11 external review: 11 internal
audits validated software-correctness without ever computing realized
PnL/Sharpe/win-rate/max-drawdown.  At V12 baseline the brain had run
498 trades for total PnL ``-$634.90`` (33.73% win rate, per-trade
Sharpe ``-1.06``) and the manifest didn't even have those fields.
"Correctly executing a losing strategy is not platform health."

This module is the single source of truth for those numbers.  It is
called from:

- ``brain_persistence._apply_live_manifest_fields`` (writes them into
  ``manifest.json`` on every save)
- ``backend/api/routes/health.py`` ``/api/v1/health/strategy``
  endpoint (live read of current expectancy)
- ``scripts/ci/compute_strategy_expectancy.py`` (CLI baseline tool —
  re-uses ``compute_from_pnls`` so all three call sites are consistent)
- ``backend/api/lifespan.py`` startup banner

A single helper, a single field schema.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


# Field schema — all three call sites must produce these keys.
_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "n_trades",
    "n_wins",
    "n_losses",
    "total_pnl",
    "mean_pnl",
    "median_pnl",
    "win_rate",
    "sharpe_ratio_per_trade",
    "max_drawdown",
    "last_25_mean_pnl",
    "last_25_win_rate",
    "last_50_mean_pnl",
    "last_50_win_rate",
})


def _pnls_from_trades(trades: Iterable[Any]) -> list[float]:
    """Extract per-trade PnL floats from heterogeneous trade objects.

    Accepts dicts (from ``brain_persistence.trade_history`` or the
    CSV reader), TradeRecord-style objects with a ``pnl`` attribute,
    or plain floats.  Skips entries that don't yield a finite float.
    """
    out: list[float] = []
    for t in trades:
        if isinstance(t, (int, float)):
            v = float(t)
        elif isinstance(t, dict):
            raw = t.get("pnl", None)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
        else:
            raw = getattr(t, "pnl", None)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
        if math.isfinite(v):
            out.append(v)
    return out


def _max_drawdown(cum: list[float]) -> float:
    if not cum:
        return 0.0
    peak = cum[0]
    worst = 0.0
    for v in cum:
        peak = max(peak, v)
        worst = min(worst, v - peak)
    return worst


def _round(v: float, n: int = 4) -> float:
    if not math.isfinite(v):
        return 0.0
    return round(v, n)


def _empty_payload() -> dict[str, Any]:
    return {
        "n_trades": 0,
        "n_wins": 0,
        "n_losses": 0,
        "total_pnl": 0.0,
        "mean_pnl": 0.0,
        "median_pnl": 0.0,
        "win_rate": 0.0,
        "sharpe_ratio_per_trade": 0.0,
        "max_drawdown": 0.0,
        "last_25_mean_pnl": 0.0,
        "last_25_win_rate": 0.0,
        "last_50_mean_pnl": 0.0,
        "last_50_win_rate": 0.0,
    }


def compute_from_pnls(pnls: list[float]) -> dict[str, Any]:
    """Compute the full expectancy payload from a list of per-trade PnLs.

    All callers (manifest writer, /health/strategy endpoint, CLI tool)
    flow through here so the schema stays consistent.
    """
    n = len(pnls)
    if n == 0:
        return _empty_payload()

    n_wins = sum(1 for p in pnls if p > 0)
    n_losses = sum(1 for p in pnls if p < 0)
    cum: list[float] = []
    running = 0.0
    for p in pnls:
        running += p
        cum.append(running)
    total = running
    mean = statistics.fmean(pnls)
    median = statistics.median(pnls)
    stdev = statistics.pstdev(pnls) if n >= 2 else 0.0
    sharpe = (mean / stdev * math.sqrt(n)) if stdev > 0 else 0.0
    mdd = _max_drawdown(cum)

    def _window(k: int) -> tuple[float, float]:
        if n == 0:
            return 0.0, 0.0
        sub = pnls[-min(k, n):]
        sub_n = len(sub)
        sub_wins = sum(1 for p in sub if p > 0)
        return statistics.fmean(sub), sub_wins / sub_n

    last25_mean, last25_wr = _window(25)
    last50_mean, last50_wr = _window(50)

    return {
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "total_pnl": _round(total, 4),
        "mean_pnl": _round(mean, 4),
        "median_pnl": _round(median, 4),
        "win_rate": _round(n_wins / n, 4),
        "sharpe_ratio_per_trade": _round(sharpe, 4),
        "max_drawdown": _round(mdd, 4),
        "last_25_mean_pnl": _round(last25_mean, 4),
        "last_25_win_rate": _round(last25_wr, 4),
        "last_50_mean_pnl": _round(last50_mean, 4),
        "last_50_win_rate": _round(last50_wr, 4),
    }


def compute_from_trades(trades: Iterable[Any]) -> dict[str, Any]:
    """Convenience: extract PnLs from heterogeneous trade objects then
    compute.  Used by the manifest writer and the live API."""
    pnls = _pnls_from_trades(trades)
    return compute_from_pnls(pnls)


def required_fields() -> frozenset[str]:
    """Schema introspection — the API endpoint and tests both rely
    on this."""
    return _REQUIRED_FIELDS
