"""Phase 3 ML target redesign comparison.

Offline research tool: compare the current next-bar close-return target with
longer-horizon and MFE/MAE-derived labels over cached bars. This does not train
or promote a live model; it ranks target hypotheses for a later shadow run.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "artifacts" / "backtest_rc_1_5"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_ml_target_redesign"


@dataclass(frozen=True)
class TargetConfig:
    horizons: tuple[int, ...] = (1, 5, 10)
    fee_bps: float = 5.0
    tradeable_bps: float = 25.0
    mfe_mae_horizon: int = 10
    mfe_target_bps: float = 30.0
    mae_stop_bps: float = 20.0
    min_samples: int = 500


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    symbols = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not symbols:
        raise ValueError("symbol filter cannot be empty")
    return symbols


def load_cached_bars(cache_dir: Path, bar_file: str = "bars.pkl") -> dict[str, Any]:
    bars_path = cache_dir / bar_file
    if not bars_path.is_file():
        raise FileNotFoundError(f"cached bars missing: {bars_path}")
    with bars_path.open("rb") as fh:
        bars = pickle.load(fh)
    if not isinstance(bars, dict) or not bars:
        raise ValueError(f"cached bars are empty or invalid: {bars_path}")
    return bars


def normalize_bars(
    raw_bars: dict[str, Any],
    symbols: list[str] | None,
) -> dict[str, pd.DataFrame]:
    selected = symbols or sorted(raw_bars)
    missing = [symbol for symbol in selected if symbol not in raw_bars]
    if missing:
        raise ValueError(f"symbols missing from cached bars: {missing}")
    normalized: dict[str, pd.DataFrame] = {}
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    for symbol in selected:
        frame = raw_bars[symbol]
        if frame is None or not required.issubset(frame.columns):
            continue
        out = frame.copy()
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        for column in ("open", "high", "low", "close", "volume"):
            out[column] = pd.to_numeric(out[column], errors="coerce")
        out = out.dropna(subset=list(required)).sort_values("timestamp")
        if len(out) >= 30:
            normalized[symbol] = out.reset_index(drop=True)
    if not normalized:
        raise ValueError("no usable bars after normalization")
    return normalized


def _mean_bool(series: pd.Series) -> float:
    return float(series.mean()) if len(series) else 0.0


def _momentum_lift(label: pd.Series, momentum: pd.Series) -> float:
    valid = label.notna() & momentum.notna()
    if not bool(valid.any()):
        return 0.0
    pos = label[valid & (momentum > 0)]
    non_pos = label[valid & (momentum <= 0)]
    if len(pos) < 5 or len(non_pos) < 5:
        return 0.0
    return float(pos.mean() - non_pos.mean())


def _balance_error(positive_rate: float) -> float:
    return min(abs(positive_rate - 0.5) * 2.0, 1.0)


def close_return_target_metrics(
    frame: pd.DataFrame,
    *,
    horizon: int,
    config: TargetConfig,
) -> dict[str, Any]:
    close = frame["close"].astype(float)
    forward_return = close.shift(-horizon) / close - 1.0
    label = (forward_return > 0).astype(float)
    valid = forward_return.notna()
    forward_return = forward_return[valid]
    label = label[valid]
    momentum = close.pct_change(3)[valid]
    fee = config.fee_bps / 10_000
    tradeable = config.tradeable_bps / 10_000
    positive_rate = _mean_bool(label)
    noise_rate = _mean_bool(forward_return.abs() <= fee)
    tradeable_rate = _mean_bool(forward_return.abs() >= tradeable)
    momentum_lift = _momentum_lift(label, momentum)
    balance_error = _balance_error(positive_rate)
    score = (
        abs(momentum_lift)
        * (1.0 - noise_rate)
        * (1.0 - balance_error)
        * min(1.0, len(label) / config.min_samples)
    )
    return {
        "target": f"close_return_h{horizon}",
        "family": "close_return",
        "horizon_bars": horizon,
        "samples": int(len(label)),
        "positive_rate": _round(positive_rate),
        "neutral_or_noise_rate": _round(noise_rate),
        "tradeable_move_rate": _round(tradeable_rate),
        "mean_abs_return_bps": _round(float(forward_return.abs().mean() * 10_000)),
        "median_abs_return_bps": _round(float(forward_return.abs().median() * 10_000)),
        "momentum_lift": _round(momentum_lift),
        "balance_error": _round(balance_error),
        "score": _round(score, 6),
    }


def _future_extremes(frame: pd.DataFrame, horizon: int) -> tuple[pd.Series, pd.Series]:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    high_window = pd.concat(
        [high.shift(-offset) for offset in range(1, horizon + 1)],
        axis=1,
    )
    low_window = pd.concat(
        [low.shift(-offset) for offset in range(1, horizon + 1)],
        axis=1,
    )
    complete = high_window.notna().sum(axis=1) == horizon
    future_high = high_window.max(axis=1).where(complete)
    future_low = low_window.min(axis=1).where(complete)
    return future_high, future_low


def mfe_mae_long_metrics(frame: pd.DataFrame, config: TargetConfig) -> dict[str, Any]:
    close = frame["close"].astype(float)
    future_high, future_low = _future_extremes(frame, config.mfe_mae_horizon)
    mfe = future_high / close - 1.0
    mae = future_low / close - 1.0
    valid = mfe.notna() & mae.notna()
    mfe = mfe[valid]
    mae = mae[valid]
    momentum = close.pct_change(3)[valid]
    target = config.mfe_target_bps / 10_000
    stop = config.mae_stop_bps / 10_000
    success = (mfe >= target) & (mae > -stop)
    stopped = mae <= -stop
    ambiguous = (mfe >= target) & stopped
    positive_rate = _mean_bool(success.astype(float))
    noise_rate = _mean_bool((~success & ~stopped).astype(float))
    momentum_lift = _momentum_lift(success.astype(float), momentum)
    balance_error = _balance_error(positive_rate)
    score = (
        abs(momentum_lift)
        * (1.0 - noise_rate)
        * (1.0 - balance_error)
        * min(1.0, len(success) / config.min_samples)
    )
    return {
        "target": f"mfe_mae_long_h{config.mfe_mae_horizon}",
        "family": "mfe_mae_long",
        "horizon_bars": config.mfe_mae_horizon,
        "samples": int(len(success)),
        "positive_rate": _round(positive_rate),
        "neutral_or_noise_rate": _round(noise_rate),
        "tradeable_move_rate": _round(_mean_bool((success | stopped).astype(float))),
        "ambiguous_rate": _round(_mean_bool(ambiguous.astype(float))),
        "mean_abs_return_bps": _round(float(mfe.abs().mean() * 10_000)),
        "median_abs_return_bps": _round(float(mfe.abs().median() * 10_000)),
        "momentum_lift": _round(momentum_lift),
        "balance_error": _round(balance_error),
        "score": _round(score, 6),
    }


def mfe_mae_symmetric_metrics(frame: pd.DataFrame, config: TargetConfig) -> dict[str, Any]:
    close = frame["close"].astype(float)
    future_high, future_low = _future_extremes(frame, config.mfe_mae_horizon)
    long_mfe = future_high / close - 1.0
    long_mae = future_low / close - 1.0
    short_mfe = 1.0 - future_low / close
    short_mae = 1.0 - future_high / close
    valid = long_mfe.notna() & long_mae.notna() & short_mfe.notna() & short_mae.notna()
    target = config.mfe_target_bps / 10_000
    stop = config.mae_stop_bps / 10_000
    long_success = (long_mfe[valid] >= target) & (long_mae[valid] > -stop)
    short_success = (short_mfe[valid] >= target) & (short_mae[valid] > -stop)
    directional = long_success ^ short_success
    labels = long_success[directional].astype(float)
    momentum = close.pct_change(3)[valid][directional]
    positive_rate = _mean_bool(labels)
    nonneutral_rate = _mean_bool(directional.astype(float))
    ambiguous_rate = _mean_bool((long_success & short_success).astype(float))
    momentum_lift = _momentum_lift(labels, momentum)
    balance_error = _balance_error(positive_rate)
    score = (
        abs(momentum_lift)
        * nonneutral_rate
        * (1.0 - balance_error)
        * min(1.0, len(labels) / config.min_samples)
    )
    return {
        "target": f"mfe_mae_symmetric_h{config.mfe_mae_horizon}",
        "family": "mfe_mae_symmetric",
        "horizon_bars": config.mfe_mae_horizon,
        "samples": int(len(labels)),
        "raw_samples": int(valid.sum()),
        "positive_rate": _round(positive_rate),
        "neutral_or_noise_rate": _round(1.0 - nonneutral_rate),
        "tradeable_move_rate": _round(nonneutral_rate),
        "ambiguous_rate": _round(ambiguous_rate),
        "mean_abs_return_bps": 0.0,
        "median_abs_return_bps": 0.0,
        "momentum_lift": _round(momentum_lift),
        "balance_error": _round(balance_error),
        "score": _round(score, 6),
    }


def aggregate_metrics(rows: list[dict[str, Any]], config: TargetConfig) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["target"], []).append(row)

    aggregate: list[dict[str, Any]] = []
    for target, target_rows in grouped.items():
        total_samples = sum(int(row["samples"]) for row in target_rows)
        if total_samples <= 0:
            continue
        weighted: dict[str, float] = {}
        for key in (
            "positive_rate",
            "neutral_or_noise_rate",
            "tradeable_move_rate",
            "ambiguous_rate",
            "mean_abs_return_bps",
            "median_abs_return_bps",
            "momentum_lift",
            "balance_error",
            "score",
        ):
            weighted[key] = sum(
                float(row.get(key, 0.0)) * int(row["samples"])
                for row in target_rows
            ) / total_samples
        first = target_rows[0]
        aggregate.append({
            "target": target,
            "family": first["family"],
            "horizon_bars": first["horizon_bars"],
            "symbols": len(target_rows),
            "samples": total_samples,
            **{key: _round(value, 6 if key == "score" else 4) for key, value in weighted.items()},
        })
    aggregate.sort(key=lambda row: float(row["score"]), reverse=True)
    return aggregate


def analyze_targets(
    bars: dict[str, pd.DataFrame],
    config: TargetConfig,
) -> dict[str, Any]:
    per_symbol: list[dict[str, Any]] = []
    for symbol, frame in bars.items():
        for horizon in config.horizons:
            per_symbol.append({
                "symbol": symbol,
                **close_return_target_metrics(frame, horizon=horizon, config=config),
            })
        per_symbol.append({"symbol": symbol, **mfe_mae_long_metrics(frame, config)})
        per_symbol.append({"symbol": symbol, **mfe_mae_symmetric_metrics(frame, config)})

    aggregate = aggregate_metrics(per_symbol, config)
    current = next(
        (row for row in aggregate if row["target"] == "close_return_h1"),
        None,
    )
    best = aggregate[0] if aggregate else None
    recommendation = "insufficient_data"
    if best and current:
        score_delta = float(best["score"]) - float(current["score"])
        if best["target"] != current["target"] and score_delta > 0.02:
            recommendation = "research_candidate_for_shadow_training_only"
        else:
            recommendation = "keep_current_target_pending_more_evidence"

    return {
        "scope": "offline_ml_target_redesign_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "horizons": list(config.horizons),
            "fee_bps": config.fee_bps,
            "tradeable_bps": config.tradeable_bps,
            "mfe_mae_horizon": config.mfe_mae_horizon,
            "mfe_target_bps": config.mfe_target_bps,
            "mae_stop_bps": config.mae_stop_bps,
            "min_samples": config.min_samples,
        },
        "bar_metadata": {
            "symbols": len(bars),
            "rows": {symbol: len(frame) for symbol, frame in bars.items()},
        },
        "aggregate": aggregate,
        "per_symbol": per_symbol,
        "current_target": current,
        "best_target": best,
        "recommendation": recommendation,
        "limitations": [
            "This is target-label diagnostics, not a trained model comparison.",
            "MFE/MAE labels use OHLC bars and cannot know intrabar event order when both target and stop are touched.",
            "Any target change still requires training, replay, and shadow validation before live influence.",
        ],
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_ml_target_redesign.json"
    aggregate_path = out_dir / "ml_target_aggregate.csv"
    per_symbol_path = out_dir / "ml_target_per_symbol.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    fields = [
        "target",
        "family",
        "horizon_bars",
        "symbols",
        "samples",
        "positive_rate",
        "neutral_or_noise_rate",
        "tradeable_move_rate",
        "ambiguous_rate",
        "mean_abs_return_bps",
        "median_abs_return_bps",
        "momentum_lift",
        "balance_error",
        "score",
    ]
    with aggregate_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["aggregate"])

    per_fields = ["symbol", *fields]
    with per_symbol_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=per_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["per_symbol"])
    return {
        "summary": str(summary_path),
        "aggregate": str(aggregate_path),
        "per_symbol": str(per_symbol_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--tradeable-bps", type=float, default=25.0)
    parser.add_argument("--mfe-target-bps", type=float, default=30.0)
    parser.add_argument("--mae-stop-bps", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = TargetConfig(
        fee_bps=args.fee_bps,
        tradeable_bps=args.tradeable_bps,
        mfe_target_bps=args.mfe_target_bps,
        mae_stop_bps=args.mae_stop_bps,
    )
    bars = normalize_bars(load_cached_bars(args.cache_dir, args.bar_file), parse_symbols(args.symbols))
    summary = analyze_targets(bars, config)
    outputs = write_outputs(summary, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
