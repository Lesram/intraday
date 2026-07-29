# Exp 5 — Stop-loss ATR re-tune (chop regime)

**Status:** DESIGN — for offline backtest first; deployment after RC-1.5 + 5-session observation
**Author:** Saturday 2026-04-25 weekend sprint
**Builds on:** Track 1 forensic root-cause; pyramid_cut deep-dive (S4)

## Question

Track 1 finding: stop_loss is the second-largest dollar drag (−$68 over 12 sessions, 19% of exits, avg −$1.94/trade). Are chop stops set too tight, causing whipsaw losses on trades that would have recovered if given more room?

## Empirical signal (stop_loss bucket, n=35)

| Metric | Value |
|---|---|
| Total PnL | −$67.75 |
| Win rate | 20% |
| Avg PnL/trade | −$1.94 |
| Avg MFE/share | **$1.25** |
| Avg MAE/share | **$1.48** |
| Median bars held | 13 (vs 30 timeout cap) |
| MAE/MFE ratio (excursion asymmetry) | 2.19× |

**Key finding: MFE ≥ MAE in 54% of stop_loss trades** (19 of 35). These trades went *more* favorable than adverse at some point before being stopped — i.e., the trade had real momentum in our direction and then reversed. A wider stop *might* convert some of these to winners.

| Pre-stop favorable bucket | n | % |
|---|---|---|
| MFE ≥ MAE (clear favorable then reversal) | 19 | 54% |
| MFE ≥ 0.5 × MAE (moderate favorable) | 23 | 66% |
| MFE ≤ $0.10 (no favorable — stop was correct) | 3 | 9% |

## Comparison to other exit types

| Exit type | n | avg MFE | avg MAE | MAE/MFE | avg PnL |
|---|---|---|---|---|---|
| **stop_loss** | 35 | $1.25 | $1.48 | **2.19×** | −$1.94 |
| max_holding_period | 40 | $5.39 | $4.10 | 0.83× | +$3.47 |
| failure_to_follow | 22 | $1.17 | $2.92 | 4.08× | −$0.73 |
| pyramid_cut (all) | 57 | $0.47 | $2.92 | 6.21× | −$2.89 |

`max_holding_period` (the primary earner) sees winners ride to bigger MFE than MAE. `stop_loss` sees moderate MFE then a 2.19× larger MAE — the trade WAS working before reversing. Compare to `pyramid_cut` (MAE/MFE = 6.21×) where the trade barely went favorable at all — those are clean losers, not whipsaws.

This shape supports the hypothesis: stop_loss is firing on real whipsaws. Wider stops in chop might convert some to winners.

## Hypothesis

**H5.A** (modest widen): chop stop ATR 2.5× → 3.0×. Reduces whipsaw on trades with MFE > MAE before reversal. Acceptable downside on real adverse moves (additional 0.5× ATR loss in the bad case ≈ +$0.30/share).

**H5.B** (aggressive widen): 3.5×. More room for whipsaws to resolve. But risks larger losses on bad trades and may push more stop_losses into pyramid_cut territory (-1.0R = roughly 2.5× ATR for chop already).

**H5.C** (regime-conditioned): only widen IF MFE > 0.3× ATR has been observed mid-trade. (Adaptive stop.) More complex, requires per-position MFE tracking — already exists in `PyramidPosition.highest_price`.

## Counterfactual estimate (rough — no replay yet)

If we assume:
- Trades where MFE ≥ MAE (n=19) had 50% chance of recovering with wider stop → +$1 avg/trade if recovered
- Trades where MFE < 0.5 × MAE (n=12) would still hit a wider stop → −$0.50 avg additional loss/trade
- Trades where MFE ≤ $0.10 (n=3) the stop was correct, wider stop adds extra loss → −$0.50 each

Rough expected delta if we widen:
- Recovery wins: 19 × 0.5 × $1.00 = +$9.50
- Tight-loss extras: 12 × −$0.50 = −$6.00
- Already-bad extras: 3 × −$0.50 = −$1.50
- **Net: +$2.00 over 35 trades = +$0.06/trade**

Marginal at best on this estimate. Worth a replay test but not a "free $50/session." Real test: how does the trajectory continue *after* the current stop fires? Replay can answer that.

## Experimental plan

### Phase 1 — Offline replay backtest (Sunday or post-RC-1.5)

Run replay with three configurations on the same 14-day Alpaca bars + same live brain seed:
- Baseline: chop stop ATR = 2.5×
- H5.A: chop stop ATR = 3.0×
- H5.B: chop stop ATR = 3.5×

Compare:
- Trade count, win rate, expectancy
- stop_loss share of exits
- pyramid_cut share of exits (do widen-stops convert into deep cuts?)
- max_holding_period share (do they convert into timeout winners?)
- Net PnL delta

Each run ~50 min on current replay. Three runs ~150 min. Cacheable.

Code change: in `backend/organism/adaptive_exits.py` (or wherever stop ATR table lives), parameterize the chop multiplier. Pass via env var or config so we can run variants without code changes.

### Phase 2 — Decision criteria

Ship Exp 5 if and only if:
- Backtest shows expectancy improvement >= +$0.50/trade in chop AND
- pyramid_cut share does NOT increase by more than 25% relative AND
- Max drawdown does not worsen by more than 0.5% absolute.

If H5.A and H5.B both pass: ship the smaller change (H5.A) first; consider H5.B as RC-3.

### Phase 3 — Live shadow before flipping

Even if backtest passes: run the new stop ATR in shadow mode for 3 sessions (log "what would have happened") before changing live behavior. Same pattern as the regime + ML-weight shadow telemetry already in RC-1.5.

## Risk controls

- The drawdown-kill is unchanged (still 20%).
- Per-trade notional cap (eb90fa3) is unchanged.
- Wider stops mean larger per-trade losses on real adverse moves. The risk-budget cap from H1 (production = 0.25%) is the protection.
- If Exp 5 ships and live performance regresses, revert is the same `git checkout` + container rebuild as any other RC.

## Out of scope for Exp 5

- Stop ATR re-tune in non-chop regimes. We have ~zero data on trending/high-vol because the regime classifier wedged in chop. Defer until regime classifier ships in RC-2.
- Adaptive (H5.C) trailing-stop variant. More complex; once Exp 4 (trailing widen) and Exp 5 (initial stop widen) both validate, consider an adaptive scheme as Exp 7.

## Timing

- **Sunday afternoon (during this sprint)**: run the three replay configurations to get a first-look number.
- **Post-RC-1.5 deploy + 5 sessions**: add live shadow telemetry for the chosen variant.
- **Post-RC-2 deploy + 3 shadow sessions**: ship the best variant as RC-3.

Estimated calendar time to live: 3 weeks from RC-1.5 deploy.
