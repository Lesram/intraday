"""Phase 4 shadow-only ML target model comparison.

This script trains auditable offline classifiers for the current one-bar target
and the Phase 3 five-bar target candidate. It writes evidence for a future
shadow run; it never changes live ranking, confidence, sizing, or orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase3_ml_target_redesign import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    load_cached_bars,
    normalize_bars,
    parse_symbols,
)

DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase4_shadow_target_model"
FEATURE_COLUMNS: tuple[str, ...] = (
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_10",
    "range_pct",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
    "volume_z20",
    "volatility_10",
    "momentum_20",
)
TARGET_HORIZONS: tuple[int, int] = (1, 5)


@dataclass(frozen=True)
class ShadowModelConfig:
    train_fraction: float = 0.70
    min_symbol_rows: int = 80
    min_train_samples: int = 500
    confidence_threshold: float = 0.35
    promotion_balanced_accuracy_delta: float = 0.03
    promotion_proxy_bps_delta: float = 1.0
    min_validation_samples: int = 200


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _finite_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def build_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build current/past-only features from normalized OHLCV bars."""

    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)
    candle_range = (high - low).replace(0.0, pd.NA)
    volume_std = volume.rolling(20, min_periods=5).std().replace(0.0, pd.NA)

    features = pd.DataFrame(index=frame.index)
    features["ret_1"] = close.pct_change(1)
    features["ret_3"] = close.pct_change(3)
    features["ret_5"] = close.pct_change(5)
    features["ret_10"] = close.pct_change(10)
    features["range_pct"] = (high - low) / close
    features["body_pct"] = (close - open_) / open_
    features["upper_wick_pct"] = (high - close.where(close >= open_, open_)) / candle_range
    features["lower_wick_pct"] = (close.where(close <= open_, open_) - low) / candle_range
    features["volume_z20"] = (volume - volume.rolling(20, min_periods=5).mean()) / volume_std
    features["volatility_10"] = features["ret_1"].rolling(10, min_periods=5).std()
    features["momentum_20"] = close.pct_change(20)
    return features.replace([float("inf"), float("-inf")], pd.NA)


def build_target_dataset(
    bars: dict[str, pd.DataFrame],
    *,
    horizon: int,
    config: ShadowModelConfig,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol, frame in bars.items():
        if len(frame) < config.min_symbol_rows:
            continue
        features = build_feature_frame(frame)
        close = frame["close"].astype(float)
        forward_return = close.shift(-horizon) / close - 1.0
        data = features.copy()
        data["symbol"] = symbol
        data["timestamp"] = frame["timestamp"]
        data["forward_return"] = forward_return
        data["target"] = (forward_return > 0).where(forward_return.notna())
        data = data.dropna(subset=[*FEATURE_COLUMNS, "forward_return", "target"])
        if len(data) < config.min_symbol_rows:
            continue
        cutoff = max(1, min(len(data) - 1, int(len(data) * config.train_fraction)))
        data["split"] = "validation"
        data.iloc[:cutoff, data.columns.get_loc("split")] = "train"
        frames.append(data.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=[*FEATURE_COLUMNS, "symbol", "timestamp", "target", "split"])
    return pd.concat(frames, ignore_index=True)


def _fallback_probabilities(train: pd.DataFrame, validation: pd.DataFrame) -> tuple[list[float], str]:
    scale = _finite_float(train["ret_3"].std(), default=0.0) or 0.001
    raw_scores = (validation["ret_3"].astype(float) / (scale * 4.0)).clip(-6.0, 6.0)
    probabilities = [1.0 / (1.0 + math.exp(-float(score))) for score in raw_scores]
    return probabilities, "momentum_logistic_fallback"


def fit_predict_probabilities(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> tuple[list[float], str]:
    if train["target"].nunique() < 2:
        return _fallback_probabilities(train, validation)
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return _fallback_probabilities(train, validation)

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=13),
    )
    try:
        model.fit(train.loc[:, FEATURE_COLUMNS], train["target"].astype(int))
    except ValueError:
        return _fallback_probabilities(train, validation)
    probabilities = model.predict_proba(validation.loc[:, FEATURE_COLUMNS])[:, 1]
    return [float(value) for value in probabilities], "logistic_regression_balanced"


