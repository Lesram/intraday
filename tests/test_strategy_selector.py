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


def test_from_config_live_builds_momentum_only_live():
    sel = StrategySelector.from_config(mode="live")
    # momentum is registered + live_routing True; MR/ORB not yet registered (steps 7/9)
    names = {s.name for s in sel.strategies}
    assert "momentum" in names
    # In a chop regime, live mode stands down (momentum not eligible there).
    assert sel.select({"A": pd.DataFrame({"ret_5d": [0.0]})}, "chop") == []
