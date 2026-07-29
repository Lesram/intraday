# Residual Mean-Reversion — Costed OOS Verdict (settled)

**Date:** 2026-06-25 · **Script:** `scripts/residual_mr_oos_backtest.py` · **Corpus:** `broad_corpus_v2` (72 RTH sessions, Mar 9–Jun 18, 22 symbols; overnight gaps masked).

## Question
The audit rated the **plain** MR scanner net-negative (−3.8 bps/trade after costs, PF 0.67, in-sample). The **`ResidualMeanReversionEngine`** (market-neutral idiosyncratic-residual variant) was shadow-only and **never measured**. Does it have a cost-clearing edge? This is the proper costed, out-of-sample read.

## Method
Faithful to the engine: residual = `stock_ret − (0.45·β_spy·SPY + 0.25·β_qqq·QQQ + 0.30·β_sec·SECTOR)` over a 120-bar rolling regression; z-score over the same window; **long-only** entry at `z ≤ −threshold`; market-neutral pnl = forward **residual** return over the hold (betas fixed at entry). 15 tradeable names (the 7 ETF/factor names excluded). Net = gross − round-trip cost; ~4 bps is the realistic cost for a market-neutral position (stock leg + hedge legs).

## Result — no edge anywhere

| z ≤ − | hold | n | gross (bps) | t | net@4bps | t@4 | verdict |
|---|---|---|---|---|---|---|---|
| 2.0 | 10 | 3738 | 0.65 | 1.24 | −3.35 | −6.43 | no edge |
| 2.0 | 20 | 3738 | **1.67** | **2.15** | −2.33 | −3.00 | no edge |
| 2.0 | 40 | 3738 | 1.78 | 1.61 | −2.22 | −2.01 | no edge |
| 2.5 | 10/20/40 | 1642 | 0.20 / 0.67 / −0.44 | <1 | −3.8 / −3.3 / −4.4 | neg | no edge |
| 3.0 | 10/20/40 | 758 | 0.80 / 0.10 / 0.20 | <1 | −3.2 / −3.9 / −3.8 | neg | no edge |

- **Gross edge is tiny and barely significant** (best cell z2.0/hold20: +1.67 bps, t=2.15) — a real-but-uneconomic idiosyncratic reversion.
- **Net is negative in every cell** at realistic cost (−2.2 to −4.4 bps, t as low as −6.4).
- **Bigger dislocations do not revert more** — gross *decreases* at z=2.5/3.0, so there's no threshold that rescues it. Not a tuning problem.
- Per-symbol gross is a few positive (CAT +10.5, TSLA +6.6, AMD +6.6) and many negative — consistent with noise, no robust cross-sectional structure, and all pre-cost.

## Verdict
**Residual MR has no cost-clearing edge — confirmed, OOS, properly costed, across the parameter space.** Same fate as the plain MR variant. **MR is settled; stop circling it.**

## Implication for the platform
This closes the last open strategy question. Combined with the prior findings — ML is noise (corr≈0, dropped from the gate), momentum/breakout is profitable *only* in trending tape (and correctly silent in chop), and now MR (both variants) net-negative — the honest status holds: **no confirmed cost-clearing edge in any regime.** Go-live stays gated on an edge that does not yet exist. The path forward is genuine research, not another tuning loop; the only positive-expectancy cell the audit ever found (trending/breakout, +$184 on 36 trades) needs more trending sessions to accumulate a verdict — which happens on its own as the engine keeps correctly standing down in chop and trading only on conviction.
