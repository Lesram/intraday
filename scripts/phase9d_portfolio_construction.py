"""Phase 9D portfolio construction report.

Consumes the Phase 9 strategy league table and produces an evidence-only
portfolio construction verdict.  This script never authorizes promotion and
never changes ranking, sizing, orders, gates, or live runtime state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.organism.evidence.portfolio_construction import (  # noqa: E402
    PortfolioConstructionConfig,
    construct_strategy_portfolio,
)

DEFAULT_LEAGUE_PATH = (
    ROOT / "artifacts" / "phase9_shadow_evidence" / "phase9_strategy_league.json"
)
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase9d_portfolio_construction"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text().strip()
    if not text:
        return default
    return json.loads(text)


def load_keyed_float_map(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    raw = load_json(path, {})
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(key): float(value) for key, value in raw.items()}


def build_phase9d_report(
    *,
    league_path: Path = DEFAULT_LEAGUE_PATH,
    betas: dict[str, float] | None = None,
    correlations: dict[str, float] | None = None,
    config: PortfolioConstructionConfig | None = None,
) -> dict[str, Any]:
    league_rows = load_json(league_path, [])
    if not isinstance(league_rows, list):
        raise ValueError(f"{league_path} must contain a JSON array")
    construction = construct_strategy_portfolio(
        league_rows,
        config=config,
        betas=betas or {},
        correlations=correlations or {},
    )
    return {
        **construction,
        "generated_at": datetime.now(UTC).isoformat(),
        "league_path": str(league_path),
        "live_promotion_authorized": False,
        "required_next_step": _required_next_step(construction),
    }


def write_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "phase9d_portfolio_summary.json"
    report_path = out_dir / "PHASE9D_PORTFOLIO_CONSTRUCTION_REPORT.md"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    report_path.write_text(render_report(payload) + "\n")
    return {"summary": str(summary_path), "report": str(report_path)}


def render_report(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Phase 9D Portfolio Construction Report",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Verdict",
        "",
        f"- Portfolio authorized: `{str(payload['portfolio_authorized']).lower()}`",
        "- Live promotion authorized: `false`",
        "- Live behavior changed: `false`",
        f"- Required next step: `{payload['required_next_step']}`",
        "",
        "## Counts",
        "",
        f"- Input strategy rows: `{counts['input_rows']}`",
        f"- Eligible strategies: `{counts['eligible_strategies']}`",
        f"- Eligible families: `{counts['eligible_families']}`",
        f"- Advisory allocations: `{counts['allocations']}`",
        "",
        "## Portfolio Blockers",
        "",
    ]
    blockers = payload.get("portfolio_blockers") or []
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Allocations",
        "",
    ])
    allocations = payload.get("allocations") or []
    if not allocations:
        lines.append("- None. No strategy risk budget is recommended.")
    else:
        lines.extend([
            "| Strategy | Family | Risk bps | Beta | Notes |",
            "|----------|--------|---------:|-----:|-------|",
        ])
        for row in allocations:
            lines.append(
                f"| `{row['strategy_id']}` | `{row['family']}` | "
                f"`{row['target_risk_budget_bps']}` | `{row['beta_to_spy']}` | "
                f"{row['notes']} |"
            )
    lines.extend([
        "",
        "## Strategy Candidates",
        "",
    ])
    candidates = payload.get("candidates") or []
    if not candidates:
        lines.append("- None.")
    else:
        lines.extend([
            "| Strategy | Family | Verdict | N | PF | Avg R | Eligible | Blockers |",
            "|----------|--------|---------|--:|---:|------:|----------|----------|",
        ])
        for row in candidates:
            blockers_text = ", ".join(f"`{item}`" for item in row["blockers"]) or "-"
            lines.append(
                f"| `{row['strategy_id']}` | `{row['family']}` | `{row['verdict']}` | "
                f"`{row['n']}` | `{row['profit_factor']}` | `{row['avg_r']}` | "
                f"`{str(row['eligible_for_portfolio']).lower()}` | {blockers_text} |"
            )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "This report is advisory evidence only. It may recommend a future risk budget "
        "shape after multiple independent strategy families prove edge, but it does "
        "not change live ranking, sizing, order placement, gates, promotion state, or "
        "runtime flags.",
    ])
    return "\n".join(lines)


def _required_next_step(payload: dict[str, Any]) -> str:
    if payload.get("portfolio_authorized"):
        return "human_review_before_any_micro_paper_or_scaling"
    blockers = set(payload.get("portfolio_blockers") or [])
    if "not_enough_validated_strategies" in blockers:
        return "collect_and_validate_more_strategy_families"
    if "weighted_beta_exceeds_limit" in blockers:
        return "research_beta_hedge_or_reduce_correlated_exposure"
    return "continue_shadow_replay_evidence_loop"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league-path", type=Path, default=DEFAULT_LEAGUE_PATH)
    parser.add_argument("--betas-json", type=Path, default=None)
    parser.add_argument("--correlations-json", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-samples", type=int, default=100)
    parser.add_argument("--max-total-risk-budget-bps", type=float, default=25.0)
    parser.add_argument("--max-strategy-risk-budget-bps", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = PortfolioConstructionConfig(
        min_samples=args.min_samples,
        max_total_risk_budget_bps=args.max_total_risk_budget_bps,
        max_strategy_risk_budget_bps=args.max_strategy_risk_budget_bps,
    )
    payload = build_phase9d_report(
        league_path=args.league_path,
        betas=load_keyed_float_map(args.betas_json),
        correlations=load_keyed_float_map(args.correlations_json),
        config=config,
    )
    print(json.dumps(write_outputs(payload, args.out_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
