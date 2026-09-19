#!/usr/bin/env python3
"""Generate daily and cumulative observation reports for Experiment 1A.

Usage:
    # Single day (defaults to today UTC):
    python scripts/generate_experiment_observation_report.py

    # Specific date:
    python scripts/generate_experiment_observation_report.py --date 2026-04-13

    # Date range (cumulative window):
    python scripts/generate_experiment_observation_report.py --from 2026-04-13 --to 2026-04-18

    # Use a specific log file:
    python scripts/generate_experiment_observation_report.py --log /path/to/application.log

    # Write to file instead of stdout:
    python scripts/generate_experiment_observation_report.py --out report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ── Baseline (Apr 7-10, 32 real trades, pre-Exp1A) ──────────
BASELINE = {
    "trades": 32,
    "pyramid_cut_pct": 75.0,
    "timeout_pct": 15.6,
    "stop_loss_pct": 9.4,
    "win_rate": 18.8,
    "expectancy": -1.92,
    "avg_hold_s": 550,
    "worst_loss": -12.69,
    "pnl_per_4_sessions": -61.37,
}

BRAIN_DIR = Path("organism_brain")
TRADE_HISTORY = BRAIN_DIR / "trade_history.csv"
MANIFEST = BRAIN_DIR / "manifest.json"
LEARNING_STATE = BRAIN_DIR / "learning_state.json"


def load_trades(date_from: str, date_to: str) -> list[dict]:
    """Load trades from trade_history.csv within date range."""
    rows = []
    if not TRADE_HISTORY.exists():
        return rows
    with open(TRADE_HISTORY) as f:
        for r in csv.DictReader(f):
            closed = r.get("closed_at", "")
            if not closed:
                continue
            day = closed[:10]
            if date_from <= day <= date_to:
                if r.get("exit_reason") != "reconciliation_adjustment":
                    rows.append(r)
    return rows


def parse_log_suppressions(log_path: str | None, date_from: str, date_to: str) -> list[dict]:
    """Parse Exp1A suppression log lines from application.log."""
    suppressions = []
    if log_path is None:
        return suppressions
    p = Path(log_path)
    if not p.exists():
        return suppressions
    pattern = re.compile(
        r"Exp1A: pyramid_cut suppressed.*?"
        r"(\w+)\s+bars_held=(\d+)/(\d+)\s+regime=(\w+)\s+r=([\d.\-]+)R\s+"
        r"unrealized=\$([\d.\-]+)\s+reason=(\S+)"
    )
    try:
        for line in p.open():
            # Filter by date
            ts_match = re.search(r'"timestamp":\s*"(\d{4}-\d{2}-\d{2})', line)
            if ts_match:
                day = ts_match.group(1)
                if day < date_from or day > date_to:
                    continue
            if "Exp1A: pyramid_cut suppressed" in line:
                m = pattern.search(line)
                if m:
                    suppressions.append({
                        "symbol": m.group(1),
                        "bars_held": int(m.group(2)),
                        "min_hold": int(m.group(3)),
                        "regime": m.group(4),
                        "r_multiple": float(m.group(5)),
                        "unrealized": float(m.group(6)),
                        "reason": m.group(7),
                    })
    except Exception:
        pass
    return suppressions


def compute_stats(trades: list[dict]) -> dict:
    """Compute key stats from a list of trade dicts."""
    if not trades:
        return {
            "count": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "avg_win": 0, "avg_loss": 0,
            "payoff_ratio": 0, "expectancy": 0, "avg_hold_s": 0,
            "worst_loss": 0,
        }

    wins = [r for r in trades if float(r.get("pnl", 0)) > 0]
    losses = [r for r in trades if float(r.get("pnl", 0)) <= 0]
    total_pnl = sum(float(r["pnl"]) for r in trades)
    avg_win = sum(float(r["pnl"]) for r in wins) / len(wins) if wins else 0
    avg_loss = sum(float(r["pnl"]) for r in losses) / len(losses) if losses else 0
    worst = min(float(r["pnl"]) for r in trades)
    hold_times = [float(r.get("time_in_trade_seconds", 0)) for r in trades]
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0

    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(abs(avg_win / avg_loss), 2) if avg_loss else 0,
        "expectancy": round(total_pnl / len(trades), 2) if trades else 0,
        "avg_hold_s": round(avg_hold),
        "worst_loss": round(worst, 2),
    }


def by_exit_reason(trades: list[dict]) -> dict[str, dict]:
    """Group trades by exit_reason category."""
    cats = defaultdict(list)
    for r in trades:
        reason = r.get("exit_reason", "unknown")
        if "cut_" in reason:
            cats["pyramid_cut"].append(r)
        elif reason == "stop_loss":
            cats["stop_loss"].append(r)
        elif "timeout" in reason or "holding_period" in reason:
            cats["timeout/max_hold"].append(r)
        else:
            cats["other"].append(r)
    return {k: compute_stats(v) for k, v in cats.items()}


def by_symbol(trades: list[dict]) -> dict[str, dict]:
    groups = defaultdict(list)
    for r in trades:
        groups[r.get("symbol", "?")].append(r)
    return {k: compute_stats(v) for k, v in sorted(groups.items(), key=lambda x: compute_stats(x[1])["total_pnl"])}


def by_regime(trades: list[dict]) -> dict[str, dict]:
    groups = defaultdict(list)
    for r in trades:
        groups[r.get("regime_at_entry", "unknown")].append(r)
    return {k: compute_stats(v) for k, v in groups.items()}


def by_confidence_bucket(trades: list[dict]) -> dict[str, dict]:
    buckets = {"<0.35": [], "0.35-0.45": [], ">=0.45": []}
    for r in trades:
        c = float(r.get("confidence", 0))
        if c < 0.35:
            buckets["<0.35"].append(r)
        elif c < 0.45:
            buckets["0.35-0.45"].append(r)
        else:
            buckets[">=0.45"].append(r)
    return {k: compute_stats(v) for k, v in buckets.items()}


def inverse_etf_analysis(trades: list[dict]) -> dict:
    inv = [r for r in trades if r.get("symbol") in ("PSQ", "SH")]
    inv_chop = [r for r in inv if r.get("regime_at_entry") == "chop"]
    return {
        "total": compute_stats(inv),
        "in_chop": compute_stats(inv_chop),
    }


def delta_indicator(current: float, baseline: float, higher_is_better: bool = True) -> str:
    diff = current - baseline
    if abs(diff) < 0.01:
        return "="
    if higher_is_better:
        return f"{'↑' if diff > 0 else '↓'}{abs(diff):.1f}"
    else:
        return f"{'↓' if diff < 0 else '↑'}{abs(diff):.1f}"


def generate_report(
    trades: list[dict],
    suppressions: list[dict],
    date_from: str,
    date_to: str,
    is_cumulative: bool = False,
) -> str:
    """Generate the markdown observation report."""
    stats = compute_stats(trades)
    exits = by_exit_reason(trades)
    symbols = by_symbol(trades)
    regimes = by_regime(trades)
    conf_buckets = by_confidence_bucket(trades)
    inv = inverse_etf_analysis(trades)

    title = "Cumulative" if is_cumulative else "Daily"
    window = f"{date_from} to {date_to}" if is_cumulative else date_from

    lines = [
        f"# Experiment 1A — {title} Observation Report",
        f"",
        f"**Window**: {window}",
        f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Status**: {'CUMULATIVE' if is_cumulative else 'DAILY'} — compare against Apr 7-10 baseline",
        f"",
        f"## Exp1A gate activity",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Pyramid_cut suppressions (Exp1A gate fires) | **{len(suppressions)}** |",
        f"| Symbols suppressed | {', '.join(sorted(set(s['symbol'] for s in suppressions))) if suppressions else 'none'} |",
        f"",
    ]

    if suppressions:
        lines.extend([
            f"### Suppression detail",
            f"",
            f"| Symbol | Bars held | R-multiple | Unrealized | Reason |",
            f"|---|---:|---:|---:|---|",
        ])
        for s in suppressions:
            lines.append(
                f"| {s['symbol']} | {s['bars_held']}/{s['min_hold']} | "
                f"{s['r_multiple']:.1f}R | ${s['unrealized']:.2f} | {s['reason']} |"
            )
        lines.append("")

    # Core comparison
    pc = exits.get("pyramid_cut", {"count": 0, "total_pnl": 0})
    to = exits.get("timeout/max_hold", {"count": 0, "total_pnl": 0})
    sl = exits.get("stop_loss", {"count": 0, "total_pnl": 0})
    pc_pct = pc["count"] / stats["count"] * 100 if stats["count"] else 0
    to_pct = to["count"] / stats["count"] * 100 if stats["count"] else 0
    sl_pct = sl["count"] / stats["count"] * 100 if stats["count"] else 0

    lines.extend([
        f"## Core metrics vs baseline",
        f"",
        f"| Metric | Baseline (Apr 7-10) | Current | Delta |",
        f"|---|---:|---:|---|",
        f"| Trades | {BASELINE['trades']} | {stats['count']} | — |",
        f"| Pyramid_cut % | {BASELINE['pyramid_cut_pct']:.0f}% | {pc_pct:.0f}% | {delta_indicator(pc_pct, BASELINE['pyramid_cut_pct'], higher_is_better=False)} |",
        f"| Timeout/max_hold % | {BASELINE['timeout_pct']:.0f}% | {to_pct:.0f}% | {delta_indicator(to_pct, BASELINE['timeout_pct'])} |",
        f"| Stop_loss % | {BASELINE['stop_loss_pct']:.0f}% | {sl_pct:.0f}% | — |",
        f"| Win rate | {BASELINE['win_rate']:.1f}% | {stats['win_rate']:.1f}% | {delta_indicator(stats['win_rate'], BASELINE['win_rate'])} |",
        f"| Expectancy/trade | ${BASELINE['expectancy']:.2f} | ${stats['expectancy']:.2f} | {delta_indicator(stats['expectancy'], BASELINE['expectancy'])} |",
        f"| Avg hold time | {BASELINE['avg_hold_s']}s | {stats['avg_hold_s']}s | {delta_indicator(stats['avg_hold_s'], BASELINE['avg_hold_s'])} |",
        f"| Worst loss | ${BASELINE['worst_loss']:.2f} | ${stats['worst_loss']:.2f} | — |",
        f"| Net PnL | ${BASELINE['pnl_per_4_sessions']:.2f}/4d | ${stats['total_pnl']:.2f} | — |",
        f"",
    ])

    # Success/failure criteria
    lines.extend([
        f"## Success criteria check",
        f"",
        f"| Criterion | Threshold | Current | Status |",
        f"|---|---|---|---|",
        f"| Win rate improvement | >25% | {stats['win_rate']:.1f}% | {'✅ PASS' if stats['win_rate'] > 25 else '⏳ PENDING' if stats['count'] < 15 else '❌ FAIL'} |",
        f"| Expectancy improvement | >-$0.50 | ${stats['expectancy']:.2f} | {'✅ PASS' if stats['expectancy'] > -0.50 else '⏳ PENDING' if stats['count'] < 15 else '❌ FAIL'} |",
        f"| Suppression events | >10 total | {len(suppressions)} | {'✅ PASS' if len(suppressions) > 10 else '⏳ PENDING'} |",
        f"| Max single-trade loss | < -$25 | ${stats['worst_loss']:.2f} | {'✅ PASS' if stats['worst_loss'] > -25 else '❌ FAIL'} |",
        f"",
    ])

    # PnL by exit reason
    lines.extend([
        f"## PnL by exit reason",
        f"",
        f"| Exit reason | Count | PnL | Win rate |",
        f"|---|---:|---:|---:|",
    ])
    for reason, s in sorted(exits.items(), key=lambda x: x[1]["total_pnl"]):
        lines.append(f"| {reason} | {s['count']} | ${s['total_pnl']:.2f} | {s['win_rate']:.0f}% |")
    lines.append("")

    # PnL by symbol
    lines.extend([
        f"## PnL by symbol",
        f"",
        f"| Symbol | Trades | PnL | Win rate |",
        f"|---|---:|---:|---:|",
    ])
    for sym, s in symbols.items():
        lines.append(f"| {sym} | {s['count']} | ${s['total_pnl']:.2f} | {s['win_rate']:.0f}% |")
    lines.append("")

    # Exp2 readiness: inverse ETF
    lines.extend([
        f"## Exp2 readiness — inverse ETF (PSQ/SH)",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| PSQ/SH total trades | {inv['total']['count']} |",
        f"| PSQ/SH total PnL | ${inv['total']['total_pnl']:.2f} |",
        f"| PSQ/SH win rate | {inv['total']['win_rate']:.0f}% |",
        f"| PSQ/SH in chop specifically | {inv['in_chop']['count']} trades, ${inv['in_chop']['total_pnl']:.2f} |",
        f"",
    ])

    # Exp3 readiness: confidence inversion
    lines.extend([
        f"## Exp3 readiness — confidence bucket analysis",
        f"",
        f"| Bucket | Trades | PnL | Win rate | Baseline comparison |",
        f"|---|---:|---:|---:|---|",
    ])
    baseline_conf = {"<0.35": "29%", "0.35-0.45": "0%", ">=0.45": "0%"}
    for bucket, s in conf_buckets.items():
        lines.append(
            f"| {bucket} | {s['count']} | ${s['total_pnl']:.2f} | "
            f"{s['win_rate']:.0f}% | baseline: {baseline_conf.get(bucket, '?')} |"
        )
    lines.append("")

    # Regime split
    lines.extend([
        f"## Regime split",
        f"",
        f"| Regime | Trades | PnL | Win rate |",
        f"|---|---:|---:|---:|",
    ])
    for regime, s in regimes.items():
        lines.append(f"| {regime} | {s['count']} | ${s['total_pnl']:.2f} | {s['win_rate']:.0f}% |")
    lines.append("")

    # Brain state
    if MANIFEST.exists() and LEARNING_STATE.exists():
        m = json.loads(MANIFEST.read_text())
        l = json.loads(LEARNING_STATE.read_text())
        lines.extend([
            f"## Brain state",
            f"",
            f"| Field | Value |",
            f"|---|---|",
            f"| Generation | {m.get('generation')} |",
            f"| Total trades | {m.get('total_trades')} |",
            f"| Cumulative PnL | ${m.get('cumulative_pnl')} |",
            f"| Best Sharpe | {m.get('best_sharpe')} |",
            f"| ML trained | {m.get('ml_is_trained')} |",
            f"| Trading phase | production_frozen ({m.get('total_trades')}/300) |",
            f"",
        ])

    lines.append(f"---")
    lines.append(f"*Generated by `scripts/generate_experiment_observation_report.py`*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Experiment 1A observation report"
    )
    parser.add_argument("--date", help="Single date (YYYY-MM-DD). Default: today UTC.")
    parser.add_argument("--from", dest="date_from", help="Start date for cumulative window.")
    parser.add_argument("--to", dest="date_to", help="End date for cumulative window.")
    parser.add_argument(
        "--log", default=None,
        help="Path to application.log for suppression parsing. "
             "Default: try container path /app/logs/application.log via local mount.",
    )
    parser.add_argument("--out", default=None, help="Output file path. Default: stdout.")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.date_from and args.date_to:
        date_from, date_to = args.date_from, args.date_to
        is_cumulative = True
    elif args.date:
        date_from = date_to = args.date
        is_cumulative = False
    else:
        date_from = date_to = today
        is_cumulative = False

    trades = load_trades(date_from, date_to)
    suppressions = parse_log_suppressions(args.log, date_from, date_to)
    report = generate_report(trades, suppressions, date_from, date_to, is_cumulative)

    if args.out:
        Path(args.out).write_text(report)
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
