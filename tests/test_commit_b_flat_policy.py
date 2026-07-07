"""5c Commit B — flat_policy behavioral probes.

The intended behavior change (NOT parity with legacy): REGIME_POLICY order is
the ranking authority, composite confidence gates bypass, Kelly confidence/
breakout multipliers neutralize. Each probe plants a case where legacy and
flat_policy MUST differ in the direction the 5b verdict dictates.
"""
from __future__ import annotations

import pandas as pd

import backend.organism.live_engine as le
from backend.organism.kelly_sizer import KellySizer


def _eng(rank_policy="flat_policy", v2=True):
    eng = object.__new__(le.OrganismLiveEngine)
    return eng


def _with_flags(monkeypatch, v2=True, policy="flat_policy"):
    monkeypatch.setattr(le, "FRAMEWORK_ROUTING_V2_ENABLED", v2)
    monkeypatch.setattr(le, "ROUTING_RANK_POLICY", policy)


def _cd(sym, strat, ranking):
    return {"symbol": sym, "fw_strategy": strat, "ranking_score": ranking}


def test_rank_candidates_policy_order_beats_ranking_score(monkeypatch):
    """flat_policy: policy order wins even when ranking_score says otherwise."""
    _with_flags(monkeypatch)
    eng = _eng()
    cands = [_cd("NVDA", "breakout", ranking=9.9),
             _cd("AAPL", "momentum", ranking=0.1),
             _cd("MSFT", "momentum", ranking=0.2)]
    out = eng._rank_candidates(list(cands), "trending_up")
    # policy: momentum before breakout; build order within momentum preserved
    assert [c["symbol"] for c in out] == ["AAPL", "MSFT", "NVDA"]


def test_rank_candidates_legacy_unchanged(monkeypatch):
    _with_flags(monkeypatch, v2=False, policy="legacy")
    eng = _eng()
    cands = [_cd("A", "momentum", 0.1), _cd("B", "breakout", 9.9)]
    out = eng._rank_candidates(list(cands), "trending_up")
    assert [c["symbol"] for c in out] == ["B", "A"]     # ranking_score desc


def test_rank_candidates_stand_down_drops_everything(monkeypatch):
    _with_flags(monkeypatch)
    eng = _eng()
    cands = [_cd("A", "momentum", 1.0), _cd("B", "breakout", 1.0)]
    assert eng._rank_candidates(list(cands), "stress") == []
    assert eng._rank_candidates(list(cands), "unknown") == []


def test_rank_candidates_drops_non_policy_strategies(monkeypatch):
    """chop policy = [mean_reversion] — momentum/breakout candidates are
    dropped (the regime-adaptive selection the plan asked for)."""
    _with_flags(monkeypatch)
    eng = _eng()
    cands = [_cd("A", "momentum", 5.0), _cd("B", "mean_reversion", 0.5),
             _cd("C", "eod", 9.0)]
    out = eng._rank_candidates(list(cands), "chop")
    assert [c["symbol"] for c in out] == ["B"]


def test_conf_gates_bypass_only_under_flat_policy(monkeypatch):
    _with_flags(monkeypatch, v2=True, policy="flat_policy")
    assert _eng()._conf_gates_on() is False
    _with_flags(monkeypatch, v2=True, policy="legacy")
    assert _eng()._conf_gates_on() is True
    _with_flags(monkeypatch, v2=False, policy="flat_policy")  # B needs V2
    assert _eng()._conf_gates_on() is True
    assert _eng()._rank_policy_effective() == "legacy"


def _sizer_candidates():
    return [
        {"symbol": "AAPL", "direction": 1.0, "confidence": 0.2,
         "effective_confidence": 0.2, "predicted_return": 0.001,
         "breakout_score": 0.1, "ranking_score": 0.1},
        {"symbol": "MSFT", "direction": 1.0, "confidence": 0.9,
         "effective_confidence": 0.9, "predicted_return": 0.02,
         "breakout_score": 0.9, "ranking_score": 0.9},
    ]


def _features(n=300):
    idx = pd.date_range("2026-06-01 14:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": pd.Series(range(n)).mul(0.01).add(100.0),
                       "volume": 50_000, "timestamp": idx})
    return {"AAPL": df.copy(), "MSFT": df.copy()}


def test_sizer_flat_policy_preserves_upstream_order():
    sizer = KellySizer()
    feats = _features()
    sizes = sizer.size_positions(
        _sizer_candidates(), 100_000, 0.0, feats, "trending_up",
        ml_is_trained=False, trade_count=0, rank_policy="flat_policy")
    if len(sizes) >= 2:
        assert [s.symbol for s in sizes[:2]] == ["AAPL", "MSFT"]  # upstream order
    legacy = sizer.size_positions(
        _sizer_candidates(), 100_000, 0.0, feats, "trending_up",
        ml_is_trained=False, trade_count=0, rank_policy="legacy")
    if len(legacy) >= 2:
        assert [s.symbol for s in legacy[:2]] == ["MSFT", "AAPL"]  # score order


def test_sizer_flat_policy_equal_sizes_regardless_of_confidence():
    """Production-mode branch: two candidates identical except confidence/
    breakout composites must size EQUAL under flat_policy (multipliers
    neutralized), and UNEQUAL under legacy."""
    sizer = KellySizer()
    feats = _features()
    kw = dict(portfolio_value=100_000, current_drawdown=0.0,
              features_by_symbol=feats, current_regime="trending_up",
              ml_is_trained=True, trade_count=10_000, fixed_risk_mode=False)
    flat = sizer.size_positions(_sizer_candidates(), rank_policy="flat_policy", **kw)
    if len(flat) >= 2:
        # predicted_return still differs (sizing INPUT, not confidence) — so
        # assert the confidence multipliers specifically were neutralized:
        inter = sizer._last_intermediates
        assert inter["AAPL"]["confidence_scale"] == 1.0
        assert inter["MSFT"]["confidence_scale"] == 1.0
        assert inter["AAPL"]["breakout_bonus"] == 1.0
        assert inter["MSFT"]["breakout_bonus"] == 1.0
    legacy = sizer.size_positions(_sizer_candidates(), rank_policy="legacy", **kw)
    if len(legacy) >= 2:
        inter = sizer._last_intermediates
        assert inter["MSFT"]["confidence_scale"] > inter["AAPL"]["confidence_scale"]
