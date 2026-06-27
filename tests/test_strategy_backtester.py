"""Phase 1 step 8 — causal, cost-disciplined backtester (checkpoint #2).

Proves the methodology by construction: causal entries (no same-bar/future fill),
costs applied, the t>=2 acceptance gate ARITHMETIC, honest sizing + OOS labels,
and — critically — that SYNTHETIC data is a smoke test that NEVER renders a
verdict (momentum wins on a drifting random walk by construction; that is not
edge). Real-bar coverage uses the cached corpus.
"""
from __future__ import annotations

import os

import pytest

from backend.organism.replay_simulator import make_features_dict
from scripts.strategy_backtester import (
    BacktestConfig, load_bars_pickle, run_backtest,
)

_CORPUS = "artifacts/broad_corpus_v2/bars.pkl"
_HAVE_CORPUS = os.path.exists(_CORPUS)


@pytest.fixture(scope="module")
def smoke():
    bars = make_features_dict(["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"],
                              n=260, seed=42, trend="up")
    return run_backtest(bars, BacktestConfig(horizon=15), data_source="synthetic")


@pytest.fixture(scope="module")
def real():
    if not _HAVE_CORPUS:
        pytest.skip("no cached real-bar corpus")
    allbars = load_bars_pickle(_CORPUS)
    syms = [s for s in ["AAPL", "MSFT", "NVDA", "SPY"] if s in allbars]
    bars = {s: allbars[s].iloc[:1600].reset_index(drop=True) for s in syms}
    return run_backtest(bars, BacktestConfig(horizon=15, lookback_window=400),
                        data_source="real")


# ── synthetic is smoke only ────────────────────────────────────────────
@pytest.mark.timeout(300)
def test_synthetic_is_smoke_and_never_accepts(smoke):
    assert smoke.is_smoke
    assert "SMOKE TEST" in smoke.report()
    # however strong the synthetic t-stat, it must NEVER produce an ACCEPT verdict
    for s in smoke.per_strategy.values():
        assert s["accepted"] is False
    assert "no verdict on synthetic" in smoke.report().lower()


@pytest.mark.timeout(300)
def test_synthetic_still_causal(smoke):
    tr = smoke.trades
    assert len(tr) > 0
    assert (tr["entry_idx"] == tr["signal_idx"] + 1).all()   # entry strictly after signal
    assert (tr["exit_idx"] > tr["entry_idx"]).all()
    assert (tr["exit_idx"] < smoke.n_bars).all()


# ── honest labels ──────────────────────────────────────────────────────
def test_labels_are_honest():
    bars = make_features_dict(["AAPL", "SPY"], n=120, seed=1, trend="up")
    r = run_backtest(bars, BacktestConfig(horizon=10), data_source="synthetic")
    assert "NOT live-P&L" in r.sizing_label
    assert "NOT held-out OOS" in r.oos_caveat
    assert "causal" in r.report().lower()


# ── real bars: causality, costs, gate arithmetic ───────────────────────
@pytest.mark.timeout(600)
def test_real_bars_causal_and_costed(real):
    tr = real.trades
    assert len(tr) > 0, "real corpus produced no trades in the sampled window"
    assert (tr["entry_idx"] == tr["signal_idx"] + 1).all()
    assert (tr["exit_idx"] < real.n_bars).all()
    assert real.data_source == "real"
    costed = [s for s in real.per_strategy.values() if s.get("n", 0) > 0]
    assert costed and all(s["net_pnl"] < s["gross_pnl"] for s in costed)  # costs bite


@pytest.mark.timeout(600)
def test_acceptance_gate_arithmetic(real):
    """On REAL bars, accepted iff net expectancy>0 AND t_stat>=gate."""
    for s in real.per_strategy.values():
        if s.get("n", 0) == 0:
            continue
        assert s["accepted"] is (s["expectancy"] > 0 and s["t_stat"] >= s["t_stat_gate"])
        assert s["t_stat_gate"] == 2.0


@pytest.mark.timeout(600)
def test_only_eligible_strategies_trade_per_regime(real):
    elig = {
        "momentum": {"trending_up", "high_vol"},
        "breakout": {"trending_up", "high_vol", "chop", "trending_down"},
        "mean_reversion": {"chop"},
    }
    for _, row in real.trades.iterrows():
        assert row["regime"] in elig[row["strategy"]]


@pytest.mark.timeout(300)
def test_deterministic():
    bars = make_features_dict(["AAPL", "MSFT", "SPY"], n=200, seed=11, trend="up")
    a = run_backtest(bars, BacktestConfig(horizon=10), data_source="synthetic")
    b = run_backtest(bars, BacktestConfig(horizon=10), data_source="synthetic")
    assert len(a.trades) == len(b.trades)
    assert round(a.trades["pnl"].sum(), 6) == round(b.trades["pnl"].sum(), 6)
