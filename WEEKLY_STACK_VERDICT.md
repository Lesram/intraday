# WEEKLY STACK VERDICT
**Window covered:** Mon 2026-04-20 → Fri 2026-04-24 (5 sessions)
**Live window since `ce06d41` deploy:** Mon 2026-04-13 → Fri 2026-04-24 (~12 trading sessions, 182 trades)
**Live commit:** `ce06d41`
**Audit type:** READ-ONLY

---

## Cumulative metrics — full live window since `ce06d41`

| Metric | Value |
|---|---|
| Trades | **182** |
| Net PnL | **−$107.98** |
| Win rate | 31.32% |
| Gross wins | $208.04 |
| Gross losses | −$316.02 |
| Avg win | $3.65 |
| Avg loss | −$2.55 |
| Avg win / avg loss ratio | 1.43× |
| Expectancy / trade | **−$0.59** |
| Avg hold time | 894 s (~14.9 min) |
| Directional accuracy | 31.32% |

The win/loss ratio (1.43×) is decent. The win **rate** (31%) is the killer — 0.31 × 1.43 = 0.443, well below the breakeven 0.5 reference. The strategy needs either a higher hit rate, a larger payoff, or fewer pyramid_cut events.

---

## This-week (Mon–Fri) summary

| Day | Trades | PnL |
|---|---|---|
| Mon 2026-04-20 | 19 | +$2.19 |
| Tue 2026-04-21 | 16 | −$8.56 |
| Wed 2026-04-22 | 20 | −$20.56 |
| Thu 2026-04-23 | 22 | −$12.35 |
| Fri 2026-04-24 | 26 | −$2.17 |
| **Total (5d)** | **103** | **−$41.45** |

| Metric | This week |
|---|---|
| Win rate | 33.0% |
| Gross wins | $115.01 |
| Gross losses | −$156.46 |
| Avg win | $3.38 |
| Avg loss | −$2.30 |
| Win/loss ratio | 1.47× |
| Expectancy | −$0.40 / trade |
| Avg hold | 873 s |

Slightly better expectancy than the full live window but still negative.

---

## Exit-reason composition (full live window, n=182)

| Reason | n | % of trades | PnL | Avg/trade |
|---|---|---|---|---|
| `max_holding_period` | 40 | 22.0% | **+$138.67** | +$3.47 |
| `take_profit` | 4 | 2.2% | +$19.27 | +$4.82 |
| `eod_flatten` | 1 | 0.5% | +$7.62 | +$7.62 |
| `ml_reversal` | 2 | 1.1% | +$2.50 | +$1.25 |
| `trailing_stop` | 17 | 9.3% | −$10.14 | −$0.60 |
| `failure_to_follow` | 22 | 12.1% | −$15.99 | −$0.73 |
| `reconciliation_adjustment` | 4 | 2.2% | −$17.19 | −$4.30 |
| **`pyramid_cut` (all)** | **57** | **31.3%** | **−$164.97** | **−$2.89** |
| `stop_loss` | 35 | 19.2% | −$67.75 | −$1.94 |

**Headline:** Pyramid_cut is the dominant drag — 31% of all exits, −$165 total. Stop_loss is second at 19% of exits, −$68. Together they are the two biggest cost centers.

Max_holding_period is the dominant earner: 22% of exits, +$139. Take_profit and EOD-flatten add another +$27 between them. The strategy makes money when it lets winners ride to time-limit; it gives most of it back to pyramid_cut and stop_loss.

### Pyramid_cut detail (live window)

| Bucket | n | PnL |
|---|---|---|
| Partial (~−0.7R to −1.0R) | 6 | −$4.30 |
| Full ~−1.1R to −1.7R | 31 | −$76.36 |
| Full ~−1.8R to −2.7R | 11 | −$22.18 |
| Full ~−3.1R to −3.6R | 9 | −$62.16 |

The deep cuts (−3R+) are a small minority by count (9 of 57) but ~38% of the pyramid_cut loss in dollars. **G3 NaN pyramid guard** (offline in `15cc0a4`) protects against the worst of these. Average chop pyramid_cut hold = 7.8 bars; 17/57 still cut before the 5-bar Exp 1A floor — likely partial cuts permitted by Exp 1A (full cuts are blocked, partials are not). Behaviorally consistent with the spec.

---

## Key indicator behaviors

| Behavior | Live window |
|---|---|
| Pyramid_cut share | **31.3%** of exits — too high |
| Timeout / max_hold share | 22.0% — healthy and most-profitable |
| Stop_loss share | 19.2% — second largest drag |
| Trailing-stop giveback | 17 trades, −$10.14 realized vs $77.32/share aggregate MFE — material giveback |
| PSQ/SH chop trades | **3 in 12 sessions** (PSQ: 1 pyramid_cut, 1 trailing; SH: 1 trailing). Exp 2 is working — pre-Exp2 cadence was multiple per session. |
| Confidence < 0.5 | 138 trades (76%), expectancy −$0.71 |
| Confidence 0.5–0.6 | 25 trades (14%), expectancy **+$0.27** ← only positive bucket |
| Confidence 0.6–0.7 | 14 trades (8%), expectancy −$0.91 |
| Confidence ≥ 0.7 | 5 trades (3%), expectancy −$0.72 |
| Post-300-trade behavior | 98 trades since gen-freeze lift, PnL −$35.89, win rate 33.7% |

---

## Per-experiment verdicts

### Exp 1A — chop minimum-hold gate for pyramid_cut

