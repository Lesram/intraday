"""Phase 6 strategy evidence warehouse and post-close research report.

Builds normalized, append-friendly evidence artifacts from live shadow
telemetry plus cached OHLCV bars. This is evidence/advisory-only: it never
changes ranking, sizing, order submission, or live gates.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
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
from scripts.phase4_candidate_shadow_analysis import load_shadow_events  # noqa: E402
from scripts.phase5_shadow_outcome_join import (  # noqa: E402
    ShadowOutcomeConfig,
    parse_horizons,
    run_outcome_join,
    write_outputs as write_outcome_join_outputs,
)

DEFAULT_TELEMETRY_PATH = ROOT / "organism_brain" / "strategy_evidence_events.jsonl"
FALLBACK_TELEMETRY_PATH = ROOT / "organism_brain" / "candidate_filter_shadow_telemetry.jsonl"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase6_strategy_evidence"
WAREHOUSE_TAG_ALL = "all_candidates"
WAREHOUSE_TAG_UNTAGGED = "untagged"


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


def resolve_telemetry_path(path: Path) -> Path:
    if path.exists():
        return path
    if path == DEFAULT_TELEMETRY_PATH and FALLBACK_TELEMETRY_PATH.exists():
        return FALLBACK_TELEMETRY_PATH
    return path


def expand_events_for_warehouse(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for event in events:
        if event.get("_invalid_json"):
            expanded.append(event)
            continue
        tags = _tags(event.get("matched_filters"))
        if not tags:
            tags = [WAREHOUSE_TAG_UNTAGGED]
        full_tags = [WAREHOUSE_TAG_ALL]
        for tag in tags:
            if tag not in full_tags:
                full_tags.append(tag)
        copy = dict(event)
        copy["matched_filters"] = full_tags
        copy["warehouse_original_filters"] = tags
        expanded.append(copy)
    return expanded


def flatten_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_line": event.get("_line_number", ""),
        "timestamp": event.get("timestamp", ""),
        "tick": event.get("tick", ""),
        "symbol": str(event.get("symbol", "")).upper(),
        "regime": event.get("regime", ""),
        "direction": _finite_float(event.get("direction")),
        "confidence": _finite_float(event.get("confidence")),
        "effective_confidence": _finite_float(event.get("effective_confidence")),
        "breakout_score": _finite_float(event.get("breakout_score")),
        "predicted_return": _finite_float(event.get("predicted_return")),
        "ranking_score": _finite_float(event.get("ranking_score")),
        "entry_source": event.get("entry_source", ""),
        "matched_filters": ",".join(_tags(event.get("matched_filters"))),
        "warehouse_original_filters": ",".join(_tags(event.get("warehouse_original_filters"))),
        "live_pipeline_candidate": bool(event.get("live_pipeline_candidate", True)),
    }


def advisory_action(
    row: dict[str, Any],
    *,
    min_mean_directional_bps: float,
    min_win_rate: float,
) -> str:
    if not row.get("sample_gate_passed") or not row.get("outcome_gate_passed"):
        return "collect_more_shadow_sample"
    mean_bps = _finite_float(row.get("mean_directional_bps"))
    win_rate = _finite_float(row.get("win_rate"))
    if mean_bps < min_mean_directional_bps or win_rate < min_win_rate:
        return "reject_or_redesign"
    return "eligible_for_replay_review"


def build_advisory_policy(
    filter_horizon_summary: list[dict[str, Any]],
    *,
    primary_horizon: int,
    min_mean_directional_bps: float,
    min_win_rate: float,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for row in filter_horizon_summary:
        if int(row.get("horizon_bars", 0)) != primary_horizon:
            continue
        action = advisory_action(
            row,
            min_mean_directional_bps=min_mean_directional_bps,
            min_win_rate=min_win_rate,
        )
        actions.append({
            "filter": row.get("filter"),
            "primary_horizon_bars": primary_horizon,
            "shadow_action": action,
            "live_behavior": "unchanged",
            "events": int(row.get("events", 0)),
            "outcomes": int(row.get("outcomes", 0)),
            "mean_directional_bps": _finite_float(row.get("mean_directional_bps")),
            "win_rate": _finite_float(row.get("win_rate")),
            "sample_gate_passed": bool(row.get("sample_gate_passed")),
            "outcome_gate_passed": bool(row.get("outcome_gate_passed")),
        })

    return {
        "scope": "phase6_realtime_advisory_policy_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_horizon_bars": primary_horizon,
        "thresholds": {
            "min_mean_directional_bps": min_mean_directional_bps,
            "min_win_rate": min_win_rate,
        },
        "actions": sorted(actions, key=lambda item: str(item["filter"])),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_report(summary: dict[str, Any], policy: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 Post-Close Strategy Research Report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Verdict",
        "",
        "This report is advisory-only. It does not change live ranking, sizing, gates, or orders.",
        "",
        "## Evidence",
        "",
        f"- Telemetry rows: `{summary['telemetry_rows']}`",
        f"- Valid events: `{summary['valid_events']}`",
        f"- Joined outcome rows: `{summary['joined_outcome_rows']}`",
        f"- Outcome recommendation: `{summary['outcome_recommendation']}`",
        "",
        "## Advisory Actions",
        "",
        "| Filter | Action | Events | Outcomes | Mean bps | Win rate |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for action in policy["actions"]:
        lines.append(
            "| `{filter}` | `{shadow_action}` | `{events}` | `{outcomes}` | "
            "`{mean_directional_bps:.4f}` | `{win_rate:.4f}` |".format(**action)
        )

    lines.extend([
        "",
        "## Promotion Rule",
        "",
        "Only `eligible_for_replay_review` may advance to replay. Nothing in this "
        "report authorizes live behavior changes.",
        "",
    ])
    return "\n".join(lines)


def build_warehouse(
    *,
    telemetry_path: Path,
    bars: dict[str, pd.DataFrame],
    config: ShadowOutcomeConfig,
    primary_horizon: int,
    min_mean_directional_bps: float,
    min_win_rate: float,
) -> dict[str, Any]:
    raw_events = load_shadow_events(telemetry_path)
    warehouse_events = expand_events_for_warehouse(raw_events)
    outcome_summary = run_outcome_join(warehouse_events, bars, config)
    policy = build_advisory_policy(
        outcome_summary["filter_horizon_summary"],
        primary_horizon=primary_horizon,
        min_mean_directional_bps=min_mean_directional_bps,
        min_win_rate=min_win_rate,
    )
    joined_rows = [
        row for row in outcome_summary["event_outcomes"]
        if row.get("status") == "joined"
    ]
    return {
        "summary": {
            "scope": "phase6_strategy_evidence_warehouse_no_live_behavior_change",
            "generated_at": datetime.now(UTC).isoformat(),
            "telemetry_path": str(telemetry_path),
            "telemetry_rows": len(raw_events),
            "valid_events": outcome_summary["valid_events"],
            "joined_outcome_rows": len(joined_rows),
            "outcome_recommendation": outcome_summary["recommendation"],
            "event_status_counts": outcome_summary["event_status_counts"],
            "filter_horizon_summary": outcome_summary["filter_horizon_summary"],
            "live_behavior": "unchanged",
        },
        "events": [flatten_event(event) for event in warehouse_events if not event.get("_invalid_json")],
        "outcomes": outcome_summary["event_outcomes"],
        "policy": policy,
        "outcome_summary": outcome_summary,
    }


def write_warehouse_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "strategy_evidence_events.csv"
    outcomes_path = out_dir / "strategy_evidence_outcomes.csv"
    summary_path = out_dir / "strategy_evidence_summary.json"
    policy_path = out_dir / "realtime_advisory_policy.json"
    report_path = out_dir / "POSTCLOSE_RESEARCH_REPORT.md"

    write_csv(events_path, payload["events"])
    write_csv(outcomes_path, payload["outcomes"])
    summary_path.write_text(json.dumps(payload["summary"], indent=2, sort_keys=True) + "\n")
    policy_path.write_text(json.dumps(payload["policy"], indent=2, sort_keys=True) + "\n")
    report_path.write_text(render_report(payload["summary"], payload["policy"]) + "\n")

    outcome_dir = out_dir / "outcome_join"
    outcome_outputs = write_outcome_join_outputs(payload["outcome_summary"], outcome_dir)
    return {
        "events": str(events_path),
        "outcomes": str(outcomes_path),
        "summary": str(summary_path),
        "advisory_policy": str(policy_path),
        "postclose_report": str(report_path),
        **{f"outcome_{key}": value for key, value in outcome_outputs.items()},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--horizons", default="1,5,10")
    parser.add_argument("--primary-horizon", type=int, default=5)
    parser.add_argument("--min-events-per-filter", type=int, default=30)
    parser.add_argument("--min-outcomes-per-filter", type=int, default=20)
    parser.add_argument("--min-mean-directional-bps", type=float, default=1.0)
    parser.add_argument("--min-win-rate", type=float, default=0.50)
    parser.add_argument("--max-event-to-bar-gap-seconds", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    telemetry_path = resolve_telemetry_path(args.telemetry_path)
    config = ShadowOutcomeConfig(
        horizons=parse_horizons(args.horizons),
        min_events_per_filter=args.min_events_per_filter,
        min_outcomes_per_filter=args.min_outcomes_per_filter,
        max_event_to_bar_gap_seconds=args.max_event_to_bar_gap_seconds,
    )
    bars = normalize_bars(
        load_cached_bars(args.cache_dir, args.bar_file),
        parse_symbols(args.symbols),
    )
    payload = build_warehouse(
        telemetry_path=telemetry_path,
        bars=bars,
        config=config,
        primary_horizon=args.primary_horizon,
        min_mean_directional_bps=args.min_mean_directional_bps,
        min_win_rate=args.min_win_rate,
    )
    outputs = write_warehouse_outputs(payload, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
