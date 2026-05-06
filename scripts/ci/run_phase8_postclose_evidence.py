"""Run and validate the Phase 8 post-close evidence loop.

This wrapper is intentionally separate from the warehouse builder so scheduled
jobs can fail loudly when a post-close run is missing required evidence. GitHub
CI can run it without DB access; local paper post-close automation should run
with ``--include-db --require-db``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase8_evidence_warehouse"


def validate_postclose_summary(summary: dict[str, Any], *, require_db: bool) -> list[str]:
    errors: list[str] = []
    if summary.get("promotion_authorized") is not False:
        errors.append("top-level promotion_authorized must be false")

    counts = summary.get("counts") or {}
    if require_db:
        for key in ("db_orders", "db_executions", "db_realized_trades"):
            if int(counts.get(key) or 0) <= 0:
                errors.append(f"{key} must be non-zero when --require-db is set")

    db_extract = summary.get("db_extract") or {}
    research = db_extract.get("research_summaries") or {}
    if int(research.get("promotion_authorized_rows") or 0) != 0:
        errors.append("research summaries must not authorize promotion")

    outputs = db_extract.get("research_outputs") or {}
    if outputs.get("post_close_verdict") != "no_live_promotion_replay_required":
        errors.append("post-close verdict must require replay before promotion")

    for candidate in outputs.get("replay_candidates") or []:
        if int(candidate.get("promotion_authorized") or 0) != 0:
            errors.append(f"{candidate.get('candidate_id')} authorized promotion")
        if candidate.get("required_next_step") != "replay_before_any_live_change":
            errors.append(f"{candidate.get('candidate_id')} missing replay gate")
    return errors


def write_run_summary(
    out_dir: Path,
    *,
    summary: dict[str, Any],
    errors: list[str],
    command: list[str],
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": not errors,
        "errors": errors,
        "command": command,
        "warehouse_summary": str(out_dir / "warehouse_summary.json"),
        "postclose_report": str(out_dir / "PHASE8_POST_CLOSE_RESEARCH_REPORT.md"),
        "replay_candidates": str(out_dir / "replay_candidates.json"),
        "counts": summary.get("counts", {}),
        "research": (summary.get("db_extract") or {}).get("research_summaries", {}),
    }
    (out_dir / "postclose_run_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--include-db", action="store_true")
    parser.add_argument("--require-db", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = [
        sys.executable,
        str(ROOT / "scripts" / "phase8_evidence_warehouse.py"),
        "--out-dir",
        str(args.out_dir),
    ]
    if args.include_db:
        command.append("--include-db")

    subprocess.run(command, cwd=ROOT, check=True)
    summary_path = args.out_dir / "warehouse_summary.json"
    summary = json.loads(summary_path.read_text())
    errors = validate_postclose_summary(summary, require_db=args.require_db)
    write_run_summary(args.out_dir, summary=summary, errors=errors, command=command)

    if errors:
        print("Phase 8 post-close evidence: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    counts = summary.get("counts", {})
    research = (summary.get("db_extract") or {}).get("research_summaries", {})
    print(
        "Phase 8 post-close evidence: PASS "
        f"events={counts.get('events')} "
        f"accounting={counts.get('realized_trade_accounting')} "
        f"replay_candidates={research.get('replay_candidate_count')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
