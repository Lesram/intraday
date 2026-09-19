"""Create replay-plan artifacts from Phase 8 replay candidates.

This does not run replay and does not change live behavior. It turns the
post-close replay queue into explicit commands so the next research step is
auditable instead of conversational.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "artifacts" / "phase8_evidence_warehouse" / "replay_candidates.json"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase8_replay_plan"
FILTER_REPLAY_SCENARIO_TAGS = frozenset({
    "alpha_breakout_chop",
    "alpha_breakout_trending_down",
    "alpha_breakout_chop_or_trending_down",
    "conf_45_55",
    "conf_55_65",
    "conf_45_65",
    "inverse_etf_alpha_breakout",
    "inverse_etf_alpha_breakout_trending_down",
    "inverse_etf_alpha_breakout_chop_or_trending_down",
})


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def load_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("replay candidate file must contain a JSON array")
    return [row for row in payload if isinstance(row, dict)]


def _symbol_commands(symbol: str, out_dir: Path) -> list[str]:
    symbol_dir = out_dir / symbol
    return [
        (
            "./venv/bin/python scripts/phase3_timeframe_scout.py "
            f"--symbols {symbol} --out-dir {symbol_dir / 'timeframe_scout'}"
        ),
        (
            "./venv/bin/python scripts/phase4_shadow_target_model.py "
            f"--symbols {symbol} --out-dir {symbol_dir / 'shadow_target_model'}"
        ),
    ]


def _safe_dir_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _filter_commands(filter_tag: str, out_dir: Path) -> list[str]:
    if filter_tag not in FILTER_REPLAY_SCENARIO_TAGS:
        return []
    filter_dir = out_dir / f"filter_{_safe_dir_name(filter_tag)}"
    return [
        (
            "./venv/bin/python scripts/phase3_candidate_filter_replay.py "
            f"--scenarios skip_{filter_tag} "
            f"--out-dir {filter_dir / 'counterfactual'}"
        ),
        (
            "./venv/bin/python scripts/phase3_candidate_filter_fill_replay.py "
            f"--scenarios candidate_{filter_tag} "
            f"--out-dir {filter_dir / 'fill_path'}"
        ),
    ]


def build_replay_plan(candidates: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    plan_items: list[dict[str, Any]] = []
    for candidate in candidates:
        if int(candidate.get("promotion_authorized") or 0) != 0:
            continue
        if candidate.get("required_next_step") != "replay_before_any_live_change":
            continue
        candidate_type = str(candidate.get("candidate_type") or "")
        symbol = str(candidate.get("symbol") or "").upper()
        filter_tag = str(candidate.get("filter_tag") or "")
        if candidate_type == "symbol" and symbol:
            commands = _symbol_commands(symbol, out_dir)
        elif candidate_type == "filter" and filter_tag:
            commands = _filter_commands(filter_tag, out_dir)
        else:
            commands = []
        plan_items.append({
            "candidate_id": candidate.get("candidate_id"),
            "candidate_type": candidate_type,
            "symbol": symbol,
            "filter_tag": filter_tag,
            "reason": candidate.get("reason"),
            "evidence": {
                "joined_outcomes": candidate.get("joined_outcomes"),
                "positive_directional_rate": candidate.get("positive_directional_rate"),
                "avg_forward_directional_bps": candidate.get("avg_forward_directional_bps"),
                "realized_rows": candidate.get("realized_rows"),
                "realized_total_pnl": candidate.get("realized_total_pnl"),
                "avg_realized_return_bps": candidate.get("avg_realized_return_bps"),
            },
            "commands": commands,
            "required_next_step": "run_replay_and_review_before_any_live_change",
            "promotion_authorized": False,
        })
    return {
        "scope": "phase8_replay_plan_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "sha": _git("rev-parse", "HEAD"),
        "candidate_count": len(plan_items),
        "promotion_authorized": False,
        "plan_items": plan_items,
    }


def render_plan(plan: dict[str, Any]) -> str:
    lines = [
        "# Phase 8 Replay Plan",
        "",
        f"Generated: {plan['generated_at']}",
        f"Branch: `{plan['branch']}`",
        f"SHA: `{plan['sha']}`",
        "",
        "## Guardrail",
        "",
        "- Live promotion authorized: `false`",
        "- Every command below is replay/research only.",
        "",
        "## Candidates",
        "",
    ]
    if not plan["plan_items"]:
        lines.append("- None.")
    for item in plan["plan_items"]:
        label = item["symbol"] or item["filter_tag"] or item["candidate_id"]
        lines.extend([
            f"### `{label}`",
            "",
            f"- Candidate: `{item['candidate_id']}`",
            f"- Reason: `{item['reason']}`",
            f"- Evidence: `{item['evidence']}`",
            "- Commands:",
            "",
        ])
        if not item["commands"]:
            lines.append("  - No direct replay command generated for this candidate type yet.")
        for command in item["commands"]:
            lines.append(f"  - `{command}`")
        lines.append("")
    return "\n".join(lines)


def write_outputs(plan: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "replay_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n"
    )
    (out_dir / "PHASE8_REPLAY_PLAN.md").write_text(render_plan(plan))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_replay_plan(load_candidates(args.candidates), args.out_dir)
    write_outputs(plan, args.out_dir)
    print(
        "Phase 8 replay plan: "
        f"candidates={plan['candidate_count']} "
        f"out_dir={args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
