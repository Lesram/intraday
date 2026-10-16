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


# ── Audit O2-02: 'alpha+breakout' attribution while ML is isolated ──────
# Engine facts behind the rule (pinned against the source below): while ML is
# isolated every main-book row records ml_spoke False; an alpha candidate records
# predicted_return 0.01 exactly and a pure breakout 0.005 + 0.015 * composite with
# composite in [0.55, 1.0], both labelled 'alpha+breakout' once breakout_score is
# >= 0.4. The ledger CSV rounds predicted_return to 6 decimals.
_O2_CUTOFF = "2026-10-01T00:00:00+00:00"


def _isolated_breakout_return(composite):
    return round(0.005 + 0.015 * composite, 6)


def _o2_stamp(i, per_session=5):
    """closed_at of trade i, `per_session` trades per session (cluster)."""
    day = pd.Timestamp("2026-10-05T14:00:00+00:00") + pd.Timedelta(days=i // per_session)
    return (day + pd.Timedelta(minutes=i % per_session)).isoformat()


def _o2_ledger(tmp_path, rows, name="o2.csv"):
    """Synthetic ledger rows (closed_at, entry_source, regime_at_entry,
    predicted_return, ml_spoke, pnl) under the paper ledger's column names."""
    frame = pd.DataFrame(rows, columns=["closed_at", "entry_source", "regime_at_entry",
                                        "predicted_return", "ml_spoke", "pnl"])
    frame["entry_price"], frame["shares"] = 100.0, 6
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_isolation_signature_splits_alpha_breakout_between_momentum_and_breakout(tmp_path):
    from backend.organism import phase2_gate as p2
    rows = [
        (_o2_stamp(0), "alpha", "trending_up", 0.01, False, 4.0),
        (_o2_stamp(1), "alpha+breakout", "trending_up", 0.01, False, 3.0),       # alpha
        (_o2_stamp(2), "alpha+breakout", "trending_up", _isolated_breakout_return(0.55), False, -2.0),
        (_o2_stamp(3), "alpha+breakout", "high_vol", _isolated_breakout_return(0.66), False, -1.0),
        (_o2_stamp(4), "alpha+breakout", "low_vol", _isolated_breakout_return(1.0), False, 1.0),
        (_o2_stamp(5), "breakout", "chop", 0.01, False, 2.0),                    # label kept
        (_o2_stamp(6), "orb", "chop", 0.01, False, 1.0),
        (_o2_stamp(7), "mr", "chop", 0.01, False, 1.0),
        (_o2_stamp(8), "reconciliation_orphan", "chop", 0.01, False, 9.0),       # unmapped
    ]
    corpus = load_forward_corpus(str(_o2_ledger(tmp_path, rows)), _O2_CUTOFF)
    assert corpus["strategy"].tolist() == ["momentum", "momentum", "breakout", "breakout",
                                           "breakout", "breakout", "orb", "mean_reversion"]
    assert p2.attribution_counts(corpus) == {"alpha": 2, "pure_breakout": 4, "ambiguous": 0,
                                             "orb": 1, "mean_reversion": 1}
    momentum = p2.gate_for_strategy(corpus, "momentum", p2.MOMENTUM_TREND_REGIMES)
    assert momentum["state"] == INSUFFICIENT and momentum["n"] == 2
    assert momentum["n_by_source"] == {"alpha": 2, "pure_breakout": 0, "ambiguous": 0}
    breakout = p2.gate_for_strategy(corpus, "breakout")
    assert breakout["state"] == INSUFFICIENT and breakout["n"] == 4
    assert breakout["n_by_source"] == {"alpha": 0, "pure_breakout": 4, "ambiguous": 0}
    assert p2.gate_for_strategy(corpus, "orb")["n_by_source"] == {
        "alpha": 0, "pure_breakout": 0, "ambiguous": 0, "orb": 1}
    assert momentum["attribution_rule"] == breakout["attribution_rule"] == p2.ATTRIBUTION_RULE


@pytest.mark.parametrize("predicted_return,ml_spoke", [
    (0.01, True),                   # ML produced the value: not an isolation signature
    (0.0142, True),
    (0.01, ""),                     # ml_spoke not recorded
    (0.01325 - 1e-6, False),        # below the band (pure breakouts need composite >= 0.55)
    (0.0201, False),                # above the band (composite cannot exceed 1.0)
    (0.010001, False),              # not 0.01 at the ledger's 6-decimal precision
    (0.012, False),                 # between the two signatures
    (0.005, False),                 # sizer floor for an ML value of ~0, not an isolation value
    (None, False),                  # predicted_return missing
])
def test_alpha_breakout_rows_outside_the_isolation_signature_are_ambiguous(
    tmp_path, predicted_return, ml_spoke,
):
    from backend.organism import phase2_gate as p2
    rows = [(_o2_stamp(0), "alpha+breakout", "trending_up", predicted_return, ml_spoke, 1.0),
            (_o2_stamp(1), "alpha", "trending_up", predicted_return, ml_spoke, 1.0),
            (_o2_stamp(2), "breakout", "chop", predicted_return, ml_spoke, 1.0)]
    corpus = load_forward_corpus(str(_o2_ledger(tmp_path, rows)), _O2_CUTOFF)
    # Only the 'alpha+breakout' label is re-attributed; 'alpha' and 'breakout' keep theirs.
    assert corpus["strategy"].tolist() == [p2.AMBIGUOUS, "momentum", "breakout"]
    assert p2.attribution_counts(corpus)["ambiguous"] == 1


def test_ledger_without_ml_spoke_or_predicted_return_cannot_split(tmp_path):
    from backend.organism import phase2_gate as p2
    rows = [(_o2_stamp(0), "alpha+breakout", "trending_up", 0.01, False, 1.0),
            (_o2_stamp(1), "alpha+breakout", "trending_up", 0.0155, False, 1.0)]
    path = _o2_ledger(tmp_path, rows)
    assert load_forward_corpus(str(path), _O2_CUTOFF)["strategy"].tolist() == ["momentum", "breakout"]
    full = pd.read_csv(path)
    for column in ("ml_spoke", "predicted_return"):
        full.drop(columns=[column]).to_csv(path, index=False)
        assert load_forward_corpus(str(path), _O2_CUTOFF)["strategy"].tolist() == [p2.AMBIGUOUS] * 2


@pytest.mark.parametrize("edge,state_without_ambiguity", [(0.8, PASS), (-0.8, FAIL)])
def test_ambiguous_trade_withholds_momentum_and_breakout_verdicts(
    tmp_path, edge, state_without_ambiguity,
):
    from backend.organism import phase2_gate as p2
    n = 130
    pnl = np.random.default_rng(7).normal(edge, 1.0, n)
    rows = [(_o2_stamp(i), "alpha+breakout", "trending_up", 0.01, False, float(p))
            for i, p in enumerate(pnl)]
    corpus = load_forward_corpus(str(_o2_ledger(tmp_path, rows)), _O2_CUTOFF)
    clean = p2.gate_for_strategy(corpus, "momentum", p2.MOMENTUM_TREND_REGIMES)
    assert clean["state"] == state_without_ambiguity and clean["n"] == n
    # One later 'alpha+breakout' trade that ML spoke on cannot be split.
    rows.append((_o2_stamp(n), "alpha+breakout", "high_vol", 0.0142, True, 0.5))
    corpus = load_forward_corpus(str(_o2_ledger(tmp_path, rows)), _O2_CUTOFF)
    momentum = p2.gate_for_strategy(corpus, "momentum", p2.MOMENTUM_TREND_REGIMES)
    assert momentum["state"] == p2.AMBIGUOUS_ATTRIBUTION
    assert momentum["t"] is None and momentum["look"] is None and momentum["n"] == n
    assert momentum["n_by_source"] == {"alpha": n, "pure_breakout": 0, "ambiguous": 1}
    assert "1 'alpha+breakout' trade(s)" in momentum["note"]
    breakout = p2.gate_for_strategy(corpus, "breakout")
    assert breakout["state"] == p2.AMBIGUOUS_ATTRIBUTION and breakout["n"] == 0
    assert breakout["n_by_source"] == {"alpha": 0, "pure_breakout": 0, "ambiguous": 1}
    for name in ("orb", "mean_reversion"):
        assert p2.gate_for_strategy(corpus, name)["state"] == INSUFFICIENT


def test_ambiguous_trade_outside_the_trend_slice_withholds_only_breakout(tmp_path):
    from backend.organism import phase2_gate as p2
    pnl = np.random.default_rng(8).normal(0.8, 1.0, 70)
    rows = [(_o2_stamp(i), "alpha", "trending_up", 0.01, False, float(p)) for i, p in enumerate(pnl)]
    rows.append((_o2_stamp(70), "alpha+breakout", "chop", 0.012, False, -3.0))
    corpus = load_forward_corpus(str(_o2_ledger(tmp_path, rows)), _O2_CUTOFF)
    momentum = p2.gate_for_strategy(corpus, "momentum", p2.MOMENTUM_TREND_REGIMES)
    # Alpha or pure breakout, a chop trade is outside the momentum trend slice.
    assert momentum["state"] == PASS
    assert momentum["n_by_source"] == {"alpha": 70, "pure_breakout": 0, "ambiguous": 0}
    breakout = p2.gate_for_strategy(corpus, "breakout")
    assert breakout["state"] == p2.AMBIGUOUS_ATTRIBUTION
    assert breakout["n_by_source"] == {"alpha": 0, "pure_breakout": 0, "ambiguous": 1}


def test_label_map_shape_moves_pure_breakouts_from_momentum_to_breakout(tmp_path):
    """Synthetic rows with the structure the O2-02 verification found in the
    September 2026 paper ledger (ML isolated): 4 alpha-signature trades and 10
    pure-breakout-signature trades, 12 of the 14 labelled 'alpha+breakout'. The
    label map put 11 in the momentum trend slice (7 pure breakouts), 0 in breakout."""
    from backend.organism import phase2_gate as p2
    alpha = [("alpha", "trending_up"), ("alpha", "trending_up"),
             ("alpha+breakout", "trending_up"), ("alpha+breakout", "trending_up")]
    composites = (0.56, 0.58, 0.6, 0.62, 0.65, 0.7, 0.75, 0.8, 0.9, 0.95)
    regimes = ["trending_up"] * 7 + ["low_vol"] * 3
    rows = [(_o2_stamp(i), label, regime, 0.01, False, 1.0) for i, (label, regime) in enumerate(alpha)]
    rows += [(_o2_stamp(4 + i), "alpha+breakout", regime, _isolated_breakout_return(c), False, -1.0)
             for i, (c, regime) in enumerate(zip(composites, regimes))]
    path = _o2_ledger(tmp_path, rows)
    raw = pd.read_csv(path)
    by_label = raw["entry_source"].map(p2._STRATEGY_MAP)
    trend = raw["regime_at_entry"].isin(p2.MOMENTUM_TREND_REGIMES)
    assert ((by_label == "momentum") & trend).sum() == 11 and (by_label == "breakout").sum() == 0
    corpus = load_forward_corpus(str(path), _O2_CUTOFF)
    momentum = p2.gate_for_strategy(corpus, "momentum", p2.MOMENTUM_TREND_REGIMES)
    breakout = p2.gate_for_strategy(corpus, "breakout")
    assert momentum["n_by_source"] == {"alpha": 4, "pure_breakout": 0, "ambiguous": 0}
    assert breakout["n_by_source"] == {"alpha": 0, "pure_breakout": 10, "ambiguous": 0}
    assert (corpus.loc[corpus["strategy"] == "momentum", "net_pnl"] > 0).all()


def test_isolation_signatures_match_the_engine_source():
    """attribute_trades relies on these engine expressions. Changing any of them is a
    frozen-surface change (or edits the unhashed label helper) and must revisit the
    rule. A value outside both signatures only makes rows ambiguous (fail closed)."""
    from pathlib import Path
    from backend.organism import phase2_gate as p2
    organism = Path(__file__).resolve().parents[1] / "backend" / "organism"
    engine = (organism / "live_engine.py").read_text()
    for expression in (
        "c.ml_signal.predicted_return if c.ml_signal else 0.01",   # alpha value without ML
        "pred_ret = 0.005 + 0.015 * bs.composite_score",           # pure-breakout heuristic
        "if bs.composite_score < 0.55:",                           # pure-breakout entry floor
        '"ml_spoke": _bo_ret_source == "calibrated_breakout"',      # breakout ml_spoke
        "breakout_score >= 0.55 and predicted_return < 0.003",     # the only 'breakout' label
        "predicted_return = abs(sz.predicted_return) if sz.predicted_return else 0.01",  # recorded
    ):
        assert expression in engine, expression
    scanner = (organism / "alpha_scanner.py").read_text()
    assert "None if (learning_mode or derive_direction_from_observables) else ml_sig" in scanner
    assert p2.ALPHA_ISOLATED_PREDICTED_RETURN == 0.01
    assert p2.PURE_BREAKOUT_SIGNATURE == pytest.approx((0.01325, 0.0200))
    low = p2.PURE_BREAKOUT_SIGNATURE[0] - p2.SIGNATURE_TOLERANCE
    assert low > p2.ALPHA_ISOLATED_PREDICTED_RETURN + p2.SIGNATURE_TOLERANCE  # no overlap
    assert p2.SIGNATURE_TOLERANCE < 0.5e-6        # finer than the CSV's 6-decimal rounding


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