def _confidence_bins(labels: pd.Series, probabilities: pd.Series) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    edges = [0.0, 0.4, 0.5, 0.6, 1.0]
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        mask = (probabilities >= low) & (probabilities < high)
        if high == 1.0:
            mask = (probabilities >= low) & (probabilities <= high)
        count = int(mask.sum())
        bins.append({
            "probability_bin": f"[{low:.1f},{high:.1f}{']' if high == 1.0 else ')'}",
            "count": count,
            "positive_rate": _round(float(labels[mask].mean()) if count else 0.0),
            "mean_probability": _round(float(probabilities[mask].mean()) if count else 0.0),
        })
    return bins


def evaluate_predictions(
    validation: pd.DataFrame,
    probabilities: list[float],
    *,
    confidence_threshold: float,
) -> dict[str, Any]:
    labels = validation["target"].astype(int).reset_index(drop=True)
    forward_returns = validation["forward_return"].astype(float).reset_index(drop=True)
    proba = pd.Series(probabilities, dtype=float)
    predictions = (proba >= 0.5).astype(int)

    tp = int(((predictions == 1) & (labels == 1)).sum())
    tn = int(((predictions == 0) & (labels == 0)).sum())
    fp = int(((predictions == 1) & (labels == 0)).sum())
    fn = int(((predictions == 0) & (labels == 1)).sum())
    accuracy = _safe_div(tp + tn, len(labels))
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0
    brier = float(((proba - labels) ** 2).mean()) if len(labels) else 0.0

    confidence = (proba - 0.5).abs() * 2.0
    selected = confidence >= confidence_threshold
    direction = proba.map(lambda value: 1.0 if value >= 0.5 else -1.0)
    proxy_return_bps = direction * forward_returns * 10_000
    selected_bps = proxy_return_bps[selected]

    return {
        "validation_samples": int(len(labels)),
        "positive_rate": _round(float(labels.mean()) if len(labels) else 0.0),
        "accuracy": _round(accuracy),
        "precision": _round(precision),
        "recall": _round(recall),
        "specificity": _round(specificity),
        "f1": _round(f1),
        "balanced_accuracy": _round(balanced_accuracy),
        "brier_score": _round(brier, 6),
        "selected_samples": int(selected.sum()),
        "selected_rate": _round(_safe_div(float(selected.sum()), len(labels))),
        "selected_proxy_mean_bps": _round(float(selected_bps.mean()) if len(selected_bps) else 0.0),
        "selected_proxy_win_rate": _round(float((selected_bps > 0).mean()) if len(selected_bps) else 0.0),
        "selected_proxy_total_bps": _round(float(selected_bps.sum()) if len(selected_bps) else 0.0),
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "calibration_bins": _confidence_bins(labels, proba),
    }


def evaluate_target_model(
    dataset: pd.DataFrame,
    *,
    target: str,
    horizon: int,
    config: ShadowModelConfig,
) -> dict[str, Any]:
    train = dataset[dataset["split"] == "train"].reset_index(drop=True)
    validation = dataset[dataset["split"] == "validation"].reset_index(drop=True)
    if len(train) < config.min_train_samples or len(validation) < config.min_validation_samples:
        return {
            "target": target,
            "horizon_bars": horizon,
            "status": "insufficient_data",
            "train_samples": int(len(train)),
            "validation_samples": int(len(validation)),
        }
    probabilities, model_name = fit_predict_probabilities(train, validation)
    metrics = evaluate_predictions(
        validation,
        probabilities,
        confidence_threshold=config.confidence_threshold,
    )
    return {
        "target": target,
        "horizon_bars": horizon,
        "status": "evaluated",
        "model": model_name,
        "train_samples": int(len(train)),
        "validation_samples": int(len(validation)),
        "symbols": int(dataset["symbol"].nunique()),
        **metrics,
    }


def _promotion_gates(
    current: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    config: ShadowModelConfig,
) -> list[dict[str, Any]]:
    if not current or not candidate:
        return [{"name": "current_and_candidate_evaluated", "passed": False}]
    if current.get("status") != "evaluated" or candidate.get("status") != "evaluated":
        return [{"name": "current_and_candidate_evaluated", "passed": False}]

    balanced_delta = (
        float(candidate["balanced_accuracy"]) - float(current["balanced_accuracy"])
    )
    proxy_delta = (
        float(candidate["selected_proxy_mean_bps"])
        - float(current["selected_proxy_mean_bps"])
    )
    return [
        {
            "name": "validation_sample_floor",
            "passed": int(candidate["validation_samples"]) >= config.min_validation_samples,
            "observed": int(candidate["validation_samples"]),
            "threshold": config.min_validation_samples,
        },
        {
            "name": "balanced_accuracy_delta",
            "passed": balanced_delta >= config.promotion_balanced_accuracy_delta,
            "observed": _round(balanced_delta),
            "threshold": config.promotion_balanced_accuracy_delta,
        },
        {
            "name": "selected_proxy_bps_delta",
            "passed": proxy_delta >= config.promotion_proxy_bps_delta,
            "observed": _round(proxy_delta),
            "threshold": config.promotion_proxy_bps_delta,
        },
        {
            "name": "live_promotion_blocked_by_phase4_scope",
            "passed": False,
            "observed": "shadow_only",
            "threshold": "requires replay_and_live_shadow_session",
        },
    ]


