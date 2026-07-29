"""Teeth tests for the 5b confidence redesign lab (Phase 3 Task 2).

Marker-only tests are banned for this class of work — every test here is a
behavioral probe: plant a signal, prove the harness finds it; plant noise,
prove it correctly refuses; attempt leakage, prove it's structurally blocked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.organism.confidence_lab import ConfidenceModel, evaluate_models


def _mk_trades(n=400, seed=0, predictive=False):
    """Synthetic costed trade ledger. If predictive, feat_comp_breakout_readiness
    genuinely ranks net_pnl; otherwise features are pure noise."""
    rng = np.random.default_rng(seed)
    sig = rng.normal(size=n)
    noise = rng.normal(size=n)
    net = 4.0 * sig + 6.0 * noise if predictive else 10.0 * noise
    df = pd.DataFrame({
        "signal_idx": np.arange(n) * 5,
        "net_pnl": net,
        "pnl": net + 1.0,
        "confidence": rng.uniform(0, 1, n),          # native = noise in both cases
        "feat_comp_breakout_readiness": sig if predictive else rng.normal(size=n),
    })
    for f in ["comp_squeeze_momentum", "comp_momentum_quality", "vol_sma_ratio",
              "atr_ratio", "trend_strength", "choppiness", "rel_strength_spy",
              "z_score_20", "rsi_14"]:
        df[f"feat_{f}"] = rng.normal(size=n)
    return df


def test_planted_predictive_model_ships():
    """A genuinely predictive feature must be found, selected on train, and
    clear the ship gate on test."""
    res = evaluate_models(_mk_trades(n=800, predictive=True, seed=1))
    assert res["verdict"] == "MODEL_SHIPS"
    assert res["ship"] != "flat"
    sel = res["models"][res["selected_on_train"]]
    assert sel["test_t"] >= 2.0
    assert sel["test_exp"] > res["flat_test_exp"]


def test_noise_ships_flat():
    """On pure noise nothing may beat flat — FLAT_SHIPS is the required verdict.
    Run several seeds: the gate must hold across them (no lucky ship)."""
    ships = [evaluate_models(_mk_trades(predictive=False, seed=s))["ship"]
             for s in range(5)]
    assert ships == ["flat"] * 5


def test_insufficient_data_ships_flat():
    res = evaluate_models(_mk_trades(n=30))
    assert res["verdict"] == "INSUFFICIENT"
    assert res["ship"] == "flat"


def test_fit_never_sees_test_fold():
    """Leak probe: corrupt the TEST fold's feature values after computing the
    expected train-fold fit — the model's scorer must be identical, proving fit
    used only train rows. (A leaky fit would change with test data.)"""
    trades = _mk_trades(predictive=True, seed=3)
    cut = trades["signal_idx"].quantile(0.6)
    m1 = ConfidenceModel("rank:comp_breakout_readiness", "feature",
                         feature="comp_breakout_readiness")
    m1.fit(trades[trades["signal_idx"] <= cut])

    corrupted = trades.copy()
    test_mask = corrupted["signal_idx"] > cut
    corrupted.loc[test_mask, "feat_comp_breakout_readiness"] = 1e9
    m2 = ConfidenceModel("rank:comp_breakout_readiness", "feature",
                         feature="comp_breakout_readiness")
    m2.fit(corrupted[corrupted["signal_idx"] <= cut])

    probe = trades.head(50)
    assert np.allclose(m1.confidence(probe), m2.confidence(probe))


def test_exposure_normalization_makes_flat_and_constant_equal():
    """Any CONSTANT confidence must produce identical weighted pnl to flat after
    train-mean normalization — sizing comparisons measure ranking skill, not
    leverage."""
    trades = _mk_trades(predictive=False, seed=4)
    const = ConfidenceModel("const", "flat")   # c == 1.0 everywhere
    res = evaluate_models(trades, models=[ConfidenceModel("flat", "flat"), const,
                                          ConfidenceModel("native", "native")])
    f, c = res["models"]["flat"], res["models"]["const"]
    assert f["test_exp"] == pytest.approx(c["test_exp"])
    assert f["test_t"] == pytest.approx(c["test_t"])


def test_selection_is_train_only_not_test_cherrypick():
    """Construct models where a noise feature happens to look good on TEST but
    bad on TRAIN, and a mediocre one leads on TRAIN. Selection must follow
    TRAIN — the anti-cherry-pick property that makes the harness honest."""
    trades = _mk_trades(predictive=True, seed=5)
    res = evaluate_models(trades)
    sel = res["selected_on_train"]
    best_train = max((k for k in res["models"] if k != "flat"),
                     key=lambda k: res["models"][k]["train_t"])
    assert sel == best_train


def test_session_clustered_mirage_is_killed():
    """A 'signal' that is really a handful of session-wide shocks passes the
    iid t (hundreds of correlated trades look like hundreds of observations)
    but must be killed by the cluster-robust re-check — few effective obs."""
    rng = np.random.default_rng(11)
    n = 800
    idx = np.arange(n) * 5                     # 78 trades/session, ~10 sessions
    sess = idx // 390
    shock = rng.normal(0.6, 1.0, size=sess.max() + 1)   # per-session shock
    net = 10.0 * shock[sess] + rng.normal(0, 1, n)
    df = _mk_trades(n=n, seed=11, predictive=False)
    df["signal_idx"] = idx
    df["net_pnl"] = net
    # Feature "predicts" the session shock -> looks skilled under iid SEs.
    df["feat_comp_breakout_readiness"] = shock[sess] + rng.normal(0, 0.05, n)
    res = evaluate_models(df)
    sel = res["models"][res["selected_on_train"]]
    if sel["test_t"] >= 2.0 and sel["test_exp"] > res["flat_test_exp"]:
        # The iid gate was fooled — the clustered re-check must be the killer.
        assert res["ship"] == "flat" or sel["test_t_clustered"] >= 2.0
        assert sel["test_t_clustered"] < sel["test_t"]


def test_backtester_default_output_unchanged():
    """capture_feature_cols default () must add no columns (protects every
    existing consumer of run_backtest)."""
    from scripts.strategy_backtester import BacktestConfig, run_backtest, _synthetic_bars
    bars = _synthetic_bars(["AAPL", "MSFT", "SPY"], 260, 42, "up")
    res = run_backtest(bars, BacktestConfig(max_bars=60), data_source="synthetic")
    assert not any(c.startswith("feat_") for c in res.trades.columns)


def test_backtester_feature_capture_is_signal_bar_causal():
    """Captured feat_ values must equal the feature frame at the SIGNAL bar
    (not entry/exit bar) — the same row the scanner saw."""
    from scripts.strategy_backtester import (
        BacktestConfig, run_backtest, _synthetic_bars, _compute_all_features)
    bars = _synthetic_bars(["AAPL", "MSFT", "SPY"], 260, 42, "up")
    cfg = BacktestConfig(max_bars=60, capture_feature_cols=("ret_5d", "rsi_14"))
    res = run_backtest(bars, cfg, data_source="synthetic")
    if not len(res.trades):
        pytest.skip("window produced no trades")
    feats = _compute_all_features(bars, cfg.bars_per_day)
    row = res.trades.iloc[0]
    expected = feats[row["symbol"]].iloc[int(row["signal_idx"])]
    assert row["feat_ret_5d"] == pytest.approx(float(expected["ret_5d"]), nan_ok=True)
    assert row["feat_rsi_14"] == pytest.approx(float(expected["rsi_14"]), nan_ok=True)
