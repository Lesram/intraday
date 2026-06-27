"""Phase 1 step 8 — OOS, cost-disciplined backtester (checkpoint #2).

Proves the methodology is sound BY CONSTRUCTION: causal/OOS entries (no same-bar
or future fills), costs applied, the t>=2 acceptance gate, honest sizing label,
and determinism. (It validates the harness, not that any synthetic strategy is
profitable — edge is a data question, methodology is the gate here.)
"""
from __future__ import annotations

import pytest

from backend.organism.replay_simulator import make_features_dict
from scripts.strategy_backtester import BacktestConfig, run_backtest


@pytest.fixture(scope="module")
def result():
    bars = make_features_dict(["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"],
                              n=260, seed=42, trend="up")
    return run_backtest(bars, BacktestConfig(horizon=15, entry_lag=1))


@pytest.mark.timeout(300)
def test_entries_are_out_of_sample(result):
    """Every entry is strictly AFTER its signal bar, and exits after entries —
    no same-bar fill, no look-ahead. This is the core OOS guarantee."""
    tr = result.trades
    assert len(tr) > 0, "harness produced no trades on up-trend data"
    assert (tr["entry_idx"] == tr["signal_idx"] + 1).all()   # entry_lag=1
    assert (tr["entry_idx"] > tr["signal_idx"]).all()
    assert (tr["exit_idx"] > tr["entry_idx"]).all()
    assert (tr["exit_idx"] < result.n_bars).all()            # never reads past the data


@pytest.mark.timeout(300)
def test_costs_applied(result):
    """Costed: for any strategy with trades, net_pnl is strictly below gross."""
    any_costed = False
    for name, s in result.per_strategy.items():
        if s.get("n", 0) > 0:
            assert s["net_pnl"] < s["gross_pnl"], f"{name} costs not applied"
            assert s["cost_bps"] > 0
            any_costed = True
    assert any_costed


@pytest.mark.timeout(300)
def test_acceptance_gate_is_net_positive_and_tstat(result):
    """Rule B: accepted iff costed net expectancy>0 AND t_stat>=gate."""
    for s in result.per_strategy.values():
        if s.get("n", 0) == 0:
            continue
        expected = s["expectancy"] > 0 and s["t_stat"] >= s["t_stat_gate"]
        assert s["accepted"] is expected
        assert s["t_stat_gate"] == 2.0


@pytest.mark.timeout(300)
def test_sizing_label_is_honest(result):
    """The output must declare itself signal-significance, not live P&L."""
    assert "NOT live-P&L" in result.sizing_label
    assert "report" and "SIGNAL" in result.report()


@pytest.mark.timeout(300)
def test_only_eligible_strategies_trade_per_regime(result):
    """A strategy may only produce a trade in a regime it is eligible for —
    proves the selector's regime routing drives the backtest."""
    elig = {
        "momentum": {"trending_up", "high_vol"},
        "breakout": {"trending_up", "high_vol", "chop", "trending_down"},
        "mean_reversion": {"chop"},
    }
    for _, row in result.trades.iterrows():
        assert row["regime"] in elig[row["strategy"]], (
            f"{row['strategy']} traded in ineligible regime {row['regime']}")


@pytest.mark.timeout(300)
def test_deterministic():
    bars = make_features_dict(["AAPL", "MSFT", "SPY"], n=200, seed=11, trend="up")
    a = run_backtest(bars, BacktestConfig(horizon=10))
    b = run_backtest(bars, BacktestConfig(horizon=10))
    assert len(a.trades) == len(b.trades)
    assert round(a.trades["pnl"].sum(), 6) == round(b.trades["pnl"].sum(), 6)
