"""Phase 5 candidate-filter shadow outcome join.

Joins paper-session candidate-filter shadow telemetry to subsequent OHLCV bars
so Phase 5 can measure observed opportunity quality before any no-entry gate is
considered. This is evidence-only and does not change live trading behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
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
from scripts.phase4_candidate_shadow_analysis import (  # noqa: E402
    DEFAULT_TELEMETRY_PATH,
    load_shadow_events,
)

DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase5_shadow_outcome_join"


@dataclass(frozen=True)
class ShadowOutcomeConfig:
    horizons: tuple[int, ...] = (1, 5, 10)
    min_events_per_filter: int = 30
    min_outcomes_per_filter: int = 20
    max_event_to_bar_gap_seconds: float = 120.0


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def _finite_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw.strip():
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def parse_horizons(raw: str | None) -> tuple[int, ...]:
    if raw is None:
        return (1, 5, 10)
    values: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        value = int(text)
        if value <= 0:
            raise ValueError("horizons must be positive integers")
        values.append(value)
    if not values:
        raise ValueError("horizon list cannot be empty")
    return tuple(dict.fromkeys(values))


def _event_timestamp(event: dict[str, Any]) -> pd.Timestamp | None:
    raw = event.get("timestamp")
    if raw is None:
        return None
    ts = pd.to_datetime(str(raw), utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _matching_bar_index(
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    max_gap_seconds: float,
) -> tuple[int | None, str, float]:
    timestamps = frame["timestamp"]
    idx = int(timestamps.searchsorted(timestamp, side="left"))
    if idx >= len(frame):
        return None, "no_bar_at_or_after_event", 0.0
    matched_ts = pd.Timestamp(timestamps.iloc[idx])
    gap_seconds = float((matched_ts - timestamp).total_seconds())
    if gap_seconds < 0 or gap_seconds > max_gap_seconds:
        return None, "bar_gap_too_large", gap_seconds
    return idx, "matched", gap_seconds


def join_event_to_bars(
    event: dict[str, Any],
    bars: dict[str, pd.DataFrame],
    config: ShadowOutcomeConfig,
) -> list[dict[str, Any]]:
    symbol = str(event.get("symbol") or "").upper()
    tags = _tags(event.get("matched_filters"))
    timestamp = _event_timestamp(event)
    base = {
        "event_line": event.get("_line_number", ""),
        "event_timestamp": str(event.get("timestamp") or ""),
        "symbol": symbol,
        "regime": str(event.get("regime") or "unknown"),
        "direction": _round(_finite_float(event.get("direction"), 1.0)),
        "confidence": _round(_finite_float(event.get("confidence"))),
        "matched_filters": ",".join(tags),
    }
    if not tags:
        return [{**base, "horizon_bars": "", "status": "no_matched_filters"}]
    if timestamp is None:
        return [{**base, "horizon_bars": "", "status": "invalid_timestamp"}]
    frame = bars.get(symbol)
    if frame is None or frame.empty:
        return [{**base, "horizon_bars": "", "status": "symbol_missing_from_bars"}]

    idx, status, gap_seconds = _matching_bar_index(
        frame,
        timestamp,
        config.max_event_to_bar_gap_seconds,
    )
    if idx is None:
        return [{**base, "horizon_bars": "", "status": status, "bar_gap_seconds": _round(gap_seconds)}]

    entry_close = float(frame["close"].iloc[idx])
    direction = _finite_float(event.get("direction"), 1.0)
    direction = -1.0 if direction < 0 else 1.0
    rows: list[dict[str, Any]] = []
    for horizon in config.horizons:
        future_idx = idx + horizon
        if future_idx >= len(frame):
            rows.append({
                **base,
                "horizon_bars": horizon,
                "status": "insufficient_future_bars",
                "bar_gap_seconds": _round(gap_seconds),
                "entry_close": _round(entry_close),
            })
            continue
        future_close = float(frame["close"].iloc[future_idx])
        raw_return = future_close / entry_close - 1.0
        directional_bps = direction * raw_return * 10_000
        rows.append({
            **base,
            "horizon_bars": horizon,
            "status": "joined",
            "bar_gap_seconds": _round(gap_seconds),
            "entry_bar_timestamp": pd.Timestamp(frame["timestamp"].iloc[idx]).isoformat(),
            "future_bar_timestamp": pd.Timestamp(frame["timestamp"].iloc[future_idx]).isoformat(),
            "entry_close": _round(entry_close),
            "future_close": _round(future_close),
            "raw_return_bps": _round(raw_return * 10_000),
            "directional_return_bps": _round(directional_bps),
        })
    return rows


def _summarize_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "outcomes": 0,
            "mean_directional_bps": 0.0,
            "median_directional_bps": 0.0,
            "win_rate": 0.0,
            "total_directional_bps": 0.0,
        }
    series = pd.Series(values, dtype=float)
    return {
        "outcomes": len(values),
        "mean_directional_bps": _round(float(series.mean())),
        "median_directional_bps": _round(float(series.median())),
        "win_rate": _round(float((series > 0).mean())),
        "total_directional_bps": _round(float(series.sum())),
    }


def summarize_joined_rows(
    events: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    config: ShadowOutcomeConfig,
) -> dict[str, Any]:
    valid_events = [event for event in events if not event.get("_invalid_json")]
    event_status_counts = Counter(str(row["status"]) for row in rows)
    values_by_filter_horizon: dict[tuple[str, int], list[float]] = defaultdict(list)
    event_counts_by_filter = Counter()
    for event in valid_events:
        for tag in _tags(event.get("matched_filters")):
            event_counts_by_filter[tag] += 1
    for row in rows:
        if row.get("status") != "joined":
            continue
        horizon = int(row["horizon_bars"])
        for tag in str(row.get("matched_filters") or "").split(","):
            if tag:
                values_by_filter_horizon[(tag, horizon)].append(
                    float(row["directional_return_bps"])
                )

    filter_horizon_summary: list[dict[str, Any]] = []
    for tag in sorted(event_counts_by_filter):
        for horizon in config.horizons:
            values = values_by_filter_horizon.get((tag, horizon), [])
            outcome_summary = _summarize_values(values)
            filter_horizon_summary.append({
                "filter": tag,
                "horizon_bars": horizon,
                "events": int(event_counts_by_filter[tag]),
                "sample_gate_passed": event_counts_by_filter[tag] >= config.min_events_per_filter,
                "outcome_gate_passed": len(values) >= config.min_outcomes_per_filter,
                **outcome_summary,
            })

    joined_outcomes = sum(row["outcomes"] for row in filter_horizon_summary)
    if not valid_events:
        recommendation = "await_live_shadow_session"
    elif joined_outcomes == 0:
        recommendation = "collect_matching_bar_outcomes"
    elif not all(
        row["sample_gate_passed"] and row["outcome_gate_passed"]
        for row in filter_horizon_summary
    ):
        recommendation = "insufficient_shadow_sample"
    else:
        recommendation = "eligible_for_replay_review_not_live_promotion"

    return {
        "scope": "phase5_shadow_outcome_join_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "horizons": list(config.horizons),
            "min_events_per_filter": config.min_events_per_filter,
            "min_outcomes_per_filter": config.min_outcomes_per_filter,
            "max_event_to_bar_gap_seconds": config.max_event_to_bar_gap_seconds,
        },
        "total_rows": len(events),
        "valid_events": len(valid_events),
        "event_status_counts": dict(event_status_counts),
        "filter_horizon_summary": filter_horizon_summary,
        "recommendation": recommendation,
        "live_behavior": "unchanged",
        "limitations": [
            "This joins shadow candidates to bars, not broker fills.",
            "Cached bars must cover the telemetry timestamps and symbols.",
            "Passing sample gates only permits replay review, not live promotion.",
        ],
    }


def run_outcome_join(
    events: list[dict[str, Any]],
    bars: dict[str, pd.DataFrame],
    config: ShadowOutcomeConfig,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.get("_invalid_json"):
            rows.append({
                "event_line": event.get("_line_number", ""),
                "event_timestamp": "",
                "symbol": "",
                "matched_filters": "",
                "horizon_bars": "",
                "status": "invalid_json",
            })
            continue
        rows.extend(join_event_to_bars(event, bars, config))
    summary = summarize_joined_rows(events, rows, config)
    summary["event_outcomes"] = rows
    return summary


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_shadow_outcome_join.json"
    outcomes_path = out_dir / "shadow_event_outcomes.csv"
    filter_path = out_dir / "shadow_filter_horizon_summary.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    outcome_fields = [
        "event_line",
        "event_timestamp",
        "symbol",
        "regime",
        "direction",
        "confidence",
        "matched_filters",
        "horizon_bars",
        "status",
        "bar_gap_seconds",
        "entry_bar_timestamp",
        "future_bar_timestamp",
        "entry_close",
        "future_close",
        "raw_return_bps",
        "directional_return_bps",
    ]
    with outcomes_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=outcome_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["event_outcomes"])

    filter_fields = [
        "filter",
        "horizon_bars",
        "events",
        "sample_gate_passed",
        "outcome_gate_passed",
        "outcomes",
        "mean_directional_bps",
        "median_directional_bps",
        "win_rate",
        "total_directional_bps",
    ]
    with filter_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=filter_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["filter_horizon_summary"])
    return {
        "summary": str(summary_path),
        "event_outcomes": str(outcomes_path),
        "filter_horizon_summary": str(filter_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--horizons", default="1,5,10")
    parser.add_argument("--min-events-per-filter", type=int, default=30)
    parser.add_argument("--min-outcomes-per-filter", type=int, default=20)
    parser.add_argument("--max-event-to-bar-gap-seconds", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = ShadowOutcomeConfig(
        horizons=parse_horizons(args.horizons),
        min_events_per_filter=args.min_events_per_filter,
        min_outcomes_per_filter=args.min_outcomes_per_filter,
        max_event_to_bar_gap_seconds=args.max_event_to_bar_gap_seconds,
    )
    events = load_shadow_events(args.telemetry_path)
    bars = normalize_bars(
        load_cached_bars(args.cache_dir, args.bar_file),
        parse_symbols(args.symbols),
    )
    summary = run_outcome_join(events, bars, config)
    outputs = write_outputs(summary, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
