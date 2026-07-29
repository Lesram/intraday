#!/usr/bin/env python3
"""Independent observer for platform-truth evidence readiness.

This script is intentionally stricter than the individual evidence builders:
it can pass operationally while still refusing a promotion-grade verdict. That
distinction matters because an off-session paper system can be safe to run but
still lack enough first-class telemetry to make strategy decisions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TELEMETRY = ROOT / "organism_brain" / "strategy_evidence_events.jsonl"
DEFAULT_WAREHOUSE = ROOT / "artifacts" / "phase8_evidence_warehouse" / "warehouse_summary.json"
DEFAULT_PHASE9 = ROOT / "artifacts" / "phase9_shadow_evidence" / "phase9_shadow_summary.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "platform_truth_observer.json"

FIRST_CLASS_FIELDS = (
    "signal_id",
    "strategy_id",
    "engine_version",
    "created_at",
    "evidence_tier",
    "shadow_only",
    "git_sha",
    "runtime_config_hash",
)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    invalid = 0
    if not path.exists():
        return rows, invalid
    with path.open() as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                invalid += 1
                continue
            rows.append(row)
    return rows, invalid


def _tags(row: dict[str, Any]) -> list[str]:
    raw = row.get("matched_filters")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def is_first_class_event(row: dict[str, Any]) -> bool:
    return all(row.get(field) not in (None, "") for field in FIRST_CLASS_FIELDS)


def is_phase9_event(row: dict[str, Any]) -> bool:
    tags = set(_tags(row))
    return is_first_class_event(row) and (
        "phase9_shadow" in tags
        or str(row.get("strategy_id") or "").strip().lower()
        in {
            "etf_intraday_momentum",
            "orb_sip_v2",
            "residual_mean_reversion",
            "eod_reversal_shadow",
        }
    )


def build_observer_report(
    *,
    telemetry_path: Path,
    warehouse_summary_path: Path,
    phase9_summary_path: Path,
) -> dict[str, Any]:
    head = _git_head()
    rows, invalid = _load_jsonl(telemetry_path)
    warehouse = _load_json(warehouse_summary_path)
    phase9 = _load_json(phase9_summary_path)
    first_class_rows = [row for row in rows if is_first_class_event(row)]
    phase9_rows = [row for row in rows if is_phase9_event(row)]
    warehouse_sha = str(warehouse.get("sha") or "")
    warehouse_sha_matches_head = bool(warehouse_sha and warehouse_sha == head)
    count_reconciliation = warehouse.get("count_reconciliation") or {}
    warehouse_counts_ok = bool(count_reconciliation.get("ok"))
    phase9_counts = phase9.get("counts") or {}
    phase9_summary_events = int(phase9_counts.get("phase9_events") or 0)

    promotion_grade = (
        invalid == 0
        and bool(first_class_rows)
        and bool(phase9_rows)
        and phase9_summary_events > 0
        and warehouse_sha_matches_head
        and warehouse_counts_ok
        and not bool(warehouse.get("promotion_authorized"))
    )
    blockers: list[str] = []
    if invalid:
        blockers.append("invalid_strategy_evidence_jsonl")
    if not first_class_rows:
        blockers.append("no_first_class_strategy_events")
    if not phase9_rows or phase9_summary_events <= 0:
        blockers.append("no_phase9_forward_events")
    if not warehouse_sha_matches_head:
        blockers.append("warehouse_sha_not_current_head")
    if not warehouse_counts_ok:
        blockers.append("warehouse_counts_not_reconciled")
    if warehouse.get("promotion_authorized"):
        blockers.append("warehouse_unexpectedly_authorizes_promotion")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "platform_truth_observer",
        "git_head": head,
        "telemetry_path": str(telemetry_path),
        "warehouse_summary_path": str(warehouse_summary_path),
        "phase9_summary_path": str(phase9_summary_path),
        "counts": {
            "raw_strategy_events": len(rows),
            "invalid_strategy_events": invalid,
            "first_class_events": len(first_class_rows),
            "phase9_events": len(phase9_rows),
            "phase9_summary_events": phase9_summary_events,
        },
        "warehouse": {
            "sha": warehouse_sha,
            "sha_matches_head": warehouse_sha_matches_head,
            "count_reconciliation_ok": warehouse_counts_ok,
            "promotion_authorized": bool(warehouse.get("promotion_authorized")),
        },
        "promotion_grade": promotion_grade,
        "verdict": "promotion_grade" if promotion_grade else "not_promotion_grade",
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--warehouse-summary", type=Path, default=DEFAULT_WAREHOUSE)
    parser.add_argument("--phase9-summary", type=Path, default=DEFAULT_PHASE9)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-promotion-grade",
        action="store_true",
        help="Exit non-zero when the observer cannot issue a promotion-grade verdict.",
    )
    args = parser.parse_args()

    report = build_observer_report(
        telemetry_path=args.telemetry_path,
        warehouse_summary_path=args.warehouse_summary,
        phase9_summary_path=args.phase9_summary,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.require_promotion_grade and not report["promotion_grade"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
