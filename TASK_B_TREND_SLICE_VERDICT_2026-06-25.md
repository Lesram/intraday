# Task B — Trend-Momentum Slice: Costed Walk-Forward Verdict

**Date:** 2026-06-25 · **Script:** `scripts/trend_slice_walkforward.py` · **Data:** broad-replay baseline trades (`edge_experiments_2026-06-22`, 72 sessions), costed @3 bps round-trip.

## Why costs had to be added here
The replay's per-trade `pnl` is **gross** — verified `mean|pnl| == mean|(exit−entry)×shares|` exactly, so `cost_profile="realistic"` was NOT applied to the trade record. Every prior replay "net" number (incl. the exit-experiment `th_net_pnl`) was gross; relative arm comparisons still held, but absolute figures were flattered. This test applies the Task-A cost helper.

## Result — trend+high_vol slice, costed @3 bps

| split | n | net | exp/trade | t | PF | win |
|---|---|---|---|---|---|---|
| whole slice | 136 | $86.39 | 0.64 | 1.22 | 1.39 | 33.8% |
| in-sample (early ½) | 68 | −$7.76 | −0.11 | −0.16 | 0.95 | 27.9% |
| **OOS (late ½)** | **68** | **+$94.15** | **1.38** | **1.87** | **2.22** | **39.7%** |
| 3-fold OOS (fold 2 / fold 3) | 45 / 46 | +$29.9 / +$30.5 | 0.66 / 0.66 | 0.72 / 0.81 | 1.41 / 1.51 | both + |

Breakeven ≈ **7.3 bps** round-trip (net-positive below that cost).

## Verdict (pre-registered bar: net exp>0 @ t≥2 over ≥40 OOS trades, costed, stable)
**NOT YET PROVEN — keep accumulating.** It clears net>0 (+$94), n≥40 (68), and stability (both 3-folds positive), but the OOS **t=1.87 < 2.0**. The meaningful signal: t **climbed from ~1.0** (the brief's hand-split on 18 live trades) **to 1.87** on 68 OOS replay trades — moving *toward* the bar, not stuck. PF 2.22 OOS is genuinely encouraging.

This is the single most hopeful result in the whole effort — the only cell that's costed-OOS-net-positive and stable — but it is **not** an edge yet. Real money stays off until it clears t≥2 over more trending sessions. The path is patience + accumulation (the engine keeps trading only on conviction), not tuning.
