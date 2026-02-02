import numpy as np
import pandas as pd
import pytest

from backend.ml.drift import build_drift_baseline, compute_drift
from backend.ml.monitoring import decide_retrain


@pytest.mark.unit
def test_psi_zero_when_distributions_same():
    rng = np.random.RandomState(0)
    x = rng.normal(loc=0.0, scale=1.0, size=1000)
    X = pd.DataFrame({"f": x})

    baseline = build_drift_baseline(X, n_bins=10)
    drift = compute_drift(baseline, X)

    assert drift.psi_score >= 0.0
    assert drift.psi_score < 1e-6


@pytest.mark.unit
def test_psi_positive_when_shifted():
    rng = np.random.RandomState(0)
    x_ref = rng.normal(loc=0.0, scale=1.0, size=1000)
    x_cur = rng.normal(loc=2.0, scale=1.0, size=1000)

    baseline = build_drift_baseline(pd.DataFrame({"f": x_ref}), n_bins=10)
    drift = compute_drift(baseline, pd.DataFrame({"f": x_cur}))

    assert drift.psi_score > 0.05


@pytest.mark.unit
def test_decide_retrain_on_drift_or_performance_drop():
    d1 = decide_retrain(
        recent_total_return=0.01,
        reference_total_return=0.05,
        psi_score=0.01,
        min_return_drop=0.02,
        psi_threshold=0.15,
    )
    assert d1.should_retrain is True

    d2 = decide_retrain(
        recent_total_return=0.06,
        reference_total_return=0.05,
        psi_score=0.20,
        min_return_drop=0.02,
        psi_threshold=0.15,
    )
    assert d2.should_retrain is True

    d3 = decide_retrain(
        recent_total_return=0.06,
        reference_total_return=0.05,
        psi_score=0.01,
        min_return_drop=0.02,
        psi_threshold=0.15,
    )
    assert d3.should_retrain is False
