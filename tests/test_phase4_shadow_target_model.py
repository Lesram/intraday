"""Tests for Phase 4 shadow-only target model comparison."""

from __future__ import annotations

import pandas as pd

from scripts.phase4_shadow_target_model import (
    ShadowModelConfig,
    build_feature_frame,
    build_target_dataset,
    compare_shadow_targets,
    evaluate_predictions,
)


def _bars(rows: int = 140, *, drift: float = 0.03) -> pd.DataFrame:
    timestamps = pd.date_range("2026-05-04T14:00:00Z", periods=rows, freq="min", tz="UTC")
    close = [100.0 + i * drift + ((i % 7) - 3) * 0.02 for i in range(rows)]
    return pd.DataFrame({
        "timestamp": [stamp.isoformat().replace("+00:00", "Z") for stamp in timestamps],
        "open": [value - 0.01 for value in close],
        "high": [value + 0.05 for value in close],
        "low": [value - 0.05 for value in close],
        "close": close,
        "volume": [1000.0 + (i % 20) * 5 for i in range(rows)],
    })


def test_feature_frame_uses_current_and_past_bars_only():
    frame = _bars()
    baseline = build_feature_frame(frame).iloc[30].copy()
    changed_future = frame.copy()
    changed_future.loc[40:, "close"] = changed_future.loc[40:, "close"] + 50.0

    after = build_feature_frame(changed_future).iloc[30]

    assert after.to_dict() == baseline.to_dict()


def test_build_target_dataset_assigns_temporal_splits_per_symbol():
    config = ShadowModelConfig(min_symbol_rows=60, min_train_samples=20)
    dataset = build_target_dataset({"AAPL": _bars(100), "MSFT": _bars(100)}, horizon=5, config=config)

    assert set(dataset["split"]) == {"train", "validation"}
    for _, group in dataset.groupby("symbol"):
        train_max = group[group["split"] == "train"].index.max()
        validation_min = group[group["split"] == "validation"].index.min()
        assert train_max < validation_min


def test_evaluate_predictions_reports_proxy_trade_metrics():
    validation = pd.DataFrame({
        "target": [1, 0, 1, 0],
        "forward_return": [0.01, -0.01, 0.005, -0.004],
    })

    metrics = evaluate_predictions(validation, [0.8, 0.2, 0.51, 0.49], confidence_threshold=0.2)

    assert metrics["accuracy"] == 1.0
    assert metrics["selected_samples"] == 2
    assert metrics["selected_proxy_mean_bps"] > 0


def test_compare_shadow_targets_is_evidence_only_and_blocks_live_promotion():
    config = ShadowModelConfig(
        min_symbol_rows=60,
        min_train_samples=20,
        min_validation_samples=20,
        confidence_threshold=0.2,
    )
    summary = compare_shadow_targets(
        {"AAPL": _bars(160), "MSFT": _bars(160, drift=0.01)},
        config,
    )

    assert summary["scope"] == "phase4_shadow_only_model_comparison_no_live_behavior_change"
    assert summary["live_behavior"] == "unchanged"
    assert {row["target"] for row in summary["targets"]} == {
        "close_return_h1",
        "close_return_h5",
    }
    assert any(
        gate["name"] == "live_promotion_blocked_by_phase4_scope"
        and gate["passed"] is False
        for gate in summary["promotion_gates"]
    )
