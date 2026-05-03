"""V12 W70/W71: compute brain expectancy stats from trade_history.csv.

Output JSON to stdout (or --json out.json) with:
- n_trades, n_wins, n_losses
- total_pnl, mean_pnl, median_pnl
- win_rate, sharpe_ratio (per-trade), max_drawdown
- last_50 / last_25 windowed mean_pnl + win_rate
- last_csv_mtime (so a stale read is observable)

This is the foundation for the strategy-expectancy gate (W71).  No
external auditor would consider the platform "ready" without these
numbers visible at runtime.

Usage:
    python scripts/ci/compute_strategy_expectancy.py [--csv organism_brain/trade_history.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from pathlib import Path


def _drawdown(cum: list[float]) -> float:
    """Max peak-to-trough drawdown across a cumulative-PnL series."""
    peak = cum[0] if cum else 0.0
    worst = 0.0
    for v in cum:
        peak = max(peak, v)
        worst = min(worst, v - peak)
    return worst


def compute(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {
            "n_trades": 0,
            "csv_path": str(csv_path),
            "csv_exists": False,
            "error": "trade_history.csv not found",
        }
    pnls: list[float] = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        if "pnl" not in (reader.fieldnames or []):
            return {
                "n_trades": 0,
                "csv_path": str(csv_path),
                "csv_exists": True,
                "error": "no pnl column",
                "fieldnames": reader.fieldnames,
            }
        for row in reader:
            try:
                pnls.append(float(row["pnl"]))
            except (KeyError, ValueError, TypeError):
                continue

    n = len(pnls)
    if n == 0:
        return {
            "n_trades": 0,
            "csv_path": str(csv_path),
            "csv_exists": True,
            "total_pnl": 0.0,
            "mean_pnl": 0.0,
            "median_pnl": 0.0,
            "win_rate": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "n_wins": 0,
            "n_losses": 0,
        }

    n_wins = sum(1 for p in pnls if p > 0)
    n_losses = sum(1 for p in pnls if p < 0)
    cum: list[float] = []
    running = 0.0
    for p in pnls:
        running += p
        cum.append(running)
    total = running
    mean = statistics.fmean(pnls)
    median = statistics.median(pnls)
    stdev = statistics.pstdev(pnls) if n >= 2 else 0.0
    sharpe = (mean / stdev * math.sqrt(n)) if stdev > 0 else 0.0
    mdd = _drawdown(cum)

    def _window(k: int) -> dict:
        if n < k:
            return {"n": n, "mean_pnl": mean, "win_rate": n_wins / n if n else 0.0}
        sub = pnls[-k:]
        sub_wins = sum(1 for p in sub if p > 0)
        return {
            "n": k,
            "mean_pnl": statistics.fmean(sub),
            "win_rate": sub_wins / k,
            "total_pnl": sum(sub),
        }

    return {
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "total_pnl": round(total, 4),
        "mean_pnl": round(mean, 4),
        "median_pnl": round(median, 4),
        "win_rate": round(n_wins / n, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(mdd, 4),
        "last_50": _window(50),
        "last_25": _window(25),
        "csv_path": str(csv_path),
        "csv_mtime": os.path.getmtime(csv_path),
        "csv_exists": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv", default="organism_brain/trade_history.csv",
    )
    parser.add_argument(
        "--json", default="-",
    )
    args = parser.parse_args()
    out = compute(Path(args.csv))
    text = json.dumps(out, indent=2, sort_keys=True)
    if args.json == "-":
        print(text)
    else:
        Path(args.json).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
