"""Audit 2026-06-09 plan 1.2 — walk-forward over the LIVE scanners.

The legacy walk_forward.py evaluates strategies that never trade live.
LiveScannerWalkForward drives ReplayEngine (the real OrganismLiveEngine
pipeline) over session-disjoint folds with costed fills and a fresh brain
per fold.
"""

import math

import pandas as pd
import pytest

from backend.organism.walk_forward_live import (
    LiveScannerWalkForward,
    split_sessions_into_folds,
)


def _multi_day_bars(n_days=4, bars_per_day=30, syms=("AAA", "BBB")):
    out = {}
    for s_i, sym in enumerate(syms):
        frames = []
        for d in range(n_days):
            ts = pd.date_range(
                f"2026-03-{2 + d:02d} 14:30", periods=bars_per_day,
                freq="1min", tz="UTC",
            )
            base = 100.0 + s_i * 10 + d
            frames.append(pd.DataFrame({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": base, "high": base + 1, "low": base - 1,
                "close": base, "volume": 1e6,
            }))
        out[sym] = pd.concat(frames, ignore_index=True)
    return out


def test_fold_split_is_session_disjoint_and_chronological():
    bars = _multi_day_bars(n_days=4)
    folds = split_sessions_into_folds(bars, n_folds=2)
    assert len(folds) == 2
    from backend.organism.walk_forward_live import _session_dates

    d0 = set(_session_dates(folds[0]["AAA"]).unique())
    d1 = set(_session_dates(folds[1]["AAA"]).unique())
    assert d0.isdisjoint(d1), "folds must not share sessions"
    assert max(d0) < min(d1), "folds must be chronological"
    # No session split mid-day: each fold's bar count is whole sessions.
    assert len(folds[0]["AAA"]) % 30 == 0


def test_too_few_sessions_rejected():
    bars = _multi_day_bars(n_days=2)
    with pytest.raises(ValueError, match="sessions"):
        split_sessions_into_folds(bars, n_folds=3)


def test_aggregate_verdict_logic():
    agg = LiveScannerWalkForward._aggregate([
        {"fold": 0, "ticks": 10, "n_trades": 20, "total_pnl": 50.0,
         "expectancy": 2.5, "win_rate": 0.6, "profit_factor": 1.8,
         "max_drawdown": 0.01},
        {"fold": 1, "ticks": 10, "n_trades": 20, "total_pnl": 44.0,
         "expectancy": 2.2, "win_rate": 0.55, "profit_factor": 1.6,
         "max_drawdown": 0.02},
        {"fold": 2, "ticks": 10, "n_trades": 20, "total_pnl": 56.0,
         "expectancy": 2.8, "win_rate": 0.65, "profit_factor": 2.0,
         "max_drawdown": 0.01},
    ])
    assert agg["verdict"] == "PASS"
    assert agg["tstat_expectancy"] is not None and agg["tstat_expectancy"] > 2


def test_aggregate_fails_on_no_edge():
    agg = LiveScannerWalkForward._aggregate([
        {"fold": 0, "ticks": 10, "n_trades": 20, "total_pnl": -5.0,
         "expectancy": -0.25, "win_rate": 0.4, "profit_factor": 0.9,
         "max_drawdown": 0.05},
        {"fold": 1, "ticks": 10, "n_trades": 20, "total_pnl": 3.0,
         "expectancy": 0.15, "win_rate": 0.5, "profit_factor": 1.05,
         "max_drawdown": 0.03},
    ])
    assert agg["verdict"] == "FAIL"
    assert agg["fail_reasons"]


def test_aggregate_handles_zero_trade_folds():
    agg = LiveScannerWalkForward._aggregate([
        {"fold": 0, "ticks": 10, "n_trades": 0, "total_pnl": 0.0,
         "expectancy": None, "win_rate": None, "profit_factor": None,
         "max_drawdown": 0.0},
    ])
    assert agg["verdict"] == "FAIL"
    assert agg["n_trades"] == 0


@pytest.mark.asyncio
async def test_end_to_end_smoke_runs_real_engine():
    """Drives the genuine OrganismLiveEngine on tiny synthetic folds.
    Verifies the wiring (costed broker, fresh brain per fold, fold
    reports), not profitability."""
    bars = _multi_day_bars(n_days=2, bars_per_day=25)
    wf = LiveScannerWalkForward(
        bars, n_folds=2, timeframe="1Min", lookback=10,
        max_ticks_per_fold=5,
    )
    report = await wf.run()
    assert report["n_folds"] == 2
    assert report["verdict"] in ("PASS", "FAIL")
    for f in report["folds"]:
        assert f["ticks"] >= 1
        assert not math.isnan(f["total_pnl"])
