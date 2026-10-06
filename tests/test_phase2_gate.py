"""Phase 2 PRECONDITION — Tasks 2 & 3 acceptance.

THE gate (analog of Task 1's overfit-plant) is `test_null_simulation_controls_type_i`:
run the verdict gate under its ACTUAL monitoring schedule across many CLUSTERED
null books and confirm the empirical false-positive rate ≤ ~5%. A gate that
secretly inflates type-I passes every other test and fails this one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.organism.costing import DEFAULT_COST_BPS, apply_costs
from backend.organism.phase2_gate import (
    FAIL, INSUFFICIENT, LOOKS, MOMENTUM_TREND_REGIMES, PASS, Z_BOUNDARY, _STRATEGY_MAP,
    cluster_robust_t, evaluate_gate, gate_for_strategy, load_forward_corpus, null_simulation,
)


# ── THE TEETH: the schedule controls type-I under clustering ────────────
@pytest.mark.timeout(300)
def test_null_simulation_controls_type_i():
    for corr in (0.0, 0.5, 0.8):
        fpr = null_simulation(n_books=8000, session_corr=corr, seed=11)
        print(f"clustered-null FPR (session_corr={corr}): {fpr:.4f}")
        assert fpr <= 0.055, f"gate inflates type-I to {fpr:.4f} at corr={corr}"


def test_cluster_robust_se_deflates_t_under_clustering():
    # 10 sessions × 5 identical trades each (perfect within-session correlation):
    # cluster-robust t must be far below the naive iid t (which over-counts info).
    rng = np.random.default_rng(3)
    means = rng.normal(0.4, 1.0, 10)
    pnl = np.repeat(means, 5)
    sess = np.repeat(np.arange(10), 5)
    naive_t = pnl.mean() / (pnl.std(ddof=1) / np.sqrt(len(pnl)))
    robust_t = cluster_robust_t(pnl, sess)
    assert abs(robust_t) < abs(naive_t)                 # clustering correctly deflates


# ── State composition (Task 3) ─────────────────────────────────────────
def _sessions(n, per=5):
    return np.repeat(np.arange(n // per + 1), per)[:n]


def test_below_first_look_is_insufficient_with_no_statistic():
    r = evaluate_gate(np.zeros(40), _sessions(40))
    assert r["state"] == INSUFFICIENT and r["t"] is None   # no t exists yet


def test_no_peeking_statistic_is_frozen_between_looks():
    rng = np.random.default_rng(4)
    pnl = rng.normal(0, 1, 119)
    sess = _sessions(119)
    at60 = evaluate_gate(pnl[:60], sess[:60])
    at90 = evaluate_gate(pnl[:90], sess[:90])
    at119 = evaluate_gate(pnl[:119], sess[:119])
    # between looks: still INSUFFICIENT, and the statistic is the FROZEN [:60]
    # look-1 stat — NOT a fresh [:90]/[:119] readout (no optional stopping).
    assert at90["state"] == INSUFFICIENT and at119["state"] == INSUFFICIENT
    assert at60["t"] == at90["t"] == at119["t"]


def test_pass_when_boundary_cleared():
    rng = np.random.default_rng(5)
    pnl = rng.normal(0.8, 1.0, 130)                    # strong edge
    r = evaluate_gate(pnl, _sessions(130))
    assert r["state"] == PASS and r["t"] >= Z_BOUNDARY[r["look"] and LOOKS[r["look"] - 1]]


def test_fail_only_at_final_look():
    rng = np.random.default_rng(6)
    pnl = rng.normal(0.0, 1.0, 130)                    # no edge
    assert evaluate_gate(pnl[:100], _sessions(100))["state"] == INSUFFICIENT  # not yet
    assert evaluate_gate(pnl, _sessions(130))["state"] == FAIL                # final look


# ── Task 2: forward-only corpus + disjointness ─────────────────────────
def test_forward_corpus_rejects_pre_cutoff(tmp_path):
    cutoff = "2026-06-27T00:00:00+00:00"
    rows = pd.DataFrame({
        "closed_at": ["2026-06-26T10:00:00+00:00",   # pre-cutoff — REJECT
                      "2026-06-28T10:00:00+00:00",   # post — keep
                      "2026-06-29T10:00:00+00:00"],  # post — keep
        "entry_source": ["alpha", "alpha", "breakout"],
        "regime_at_entry": ["trending_up", "trending_up", "chop"],
        "pnl": [10.0, 5.0, -3.0], "entry_price": [100.0, 100.0, 50.0],
        "shares": [10, 10, 20],
    })
    p = tmp_path / "th.csv"
    rows.to_csv(p, index=False)
    corpus = load_forward_corpus(str(p), cutoff)
    assert len(corpus) == 2                                  # pre-cutoff dropped
    assert (pd.to_datetime(corpus["closed_at"], utc=True) > pd.Timestamp(cutoff)).all()
    assert set(corpus["strategy"]) == {"momentum", "breakout"}
    assert (corpus["net_pnl"] < corpus.assign(g=[10.0, -3.0])["g"]).all()  # costs applied


def test_empty_forward_corpus_is_valid(tmp_path):
    rows = pd.DataFrame({
        "closed_at": ["2026-06-01T10:00:00+00:00"], "entry_source": ["alpha"],
        "regime_at_entry": ["trending_up"], "pnl": [1.0], "entry_price": [100.0],
        "shares": [10],
    })
    p = tmp_path / "th.csv"
    rows.to_csv(p, index=False)
    corpus = load_forward_corpus(str(p), "2026-06-27T00:00:00+00:00")
    assert len(corpus) == 0                                  # empty is a valid state
    assert evaluate_gate(corpus.get("net_pnl", pd.Series([])).to_numpy(),
                         corpus.get("session", pd.Series([])).to_numpy())["state"] == INSUFFICIENT


# ── Audit 2026-10-05 C06-01 review: reconciliation artifacts never count ──
def test_forward_corpus_excludes_reconciliation_artifacts(tmp_path):
    # An external close keeps the lifetime's mapped entry_source (alpha,
    # breakout, ...); the source map alone let it into the verdict corpus.
    cutoff = "2026-10-01T00:00:00+00:00"
    rows = pd.DataFrame({
        "closed_at": [f"2026-10-06T15:0{m}:00+00:00" for m in range(6)],
        "entry_source": ["alpha", "alpha", "breakout", "alpha+breakout", "reconciliation_orphan", "alpha"],
        "regime_at_entry": ["trending_up"] * 6,
        "exit_reason": ["trailing_stop", "external_close", "external_close",
                        "reconciliation_adjustment", "stop_loss", "stop_loss"],
        "is_reconciliation_artifact": ["False", "True", "true", "1", "True", "False"],
        "price_source": ["db_position_fills", "external_close_db_fills",
                         "external_close_approximate_bar_close", "bar_close", "bar_close",
                         "db_position_fills"],
        "pnl": [12.0, -18.0, -126.0, 5.0, -50.0, -3.0],
        "entry_price": [100.0] * 6, "shares": [6] * 6,
    })
    p = tmp_path / "th.csv"
    rows.to_csv(p, index=False)
    corpus = load_forward_corpus(str(p), cutoff)
    assert corpus["strategy"].tolist() == ["momentum", "momentum"]
    assert corpus["net_pnl"].round(2).tolist() == [11.82, -3.18]
    assert gate_for_strategy(corpus, "momentum", MOMENTUM_TREND_REGIMES)["n"] == 2
    assert gate_for_strategy(corpus, "breakout")["n"] == 0
    # A ledger written without the flag column: exit reasons and the orphan
    # source still identify the artifacts.
    legacy = tmp_path / "legacy.csv"
    rows.drop(columns=["is_reconciliation_artifact"]).to_csv(legacy, index=False)
    assert load_forward_corpus(str(legacy), cutoff)["net_pnl"].round(2).tolist() == [11.82, -3.18]
    # The flag alone suffices (any exit reason), and only artifact rows drop out.
    flagged = rows.assign(exit_reason="stop_loss", is_reconciliation_artifact=[
        False, True, True, True, True, False])
    flagged.to_csv(p, index=False)
    assert len(load_forward_corpus(str(p), cutoff)) == 2
    # Every row an artifact: the empty corpus is still the valid empty state.
    rows.iloc[1:5].to_csv(p, index=False)
    empty = load_forward_corpus(str(p), cutoff)
    assert len(empty) == 0 and list(empty.columns) == ["strategy", "regime", "session", "net_pnl", "closed_at"]


def _pre_review_load_forward_corpus(path, frozen_at, cost_bps=DEFAULT_COST_BPS):
    """load_forward_corpus as it was before the artifact exclusion (proof reference)."""
    df = pd.read_csv(path)
    cutoff = pd.Timestamp(frozen_at)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    closed = pd.to_datetime(df["closed_at"], utc=True, errors="coerce")
    df = df[closed.notna() & (closed > cutoff)].copy()
    if len(df) == 0:
        return pd.DataFrame(columns=["strategy", "regime", "session", "net_pnl", "closed_at"])
    df["closed_at"] = closed[df.index]
    df["session"] = df["closed_at"].dt.date.astype(str)
    df["strategy"] = df["entry_source"].map(_STRATEGY_MAP)
    df = df[df["strategy"].notna()]
    df["net_pnl"] = apply_costs(df, cost_bps)["net_pnl"]
    return df[["strategy", "regime_at_entry", "session", "net_pnl", "closed_at"]].rename(
        columns={"regime_at_entry": "regime"}).sort_values("closed_at").reset_index(drop=True)


# Every FROZEN_AT committed to artifacts/phase2/param_freeze.json (git history).
_HISTORICAL_CUTOFFS = (
    "2026-06-27T02:33:43.330051+00:00", "2026-07-07T17:30:19.356337+00:00",
    "2026-07-07T18:01:16.307237+00:00", "2026-07-07T20:36:49.008305+00:00",
    "2026-09-21T06:54:41.006178+00:00", "2026-09-21T08:20:53.394292+00:00",
    "2026-09-21T10:10:39.684894+00:00", "2026-09-22T07:29:22.720890+00:00",
    "2026-09-22T08:49:11.247316+00:00", "2026-09-23T05:46:45.011846+00:00",
    "2026-09-23T15:29:47.287731+00:00", "2026-09-25T21:11:46.270521+00:00",
)


def _production_shaped_ledger():
    """Synthetic rows in the paper ledger's shape (its 29 columns). As in the
    September 28 brain snapshot, every reconciliation artifact closed before the
    first freeze cutoff: April 'reconciliation_adjustment' rows WITH mapped
    sources, one May orphan; legacy rows carry no entry_source."""
    columns = ["symbol", "direction", "entry_price", "exit_price", "entry_bar", "exit_bar",
               "shares", "pnl", "exit_reason", "predicted_return", "actual_return", "confidence",
               "correct_direction", "is_exploration", "is_reconciliation_artifact", "entry_source",
               "strategy_id", "regime_at_entry", "regime_at_exit", "mfe", "mae",
               "bars_held_at_exit", "time_in_trade_seconds", "closed_at",
               "predicted_return_signed", "ml_spoke", "entry_order_id", "price_source",
               "had_partial_exits"]
    spec = [  # closed_at, entry_source, exit_reason, artifact, regime, pnl, price_source
        ("2026-04-02T15:00:00+00:00", None, "stop_loss", False, "chop", -4.0, None),
        ("2026-04-08T13:29:47+00:00", "alpha", "reconciliation_adjustment", True, "chop", 183.28, None),
        ("2026-04-24T13:28:47+00:00", "alpha+breakout", "reconciliation_adjustment", True, "chop", -21.55, None),
        ("2026-04-30T14:13:56+00:00", "alpha", "reconciliation_adjustment", True, "high_vol", -54.95, None),
        ("2026-05-07T13:34:23+00:00", "reconciliation_orphan", "trailing_stop", True, "unknown", 2.15, None),
        ("2026-06-30T15:00:00+00:00", "alpha", "trailing_stop", False, "trending_up", 7.5, "db_fill"),
        ("2026-07-08T15:00:00+00:00", "alpha+breakout", "live_close", False, "high_vol", -2.0, None),
        ("2026-07-09T15:00:00+00:00", "breakout", "stop_loss", False, "chop", -6.0, "db_fill"),
        ("2026-09-21T09:00:00+00:00", "alpha", "failure_to_follow", False, "trending_up", 1.25, "db_position_fills"),
        ("2026-09-22T16:00:00+00:00", None, "max_holding_period", False, "chop", 0.5, None),
        ("2026-09-26T15:00:00+00:00", "alpha", "trailing_stop", False, "high_vol", 9.0, "db_position_fills"),
    ]
    rows = []
    for i, (closed, source, reason, artifact, regime, pnl, price_source) in enumerate(spec):
        row = dict.fromkeys(columns)
        row.update(symbol=f"S{i}", direction=1.0, entry_price=100.0, exit_price=100.0 + pnl / 6,
                   shares=6, pnl=pnl, exit_reason=reason, is_reconciliation_artifact=artifact,
                   entry_source=source, regime_at_entry=regime, closed_at=closed,
                   price_source=price_source)
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def test_no_historical_corpus_or_verdict_changes_on_the_ledger_shape(tmp_path):
    p = tmp_path / "trade_history.csv"
    ledger = _production_shaped_ledger()
    ledger.to_csv(p, index=False)
    for cutoff in _HISTORICAL_CUTOFFS:
        new, old = load_forward_corpus(str(p), cutoff), _pre_review_load_forward_corpus(str(p), cutoff)
        pd.testing.assert_frame_equal(new, old)
        for strategy, regimes in (("momentum", MOMENTUM_TREND_REGIMES), ("breakout", None)):
            assert gate_for_strategy(new, strategy, regimes) == gate_for_strategy(old, strategy, regimes)
    # The leak the review found: a post-cutoff external close with a mapped source.
    leak = ledger.iloc[[-1]].assign(closed_at="2026-10-06T15:10:00+00:00", exit_reason="external_close",
                                    is_reconciliation_artifact=True, pnl=-126.0,
                                    price_source="external_close_approximate_observed_bar_close")
    pd.concat([ledger, leak]).to_csv(p, index=False)
    cutoff = _HISTORICAL_CUTOFFS[-1]
    assert len(_pre_review_load_forward_corpus(str(p), cutoff)) == 2  # the artifact leaked in
    new = load_forward_corpus(str(p), cutoff)
    assert len(new) == 1 and new["net_pnl"].round(2).tolist() == [8.82]
