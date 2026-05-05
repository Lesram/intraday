"""Phase 3 candidate-filter counterfactual replay.

This is an offline research tool. It replays the closed-trade PnL stream from
the persisted brain and evaluates "what if we had skipped this candidate slice?"
scenarios surfaced by trade attribution. It is not a fill-level market replay
and it does not change live trading behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase3_trade_attribution import (
    DEFAULT_TRADE_HISTORY,
    WINDOWS,
    TradeRecord,
    load_strategy_trades,
    summarise,
)

DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_candidate_filter_replay"


Predicate = Callable[[TradeRecord], bool]


@dataclass(frozen=True)
class ReplayConfig:
    min_all_skipped_trades: int = 20
    min_recent_skipped_trades: int = 10
    min_net_pnl_delta: float = 10.0
    max_trade_reduction_for_shadow: float = 0.60
    drawdown_regression_tolerance: float = 5.0
    top_n: int = 12


@dataclass(frozen=True)
class FilterScenario:
    name: str
    description: str
    predicate: Predicate

    def metadata(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def confidence_between(record: TradeRecord, low: float, high: float) -> bool:
    return low <= record.confidence < high


def default_scenarios() -> list[FilterScenario]:
    return [
        FilterScenario(
            name="skip_alpha_breakout_chop",
            description="Skip alpha+breakout entries when regime_at_entry is chop.",
            predicate=lambda r: (
                r.entry_source == "alpha+breakout"
                and r.regime_at_entry == "chop"
            ),
        ),
        FilterScenario(
            name="skip_conf_45_55",
            description="Skip confidence band [0.45,0.55).",
            predicate=lambda r: confidence_between(r, 0.45, 0.55),
        ),
        FilterScenario(
            name="skip_conf_55_65",
            description="Skip confidence band [0.55,0.65).",
            predicate=lambda r: confidence_between(r, 0.55, 0.65),
        ),
        FilterScenario(
            name="skip_conf_45_65",
            description="Skip combined mid-confidence band [0.45,0.65).",
            predicate=lambda r: confidence_between(r, 0.45, 0.65),
        ),
        FilterScenario(
            name="skip_alpha_breakout_chop_or_conf_45_65",
            description=(
                "Skip alpha+breakout in chop OR confidence band [0.45,0.65)."
            ),
            predicate=lambda r: (
                (
                    r.entry_source == "alpha+breakout"
                    and r.regime_at_entry == "chop"
                )
                or confidence_between(r, 0.45, 0.65)
            ),
        ),
        FilterScenario(
            name="skip_avgo",
            description="Skip AVGO trades, the largest all-time symbol drag.",
            predicate=lambda r: r.symbol == "AVGO",
        ),
    ]


def scenario_by_name() -> dict[str, FilterScenario]:
    return {scenario.name: scenario for scenario in default_scenarios()}


def _window_records(records: list[TradeRecord], window: int | None) -> list[TradeRecord]:
    if window is None:
        return records
    return records[-min(window, len(records)):]


def max_drawdown(records: list[TradeRecord]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for record in records:
        equity += record.pnl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return _round(worst)


def exit_mix(records: list[TradeRecord], *, top_n: int = 8) -> dict[str, int]:
    counts = Counter(record.exit_family for record in records)
    return dict(counts.most_common(top_n))


def pnl_risk_summary(records: list[TradeRecord]) -> dict[str, Any]:
    summary = summarise(records)
    wins = [record.pnl for record in records if record.pnl > 0]
    losses = [record.pnl for record in records if record.pnl < 0]
    summary.update({
        "gross_profit": _round(sum(wins)),
        "gross_loss_abs": _round(abs(sum(losses))),
        "max_drawdown": max_drawdown(records),
        "exit_mix": exit_mix(records),
    })
    return summary


def classify_result(
    *,
    window: str,
    skipped: dict[str, Any],
    kept: dict[str, Any],
    baseline: dict[str, Any],
    net_pnl_delta: float,
    max_drawdown_delta: float,
    trade_count_reduction: float,
    config: ReplayConfig,
) -> str:
    min_skipped = (
        config.min_all_skipped_trades
        if window == "all"
        else config.min_recent_skipped_trades
    )
    if int(skipped["n_trades"]) < min_skipped:
        return "insufficient_sample"
    if net_pnl_delta <= 0:
        return "do_not_promote_negative_counterfactual"
    if trade_count_reduction > config.max_trade_reduction_for_shadow:
        return "positive_but_removes_too_many_trades"
    if max_drawdown_delta < -config.drawdown_regression_tolerance:
        return "positive_but_drawdown_regresses"
    kept_profit_factor_ok = (
        float(kept["profit_factor"]) >= float(baseline["profit_factor"])
        or (
            float(kept["gross_loss_abs"]) == 0.0
            and float(kept["gross_profit"]) > 0.0
        )
    )
    if net_pnl_delta >= config.min_net_pnl_delta and kept_profit_factor_ok:
        return "shadow_candidate_from_trade_history_counterfactual"
    return "weak_positive_needs_fill_level_replay"


def evaluate_scenario(
    records: list[TradeRecord],
    scenario: FilterScenario,
    *,
    window: str,
    config: ReplayConfig,
) -> dict[str, Any]:
    skipped = [record for record in records if scenario.predicate(record)]
    kept = [record for record in records if not scenario.predicate(record)]
    baseline_summary = pnl_risk_summary(records)
    kept_summary = pnl_risk_summary(kept)
    skipped_summary = pnl_risk_summary(skipped)

    baseline_total = float(baseline_summary["total_pnl"])
    kept_total = float(kept_summary["total_pnl"])
    skipped_total = float(skipped_summary["total_pnl"])
    net_pnl_delta = kept_total - baseline_total
    max_drawdown_delta = (
        float(kept_summary["max_drawdown"])
        - float(baseline_summary["max_drawdown"])
    )
    trade_count_reduction = (
        len(skipped) / len(records)
        if records
        else 0.0
    )

    result = {
        "window": window,
        **scenario.metadata(),
        "baseline": baseline_summary,
        "kept": kept_summary,
        "skipped": skipped_summary,
        "net_pnl_delta": _round(net_pnl_delta),
        "skipped_total_pnl": _round(skipped_total),
        "avoided_loss": skipped_summary["gross_loss_abs"],
        "opportunity_cost": skipped_summary["gross_profit"],
        "trade_count_reduction": _round(trade_count_reduction),
        "max_drawdown_delta": _round(max_drawdown_delta),
    }
    result["recommendation"] = classify_result(
        window=window,
        skipped=skipped_summary,
        kept=kept_summary,
        baseline=baseline_summary,
        net_pnl_delta=net_pnl_delta,
        max_drawdown_delta=max_drawdown_delta,
        trade_count_reduction=trade_count_reduction,
        config=config,
    )
    return result


def run_counterfactuals(
    records: list[TradeRecord],
    metadata: dict[str, Any],
    scenarios: list[FilterScenario],
    config: ReplayConfig,
) -> dict[str, Any]:
    windows: dict[str, list[TradeRecord]] = {
        "all": records,
    }
    for window in WINDOWS:
        windows[f"last_{window}"] = _window_records(records, window)

    evaluations: dict[str, list[dict[str, Any]]] = {}
    for window_name, window_records in windows.items():
        results = [
            evaluate_scenario(
                window_records,
                scenario,
                window=window_name,
                config=config,
            )
            for scenario in scenarios
        ]
        results.sort(key=lambda row: float(row["net_pnl_delta"]), reverse=True)
        evaluations[window_name] = results

    top_shadow_candidates = [
        result
        for results in evaluations.values()
        for result in results
        if result["recommendation"].startswith("shadow_candidate")
    ]
    top_shadow_candidates.sort(
        key=lambda row: (
            row["window"] != "last_100",
            row["window"] != "last_50",
            -float(row["net_pnl_delta"]),
        )
    )

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": "closed_trade_counterfactual_no_live_behavior_change",
        "limitations": [
            "Uses realized closed-trade PnL only; not a fill-level market replay.",
            "Skipping a trade does not model freed capital, replacement trades, or changed state.",
            "Positive results require fill-level replay and shadow telemetry before promotion.",
        ],
        "criteria": {
            "min_all_skipped_trades": config.min_all_skipped_trades,
            "min_recent_skipped_trades": config.min_recent_skipped_trades,
            "min_net_pnl_delta": config.min_net_pnl_delta,
            "max_trade_reduction_for_shadow": config.max_trade_reduction_for_shadow,
            "drawdown_regression_tolerance": config.drawdown_regression_tolerance,
        },
        "metadata": metadata,
        "scenarios": [scenario.metadata() for scenario in scenarios],
        "baseline": pnl_risk_summary(records),
        "windows": evaluations,
        "top_shadow_candidates": top_shadow_candidates[:config.top_n],
    }


def flatten_results(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, results in summary["windows"].items():
        for result in results:
            rows.append({
                "window": window,
                "scenario": result["name"],
                "recommendation": result["recommendation"],
                "baseline_trades": result["baseline"]["n_trades"],
                "baseline_pnl": result["baseline"]["total_pnl"],
                "kept_trades": result["kept"]["n_trades"],
                "kept_pnl": result["kept"]["total_pnl"],
                "skipped_trades": result["skipped"]["n_trades"],
                "skipped_pnl": result["skipped_total_pnl"],
                "net_pnl_delta": result["net_pnl_delta"],
                "trade_count_reduction": result["trade_count_reduction"],
                "max_drawdown_delta": result["max_drawdown_delta"],
                "opportunity_cost": result["opportunity_cost"],
                "avoided_loss": result["avoided_loss"],
            })
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else [
        "window",
        "scenario",
        "recommendation",
        "baseline_trades",
        "baseline_pnl",
        "kept_trades",
        "kept_pnl",
        "skipped_trades",
        "skipped_pnl",
        "net_pnl_delta",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_candidate_filter_replay.json"
    results_path = out_dir / "candidate_filter_results.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_csv(results_path, flatten_results(summary))
    return {"summary": str(summary_path), "results": str(results_path)}


def _selected_scenarios(raw: str | None) -> list[FilterScenario]:
    scenarios = scenario_by_name()
    if raw is None or raw.strip().lower() in {"", "default", "all"}:
        return list(scenarios.values())
    selected: list[FilterScenario] = []
    missing: list[str] = []
    for name in [part.strip() for part in raw.split(",") if part.strip()]:
        scenario = scenarios.get(name)
        if scenario is None:
            missing.append(name)
        else:
            selected.append(scenario)
    if missing:
        raise ValueError(f"unknown scenario name(s): {', '.join(missing)}")
    if not selected:
        raise ValueError("at least one scenario must be selected")
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-history", type=Path, default=DEFAULT_TRADE_HISTORY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--scenarios", default=None)
    parser.add_argument("--min-all-skipped-trades", type=int, default=20)
    parser.add_argument("--min-recent-skipped-trades", type=int, default=10)
    parser.add_argument("--min-net-pnl-delta", type=float, default=10.0)
    parser.add_argument("--max-trade-reduction-for-shadow", type=float, default=0.60)
    parser.add_argument("--drawdown-regression-tolerance", type=float, default=5.0)
    parser.add_argument("--top-n", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ReplayConfig(
        min_all_skipped_trades=args.min_all_skipped_trades,
        min_recent_skipped_trades=args.min_recent_skipped_trades,
        min_net_pnl_delta=args.min_net_pnl_delta,
        max_trade_reduction_for_shadow=args.max_trade_reduction_for_shadow,
        drawdown_regression_tolerance=args.drawdown_regression_tolerance,
        top_n=args.top_n,
    )
    scenarios = _selected_scenarios(args.scenarios)
    records, metadata = load_strategy_trades(args.trade_history)
    summary = run_counterfactuals(records, metadata, scenarios, config)
    outputs = write_outputs(summary, args.out_dir)

    baseline = summary["baseline"]
    print(f"[filters] strategy_trades={baseline['n_trades']}")
    print(f"[filters] baseline_pnl={baseline['total_pnl']:.2f}")
    print(f"[filters] scenarios={len(summary['scenarios'])}")
    print(f"[filters] shadow_candidates={len(summary['top_shadow_candidates'])}")
    for candidate in summary["top_shadow_candidates"][:5]:
        print(
            "[filters] candidate="
            f"{candidate['window']}:{candidate['name']} "
            f"delta={candidate['net_pnl_delta']:.2f} "
            f"skipped={candidate['skipped']['n_trades']}"
        )
    print(f"[filters] summary={outputs['summary']}")
    print(f"[filters] results={outputs['results']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
