"""Phase 3 Task 4 — regime policy + shadow attribution behavioral probes."""
from __future__ import annotations

import pandas as pd

from backend.organism.strategies.base import Candidate
from backend.organism.strategies.strategy_config import REGIME_POLICY, regime_policy
from backend.organism.strategy_selector import StrategySelector


def _cand(sym, strat, conf=0.5, direction=1.0, extra=None):
    return Candidate(symbol=sym, direction=direction, confidence=conf,
                     strategy_name=strat, extra=extra or {})


def _scan_res(**per_strategy):
    """per_strategy: name=(candidates, routed)"""
    return {k: {"candidates": v[0], "routed": v[1]} for k, v in per_strategy.items()}


def _sel():
    return StrategySelector.from_config(mode="live")


def test_policy_order_is_ranking_authority():
    """Candidates come out in policy order, native order within a strategy —
    confidence values must NOT reorder them (5b: flat ships)."""
    res = _scan_res(
        momentum=([_cand("AAPL", "momentum", conf=0.1),
                   _cand("MSFT", "momentum", conf=0.2)], True),
        breakout=([_cand("NVDA", "breakout", conf=0.99)], True),
    )
    out = _sel().select_policy_ranked({}, "trending_up",
                                      policy={"trending_up": ["momentum", "breakout"]},
                                      scan_res=res)
    assert [(c.strategy_name, c.symbol) for c in out] == [
        ("momentum", "AAPL"), ("momentum", "MSFT"), ("breakout", "NVDA")]


def test_stand_down_on_empty_or_missing_regime():
    res = _scan_res(momentum=([_cand("AAPL", "momentum")], True))
    sel = _sel()
    assert sel.select_policy_ranked({}, "stress",
                                    policy={"stress": []}, scan_res=res) == []
    assert sel.select_policy_ranked({}, "never_heard_of_it",
                                    policy={}, scan_res=res) == []


def test_policy_cannot_widen_rule_a():
    """A strategy named in the policy but NOT routed (Rule A) contributes
    nothing — the policy narrows, never widens."""
    res = _scan_res(mean_reversion=([_cand("AAPL", "mean_reversion")], False))
    out = _sel().select_policy_ranked({}, "chop",
                                      policy={"chop": ["mean_reversion"]},
                                      scan_res=res)
    assert out == []


def test_committed_policy_stands_down_on_stress_and_unknown():
    assert REGIME_POLICY["stress"] == []
    assert REGIME_POLICY["unknown"] == []
    # Rule-A note holds: MR is chop-only in the policy and live_routing:false
    # in config — the committed tables are consistent with shadow-only MR.
    assert REGIME_POLICY["chop"] == ["mean_reversion"]
    pol = regime_policy()
    pol["chop"].append("mutated")
    assert REGIME_POLICY["chop"] == ["mean_reversion"]   # deep-copied


def test_scan_res_reuse_avoids_second_scan():
    calls = {"n": 0}

    class _SpySel(StrategySelector):
        def scan_all(self, features, regime):
            calls["n"] += 1
            return {}

    sel = _SpySel([], mode="live")
    sel.select_policy_ranked({}, "trending_up",
                             policy={"trending_up": ["momentum"]},
                             scan_res={"momentum": {"candidates": [], "routed": True}})
    assert calls["n"] == 0                      # reused the provided result


def test_framework_shadow_records_unrouted_only_with_bar_dedup():
    import backend.organism.live_engine as le

    recorded = []

    class _Recorder:
        def record_signals(self, signals, tick, timestamp):
            recorded.extend(signals)
            return len(signals)

    eng = object.__new__(le.OrganismLiveEngine)
    eng._strategy_evidence_recorder = _Recorder()
    eng._fw_shadow_last_signal_keys = set()
    eng._strategy_evidence_events = 0
    eng._phase9_shadow_signal_events = 0
    eng._tick_count = 3
    eng._now_fn = lambda: pd.Timestamp("2026-07-07 15:00", tz="UTC")

    res = _scan_res(
        momentum=([_cand("AAPL", "momentum")], True),           # routed -> NOT recorded
        mean_reversion=([_cand("MSFT", "mean_reversion",
                               extra={"stop_price": 99.0})], False),
        orb=([_cand("NVDA", "orb", direction=-1.0)], False),
    )
    eng._record_framework_shadow_candidates(res, regime="chop",
                                            now_iso="2026-07-07T15:00:00Z")
    assert sorted(s.strategy_id for s in recorded) == [
        "fw_mean_reversion_shadow", "fw_orb_shadow"]
    assert all(s.shadow_only for s in recorded)
    assert {s.regime for s in recorded} == {"chop"}
    by_id = {s.strategy_id: s for s in recorded}
    assert by_id["fw_orb_shadow"].side == "short"
    assert by_id["fw_mean_reversion_shadow"].stop_price == 99.0

    # Same bar, same signals -> dedup: nothing new recorded.
    n_before = len(recorded)
    eng._record_framework_shadow_candidates(res, regime="chop",
                                            now_iso="2026-07-07T15:00:00Z")
    assert len(recorded) == n_before
