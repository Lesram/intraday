#!/usr/bin/env python3
"""Phase 2 — walk-forward PARAMETER SWEEP (the honest "backtest and tune").

The trap: sweep params against history, ship the best backtest → overfit, fails
forward. The honest way (what this does): SELECT a config on the TRAIN fold,
REPORT it on the untouched TEST fold, accept ONLY configs that clear t>=2 on TEST.
A config that survives that is real; one that doesn't is correctly rejected.

Notes:
- Sweeping is free and does NOT touch the live clock — this patches the in-memory
  config only; the committed param_freeze.json and the live container are untouched.
- Momentum's live regime gate ({trending_up,high_vol}) blocks it on this all-chop
  corpus, so to test the SIGNAL's edge we RELAX eligible_regimes to all regimes.
  That tests whether the ret/readiness thresholds carry edge at all (clearly a
  signal test, not the live config).
- t_stat here is the backtester's simple costed t — LENIENT vs the gate's
  cluster-robust t. So failing this bar is conclusive (cluster-robust would be
  lower); only a PASS would need the stricter re-check.
"""
from __future__ import annotations

import argparse
import copy
import itertools

import pandas as pd

import backend.organism.strategies.strategy_config as sc
from scripts.strategy_backtester import (
    BacktestConfig, _compute_all_features, load_bars_pickle, run_backtest,
)

ALL_REGIMES = ["trending_up", "high_vol", "chop", "trending_down",
               "low_vol", "stress", "unknown"]

MOM_GRID = {
    "ret_5d_threshold": [0.002, 0.005, 0.010],
    "ret_20d_threshold": [0.005, 0.010, 0.020],
    "breakout_readiness_threshold": [0.50, 0.60, 0.70],
}
BO_GRID = {
    "entry_composite_threshold": [0.45, 0.55, 0.65],
    "min_rv_ratio": [1.0, 1.5],
}


def _grid(grid):
    keys = list(grid)
    for combo in itertools.product(*[grid[k] for k in keys]):
        yield dict(zip(keys, combo))


def _time_split(bars, train_frac, embargo):
    n = min(len(df) for df in bars.values())
    split = int(n * train_frac)
    train = {s: df.iloc[:split].reset_index(drop=True) for s, df in bars.items()}
    test = {s: df.iloc[split + embargo:].reset_index(drop=True) for s, df in bars.items()}
    return train, test, split, n


def _sweep(strategy, grid, relax_regime, train_bars, test_bars, cfg):
    base = sc.STRATEGY_CONFIG[strategy]
    orig = copy.deepcopy(base)
    tr_f = _compute_all_features(train_bars, cfg.bars_per_day)
    te_f = _compute_all_features(test_bars, cfg.bars_per_day)
    rows = []
    try:
        for gconf in _grid(grid):
            base.update(gconf)
            if relax_regime:
                base["eligible_regimes"] = list(ALL_REGIMES)
            tr = run_backtest(train_bars, cfg, only={strategy}, precomputed_feats=tr_f)
            te = run_backtest(test_bars, cfg, only={strategy}, precomputed_feats=te_f)
            a = tr.per_strategy.get(strategy, {})
            b = te.per_strategy.get(strategy, {})
            rows.append({**gconf,
                         "train_n": a.get("n", 0), "train_t": a.get("t_stat", 0.0),
                         "train_exp": a.get("expectancy", 0.0),
                         "test_n": b.get("n", 0), "test_t": b.get("t_stat", 0.0),
                         "test_exp": b.get("expectancy", 0.0)})
    finally:
        base.clear()
        base.update(orig)
    return pd.DataFrame(rows)


def _report(name, df, min_n):
    print("=" * 78)
    print(f"WALK-FORWARD SWEEP — {name}  (select on TRAIN, report on TEST; gate test_t>=2)")
    print("=" * 78)
    if df.empty or df["train_n"].max() == 0:
        print("no trades produced across the grid (strategy structurally inert on this corpus)")
        return
    df = df.sort_values("train_t", ascending=False).reset_index(drop=True)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(df.to_string(index=False))
    elig = df[df["train_n"] >= min_n]
    if elig.empty:
        print(f"\nno config reached min_n={min_n} train trades — INSUFFICIENT")
        return
    best = elig.iloc[0]  # selected PURELY on train_t — committed before seeing test
    keys = [k for k in df.columns if k not in
            ("train_n", "train_t", "train_exp", "test_n", "test_t", "test_exp")]
    print(f"\nSELECTED on train (train_t={best['train_t']:.2f}, n={int(best['train_n'])}): "
          f"{ {k: best[k] for k in keys} }")
    print(f"  -> TEST fold (the only valid read): t={best['test_t']:.2f}  "
          f"exp={best['test_exp']:.4f}  n={int(best['test_n'])}")
    # THE verdict is the train-selected config's TEST t-stat — nothing else.
    passed = best["test_t"] >= 2.0 and best["test_exp"] > 0
    print(f"\nVERDICT: {'PASS — train-selected config clears test_t>=2 (RE-CHECK cluster-robust)' if passed else 'NO EDGE — train-selected config test_t=%.2f < 2' % best['test_t']}")
    # Honesty guard: report (do NOT act on) test-fold cherry-picks.
    n_cherry = int(((elig['test_t'] >= 2.0) & (elig['test_exp'] > 0)).sum())
    if n_cherry:
        print(f"(note: {n_cherry} configs happen to have test_t>=2, but choosing among "
              f"them by TEST performance is the exact leakage the walk-forward prevents — "
              f"the train-selected config above is the only honest answer.)")


def main() -> int:
    p = argparse.ArgumentParser(description="walk-forward param sweep (honest tune)")
    p.add_argument("--bars-pickle", default="artifacts/broad_corpus_v2/bars.pkl")
    p.add_argument("--max-bars", type=int, default=None, help="cap bars per symbol (tractability)")
    p.add_argument("--train-frac", type=float, default=0.6)
    p.add_argument("--embargo", type=int, default=300)
    p.add_argument("--min-n", type=int, default=30)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--lookback-window", type=int, default=300)
    p.add_argument("--which", default="momentum", choices=["momentum", "breakout", "both"])
    args = p.parse_args()

    bars = load_bars_pickle(args.bars_pickle)
    if args.max_bars:
        bars = {s: df.iloc[:args.max_bars].reset_index(drop=True) for s, df in bars.items()}
    cfg = BacktestConfig(horizon=args.horizon, lookback_window=args.lookback_window)
    train, test, split, n = _time_split(bars, args.train_frac, args.embargo)
    print(f"corpus={n} bars/symbol  train=[:{split}]  embargo={args.embargo}  "
          f"test=[{split + args.embargo}:]  symbols={len(bars)}")

    if args.which in ("momentum", "both"):
        df = _sweep("momentum", MOM_GRID, True, train, test, cfg)
        _report("MOMENTUM (regime-relaxed signal test)", df, args.min_n)
    if args.which in ("breakout", "both"):
        df = _sweep("breakout", BO_GRID, False, train, test, cfg)
        _report("BREAKOUT", df, args.min_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
