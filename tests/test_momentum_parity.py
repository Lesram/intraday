"""Phase 1 step 3 — momentum extraction PARITY (Section 9, module level).

The extracted MomentumStrategy._direction must equal the live
alpha_scanner._observable_direction bit-for-bit on an exhaustive boundary grid,
in BOTH symmetric-short modes. This is the entry-deciding core of the live book;
if it diverges anywhere, the extraction is wrong.
"""
from __future__ import annotations

import itertools

import pandas as pd
import pytest

import backend.organism.alpha_scanner as als
import backend.organism.strategies.momentum as mom
from backend.organism.alpha_scanner import AlphaScanner
from backend.organism.strategies.momentum import MomentumStrategy
from backend.organism.strategies.strategy_config import get_config

# Boundary-straddling values around every threshold the logic uses.
RET5 = [-0.02, -0.006, -0.005, -0.004, 0.0, 0.004, 0.005, 0.006, 0.02]
RET20 = [-0.02, -0.011, -0.010, -0.009, 0.0, 0.009, 0.010, 0.011, 0.02]
READY = [0.0, 0.49, 0.50, 0.51, 0.59, 0.60, 0.61, 1.0]
SQZ = [-0.6, -0.51, -0.50, -0.49, 0.0, 0.49, 0.50, 0.51, 0.6]
TREND = [-1.0, -0.001, 0.0, 0.001, 1.0]


def _grid_rows():
    for r5, r20, rd, sq, tr in itertools.product(RET5, RET20, READY, SQZ, TREND):
        yield pd.Series({
            "ret_5d": r5, "ret_20d": r20, "comp_breakout_readiness": rd,
            "comp_squeeze_momentum": sq, "trend_strength": tr,
        })


def _run_parity():
    scanner = AlphaScanner(top_n=5)
    strat = MomentumStrategy(get_config("momentum"))
    mismatches = []
    n = 0
    for row in _grid_rows():
        n += 1
        live = scanner._observable_direction(row)
        ours = strat._direction(row)
        if live != ours:
            mismatches.append((dict(row), live, ours))
            if len(mismatches) >= 5:
                break
    return n, mismatches


def test_parity_default_long_only():
    # default: symmetric short OFF (live default)
    assert als.SYMMETRIC_SHORT_ENABLED is False
    # momentum reads the flag from alpha_scanner at call time — it must NOT
    # carry its own module-level copy that could drift.
    assert not hasattr(mom, "SYMMETRIC_SHORT_ENABLED"), (
        "momentum.py must read SYMMETRIC_SHORT_ENABLED from alpha_scanner at "
        "call time, not bind its own module-level copy."
    )
    n, mism = _run_parity()
    assert not mism, f"{len(mism)} direction mismatches over {n} rows; first: {mism[:3]}"


def test_parity_symmetric_short_on(monkeypatch):
    # Flip the flag in ONLY the canonical home (alpha_scanner). Because momentum
    # reads it at call time, patching one place must flip BOTH paths in lockstep
    # — this is the regression test for the call-time-read fix.
    monkeypatch.setattr(als, "SYMMETRIC_SHORT_ENABLED", True)
    n, mism = _run_parity()
    assert not mism, f"{len(mism)} mismatches (short-on) over {n} rows; first: {mism[:3]}"


def test_scan_emits_candidates_for_nonzero_direction():
    strat = MomentumStrategy(get_config("momentum"))
    feats = {
        "BULL": pd.DataFrame({"ret_5d": [0.01], "ret_20d": [0.0],
                              "comp_breakout_readiness": [0.0], "comp_squeeze_momentum": [0.0],
                              "trend_strength": [0.0]}),
        "FLAT": pd.DataFrame({"ret_5d": [0.0], "ret_20d": [0.0],
                              "comp_breakout_readiness": [0.0], "comp_squeeze_momentum": [0.0],
                              "trend_strength": [0.0]}),
    }
    cands = strat.scan(feats, "trending_up")
    syms = {c.symbol: c for c in cands}
    assert "BULL" in syms and syms["BULL"].direction == 1.0  # ret_5d>0.005 -> long
    assert "FLAT" not in syms  # direction 0 -> no candidate
    assert 0.0 <= syms["BULL"].confidence <= 1.0


def test_validate_config_fail_closed():
    with pytest.raises(ValueError):
        MomentumStrategy({"eligible_regimes": ["x"]})  # missing thresholds
