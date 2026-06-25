#!/usr/bin/env python3
"""Task B — costed walk-forward, out-of-sample test of the trend+high_vol slice.

The only book cell that ever stayed net-positive OOS was trend-momentum. The
deciding question: does its t-stat climb above 2 with more trending data, or
stay stuck near 1? This runs the rigorous version on the broad-replay baseline
trades, COSTED (the replay's per-trade pnl is gross — verified mean|pnl| ==
mean|(exit-entry)*shares| — so costs must be applied here), chronological
out-of-sample.

Bar (pre-registered): trend-momentum upgrades to "candidate edge" ONLY if it
shows net expectancy > 0 at t >= 2 over >= 40 OOS trades, costed, stable across
folds. Anything short = "not yet proven; keep accumulating."
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.organism.costing import DEFAULT_COST_BPS, apply_costs

TREND_REGIMES = {"trending_up", "high_vol"}


def _stats(x: pd.Series) -> dict:
    n = len(x)
    if n == 0:
        return {"n": 0, "net": 0.0, "exp": 0.0, "t": 0.0, "pf": None, "win": 0.0}
    wins, losses = x[x > 0], x[x < 0]
    gl = float(abs(losses.sum()))
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    t = float(x.mean() / (sd / (n ** 0.5))) if sd > 0 else 0.0
    return {"n": n, "net": round(float(x.sum()), 2), "exp": round(float(x.mean()), 4),
            "t": round(t, 3), "pf": round(float(wins.sum()) / gl, 4) if gl > 0 else None,
            "win": round(float((x > 0).mean()), 4)}


def main() -> None:
    bps = DEFAULT_COST_BPS
    f = sorted(glob.glob(str(ROOT / "artifacts/edge_experiments_2026-06-2*/baseline_trades.csv")))[-1]
    df = pd.read_csv(f)
    df = apply_costs(df, bps)  # gross replay pnl -> costed net_pnl
    trend = df[df["regime_at_entry"].isin(TREND_REGIMES)].sort_values("entry_bar").reset_index(drop=True)

    print(f"=== Task B: trend+high_vol slice, costed @{bps}bps walk-forward ===")
    print(f"corpus: {Path(f).parent.name}  | trend-slice trades: {len(trend)} "
          f"(of {len(df)} total; regimes {sorted(TREND_REGIMES)})")
    print(f"\nWHOLE trend slice (costed): {_stats(trend['net_pnl'])}")

    # 2-way chronological OOS split: train/select early, evaluate held-out late.
    h = len(trend) // 2
    insample, oos = trend.iloc[:h], trend.iloc[h:]
    print("\n-- 2-way chronological split --")
    print(f"  in-sample (early): {_stats(insample['net_pnl'])}")
    print(f"  OUT-OF-SAMPLE (late): {_stats(oos['net_pnl'])}")

    # 3-fold walk-forward: each later third evaluated after the earlier data.
    print("\n-- 3-fold walk-forward (each fold = held-out later third) --")
    n = len(trend)
    bounds = [0, n // 3, 2 * n // 3, n]
    folds = [trend.iloc[bounds[k]:bounds[k + 1]] for k in range(3)]
    fold_oos = []
    for i, fold in enumerate(folds[1:], start=2):  # folds 2,3 are OOS
        s = _stats(fold["net_pnl"])
        fold_oos.append(s)
        print(f"  fold {i} (OOS): {s}")

    # Verdict against the pre-registered bar.
    oos_s = _stats(oos["net_pnl"])
    bar_ok = (oos_s["exp"] > 0) and (oos_s["t"] >= 2) and (oos_s["n"] >= 40)
    folds_pos = all((s["exp"] or 0) > 0 for s in fold_oos)
    print("\n=== VERDICT (bar: net exp>0 @ t>=2 over >=40 OOS trades, costed, stable) ===")
    print(f"  OOS net exp={oos_s['exp']} t={oos_s['t']} n={oos_s['n']} "
          f"PF={oos_s['pf']} | folds all positive: {folds_pos}")
    print(f"  --> {'CANDIDATE EDGE' if (bar_ok and folds_pos) else 'NOT YET PROVEN — keep accumulating'}")
    # Breakeven cost: where mean(gross) == mean(cost) = B/1e4 * notional.
    gross_exp = float(trend["pnl"].mean())
    notional = float((trend["entry_price"] * trend["shares"].abs()).mean())
    be_bps = (gross_exp / notional * 1e4) if notional > 0 else 0.0
    print(f"  (whole-slice gross exp/trade ${gross_exp:.2f}; breakeven "
          f"~{be_bps:.1f} bps round-trip — net-positive below that cost)")


if __name__ == "__main__":
    main()