def compare_shadow_targets(
    bars: dict[str, pd.DataFrame],
    config: ShadowModelConfig,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    dataset_metadata: dict[str, Any] = {}
    for horizon in TARGET_HORIZONS:
        target = f"close_return_h{horizon}"
        dataset = build_target_dataset(bars, horizon=horizon, config=config)
        dataset_metadata[target] = {
            "rows": int(len(dataset)),
            "symbols": int(dataset["symbol"].nunique()) if "symbol" in dataset else 0,
        }
        results.append(
            evaluate_target_model(
                dataset,
                target=target,
                horizon=horizon,
                config=config,
            )
        )

    current = next((row for row in results if row["target"] == "close_return_h1"), None)
    candidate = next((row for row in results if row["target"] == "close_return_h5"), None)
    gates = _promotion_gates(current, candidate, config)
    candidate_gate_count = max(0, len(gates) - 1)
    candidate_passes = sum(1 for gate in gates[:-1] if gate.get("passed"))
    recommendation = "do_not_promote_shadow_model"
    if candidate_gate_count and candidate_passes == candidate_gate_count:
        recommendation = "shadow_candidate_pending_replay_and_live_telemetry"

    return {
        "scope": "phase4_shadow_only_model_comparison_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "train_fraction": config.train_fraction,
            "min_symbol_rows": config.min_symbol_rows,
            "min_train_samples": config.min_train_samples,
            "min_validation_samples": config.min_validation_samples,
            "confidence_threshold": config.confidence_threshold,
            "promotion_balanced_accuracy_delta": config.promotion_balanced_accuracy_delta,
            "promotion_proxy_bps_delta": config.promotion_proxy_bps_delta,
        },
        "feature_columns": list(FEATURE_COLUMNS),
        "dataset_metadata": dataset_metadata,
        "targets": results,
        "current_target": current,
        "candidate_target": candidate,
        "promotion_gates": gates,
        "recommendation": recommendation,
        "live_behavior": "unchanged",
        "limitations": [
            "Offline OHLCV labels are not proof of trading expectancy.",
            "The proxy return ignores fills, slippage, risk sizing, exits, and opportunity cost.",
            "Even a passing candidate remains shadow-only until replay and live shadow telemetry pass.",
        ],
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_shadow_target_model.json"
    target_path = out_dir / "shadow_target_model_metrics.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    fields = [
        "target",
        "horizon_bars",
        "status",
        "model",
        "train_samples",
        "validation_samples",
        "symbols",
        "positive_rate",
        "accuracy",
        "precision",
        "recall",
        "specificity",
        "f1",
        "balanced_accuracy",
        "brier_score",
        "selected_samples",
        "selected_rate",
        "selected_proxy_mean_bps",
        "selected_proxy_win_rate",
        "selected_proxy_total_bps",
    ]
    with target_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["targets"])
    return {"summary": str(summary_path), "metrics": str(target_path)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--confidence-threshold", type=float, default=0.35)
    parser.add_argument("--min-symbol-rows", type=int, default=80)
    parser.add_argument("--min-train-samples", type=int, default=500)
    parser.add_argument("--min-validation-samples", type=int, default=200)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = ShadowModelConfig(
        train_fraction=args.train_fraction,
        min_symbol_rows=args.min_symbol_rows,
        min_train_samples=args.min_train_samples,
        min_validation_samples=args.min_validation_samples,
        confidence_threshold=args.confidence_threshold,
    )
    bars = normalize_bars(
        load_cached_bars(args.cache_dir, args.bar_file),
        parse_symbols(args.symbols),
    )
    summary = compare_shadow_targets(bars, config)
    outputs = write_outputs(summary, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
