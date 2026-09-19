"""Audit 2026-06-09 finding 3.2 — background trainer same-holdout promotion.

The production promotion path (background trainer worker) previously compared
the new model's fresh-holdout score against the OLD model's metrics from a
DIFFERENT historical window, with the relative "beat by 0.05" path enabled —
allowing promotion against a deflated stale baseline.

Verifies:
1. acceptance_gate defaults to allow_relative=False (fail-closed).
2. The worker re-scores the old model on the new model's validation set
   (same-holdout) when old artifacts are available.
3. Without same-holdout artifacts, relative promotion stays disabled.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from backend.organism.continuous_learner import acceptance_gate
from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics


def _metrics(score_like: float, **kw) -> ModelMetrics:
    """Build ModelMetrics with a controllable composite score."""
    defaults = dict(
        generation=1,
        accuracy=score_like,
        precision=0.5,
        recall=0.5,
        f1=0.5,
        direction_accuracy=0.5,
        mean_pred_return=0.001,
        hit_rate=score_like,
        calibration_sample_count=100,
        calibration_monotonic=True,
        calibration_error=0.05,
        effective_mean_pred_return=0.001,
        candidate_calibration_sample_count=100,
        candidate_calibration_monotonic=True,
        candidate_calibration_error=0.05,
    )
    defaults.update(kw)
    return ModelMetrics(**defaults)


# ── 1. Fail-closed default ───────────────────────────────────────────


def test_acceptance_gate_default_is_absolute_bar():
    sig = inspect.signature(acceptance_gate)
    assert sig.parameters["allow_relative"].default is False, (
        "acceptance_gate must default to allow_relative=False (fail-closed): "
        "relative promotion is only sound after a same-holdout eval"
    )


def test_weak_challenger_not_promoted_against_stale_baseline_by_default():
    # Challenger: mediocre (score ~0.39 < absolute bar 0.40 via hit_rate 0.46).
    weak_new = _metrics(0.46)
    # Stale incumbent baseline: deflated (measured in a hostile regime).
    stale_old = _metrics(0.30)
    accepted, _ = acceptance_gate(weak_new, old_metrics=stale_old)
    assert accepted is False, (
        "default call must use the absolute bar, not relative-vs-stale"
    )
    # Same comparison with explicit relative path would have accepted —
    # proving the default is what protects us.
    accepted_rel, _ = acceptance_gate(
        weak_new, old_metrics=stale_old, allow_relative=True
    )
    assert accepted_rel is True


# ── 2. Worker performs same-holdout comparison ───────────────────────


def _make_features(n=400, seed=7):
    rng = np.random.default_rng(seed)
    from backend.organism.ml_features import FEATURE_COLUMNS

    df = pd.DataFrame(
        rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS
    )
    # close column required for label construction
    df["close"] = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    df["timestamp"] = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return {"TEST": df}


@pytest.mark.slow
def test_worker_same_holdout_eval_when_old_artifacts_present(monkeypatch):
    """End-to-end through the worker function: with old clf/reg pickles in
    signal_gen_state, the gate must receive a same-holdout old_metrics
    (fair_baseline path), not the stale metrics dict."""
    import pickle as _pickle

    from backend.organism import background_trainer as bt

    # Train a quick incumbent to produce artifacts.
    gen = MLSignalGenerator(train_window=200, n_estimators=5, max_depth=2)
    feats = _make_features()
    m = gen.train(feats)
    assert m is not None

    captured = {}

    from backend.organism import continuous_learner as cl

    real_gate = cl.acceptance_gate

    def spy_gate(new_metrics, old_metrics=None, **kw):
        captured["old_metrics"] = old_metrics
        captured["allow_relative"] = kw.get("allow_relative", "MISSING")
        return real_gate(new_metrics, old_metrics=old_metrics, **kw)

    # The worker does `from backend.organism.continuous_learner import
    # acceptance_gate` at call time, so patching the module attribute works.
    monkeypatch.setattr(cl, "acceptance_gate", spy_gate)

    signal_gen_state = {
        "train_window": 200,
        "xgb_params": {"n_estimators": 5, "max_depth": 2},
        "clf_pickle": _pickle.dumps(gen._clf),
        "reg_pickle": _pickle.dumps(gen._reg),
        "is_trained": True,
        "feature_cols": gen._feature_cols,
    }
    learner_state = {
        "old_model_metrics": {"accuracy": 0.99, "hit_rate": 0.99},  # absurd stale dict
    }
    features_pickle = {k: v.to_dict("list") for k, v in _make_features(seed=11).items()}

    result = bt._train_in_process(
        features_pickle, "chop", [], signal_gen_state, {}, learner_state
    )

    assert "error" not in result, result.get("error")
    # The gate must have been called with allow_relative explicitly set
    # (never left to default/missing) ...
    assert captured["allow_relative"] in (True, False)
    # ... and with a same-holdout ModelMetrics, not the absurd stale dict:
    om = captured["old_metrics"]
    assert om is not None
    assert not (om.accuracy == 0.99 and om.hit_rate == 0.99), (
        "gate received the stale historical dict — same-holdout eval "
        "did not run"
    )
    assert captured["allow_relative"] is True, (
        "fair_baseline must be True when same-holdout eval succeeded"
    )


def test_worker_disables_relative_path_without_old_artifacts():
    """Source guard: the worker must pass allow_relative=fair_baseline and
    fair_baseline must start False (only set True after a successful
    same-holdout eval)."""
    from backend.organism import background_trainer as bt

    src = inspect.getsource(bt._train_in_process)
    assert "allow_relative=fair_baseline" in src
    assert "fair_baseline = False" in src
    assert "evaluate_external_clf_reg" in src
