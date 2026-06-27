"""Phase 1 step 4 — StrategySelector routing policy (Rule A) + stand-down."""
from __future__ import annotations

import pandas as pd

from backend.organism.strategies import Candidate, Strategy, register
from backend.organism.strategy_selector import StrategySelector


@register("_sel_chop_gated")
class _ChopGated(Strategy):
    """A chop strategy with live_routing False (benchmark only)."""
    def required_features(self): return set()
    def eligible_regimes(self): return {"chop"}
    def validate_config(self): return None
    def scan(self, features, regime):
        return [Candidate(s, 1.0, 0.4, self.name) for s in features]


def _mom():
    from backend.organism.strategies.momentum import MomentumStrategy
    from backend.organism.strategies.strategy_config import get_config
    return MomentumStrategy(get_config("momentum"))


def _feats():
    # one clearly-bullish row (ret_5d>0.005 -> momentum long)
    return {"AAPL": pd.DataFrame({"ret_5d": [0.02], "ret_20d": [0.0],
            "comp_breakout_readiness": [0.7], "comp_squeeze_momentum": [0.0],
            "trend_strength": [0.0]})}


def test_live_mode_routes_only_live_routing_true_in_eligible_regime():
    sel = StrategySelector([_mom(), _ChopGated({})], mode="live")
    # trending_up: momentum eligible (live_routing True) -> candidate
    out = sel.select(_feats(), "trending_up")
    assert [c.strategy_name for c in out] == ["momentum"]


def test_live_mode_stands_down_when_no_live_strategy_for_regime():
    sel = StrategySelector([_mom(), _ChopGated({})], mode="live")
    # chop: momentum not eligible; chop strat is live_routing False -> STAND DOWN
    assert sel.select({"AAPL": pd.DataFrame({"ret_5d": [0.0]})}, "chop") == []


def test_backtest_mode_measures_gated_strategy():
    sel = StrategySelector([_mom(), _ChopGated({})], mode="backtest")
    # chop, backtest: the gated chop strat runs (measurement), despite live_routing False
    out = sel.select(_feats(), "chop")
    assert "_sel_chop_gated" in {c.strategy_name for c in out}


def test_select_ranks_by_confidence_desc():
    @register("_sel_hi")
    class _Hi(_ChopGated):
        def scan(self, features, regime):
            return [Candidate("X", 1.0, 0.9, self.name)]

    sel = StrategySelector([_ChopGated({}), _Hi({})], mode="backtest")
    out = sel.select({"X": pd.DataFrame({"a": [1]})}, "chop")
    confs = [c.confidence for c in out]
    assert confs == sorted(confs, reverse=True) and confs[0] == 0.9


def test_from_config_builds_registered_strategies():
    # momentum + breakout (live_routing True) + mean_reversion (registered but
    # live_routing False) are built; ORB not yet registered (step 9) -> skipped.
    names = {s.name for s in StrategySelector.from_config(mode="live").strategies}
    assert {"momentum", "breakout", "mean_reversion"} <= names
    assert "orb" not in names
    # low_vol is eligible for NEITHER momentum {trending_up,high_vol} nor breakout
    # {trending_up,high_vol,chop,trending_down} -> live mode stands down.
    sel = StrategySelector.from_config(mode="live")
    assert sel.select({"A": pd.DataFrame({"close": [1.0]})}, "low_vol") == []


def test_rule_a_mean_reversion_measured_not_routed():
    """MR's regime is chop. In BACKTEST it is measured; in LIVE it is NOT routed
    (live_routing False) even in its own regime — Rule A."""
    live = StrategySelector.from_config(mode="live")
    bt = StrategySelector.from_config(mode="backtest")
    live_chop = {s.name for s in live.eligible_strategies("chop")}
    bt_chop = {s.name for s in bt.eligible_strategies("chop")}
    assert "mean_reversion" not in live_chop   # capital gated off
    assert "mean_reversion" in bt_chop          # measured
