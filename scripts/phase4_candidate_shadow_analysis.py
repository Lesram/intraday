"""Phase 4 candidate-filter shadow telemetry analyzer.

Reads the JSONL produced by candidate-filter shadow telemetry and summarizes
whether the Phase 3 candidate no-entry gates have enough live shadow evidence
to justify a replay/live promotion discussion. This is evidence-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TELEMETRY_PATH = ROOT / "organism_brain" / "candidate_filter_shadow_telemetry.jsonl"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase4_candidate_shadow_analysis"
OUTCOME_FIELDS: tuple[str, ...] = (
    "shadow_pnl_bps",
    "outcome_bps",
    "forward_return_bps",
    "pnl_bps",
    "pnl",
)


@dataclass(frozen=True)
class CandidateShadowAnalysisConfig:
    min_events: int = 30
    min_outcome_events: int = 20


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def _finite_float(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _as_filters(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw.strip():
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def load_shadow_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open() as fh:
        for line_number, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                events.append({"_invalid_json": True, "_line_number": line_number})
                continue
            if isinstance(raw, dict):
                raw["_line_number"] = line_number
                events.append(raw)
    return events


def _outcome_value(event: dict[str, Any]) -> tuple[str, float] | None:
    for field in OUTCOME_FIELDS:
        value = _finite_float(event.get(field))
        if value is not None:
            return field, value
    return None


def _confidence_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.45:
        return "<0.45"
    if value < 0.55:
        return "[0.45,0.55)"
    if value < 0.65:
        return "[0.55,0.65)"
    return ">=0.65"


def _counter_table(counter: Counter[str], *, limit: int = 20) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def _outcome_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "events_with_outcome": 0,
            "mean_outcome": 0.0,
            "win_rate": 0.0,
            "total_outcome": 0.0,
        }
    wins = sum(1 for value in values if value > 0)
    return {
        "events_with_outcome": len(values),
        "mean_outcome": _round(sum(values) / len(values)),
        "win_rate": _round(wins / len(values)),
        "total_outcome": _round(sum(values)),
    }


def summarize_shadow_events(
    events: list[dict[str, Any]],
    config: CandidateShadowAnalysisConfig,
) -> dict[str, Any]:
    invalid_rows = sum(1 for event in events if event.get("_invalid_json"))
    valid_events = [event for event in events if not event.get("_invalid_json")]
    filter_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    outcome_field_counts: Counter[str] = Counter()
    outcomes_by_filter: dict[str, list[float]] = defaultdict(list)

    for event in valid_events:
        tags = _as_filters(event.get("matched_filters"))
        confidence = _finite_float(event.get("confidence"))
        confidence_counts[_confidence_bucket(confidence)] += 1
        symbol = str(event.get("symbol") or "unknown")
        regime = str(event.get("regime") or "unknown")
        symbol_counts[symbol] += 1
        regime_counts[regime] += 1
        outcome = _outcome_value(event)
        for tag in tags:
            filter_counts[tag] += 1
            if outcome is not None:
                outcome_field, value = outcome
                outcome_field_counts[outcome_field] += 1
                outcomes_by_filter[tag].append(value)

    filter_rows: list[dict[str, Any]] = []
    for tag, count in filter_counts.most_common():
        row = {
            "filter": tag,
            "events": count,
            "sample_gate_passed": count >= config.min_events,
            **_outcome_summary(outcomes_by_filter[tag]),
        }
        row["outcome_gate_passed"] = row["events_with_outcome"] >= config.min_outcome_events
        filter_rows.append(row)

    if not valid_events:
        recommendation = "await_live_shadow_session"
    elif not any(row["events_with_outcome"] for row in filter_rows):
        recommendation = "collect_outcomes_before_promotion"
    elif not all(row["sample_gate_passed"] and row["outcome_gate_passed"] for row in filter_rows):
        recommendation = "insufficient_shadow_sample"
    else:
        recommendation = "eligible_for_replay_review_not_live_promotion"

    return {
        "scope": "phase4_candidate_shadow_analysis_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "min_events": config.min_events,
            "min_outcome_events": config.min_outcome_events,
        },
        "total_rows": len(events),
        "valid_events": len(valid_events),
        "invalid_rows": invalid_rows,
        "filters": filter_rows,
        "symbols": _counter_table(symbol_counts),
        "regimes": _counter_table(regime_counts),
        "confidence_buckets": _counter_table(confidence_counts),
        "outcome_fields": _counter_table(outcome_field_counts),
        "recommendation": recommendation,
        "live_behavior": "unchanged",
        "limitations": [
            "Telemetry rows are candidate observations; they are not filled trades.",
            "Rows without outcome fields can only prove exposure, not expectancy.",
            "Promotion still requires replay and a live shadow session with outcome joins.",
        ],
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_candidate_shadow_analysis.json"
    filters_path = out_dir / "candidate_shadow_filter_summary.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    fields = [
        "filter",
        "events",
        "sample_gate_passed",
        "events_with_outcome",
        "outcome_gate_passed",
        "mean_outcome",
        "win_rate",
        "total_outcome",
    ]
    with filters_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["filters"])
    return {"summary": str(summary_path), "filters": str(filters_path)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-events", type=int, default=30)
    parser.add_argument("--min-outcome-events", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = CandidateShadowAnalysisConfig(
        min_events=args.min_events,
        min_outcome_events=args.min_outcome_events,
    )
    events = load_shadow_events(args.telemetry_path)
    summary = summarize_shadow_events(events, config)
    outputs = write_outputs(summary, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
