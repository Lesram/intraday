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

## Cross-agent reconciliation (2026-06-25) — the replay t=1.87 is the LENIENT read

A third agent correctly flagged that my t=1.87 and the earlier t≈1.0 are **two
estimators on two surfaces**, not one gaining power:
- **t≈1.0** = 18 OOS trades from the LIVE forward record (real money).
- **t=1.87** = 68 trades from the REPLAY corpus, which runs structurally rosier
  (+$276 replay vs −$792 live on the same window — a ~$1,000 optimism gap).

So "t climbed 1.0→1.87 with more data" overstates it: the replay surface
flatters. **The honest read is the live one, still stuck near 1.0.** Replay
trend-slice CSV exported to `~/Desktop/desk/replay_trend_slice_costed_2026-06-25.csv`
for a trade-for-trade line-up against the live record.

**Time-to-verdict is quarters, not weeks.** Forward estimator (SNR from 18
live trades): t≥2 needs ~69 OOS trend trades — ~51 more than we have. At ~3
trend trades/week that's **~4 months minimum**, and only if the effect holds
(OOS effects usually shrink). Order-of-magnitude, not precise. So a live
trend-edge verdict is a **late-2026 question at the earliest** — accumulation
is free, but "near 2 on the replay" must NOT drift into "basically proven."

**Flip-gate coherence (for the retracement exit shadow):** when it's ever
considered for live, hold it to the SAME bar as entries — **costed and
OOS-stable at t≥2**, not "beats baseline gross in-sample." The earlier exit
"+$74 net, PF 1.85" was never costed; demanding t≥2 of the entry edge while
waving an exit change through on gross numbers would be incoherent.
