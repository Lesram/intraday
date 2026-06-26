"""Single source of truth for every strategy's parameters (Phase 1, Section 7).

VALUES ARE CARRIED OVER FROM CURRENT CODE VERBATIM — no tuning in Phase 1. A
Phase-2 sweep edits THIS file, never strategy code; each Strategy reads every
tunable from its block here and validates fail-closed.

live_routing gates CAPITAL, not measurement (Rule A): momentum is the only live
book (and still unproven); mean_reversion (evidence-negative after costs) and
orb (unbuilt/untested) are backtest/shadow benchmarks until they pass the
Section-8 OOS bar (net exp>0 at t>=2 out-of-sample, costed) and a human flips
live_routing to true.
"""
from __future__ import annotations

import copy
from typing import Any

STRATEGY_CONFIG: dict[str, dict[str, Any]] = {
    # ── Momentum: the live book. Thresholds VERBATIM from
    #    alpha_scanner._observable_direction (do not change in Phase 1). ──
    "momentum": {
        "timeframe": "1Min",
        "top_n": 5,  # ALPHA_TOP_N (env ORGANISM_ALPHA_TOP_N default 5)
        # bullish_breakout = readiness>0.60 OR (readiness>0.50 AND squeeze>0.50)
        "breakout_readiness_threshold": 0.60,
        "breakout_readiness_squeeze_threshold": 0.50,
        "squeeze_momentum_threshold": 0.50,
        # bullish_momentum = ret_5d>0.005 OR (ret_20d>0.010 AND trend_strength>=0)
        "ret_5d_threshold": 0.005,
        "ret_20d_threshold": 0.010,
        "trend_strength_min": 0.0,
        # Symmetric short mirror (active only when ORGANISM_SYMMETRIC_SHORT_ENABLED;
        # default off => byte-identical). Values mirror the long side.
        "bearish_squeeze_threshold": -0.50,
        "bearish_ret_5d_threshold": -0.005,
        "bearish_ret_20d_threshold": -0.010,
        "trend_strength_max": 0.0,
        "eligible_regimes": ["trending_up", "high_vol"],
        "live_routing": True,  # only live book (still unproven; t≈0.2 OOS)
    },

    # ── Mean-reversion: VERBATIM from mean_reversion_scanner defaults. ──
    "mean_reversion": {
        "timeframe": "1Min",
        "min_displacement_atr": 4.0,
        "target_retracement": 0.8,
        "stop_extension_atr": 1.0,
        "min_stop_bps": 5.0,
        "min_price": 5.0,
        "eligible_regimes": ["chop"],
        # Rule A: evidence-NEGATIVE — gross bounce ~1.7-2.2bps < ~4bps round-trip
        # cost, net-negative in every sweep incl. residual variant; bounce
        # shrinks at larger dislocations. Benchmark only. Flip requires a
        # STRUCTURAL change (cost/horizon/instrument) that is OOS-positive at t>=2.
        "live_routing": False,
    },

    # ── ORB: BUILT to the contract in step 9 (was never properly built). ──
    "orb": {
        "timeframe": "1Min",
        "opening_range_minutes": 15,   # opening-range window
        "min_relative_volume": 1.5,    # in-play universe rank gate
        "breakout_buffer_atr": 0.1,    # trigger = OR high/low +/- buffer*ATR
        "universe_size": 50,           # dynamic in-play universe (wider than the 22)
        "eligible_regimes": ["high_vol"],
        # Rule A: unbuilt/untested; no validated backtest exists. Prove OOS at
        # t>=2 (incl. the dynamic in-play universe feed) before routing.
        "live_routing": False,
    },

    # breakout: resolved in step 6 (fold into momentum vs keep distinct), then
    #   added here with a documented parity decision.
    # eod: PARKED — two contradictory unvalidated engines; excluded from the
    #   registry entirely (Section 5). Do not expand Phase 1 scope on it.
}


def get_config(name: str) -> dict[str, Any]:
    """Return a deep copy of a strategy's config block (mutation-safe)."""
    return copy.deepcopy(STRATEGY_CONFIG.get(name, {}))


def all_configs() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(STRATEGY_CONFIG)