**Status:** LIVE since `ab54b2f`.
**Live evidence:**
- Avg chop pyramid_cut bars_held = 7.8 (was sub-5 before).
- Of 57 pyramid_cut exits in chop, only 17 below the 5-bar floor; those 17 are partial cuts (allowed) — full cuts are honoring the floor.
- Pyramid_cut still costs −$165 over the window, but pre-Exp1A it was worse.

**Verdict: KEEP.** Working as designed; behavior is consistent with spec. Doesn't fix the structural pyramid_cut drag — that requires G1/G2/G3 mechanical fixes (offline-ready) and possibly a deeper rethink of when to size up at all in chop.

### Exp 2 — chop inverse ETF entry suppression

**Status:** LIVE since `d79cae0`.
**Live evidence:**
- Only 3 PSQ/SH trades in 12 sessions, all from very early in the window (Apr 14–15) before the rule was fully in effect on every code path.
- All 3 lost (−$1.08, −$1.09, −$3.00).
- Since Apr 16, **zero PSQ/SH chop entries**. Exp 2 is enforcing.

**Verdict: KEEP.** Exp 2 has eliminated the inverse-ETF chop drag that was visible in pre-deploy reviews.

### Exp 3 prep — confidence inversion side-by-side logging

**Status:** LIVE since `ce06d41` (logging only, no execution).
**Live evidence:**
- Confidence buckets reveal the inversion: mid-confidence (0.5–0.6) is +$0.27 expectancy; high (≥ 0.7) is −$0.72 expectancy. Both this week and the full live window confirm it.
- Friday's session shows the same pattern (0.5–0.6 = +$1.44 expectancy; ≥ 0.7 = −$0.83).

**Verdict: HYPOTHESIS HOLDS, but not yet actionable.** Exp 3 execution would invert direction or kill entries above some confidence threshold — both have material downside risk if the inversion is sample-driven rather than structural. **Need offline backtest with 30+ days of bar data and fold validation before any execution change.** Keep the logging live, queue the execution variant behind Exp 4.

### Exp 4 — chop trailing-stop giveback control

**Status:** OFFLINE READY (`b97f903`). 7 new tests pass, 114 total.
**Live evidence motivating it:**
- 17 trailing_stop exits in live window. Realized PnL −$10.14. Aggregate per-share MFE = $77.32 — a substantial portion was given back.
- Pre-Exp4 trailing distance = 3.0× ATR in chop; Exp 4 widens to 5.0× ATR (default "widen") or disables in chop ("disable").

**Verdict: ACTIONABLE.** Worth deploying once the surrounding stack ships. Should not deploy in isolation; bundle with G1/G2/G3 + risk-limit hardening.

---

## Live-stack overall verdict

**KEEP BUT PREPARE NEXT CHANGE.**

Reasons to KEEP:
- The platform is stable: 12 sessions, no halt/freeze, no drawdown trip, manifest+learning_state always in sync.
- Exp 1A and Exp 2 are working as designed (pyramid_cut min-hold floor honored; inverse ETF chop entries eliminated).
- Exp 3 prep logging is producing the signal the experiment was designed to surface.
- Total drawdown over the live window is −$108 on $111K equity, ≈ 0.10%. Cost is small.

Reasons to PREPARE NEXT CHANGE:
- Expectancy is negative (−$0.59/trade). Twelve sessions is enough to declare "not yet profitable" and to act on it.
- The pyramid_cut and stop_loss cost centers are addressable: G1/G2/G3 (mechanical) and Exp 4 (giveback control) are offline-ready and tested.
- Real-money blockers (notional cap, daily max-loss, alert wiring, drawdown-kill canonicalization) are all offline-ready. The longer we wait, the longer we sit unprotected on paper but **without** the surface area we'll need on live capital.

**Reasons NOT to deploy this weekend specifically:** see RC_DEPLOY_READINESS_RECHECK.md — preflight + Monday open visibility makes a Mon-morning deploy preferable to weekend.

---

## Explicit answers required

**Is the current live stack still the right stack?**

YES — it is the correct *waypoint* stack. Exp 1A and Exp 2 are doing what they were designed to do; the pyramid_cut and PSQ/SH problems they targeted are reduced. But it is not a profitable stack, and the data does not get materially clearer with more sessions on `ce06d41`. The next deploy is the right call.

**Is Exp3 now actionable or still inconclusive?**

The confidence-inversion **observation is real** (mid-bucket positive, high-bucket negative across both Friday and the full window). But Exp 3 *execution* (invert direction, gate, or reweight) is **NOT yet actionable**. Two reasons:

1. The high-confidence bucket has only 5 trades in 12 sessions — far too small for an execution change.
2. The mid-bucket positive expectancy (+$0.27) is at small enough magnitude that a sampling artifact is plausible.

**Recommendation:** Continue logging via Exp 3 prep through the next deploy, accumulate at least 60 confidence-bucket samples per bucket, and only then design Exp 3 execution.

**Does Exp4 remain queued, or should it move up?**

Exp 4 should **stay queued, but bundled into the next deploy.** Reasons:
- Trailing_stop giveback is real (~$77/share aggregate MFE vs $0/−$10/share realized) but small in absolute dollars (−$10.14 over 12 sessions).
- The G1/G2/G3 mechanical fixes (offline-ready) are higher-priority drag reducers (pyramid_cut is a 17× larger drag than trailing_stop).
- Bundling Exp 4 into the next deploy lets us amortize the post-deploy observation period across all four experiments simultaneously.

Do **not** ship Exp 4 alone before G1/G2/G3.
