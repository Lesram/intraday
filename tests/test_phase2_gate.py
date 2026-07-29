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

from backend.organism.phase2_gate import (
    FAIL, INSUFFICIENT, LOOKS, PASS, Z_BOUNDARY,
    cluster_robust_t, evaluate_gate, load_forward_corpus, null_simulation,
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
