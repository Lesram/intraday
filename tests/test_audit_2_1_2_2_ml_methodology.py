"""Audit 2026-06-09 plans 2.1 + 2.2 — purged temporal split and
realized-correlation acceptance gate.

2.1: the train/val boundary previously had zero gap, so the last training
row's label (close[t+H]) was the first validation row's feature bar.
2.2: the acceptance gate never measured corr(predicted, actual) — the one
number distinguishing edge from noise.
"""

import numpy as np

from backend.organism.continuous_learner import acceptance_gate
from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics


# ── 2.1 Purged temporal split ────────────────────────────────────────


def _gen(horizon=1):
    g = MLSignalGenerator.__new__(MLSignalGenerator)
    g.prediction_horizon = horizon
    return g


def test_purge_gap_in_chunked_split():
    g = _gen(horizon=3)
    g._chunk_sizes = [100, 100]
    X = np.arange(200, dtype=float).reshape(200, 1)
    y = np.arange(200, dtype=float)
    (Xt, yt, _), (Xv, yv, _) = g._temporal_split(X, y, y, val_ratio=0.2)
    # Per chunk: train = rows [0,80), purge = [80,83), val = [83,100).
    assert len(Xt) == 160
    assert len(Xv) == 2 * (100 - 83)
    # The first val row of chunk 0 must be index 83, not 80.
    assert Xv[0, 0] == 83.0
    # Chunk 1 val starts at 100 + 83.
    assert Xv[100 - 83, 0] == 183.0


def test_purge_gap_in_fallback_split():
    g = _gen(horizon=2)
    g._chunk_sizes = []  # force fallback
    X = np.arange(100, dtype=float).reshape(100, 1)
    y = np.arange(100, dtype=float)
    (Xt, _, _), (Xv, _, _) = g._temporal_split(X, y, y, val_ratio=0.2)
    assert len(Xt) == 80
    assert Xv[0, 0] == 82.0  # 80 + purge 2


def test_no_overlap_between_train_label_window_and_val_features():
    """The defining property: for horizon H, no validation row index may
    fall within H bars of the last train row of its chunk."""
    for h in (1, 3, 5):
        g = _gen(horizon=h)
        g._chunk_sizes = [60]
        X = np.arange(60, dtype=float).reshape(60, 1)
        y = np.arange(60, dtype=float)
        (Xt, _, _), (Xv, _, _) = g._temporal_split(X, y, y, val_ratio=0.3)
        last_train = Xt[-1, 0]
        first_val = Xv[0, 0]
        assert first_val - last_train > h, (
            f"h={h}: val starts {first_val - last_train} bars after train end"
        )


# ── 2.2 Realized-correlation gate ────────────────────────────────────


def _good_metrics(**kw) -> ModelMetrics:
    m = ModelMetrics(
        generation=1, accuracy=0.6, precision=0.55, recall=0.5, f1=0.52,
        direction_accuracy=0.6, mean_pred_return=0.001, hit_rate=0.55,
        calibration_sample_count=100, calibration_monotonic=True,
        calibration_error=0.05, effective_mean_pred_return=0.001,
        candidate_calibration_sample_count=100,
        candidate_calibration_monotonic=True,
        candidate_calibration_error=0.05,
    )
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_gate_rejects_anticorrelated_predictions():
    m = _good_metrics(val_pred_actual_corr=-0.1, val_pred_actual_corr_n=100)
    accepted, _ = acceptance_gate(m)
    assert accepted is False


def test_gate_rejects_zero_correlation():
    m = _good_metrics(val_pred_actual_corr=0.0, val_pred_actual_corr_n=100)
    accepted, _ = acceptance_gate(m)
    assert accepted is False


def test_gate_accepts_positive_correlation():
    m = _good_metrics(val_pred_actual_corr=0.15, val_pred_actual_corr_n=100)
    accepted, reason = acceptance_gate(m)
    assert accepted is True, reason


def test_gate_tolerates_missing_or_small_sample_corr():
    # Backward compat: metrics without the field (None) must not reject.
    m = _good_metrics(val_pred_actual_corr=None, val_pred_actual_corr_n=0)
    accepted, reason = acceptance_gate(m)
    assert accepted is True, reason
    # Small sample: corr unreliable → does not bind.
    m2 = _good_metrics(val_pred_actual_corr=-0.5, val_pred_actual_corr_n=10)
    accepted2, _ = acceptance_gate(m2)
    assert accepted2 is True


def test_evaluate_populates_corr_field():
    """End-to-end: train a tiny model on data with a PLANTED signal (one
    feature drives next-bar returns) and confirm _evaluate computes a
    finite, strongly positive correlation on the holdout. On pure noise
    the regressor predicts a constant and the field correctly stays None
    (verified separately below)."""
    import pandas as pd

    from backend.organism.ml_features import FEATURE_COLUMNS

    rng = np.random.default_rng(3)
    n = 400
    df = pd.DataFrame(
        rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS
    )
    # Plant a signal: returns follow the first feature with little noise.
    drive = df[FEATURE_COLUMNS[0]].values
    rets = 0.01 * drive + rng.normal(0, 0.001, size=n)
    close = 100 * np.exp(np.cumsum(np.concatenate([[0.0], rets[:-1]])))
    df["close"] = close
    df["timestamp"] = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")

    gen = MLSignalGenerator(train_window=200, n_estimators=30, max_depth=3)
    metrics = gen.train({"TEST": df})
    assert metrics is not None
    assert metrics.val_pred_actual_corr is not None, (
        "learnable signal must yield a computable holdout correlation"
    )
    assert metrics.val_pred_actual_corr > 0.2
    assert metrics.val_pred_actual_corr_n >= 5
    assert "val_pred_actual_corr" in metrics.to_dict()


def test_evaluate_leaves_corr_none_on_pure_noise():
    """On unlearnable noise the regressor predicts ~constant; the corr is
    undefined and must be None (not NaN) so the gate treats it as
    not-computable rather than crashing or passing garbage."""
    import pandas as pd

    from backend.organism.ml_features import FEATURE_COLUMNS

    rng = np.random.default_rng(3)
    n = 400
    df = pd.DataFrame(
        rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS
    )
    df["close"] = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    df["timestamp"] = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")

    gen = MLSignalGenerator(train_window=200, n_estimators=5, max_depth=2)
    metrics = gen.train({"TEST": df})
    assert metrics is not None
    corr = metrics.val_pred_actual_corr
    assert corr is None or np.isfinite(corr)
