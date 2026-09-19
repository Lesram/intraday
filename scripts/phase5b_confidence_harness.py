#!/usr/bin/env python3
"""Phase 3 Task 2 (5b) — confidence redesign harness.

Runs the causal costed backtester over a REAL corpus with per-trade feature
snapshots, then evaluates candidate confidence models per strategy through the
confidence_lab protocol (fit/select on TRAIN fold, verdict on TEST fold).

Ship rule (pre-registered): a model routes into live sizing/ranking ONLY if it
beats flat on costed test-fold expectancy at t>=2. Otherwise FLAT SHIPS.

Momentum is regime-relaxed (same rationale as phase2_param_sweep: the corpus is
all-chop and momentum's live regime gate blocks it entirely — this is a SIGNAL
test of "can any confidence model rank momentum's trades", not the live config).

Usage:
  PYTHONPATH=. venv/bin/python scripts/phase5b_confidence_harness.py \
      --bars-pickle artifacts/broad_corpus_v2/bars.pkl \
      --out artifacts/phase2/phase5b_confidence_verdict.txt
"""
from __future__ import annotations

import argparse
import copy

from backend.organism.confidence_lab import MODEL_FEATURES, evaluate_models, report
from backend.organism.costing import apply_costs
import backend.organism.strategies.strategy_config as sc
from scripts.strategy_backtester import (
    BacktestConfig, _compute_all_features, load_bars_pickle, run_backtest,
)

ALL_REGIMES = ["trending_up", "high_vol", "chop", "trending_down",
               "low_vol", "stress", "unknown"]


def main() -> int:
    p = argparse.ArgumentParser(description="5b confidence redesign harness")
    p.add_argument("--bars-pickle", default="artifacts/broad_corpus_v2/bars.pkl")
    p.add_argument("--max-bars", type=int, default=None)
    p.add_argument("--train-frac", type=float, default=0.6)
    p.add_argument("--embargo", type=int, default=300)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--lookback-window", type=int, default=300)
    p.add_argument("--out", default="artifacts/phase2/phase5b_confidence_verdict.txt")
    args = p.parse_args()

    bars = load_bars_pickle(args.bars_pickle)
    if args.max_bars:
        bars = {s: df.iloc[:args.max_bars].reset_index(drop=True) for s, df in bars.items()}
    cfg = BacktestConfig(horizon=args.horizon, lookback_window=args.lookback_window,
                         capture_feature_cols=tuple(MODEL_FEATURES))
    feats = _compute_all_features(bars, cfg.bars_per_day)

    # One backtest pass per strategy family. Momentum gets the regime-relaxed
    # SIGNAL-test pass (config restored afterwards); the rest run natively.
    mom_cfgblock = sc.STRATEGY_CONFIG["momentum"]
    orig = copy.deepcopy(mom_cfgblock)
    try:
        mom_cfgblock["eligible_regimes"] = list(ALL_REGIMES)
        res_mom = run_backtest(bars, cfg, only={"momentum"}, precomputed_feats=feats)
    finally:
        mom_cfgblock.clear()
        mom_cfgblock.update(orig)
    res_rest = run_backtest(bars, cfg, only={"breakout", "mean_reversion", "orb"},
                            precomputed_feats=feats)

    chunks = ["5b CONFIDENCE REDESIGN VERDICT",
              f"corpus={args.bars_pickle}  horizon={args.horizon}  "
              f"train_frac={args.train_frac}  embargo={args.embargo}",
              "(momentum = regime-relaxed signal test; others = native config)", ""]
    verdicts = {}
    frames = []
    if len(res_mom.trades):
        frames.append(("momentum(signal-test)", res_mom.trades))
    if len(res_rest.trades):
        for name, sub in res_rest.trades.groupby("strategy"):
            frames.append((str(name), sub))
    for name, sub in frames:
        costed = apply_costs(sub)
        res = evaluate_models(costed, train_frac=args.train_frac,
                              embargo_bars=args.embargo)
        verdicts[name] = res["ship"]
        chunks.append(report(name, res))
    if not frames:
        chunks.append("NO TRADES produced on this corpus — nothing to evaluate.")

    chunks.append("")
    chunks.append("SHIP DECISIONS: " + (", ".join(f"{k} -> {v}" for k, v in verdicts.items())
                                        or "none"))
    text = "\n".join(chunks)
    print(text)
    with open(args.out, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
