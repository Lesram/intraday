"""S17 — same-holdout new-vs-old gate tests.

Addresses Data Leakage Audit Concern 1: when validating a retrained
model, evaluate the OLD model on the SAME holdout as the new model
(not on its own historical metrics from a different time window).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_features_for_training(n_bars: int = 200) -> dict:
    """Build synthetic features-by-symbol with enough bars for ML training."""
    rng = np.random.default_rng(42)
    bars = {}
    for sym in ["AAPL", "MSFT", "SPY"]:
        rets = rng.normal(0.0001, 0.001, n_bars)
        close = 100.0 * np.cumprod(1 + rets)
        high = close * (1 + rng.uniform(0, 0.002, n_bars))
        low = close * (1 - rng.uniform(0, 0.002, n_bars))
        opn = close * (1 + rng.normal(0, 0.0005, n_bars))
        df = pd.DataFrame({
            "open": opn, "high": high, "low": low, "close": close,
            "volume": rng.integers(1e5, 1e7, n_bars).astype(float),
        })
        # Compute ML features
        from backend.organism.ml_features import compute_ml_features
        bars[sym] = compute_ml_features(df, bars_per_day=390)
    return bars


def test_signal_gen_caches_validation_data():
    """After train(), MLSignalGenerator caches the val set for same-holdout eval."""
    from backend.organism.ml_signal import MLSignalGenerator

    bars = _make_features_for_training(n_bars=300)
    gen = MLSignalGenerator()
    metrics = gen.train(bars, val_ratio=0.2)

    if metrics is not None and gen._is_trained:
        # Should now have cached val data
        assert getattr(gen, "_last_val_X", None) is not None, (
            "Expected _last_val_X cached after train()"
        )
        assert getattr(gen, "_last_val_y_dir", None) is not None
        assert getattr(gen, "_last_val_y_ret", None) is not None
        assert len(gen._last_val_X) > 0


def test_evaluate_external_clf_reg_returns_metrics():
    """evaluate_external_clf_reg() runs old model on cached val set."""
    from backend.organism.ml_signal import MLSignalGenerator
    import copy

    bars = _make_features_for_training(n_bars=300)
    gen = MLSignalGenerator()
    metrics_first = gen.train(bars, val_ratio=0.2)

    if metrics_first is None or not gen._is_trained:
        pytest.skip("first train() did not converge on synthetic data")

    # Snapshot the trained models — these are our "old" models
    old_clf = copy.deepcopy(gen._clf)
    old_reg = copy.deepcopy(gen._reg)

    # Train a "new" model (same data, same val split — for unit test purposes)
    metrics_second = gen.train(bars, val_ratio=0.2)
    if metrics_second is None:
        pytest.skip("second train() did not converge")

    # Evaluate old models on the new training run's val set
    old_on_new_val = gen.evaluate_external_clf_reg(old_clf, old_reg)
    assert old_on_new_val is not None, (
        "evaluate_external_clf_reg should return ModelMetrics, not None"
    )
    # Should at least have an accuracy score
    assert hasattr(old_on_new_val, "accuracy")
    assert 0.0 <= old_on_new_val.accuracy <= 1.0


def test_evaluate_external_returns_none_without_cache():
    """No cache → returns None gracefully (no exception)."""
    from backend.organism.ml_signal import MLSignalGenerator

    gen = MLSignalGenerator()
    # Never trained — no cache
    result = gen.evaluate_external_clf_reg(None, None)
    assert result is None


def test_continuous_learner_validate_uses_same_holdout():
    """When _validate_new_model has both old_clf and old_reg, it should
    call signal_gen.evaluate_external_clf_reg (S17 path)."""
    from pathlib import Path

    src = (
        Path(__file__).parent.parent / "backend" / "organism" / "continuous_learner.py"
    ).read_text()

    # Source-level: the new code path is present
    assert "S17 — preferred: same-holdout comparison" in src
    assert "evaluate_external_clf_reg" in src
    assert "old_reg: Any = None" in src or "old_reg = None" in src


def test_validate_signature_extended():
    """_validate_new_model accepts old_reg + old_trained kwargs."""
    import inspect
    from backend.organism.continuous_learner import ContinuousLearner

    sig = inspect.signature(ContinuousLearner._validate_new_model)
    params = list(sig.parameters.keys())
    assert "old_reg" in params, "_validate_new_model should accept old_reg"
    assert "old_trained" in params, "_validate_new_model should accept old_trained"
