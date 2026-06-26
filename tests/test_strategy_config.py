"""Intra 2.0 Phase 1 — Step 2: externalized strategy config.

Proves momentum's externalized values are VERBATIM the current hardcoded ones
(no tuning in Phase 1), and that live_routing gating follows Rule A.
"""
from __future__ import annotations

import inspect

from backend.organism.alpha_scanner import AlphaScanner
from backend.organism.strategies.strategy_config import (
    STRATEGY_CONFIG,
    all_configs,
    get_config,
)


def test_momentum_values_are_verbatim_from_observable_direction():
    m = get_config("momentum")
    # The literals must equal what _observable_direction hardcodes today.
    assert m["breakout_readiness_threshold"] == 0.60
    assert m["breakout_readiness_squeeze_threshold"] == 0.50
    assert m["squeeze_momentum_threshold"] == 0.50
    assert m["ret_5d_threshold"] == 0.005
    assert m["ret_20d_threshold"] == 0.010
    assert m["trend_strength_min"] == 0.0
    # And prove they actually appear in the live source (no silent drift).
    src = inspect.getsource(AlphaScanner._observable_direction)
    for lit in ("0.60", "0.50", "0.005", "0.010"):
        assert lit in src, f"{lit} not found in _observable_direction — config drift"


def test_live_routing_gating_rule_a():
    assert get_config("momentum")["live_routing"] is True   # only live book
    assert get_config("mean_reversion")["live_routing"] is False  # evidence-negative
    assert get_config("orb")["live_routing"] is False        # unbuilt/untested


def test_every_block_declares_eligible_regimes():
    for name, cfg in all_configs().items():
        assert cfg.get("eligible_regimes"), f"{name} missing eligible_regimes"


def test_eod_is_parked_excluded():
    assert "eod" not in STRATEGY_CONFIG, "EOD must stay parked/excluded in Phase 1"


def test_get_config_is_deep_copy():
    a = get_config("momentum")
    a["ret_5d_threshold"] = 999
    assert get_config("momentum")["ret_5d_threshold"] == 0.005  # source untouched
