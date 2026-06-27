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

    # ── Mean-reversion: VERBATIM from mean_reversion_scanner + live MR_* env
    #    defaults (live_engine sets top_n=3, cooldown=60, long_only=LONG_ONLY). ──
    "mean_reversion": {
        "timeframe": "1Min",
        "min_displacement_atr": 4.0,
        "target_retracement": 0.8,
        "stop_extension_atr": 1.0,
        "min_stop_bps": 5.0,
        "min_price": 5.0,
        "cooldown_minutes": 60,   # MR_COOLDOWN_MINUTES
        "top_n": 3,               # MR_TOP_N (live overrides scanner default 5)
        "long_only": True,        # scanner long_only (LONG_ONLY env)
        "min_vwap_bars": 10,      # DEFAULT_MIN_VWAP_BARS
        "entry_hour_et": 9, "entry_min_et": 45,    # skip 9:30-9:45 open vol
        "no_new_hour_et": 15, "no_new_min_et": 30,  # no entries into EOD flatten
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

    # ── Breakout: KEEP-DISTINCT (step-6 decision). A separate multi-factor
    #    generator (BreakoutScanner) that enters symbols momentum's
    #    _observable_direction never flags — folding it into momentum would
    #    either DROP those entries (parity break) or force momentum to replicate
    #    the whole breakout composite (conflating two signals). So it stays its
    #    own Strategy. Params VERBATIM from BreakoutScanner; the live pure-
    #    breakout entry path forces LONG and gates at composite>=0.55. ──
    "breakout": {
        "timeframe": "1Min",
        "top_n": 8,  # MAX_OPEN_POSITIONS (BreakoutScanner default)
        # Scanner composite weights (BreakoutScanner.W_*).
        "w_squeeze": 0.25, "w_volume": 0.25, "w_contraction": 0.15,
        "w_rs": 0.15, "w_pivot": 0.15, "w_flow": 0.05,
        "min_breakout_score": 0.20,  # scanner's own floor (MIN_BREAKOUT_SCORE)
        # Lookbacks: intraday-scaled (engine sets 4x for 1Min bars).
        "bb_period": 80, "atr_short": 40, "atr_long": 200, "vol_avg_period": 80,
        # Live pure-breakout ENTRY rule (live_engine ~4307/4321/4371):
        "entry_composite_threshold": 0.55,  # engine gate, above the scanner floor
        "max_pure_breakout": 2,             # per-tick cap (selector/routing concern)
        "long_only": True,                  # entry path forces direction=1.0
        # No hard regime gate live (runs every tick, gated by _MIN_MAIN_CONF +
        # shared entry gates). eligible_regimes here is the framework view; the
        # engine's real regime behavior is authoritative until 5c reconciliation.
        "eligible_regimes": ["trending_up", "high_vol", "chop", "trending_down"],
        "live_routing": True,  # a LIVE capital path today (still unproven, like momentum)
    },

    # eod: PARKED — two contradictory unvalidated engines; excluded from the
    #   registry entirely (Section 5). Do not expand Phase 1 scope on it.
}


def get_config(name: str) -> dict[str, Any]:
    """Return a deep copy of a strategy's config block (mutation-safe)."""
    return copy.deepcopy(STRATEGY_CONFIG.get(name, {}))


def all_configs() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(STRATEGY_CONFIG)
