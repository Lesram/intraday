"""Scalar division and actual composite computation, using synthetic bars only."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal
import pytest

from backend.organism import composite_indicators as indicators
from backend.organism.ml_features import compute_ml_features


def _bars(kind: str, rows: int = 120) -> pd.DataFrame:
    step = np.arange(rows, dtype=float)
    if kind == "falling":
        close = 150 - step * 0.08 + np.sin(step / 4) * 0.2
    elif kind == "oscillating":
        close = 100 + np.sin(step / 4) * 2 + np.sin(step / 11) * 0.4
    elif kind == "flat":
        close = np.full(rows, 100.0)
    else:
        close = 100 + step * 0.08 + np.sin(step / 4) * 0.2
    spread = 0.0 if kind == "flat" else 0.25
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-23T13:30:00Z", periods=rows, freq="min"),
        "open": close - spread / 4, "high": close + spread,
        "low": close - spread, "close": close,
        "volume": np.zeros(rows) if kind in {"flat", "zero_volume"}
        else 10000 + step * 31 + (step % 7) * 97,
    })
    frame.index.name = "causal_bar_index"
    frame.attrs["input_kind"] = kind
    return frame


def _original_series_only_division(a, b):
    """Pre-repair arithmetic, retained only to compare unaffected ML output."""
    a_zero = a.abs() < 1e-12
    b_zero = b.abs() < 1e-12
    raw = a / b.replace(0, 1e-10)
    return raw.where(~(a_zero & b_zero), other=float("nan"))


@pytest.mark.parametrize(("numerator", "expected"), [
    (100, [50., -50., 1e12, 2e14, -2e14, np.nan]),
    (100.0, [50., -50., 1e12, 2e14, -2e14, np.nan]),
    (-2.5, [-1.25, 1.25, -2.5e10, -5e12, 5e12, np.nan]),
    (0, [0., -0., np.nan, np.nan, np.nan, np.nan]),
    (0.0, [0., -0., np.nan, np.nan, np.nan, np.nan]),
    (1e-13, [5e-14, -5e-14, np.nan, np.nan, np.nan, np.nan]),
    (1e-12, [5e-13, -5e-13, 0.01, 2., -2., np.nan]),
    (-1e-12, [-5e-13, 5e-13, -0.01, -2., 2., np.nan]),
])
def test_scalar_numerator_signed_zero_epsilon_and_nan(numerator, expected):
    denominator = pd.Series([2., -2., 0., 5e-13, -5e-13, np.nan],
                            index=list("abcdef"), name="ratio")
    before = denominator.copy(deep=True)
    result = indicators._safe_div(numerator, denominator)
    assert_series_equal(result, pd.Series(expected, index=denominator.index, name="ratio"))
    assert_series_equal(denominator, before)


def test_series_alignment_missing_values_and_inputs_are_preserved():
    numerator = pd.Series([0., -4., 7.], index=["b", "a", "numerator_only"])
    denominator = pd.Series([2., 0., 3.], index=["a", "b", "denominator_only"])
    numerator_before, denominator_before = numerator.copy(), denominator.copy()
    expected = pd.Series([-2., np.nan, np.nan, np.nan],
                         index=["a", "b", "denominator_only", "numerator_only"])
    assert_series_equal(indicators._safe_div(numerator, denominator), expected)
    assert_series_equal(numerator, numerator_before)
    assert_series_equal(denominator, denominator_before)


def test_series_near_zero_boundary_matches_original_arithmetic_exactly():
    numerator = pd.Series([0., -0., 1e-13, 1e-12, 1., -2., np.nan, np.inf])
    denominator = pd.Series([0., -0., -1e-13, 0., 1e-15, 0., 1., 2.])
    result = indicators._safe_div(numerator, denominator)
    assert_series_equal(result, _original_series_only_division(numerator, denominator),
                        check_exact=True)
    assert result.iloc[:3].isna().all()
    assert result.iloc[3] == 0.01  # Threshold is strictly less than 1e-12.
    assert result.iloc[4] == pytest.approx(1e15)  # Tiny nonzero denominator is not replaced.


@pytest.mark.parametrize("numerator", [np.nan, np.inf, -np.inf])
def test_nonfinite_scalar_is_not_silently_coerced_to_zero(numerator):
    result = indicators._safe_div(numerator, pd.Series([2.]))
    if np.isnan(numerator):
        assert np.isnan(result.iloc[0])
    else:
        assert result.iloc[0] == numerator


@pytest.mark.parametrize("numerator", ["100", [100], object()])
def test_unsupported_numerator_is_rejected(numerator):
    with pytest.raises(TypeError):
        indicators._safe_div(numerator, pd.Series([2.]))


@pytest.mark.parametrize("kind", ["rising", "falling", "oscillating"])
@pytest.mark.parametrize(("function", "minimum"), [
    (indicators.volume_price_divergence, 0.),
    (indicators.mean_reversion_extremity, -1.),
    (indicators.momentum_quality_score, 0.),
])
def test_all_three_real_scalar_callers_finish_with_finite_scores(kind, function, minimum):
    bars = _bars(kind)
    before = bars.copy(deep=True)
    result = function(bars)
    assert len(result) == len(bars)
    assert result.index.equals(bars.index)
    assert np.isfinite(result.to_numpy()).all()
    assert result.between(minimum, 1.).all()
    assert (result != 0.).any()
    assert_frame_equal(bars, before, check_exact=True)


def _assert_composite_ranges(frame):
    for column in indicators.COMPOSITE_COLUMNS:
        minimum = -1. if column == "comp_mean_rev_extreme" else 0.
        assert np.isfinite(frame[column].to_numpy()).all()
        assert frame[column].between(minimum, 1.).all()


@pytest.mark.parametrize("kind", ["rising", "falling", "oscillating", "flat", "zero_volume"])
def test_master_computes_all_seven_and_preserves_input(kind):
    bars = _bars(kind)
    before = bars.copy(deep=True)
    result = indicators.compute_composite_indicators(bars)
    assert result.columns.tolist() == bars.columns.tolist() + indicators.COMPOSITE_COLUMNS
    _assert_composite_ranges(result)
    assert_frame_equal(result[bars.columns], before, check_exact=True)
    assert_frame_equal(bars, before, check_exact=True)
    assert result.attrs == bars.attrs
    if kind == "flat":
        # Retain the original zero/zero fix: flat halted bars cannot manufacture breakout.
        assert (result["comp_breakout_readiness"] == 0.).all()
    elif kind != "zero_volume":
        assert (result[indicators.COMPOSITE_COLUMNS] != 0.).any().all()


@pytest.mark.parametrize("rows", [0, 1, 19])
def test_short_input_retains_explicit_zero_warmup_contract(rows):
    bars = _bars("rising", rows)
    before = bars.copy(deep=True)
    result = indicators.compute_composite_indicators(bars)
    assert_frame_equal(result[bars.columns], before, check_exact=True)
    assert_frame_equal(bars, before, check_exact=True)
    assert (result[indicators.COMPOSITE_COLUMNS] == 0.).all().all()


@pytest.mark.parametrize(("kind", "rows"), [
    ("rising", 20), ("rising", 80), ("falling", 80), ("oscillating", 120),
    ("flat", 80), ("zero_volume", 80), ("rising", 500),
])
def test_actual_ml_path_completes_composites_without_changing_other_features(monkeypatch, kind, rows):
    bars = _bars(kind, rows)
    spy = _bars("oscillating", rows)
    before, spy_before = bars.copy(deep=True), spy.copy(deep=True)
    completed = []
    master = indicators.compute_composite_indicators

    def capture_success(frame):
        # Full ML features supply ADX and other intermediate context. Compare
        # the real master on that context, not an inequivalent raw-only frame.
        result = master(frame)
        completed.append(result[indicators.COMPOSITE_COLUMNS].copy(deep=True))
        return result

    with monkeypatch.context() as probe:
        probe.setattr(indicators, "compute_composite_indicators", capture_success)
        actual = compute_ml_features(bars, spy_df=spy, bars_per_day=390)
    assert len(completed) == 1, "The composite computation must return; seven fallback zeros do not qualify"
    assert_frame_equal(actual[indicators.COMPOSITE_COLUMNS], completed[0], check_exact=True)
    _assert_composite_ranges(actual)
    if kind not in {"flat", "zero_volume"}:
        assert (actual[indicators.COMPOSITE_COLUMNS] != 0.).any().any()
        if rows >= 80:
            # At exactly 20 bars some longer-window indicators are still
            # legitimately zero even though the master computation succeeds.
            assert (actual[indicators.COMPOSITE_COLUMNS] != 0.).any().all()

    with monkeypatch.context() as legacy:
        legacy.setattr(indicators, "_safe_div", _original_series_only_division)
        old = compute_ml_features(bars, spy_df=spy, bars_per_day=390)
    assert (old[indicators.COMPOSITE_COLUMNS] == 0.).all().all()
    # The correction may change composite scores only. This also checks the
    # missingness metadata, dtype/order, index, timestamps and frame attrs.
    other_columns = [column for column in actual if column not in indicators.COMPOSITE_COLUMNS]
    assert_frame_equal(actual[other_columns], old[other_columns], check_exact=True)
    assert actual.attrs == old.attrs == bars.attrs
    assert actual.columns.equals(old.columns)
    assert_frame_equal(bars, before, check_exact=True)
    assert_frame_equal(spy, spy_before, check_exact=True)


def test_transient_composite_failure_falls_back_then_retries_identical_input(monkeypatch):
    bars = _bars("oscillating", 120)
    before = bars.copy(deep=True)
    master = indicators.compute_composite_indicators
    attempts = 0
    successful_output = []

    def transient_failure(frame):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Synthetic transient composite failure")
        result = master(frame)
        successful_output.append(result[indicators.COMPOSITE_COLUMNS].copy(deep=True))
        return result

    monkeypatch.setattr(indicators, "compute_composite_indicators", transient_failure)
    fallback = compute_ml_features(bars, bars_per_day=390)
    recovered = compute_ml_features(bars, bars_per_day=390)
    assert attempts == 2 and len(successful_output) == 1
    assert (fallback[indicators.COMPOSITE_COLUMNS] == 0.).all().all()
    assert_frame_equal(recovered[indicators.COMPOSITE_COLUMNS], successful_output[0], check_exact=True)
    assert (recovered[indicators.COMPOSITE_COLUMNS] != 0.).any().all()
    other_columns = [column for column in recovered if column not in indicators.COMPOSITE_COLUMNS]
    assert_frame_equal(recovered[other_columns], fallback[other_columns], check_exact=True)
    assert_frame_equal(bars, before, check_exact=True)
