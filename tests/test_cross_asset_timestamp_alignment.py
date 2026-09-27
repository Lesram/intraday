"""Causal benchmark alignment on actual provider-shaped OHLCV frames."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from backend.organism.ml_features import compute_ml_features

CROSS = ["rel_strength_spy", "beta_20d", "corr_to_market", "idio_vol"]


def bars(n=100, *, start="2026-09-24T13:30:00Z", phase=0.0):
    x = np.arange(n, dtype=float)
    close = 100 + 0.025 * x + np.sin(x * 0.37 + phase) * 0.8 + np.cos(x * 0.11 + phase) * 0.3
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=n, freq="min"),
            "open": close - 0.08,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 10000 + x * 11,
        }
    )


def oracle(stock, spy):
    """Independent explicit timestamp lookup; no index/reindex/asof operations."""
    history = [
        (pd.Timestamp(t).tz_convert("UTC"), float(c)) for t, c in zip(spy.timestamp, spy.close)
    ]
    aligned, matched = [], []
    for stamp in stock.timestamp:
        eligible = [(t, c) for t, c in history if t <= pd.Timestamp(stamp).tz_convert("UTC")]
        matched.append(eligible[-1][0].isoformat() if eligible else None)
        aligned.append(eligible[-1][1] if eligible else np.nan)
    c = stock.close.to_numpy()
    m = np.array(aligned)
    sr = np.r_[np.nan, c[1:] / c[:-1] - 1]
    mr = np.r_[np.nan, m[1:] / m[:-1] - 1]
    result = []
    for i in range(len(c)):
        rel, beta, corr = 0.0, 1.0, 0.0
        if i >= 20 and np.isfinite(m[i]) and np.isfinite(m[i - 20]):
            rel = c[i] / c[i - 20] - 1 - (m[i] / m[i - 20] - 1)
        if i >= 20:
            a, b = sr[i - 20 : i], mr[i - 20 : i]
            if np.isfinite(a).all() and np.isfinite(b).all() and np.std(b) > 0 and np.std(a) > 0:
                corr = float(np.corrcoef(a, b)[0, 1])
                beta = corr * np.std(a) / np.std(b)
        vol = pd.Series(np.r_[np.nan, np.log(c[1:] / c[:-1])]).iloc[
            max(0, i - 19) : i + 1
        ].std() * math.sqrt(252 * 390)
        result.append([rel, beta, corr, 0.0 if np.isnan(vol) else vol * (1 - abs(corr))])
    return pd.DataFrame(result, columns=CROSS), matched


def cross(frame):
    return frame[CROSS].reset_index(drop=True)


def metadata(frame):
    return frame.attrs["cross_asset_alignment"]


@pytest.mark.parametrize("shape", ["tail", "gaps", "short_spy", "leading_uncovered"])
def test_provider_range_index_matches_explicit_timestamp_oracle(shape):
    stock, spy = bars(80, phase=0.8), bars(120)
    if shape == "tail":
        stock["timestamp"] = spy.timestamp.iloc[-80:].to_numpy()
    elif shape == "gaps":
        stock = stock.iloc[::2].reset_index(drop=True)
    elif shape == "short_spy":
        spy = spy.iloc[::3].reset_index(drop=True)
    else:
        spy = spy.iloc[35:].reset_index(drop=True)
    result = compute_ml_features(stock, spy, bars_per_day=390)
    expected, matched = oracle(stock, spy)
    assert_frame_equal(cross(result), expected, check_exact=False, atol=1e-10, rtol=1e-10)
    assert metadata(result)["matched_timestamps"] == matched
    assert result.index.equals(stock.index)
    assert result.timestamp.equals(stock.timestamp)


def test_range_and_datetime_index_representations_have_identical_cross_features():
    stock, spy = bars(80, start="2026-09-24T14:10:00Z", phase=0.8), bars(120)
    ranged = compute_ml_features(stock, spy, bars_per_day=390)
    indexed = compute_ml_features(
        stock.set_index("timestamp", drop=False),
        spy.set_index("timestamp", drop=False),
        bars_per_day=390,
    )
    assert_frame_equal(cross(ranged), cross(indexed))
    assert metadata(ranged) == metadata(indexed)


def test_timestamp_column_is_authoritative_and_aware_datetime_index_is_fallback():
    stock, spy = bars(80, phase=0.8), bars(100)
    # Arbitrary indexes cannot override authoritative timestamp columns.
    stock.index = pd.date_range("2040-01-01", periods=80, freq="min", tz="UTC")
    spy.index = pd.date_range("2041-01-01", periods=100, freq="min", tz="UTC")
    actual = compute_ml_features(stock, spy, bars_per_day=390)
    expected, _ = oracle(stock, spy)
    assert_frame_equal(cross(actual), expected, check_exact=False, atol=1e-10, rtol=1e-10)
    fallback = compute_ml_features(
        stock.set_index("timestamp"), spy.set_index("timestamp"), bars_per_day=390
    )
    assert_frame_equal(cross(fallback), cross(actual))


def test_offset_timezones_match_instants_without_changing_stock_order_or_input():
    stock, spy = bars(80, phase=0.8), bars(100)
    baseline = compute_ml_features(stock, spy, bars_per_day=390)
    stock["timestamp"] = stock.timestamp.dt.tz_convert("America/New_York")
    spy["timestamp"] = spy.timestamp.dt.tz_convert("Asia/Tokyo")
    original_stock, original_spy = stock.copy(deep=True), spy.copy(deep=True)
    actual = compute_ml_features(stock, spy, bars_per_day=390)
    assert_frame_equal(cross(actual), cross(baseline))
    assert_frame_equal(stock, original_stock)
    assert_frame_equal(spy, original_spy)


def test_future_benchmark_values_or_rows_cannot_change_prefix_values_or_validity():
    stock, spy = bars(80, phase=0.8), bars(120)
    short = compute_ml_features(stock.iloc[:60], spy.iloc[:60], bars_per_day=390)
    future = spy.copy()
    future.loc[60:, "close"] *= 100
    longer = compute_ml_features(stock, future, bars_per_day=390)
    assert_frame_equal(cross(short), cross(longer.iloc[:60]))
    for name in ("matched_timestamps", "age_seconds", "matched"):
        assert metadata(short)[name] == metadata(longer)[name][:60]
    for name in CROSS:
        assert (
            metadata(short)["feature_valid"][name] == metadata(longer)["feature_valid"][name][:60]
        )


@pytest.mark.parametrize("side", ["stock", "spy"])
@pytest.mark.parametrize(
    "fault", ["duplicate", "unsorted", "naive", "invalid", "numeric", "missing"]
)
def test_invalid_temporal_input_is_explicitly_unavailable_without_losing_stock_features(
    side, fault
):
    stock, spy = bars(60, phase=0.8), bars(80)
    frame = stock if side == "stock" else spy
    if fault == "duplicate":
        frame.loc[20, "timestamp"] = frame.loc[19, "timestamp"]
    elif fault == "unsorted":
        frame.loc[[19, 20], "timestamp"] = frame.loc[[20, 19], "timestamp"].to_numpy()
    elif fault == "naive":
        frame["timestamp"] = frame.timestamp.dt.tz_localize(None)
    elif fault in ("invalid", "numeric"):
        frame["timestamp"] = frame.timestamp.astype(object)
        frame.loc[20, "timestamp"] = "not-a-time" if fault == "invalid" else 123456
    else:
        frame.drop(columns="timestamp", inplace=True)
    result = compute_ml_features(stock, spy, bars_per_day=390)
    without_spy = compute_ml_features(stock, bars_per_day=390)
    assert_frame_equal(result.drop(columns=CROSS), without_spy.drop(columns=CROSS))
    assert metadata(result)["status"] == "unavailable"
    assert metadata(result)["reason"].startswith(side + "_")
    assert not any(metadata(result)["matched"])
    assert all(not any(v) for v in metadata(result)["feature_valid"].values())
    assert (result.rel_strength_spy == 0).all() and (result.beta_20d == 1).all()
    assert (result.corr_to_market == 0).all()
    assert result.idio_vol.equals(result.realized_vol_20)


def test_no_prior_benchmark_is_neutral_and_short_history_is_marked_not_valid():
    stock, spy = bars(40), bars(10, start="2026-09-24T16:00:00Z")
    result = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(result)["status"] == "unavailable"
    assert metadata(result)["reason"] == "no_prior_benchmark"
    assert metadata(result)["matched_timestamps"] == [None] * 40
    assert (result.beta_20d == 1).all() and (result.rel_strength_spy == 0).all()
    dense = compute_ml_features(stock.iloc[:15], stock.iloc[:15], bars_per_day=390)
    assert all(not any(v) for v in metadata(dense)["feature_valid"].values())


def test_sparse_past_only_coverage_is_reported_without_new_age_tolerance():
    stock = bars(60)
    spy = bars(2).iloc[:1]
    result = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(result)["matched"] == [True] * 60
    assert metadata(result)["age_seconds"][-1] == 59 * 60
    assert not any(metadata(result)["feature_valid"]["corr_to_market"])
    assert (result.corr_to_market == 0).all()


def legacy_ordinal_alignment(stock, spy):
    """Exact old alignment predicate/reindex, test-only; no Git dependency."""
    from backend.organism.ml_features import _cross_asset_alignment

    _, info = _cross_asset_alignment(stock, spy)
    info["status"] = "counterfactual_old_ordinal"
    if spy is None or "close" not in spy or len(spy) < len(stock):
        return None, info
    return spy["close"].reindex(stock.index, method="ffill").to_numpy(), info


@pytest.mark.parametrize("shape", ["dense", "unequal", "short_spy", "offset"])
def test_non_cross_features_exactly_equal_old_alignment_and_dense_all_values_equal(
    shape, monkeypatch
):
    from backend.organism import ml_features

    original = ml_features._cross_asset_alignment
    stock, spy = bars(80, phase=0.8), bars(120)
    if shape == "unequal":
        stock["timestamp"] = spy.timestamp.iloc[-80:].to_numpy()
    elif shape == "short_spy":
        spy = spy.iloc[::3].reset_index(drop=True)
    elif shape == "offset":
        stock["timestamp"] = stock.timestamp.dt.tz_convert("America/New_York")
        spy["timestamp"] = spy.timestamp.dt.tz_convert("Asia/Tokyo")
    current = compute_ml_features(stock, spy, bars_per_day=390)

    def legacy(a, b):
        with monkeypatch.context() as context:
            context.setattr(ml_features, "_cross_asset_alignment", original)
            return legacy_ordinal_alignment(a, b)

    monkeypatch.setattr(ml_features, "_cross_asset_alignment", legacy)
    baseline = compute_ml_features(stock, spy, bars_per_day=390)
    assert_frame_equal(current.drop(columns=CROSS), baseline.drop(columns=CROSS))
    if shape in ("dense", "offset"):
        assert_frame_equal(current, baseline)
    else:
        assert not cross(current).equals(cross(baseline))


def test_mixed_aware_offsets_and_invalid_row_calendar_fallback_preserve_event_times():
    stock, spy = bars(60, phase=0.8), bars(80)
    ordinary = compute_ml_features(stock, spy, bars_per_day=390)
    stock["timestamp"] = [
        stamp.tz_convert("America/New_York").isoformat() if i % 2 else stamp.isoformat()
        for i, stamp in enumerate(stock.timestamp)
    ]
    mixed = compute_ml_features(stock, spy, bars_per_day=390)
    assert_frame_equal(cross(mixed), cross(ordinary))
    assert mixed.timestamp.equals(stock.timestamp)
    stock.loc[20, "timestamp"] = "invalid-event-time"
    bad = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(bad)["invalid_timestamp_rows"]["stock"] == [20]
    assert bad.loc[20, "timestamp"] == "invalid-event-time"
    assert bad.loc[20, ["day_of_week", "month_sin", "month_cos"]].tolist() == [0.0, 0.0, 0.0]
    assert bad.drop(index=20).day_of_week.equals(mixed.drop(index=20).day_of_week)


@pytest.mark.parametrize("invalid", [np.nan, np.inf, 0.0, -1.0, "malformed", True, complex(1, 2)])
def test_invalid_latest_benchmark_price_cannot_borrow_an_older_valid_price(invalid):
    stock, spy = bars(60), bars(60)
    spy["close"] = spy.close.astype(object)
    spy.loc[59, "close"] = invalid
    result = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(result)["status"] == "partial"
    assert metadata(result)["matched"][-1] is False
    assert result.rel_strength_spy.iloc[-1] == 0.0
    assert metadata(result)["feature_valid"]["rel_strength_spy"][-1] is False


@pytest.mark.asyncio
async def test_actual_feeder_preserves_alignment_metadata_and_stock_outputs():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from backend.organism.live_engine_data import _DataFeederMixin

    stock, spy = bars(220, phase=0.8), bars(260)
    stock["timestamp"] = spy.timestamp.iloc[-220:].to_numpy()
    expected = compute_ml_features(stock, spy, bars_per_day=390)
    engine = _DataFeederMixin()
    engine._streaming_provider = None
    engine._feature_store = None
    engine._bars_per_day = 390
    engine._universe = ["SYNTH"]
    engine._positions_service = SimpleNamespace(get_all_positions=AsyncMock(return_value={}))
    engine._fetch_bars = AsyncMock(side_effect=lambda symbol: spy if symbol == "SPY" else stock)
    actual = (await engine._fetch_and_compute_features())["SYNTH"]
    assert metadata(actual) == metadata(expected)
    assert_frame_equal(cross(actual), cross(expected))


@pytest.mark.parametrize("invalid", ["invalid-event-time", "2026-09-24T14:29:00", None])
def test_temporal_fallback_does_not_make_invalid_stock_frame_entry_eligible(invalid):
    from types import SimpleNamespace
    from backend.organism.entry_evidence import _frame_receipt
    from backend.organism.entry_freshness import require_fresh_entry, EntryFreshnessRejected

    stock, spy = bars(60), bars(80)
    stock["timestamp"] = stock.timestamp.astype(object)
    stock.loc[30, "timestamp"] = invalid
    features = compute_ml_features(stock, spy, bars_per_day=390)
    engine = SimpleNamespace(
        _tick_count=7, _now_fn=lambda: pd.Timestamp("2026-09-24T14:29:30Z"), _timeframe="1Min"
    )
    receipt = _frame_receipt(engine, "SYNTH", 1.0, features)
    engine._entry_evidence_tick = 7
    engine._entry_evidence_frames = {("SYNTH", 1.0): receipt}
    with pytest.raises(EntryFreshnessRejected):
        require_fresh_entry(engine, "SYNTH", 1.0)


@pytest.mark.parametrize("fault", ["naive", "duplicate", "unsorted"])
def test_datetime_index_fallback_has_same_strict_temporal_validation(fault):
    stock, spy = bars(60), bars(80).set_index("timestamp")
    if fault == "naive":
        spy.index = spy.index.tz_localize(None)
    elif fault == "duplicate":
        spy.index = spy.index.where(np.arange(len(spy)) != 20, spy.index[19])
    else:
        spy = spy.iloc[::-1]
    result = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(result)["status"] == "unavailable"
    assert metadata(result)["reason"].startswith("spy_")
    assert (result.rel_strength_spy == 0).all()


@pytest.mark.parametrize("absence", ["none", "empty", "missing_price"])
def test_absent_benchmark_contract_stays_neutral(absence):
    stock, spy = bars(60), bars(80)
    if absence == "none":
        spy = None
    elif absence == "empty":
        spy = spy.iloc[:0]
    else:
        spy = spy.drop(columns="close")
    result = compute_ml_features(stock, spy, bars_per_day=390)
    assert metadata(result)["status"] == ("not_requested" if absence == "none" else "unavailable")
    assert (result.rel_strength_spy == 0).all() and (result.beta_20d == 1).all()
