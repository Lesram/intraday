"""Tests for Phase 3 ML target redesign comparison tooling."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_ml_target_redesign import (
    TargetConfig,
    aggregate_metrics,
    analyze_targets,
    close_return_target_metrics,
    mfe_mae_long_metrics,
    mfe_mae_symmetric_metrics,
    normalize_bars,
    parse_symbols,
)


def _trend_bars(rows: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2026-05-04T14:00:00Z", periods=rows, freq="min", tz="UTC")
    close = [100.0 + i * 0.1 for i in range(rows)]
    return pd.DataFrame({
        "timestamp": [stamp.isoformat().replace("+00:00", "Z") for stamp in ts],
        "open": close,
        "high": [value + 0.08 for value in close],
        "low": [value - 0.04 for value in close],
        "close": close,
        "volume": [1000.0 + i for i in range(rows)],
    })


def _zigzag_bars(rows: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2026-05-04T14:00:00Z", periods=rows, freq="min", tz="UTC")
    close = [100.0 + ((-1) ** i) * 0.2 + i * 0.01 for i in range(rows)]
    return pd.DataFrame({
        "timestamp": [stamp.isoformat().replace("+00:00", "Z") for stamp in ts],
        "open": close,
        "high": [value + 0.4 for value in close],
        "low": [value - 0.4 for value in close],
        "close": close,
        "volume": [1000.0 + i for i in range(rows)],
    })


def test_parse_symbols_and_normalize_bars_validate_input():
    assert parse_symbols("aapl, MSFT") == ["AAPL", "MSFT"]
    assert parse_symbols(None) is None

    bars = normalize_bars({"AAPL": _trend_bars(35)}, ["AAPL"])

    assert list(bars) == ["AAPL"]
    assert str(bars["AAPL"]["timestamp"].dtype).startswith("datetime64")

    with pytest.raises(ValueError):
        parse_symbols(" , ")
    with pytest.raises(ValueError):
        normalize_bars({"AAPL": _trend_bars(35)}, ["MSFT"])


def test_close_return_target_metrics_measure_noise_and_balance():
    metrics = close_return_target_metrics(
        _trend_bars(80),
        horizon=5,
        config=TargetConfig(min_samples=10),
    )

    assert metrics["target"] == "close_return_h5"
    assert metrics["samples"] == 75
    assert metrics["positive_rate"] == 1.0
    assert metrics["balance_error"] == 1.0
    assert metrics["score"] == 0.0


def test_mfe_mae_metrics_expose_tradeable_and_ambiguous_rates():
    frame = _zigzag_bars(80)
    config = TargetConfig(
        mfe_mae_horizon=5,
        mfe_target_bps=20,
        mae_stop_bps=20,
        min_samples=10,
    )

    long_metrics = mfe_mae_long_metrics(frame, config)
    symmetric_metrics = mfe_mae_symmetric_metrics(frame, config)

    assert long_metrics["samples"] == 75
    assert long_metrics["tradeable_move_rate"] > 0.0
    assert "ambiguous_rate" in long_metrics
    assert symmetric_metrics["target"] == "mfe_mae_symmetric_h5"
    assert symmetric_metrics["raw_samples"] == 75


def test_aggregate_metrics_weights_by_samples_and_sorts_by_score():
    rows = [
        {"target": "a", "family": "x", "horizon_bars": 1, "samples": 10, "score": 0.1},
        {"target": "a", "family": "x", "horizon_bars": 1, "samples": 30, "score": 0.3},
        {"target": "b", "family": "y", "horizon_bars": 5, "samples": 10, "score": 0.4},
    ]

    aggregate = aggregate_metrics(rows, TargetConfig())

    assert aggregate[0]["target"] == "b"
    a_row = next(row for row in aggregate if row["target"] == "a")
    assert a_row["samples"] == 40
    assert a_row["score"] == pytest.approx(0.25)


def test_analyze_targets_returns_current_and_best_target():
    summary = analyze_targets(
        {"AAPL": _trend_bars(80), "MSFT": _zigzag_bars(80)},
        TargetConfig(min_samples=10),
    )

    assert summary["scope"] == "offline_ml_target_redesign_no_live_behavior_change"
    assert summary["current_target"]["target"] == "close_return_h1"
    assert summary["best_target"] is not None
    assert summary["recommendation"] in {
        "research_candidate_for_shadow_training_only",
        "keep_current_target_pending_more_evidence",
        "insufficient_data",
    }
