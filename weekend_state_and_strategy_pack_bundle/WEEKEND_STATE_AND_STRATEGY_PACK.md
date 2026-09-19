# WEEKEND STATE AND STRATEGY PACK
**Generated:** 2026-04-25T00:50Z (Friday post-close, weekend audit window)
**Live commit:** `ce06d41`
**HEAD:** `eb90fa3`
**Audit type:** READ-ONLY (no edits, no deploys, no restarts, no broker mutations)

This is the authoritative weekend package. The 8 derivative reports referenced below contain the granular evidence; this file is the single source of truth answering: where are we, did this week help, should we deploy this weekend, what are we doing next.

---

# 1. Executive summary

**What is live.** The container has been running cleanly since 2026-04-16 (and was just restarted at 00:48Z today, restart count 0, healthy). Live commit verified by file SHA = `ce06d41`. That gives us:
- **Exp 1A live** — chop-regime minimum-hold gate for pyramid_cut.
- **Exp 2 live** — chop inverse-ETF entry suppression.
- **Exp 3 prep live** — confidence inversion side-by-side logging (observation only).

The 8-commit chain `ce06d41 → eb90fa3` is offline-ready: G1/G2/G3 mechanical fixes, Exp 4 trailing giveback, H1/H2 risk-budget cap + feature drift guard, per-trade notional cap, daily max-loss kill, alert wiring, H5 settings governance, canonical drawdown-kill, compose alignment.

**What worked this week.** (1) The platform stayed up — 5 clean sessions, no halts, no freezes, manifest+learning_state always coherent. (2) Exp 1A enforced (avg chop pyramid_cut bars_held=7.8). (3) Exp 2 eliminated inverse-ETF chop drag (3 PSQ/SH trades total in 12 sessions, all early-window). (4) Exp 3 prep produced the signal it was designed to surface — mid-confidence (0.5–0.6) is the only positive bucket (+$0.27 expectancy), confirming a non-monotonic confidence→outcome mapping. (5) Friday closed essentially flat (−$2.17, 26 trades, 42% win rate); strategy-pure P&L excluding broker reconciliation events was −$0.08.

**What did not work.** (1) Cumulative live-window expectancy is **−$0.59 / trade** over 182 trades since `ce06d41` (12 sessions, −$107.98 total). (2) Pyramid_cut is the dominant drag — 31% of all exits, −$165 over the window. (3) Stop_loss is the second drag — 19% of exits, −$68. (4) Win rate at 31% with 1.43× win/loss ratio is below breakeven (0.31 × 1.43 = 0.443). (5) Directional accuracy is also 31% — meaning we're often wrong on direction, not just unlucky on outcomes.

**Did the platform improve this week?** **YES — but in plumbing, not P&L.** The `eb90fa3` bundle is now fully composed and tested (8 commits, +1144/−13, 14 new tests). The offline-ready hardening backlog that was partial last week is complete. P&L did not improve; expectancy is roughly flat-to-slightly-better than the prior week.

**Should we deploy anything this weekend?** **NO.** The deploy adds 6 distinct behavior changes — the right window for it is Monday pre-open with a human at the keyboard. The two mandatory P0 preflight items (replay regression on `eb90fa3` + brain backup) should be done Saturday so Monday is just a checklist.

**Single most important next move.** Run the Saturday-morning preflight (replay + brain backup), compose the PR review bundle, and **deploy `eb90fa3` at Monday open (8:30–9:00 ET)** with the full preflight from `RC_DEPLOY_READINESS_RECHECK.md`.

---

# 2. Live truth right now

| Item | Value |
|---|---|
| Live container | `intra-api-1`, healthy, restart count 0 |
| Live container started | 2026-04-25T00:48:48Z (~24 min before audit) |
| Live container image created | 2026-04-16T02:42:19Z |
| Live container commit | **`ce06d41`** (verified via `live_engine.py` SHA = `9b5ddb5c…`; only `ce06d41` matches across the post-`7d36b61` chain) |
| Repo HEAD | `eb90fa369e2739f77c7b1789aa47bd8b83184912` |
| Branch | `main` |
| Tracked worktree | clean (only untracked audit `*.md` files and bundle dirs — intentional) |
| Worktree ambiguity | **NONE** |
| Live ↔ HEAD gap | 8 commits |

### Live capabilities

| Capability | Status |
|---|---|
| Exp 1A (chop min-hold pyramid_cut) | **LIVE** |
| Exp 2 (chop inverse-ETF suppression) | **LIVE** |
| Exp 3 prep (confidence inversion logging) | **LIVE** |
| F1–F4 + F-lite brain guards | **LIVE** |
| ML classifier+regressor (79 features) | **LIVE** |
| Drawdown-kill 20% governance | **LIVE** |

### Offline-ready in `eb90fa3`

Exp 4, G1/G2/G3, H1, H2, per-trade notional cap, daily max-loss circuit breaker, Slack/webhook alert wiring, H5 settings API enforcement, canonical drawdown-kill resolver+startup validator, compose drawdown-kill default alignment. **All in `main` HEAD, all tested (114 tests pass per last commit log).**

### Frozen

Brain persistence path (F1–F4 + F-lite). Observation-only. No further structural edits in flight.

### Backlog

Phase C-1 ranking_score/direction/expected_return/size separation; Phase C-2 microstructure alpha; Phase C-3 staged learning→production transition; Stage-1 capital plan; Exp 3 execution variant; Exp 5 stop-loss ATR re-tune; brain backup rotation; replay regression in CI gate.

---

# 3. Current brain / runtime snapshot

From `organism_brain/manifest.json` (saved 2026-04-24T20:00:24Z, post-close):

| Field | Value |
|---|---|
| `brain_format_version` | 2 |
| `total_runs` | 1300 |
| `generation` | **124** |
| `total_trades` | **396** |
| `cumulative_pnl` | **−$621.92** |
| `best_sharpe` | **3.4363** |
| `ml_is_trained` | **true** |
| `feature_count` | **79** |

`learning_state.json` is **in sync**: gen=124, total_trades=396, cumulative_pnl=−621.92, best_sharpe=3.4363, retrain_count=124, drift_events=0.

| Runtime | Value |
|---|---|
| Container health | healthy |
| Container uptime | 24 minutes (just restarted) |
| Container restart count | 0 |
| Account | ACTIVE, paper, PA3RLEN7T0N4 |
| Peak equity | $111,784.74 |
| Current equity | $111,531.07 |
| Drawdown vs peak | −0.227% (well within 20% kill) |
| Positions | flat (post-close, EOD policy) |
| `frozen` | false |
| `trading_halted` | false |
| Universe size | 22 |
| Tick interval | 10 s |

Manifest ↔ learning_state coherence: **YES.**

---

# 4. Friday post-close review (2026-04-24)

| Metric | Value |
|---|---|
| Trades | 26 |
| Net PnL | **−$2.17** (essentially flat) |
| Win rate | 42.31% |
| Expectancy | −$0.083 / trade |
| Avg hold | 918 s |
| Best | NVDA +$19.46 (`reconciliation_adjustment` — broker side) |
| Worst | AMZN −$21.55 (`reconciliation_adjustment` — broker side, offsets the NVDA above) |
| Strategy-pure PnL (excl. reconciliation) | −$0.08 |

**Exit reason breakdown:** stop_loss=6 (−$21.42), max_holding_period=6 (+$14.09, 100% wins), trailing_stop=4 (+$0.03), failure_to_follow=3 (−$1.96), pyramid_cut=3 (−$4.80), reconciliation=2 (−$2.09), take_profit=1 (+$11.64), ml_reversal=1 (+$2.34).

**Confidence:** the **0.5–0.6 bucket** (n=11) was **+$15.80 (+$1.44 expectancy)** — the only positive bucket. ≥0.7 (n=3) = −$2.49.

**Regime:** 100% chop. **Trustworthy: YES.**

Full breakdown: `FRIDAY_POSTCLOSE_REVIEW.md`.

---

# 5. Weekly stack verdict

## Cumulative metrics — full live window since `ce06d41` (12 sessions, 182 trades)

| Metric | Value |
|---|---|
| Trades | 182 |
| Net PnL | **−$107.98** |
| Win rate | 31.32% |
| Expectancy | **−$0.59 / trade** |
| Avg win / avg loss | $3.65 / −$2.55 (1.43× ratio) |
| Pyramid_cut share | **31.3% of exits** (n=57, −$164.97) |
| Timeout / max_hold share | 22.0% (n=40, **+$138.67** — primary earner) |
| Stop_loss share | 19.2% (n=35, −$67.75) |
| Trailing-stop share | 9.3% (n=17, −$10.14, $77/share aggregate MFE) |
| PSQ/SH chop trades | **3 total in 12 sessions** (all early window; Exp 2 enforcing) |
| Confidence ≥ 0.7 expectancy | −$0.72 (n=5) |
| Confidence 0.6–0.7 expectancy | −$0.91 (n=14) |
| Confidence 0.5–0.6 expectancy | **+$0.27 (n=25)** ← only positive |
| Confidence < 0.5 expectancy | −$0.71 (n=138) |
| Post-300-trade behavior | 98 trades, −$35.89, 33.7% win rate |

## Per-experiment verdicts

- **Exp 1A — KEEP.** Working as designed. Avg chop pyramid_cut bars=7.8; full cuts honor 5-bar floor.
- **Exp 2 — KEEP.** Working. Eliminated inverse-ETF chop drag.
- **Exp 3 prep — KEEP, hypothesis confirmed but execution NOT YET ACTIONABLE.** Bucket inversion is real; n is too small for execution change. Need 60+ samples per bucket and offline backtest.
- **Exp 4 (queued) — KEEP IN QUEUE, BUNDLE INTO NEXT DEPLOY.** Trailing giveback small-dollar but real; do not ship in isolation.

## Live-stack overall verdict

**KEEP BUT PREPARE NEXT CHANGE.** Stable platform, working experiments, but negative expectancy and addressable drag. The next deploy (`eb90fa3`) is the right call.

### Explicit answers

- **Is the current live stack still the right stack?** YES, as a *waypoint*. NO, as a final stack — deploy `eb90fa3` Monday.
- **Is Exp 3 actionable now?** NO. Continue logging on `eb90fa3` post-deploy; design execution variant only after 60+ bucket samples + offline 30-day backtest.
- **Should Exp 4 move up?** NO. Stay queued; bundle into the `eb90fa3` deploy (which is what already exists).

Full breakdown: `WEEKLY_STACK_VERDICT.md`.

---

# 6. Release candidate re-check — `eb90fa3`

**Is `eb90fa3` still the correct next RC?** **YES.** No newer commit on `main`; bundle composition is logically coherent (governance + risk + mechanical + Exp 4); 1144 LOC additions, 14 new tests; addresses 5 P0 real-money blockers in one shot.

**Is the worktree/HEAD/live relationship clean?** **YES.** No tracked diff, HEAD = `main` = `eb90fa3`, live container at `ce06d41` is verified (file SHA forensics).

**Outstanding blockers before deploy:**
- P0: Replay regression on `eb90fa3` against last 30 days (not yet done).
- P0: Brain backup snapshot before deploy (not yet done).
- P1: PR review bundle in `docs/engineering/reviews/pr-XXX-eb90fa3/` per AGENTS.md.
- P1: Slack/webhook URLs provisioned in `.env`.
- P1: Monday-morning attention available.

**Should we deploy this weekend? NO.** Five reasons:

1. Weekend deploy has no market-hours human visibility.
2. Two mandatory P0 preflight items still outstanding.
3. Live-stack is mildly negative but stable — no fire being put out, no urgency premium.
4. Exp 3 prep is still accumulating useful signal data.
5. No external deadline forces the deploy this weekend.

**Recommended deploy window: Monday 2026-04-27 pre-open (8:30–9:00 ET).**

**If yes, exact preflight checklist:** see `RC_DEPLOY_READINESS_RECHECK.md` §"If yes, exact preflight checklist" — full 22-item checklist.

---

# 7. Whole-platform status refresh

## Structural / mechanical state

- **Persistence path:** F1–F4 + F-lite shipped earlier; observation-only / FROZEN. Read-back invariant holds. No suspicious-write events in log window.
- **State restoration:** governance restored from brain on startup (`Governance state restored from brain` confirmed at 00:48:56Z). Manifest+learning_state coherence: 100%.
- **Mechanical drag:** **G1/G2/G3 still offline-ready.** This is the platform's largest known structural gap.
- **Universe:** stable at 22 symbols, including PSQ/SH inverse ETFs (gated by Exp 2 in chop).

## Algorithmic state

- **Confidence weighting:** production weights live (ml=0.5, breakout=0.3, tension=0.2). Working but bucket-distribution is suspicious (76% of trades are <0.5 confidence; high-confidence bucket loses).
- **Stop sizing:** chop=2.5×ATR. Producing −$1.94 avg/stop, 19% of exits. Re-tune queued (Exp 5).
- **Pyramid sizing:** correct in normal regimes; G3 NaN guard offline-ready protects edge case.
- **Trailing stops:** chop=3.0×ATR currently; Exp 4 widens to 5.0× (default) once deployed.
- **Direction logic:** 31% directional accuracy is a flag — this is alpha+breakout output, not random. Investigation queued.
- **ML retrain:** healthy cadence (retrain_count=124). 0 drift events. H2 feature drift guard offline-ready.

## Organism coherence

- **Working as one organism:** ML signal + alpha scanner + breakout scanner + Kelly sizer + adaptive exits + pyramider + brain persistence + self-evolution + governance + regime detector — all wired into the unified `live_tick()`. Verified.
- **Cross-component synchronization:** brain↔learner↔signal_gen all reading authoritative best_sharpe. Trade counts increment at source (no double-count).
- **Telemetry:** decision_telemetry, equity_curve.csv, trade_history.csv all populated and analysis-grade.

## Dormant / dead / partial subsystems

- **Exploration:** fully removed. CSV `is_exploration` column always False — cosmetic; no execution path.
- **`entry_source` empty for ml_reversal/trailing_stop entries:** observability gap, non-blocking.
- **`policy_version` and `config_hash` empty:** should be set on deploy/startup; non-blocking.
- **Phase C subsystems** (clean ranking_score, microstructure alpha, staged transition): not implemented. BACKLOG.

## Organism status

**LEARNING / ADAPTING AS INTENDED**, with a known mechanical drag (pyramid_cut) being addressed in `eb90fa3`. The organism is not "mostly legacy" — it is the unified architecture intended by improve9 with the F-track persistence guards. It is also not "partially functional" — every wired component is firing.

## Coherence verdict

**PARTIALLY COHERENT.** The platform is structurally coherent (one unified tick, one brain, one persistence path). It is also algorithmically incoherent in one specific way: **the confidence-bucket inversion** says the high-confidence path is doing the wrong thing in chop, and that contradicts the design intent that more confidence = more profitability. Until Exp 3 execution lands, that's a coherence gap. We are not FRAGMENTED, but we are not COHERENT — we are between.

---

# 8. Master issue ledger refresh

**Headline:** of **9 P0 issues, 4 are RESOLVED (F-1..F-4) and 5 are OFFLINE READY** (notional cap, daily max-loss, H1, H2, canonical drawdown-kill). **Zero open P0s.**

| Category | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| Real-money blockers | 5 (all OFFLINE READY) | 4 | 0 | 0 |
| Strategy / algorithm | 0 | 2 | 4 | 0 |
| Mechanical / structural | 0 | 3 | 0 | 1 |
| Brain / persistence | 4 (all RESOLVED) | 0 | 0 | 0 |
| Experiments | 0 | 0 | 6 | 0 |
| Observability / ops | 0 | 1 | 4 | 0 |
| Coherence | 0 | 0 | 0 | 6 |
| **Total** | **9** | **10** | **14** | **7** |

Full ledger: `MASTER_ISSUE_LEDGER_REFRESH.md`.

Top 5 actionable items this window:
1. **Deploy `eb90fa3`** Monday pre-open → resolves RM-1..RM-5, RM-7, RM-8, MECH-1..MECH-3, EXP-4.
2. **Saturday replay regression + brain backup** → unblocks safe deploy.
3. **Compose PR review bundle** → AGENTS.md two-step convention.
4. **Provision Slack URL in `.env`** → makes alert wiring useful.
5. **Brain backup rotation** in post-close hook → small ops task, big safety win.

---

# 9. Real-money status refresh

**In place:** paper runtime stable, F1–F4 brain guards, manifest coherence, drawdown-kill 20%, account ACTIVE, audit trail in place, Exp 1A/Exp 2 deployed, AGENTS.md/CONTROL_PLANE.md/mapss.md, CI pipeline, daily post-close audit workflow.

**Must deploy** (in `eb90fa3`): per-trade notional cap, daily max-loss kill, H1 production risk-budget cap, H2 feature drift guard, canonical drawdown-kill resolver + startup validator, compose drawdown-kill alignment, H5 settings API enforcement, Slack/webhook alert wiring, G1/G2/G3 mechanical fixes, Exp 4.

**Must prove (after deploy):** 5+ clean sessions, notional-cap reject path, daily max-loss kill path, alert wiring delivery, drawdown-kill startup validator log, no regression in latency / brain save / ML retrain, expectancy ≥ neutral over 5 sessions, G1/G2/G3 reduces pyramid_cut share by ≥30%, Exp 4 reduces trailing giveback measurably.

**Still blocked:** brain backup rotation automation, replay regression in CI, Stage-1 capital plan documentation, real-money policy discussion (capital, per-trade cap %, max positions for tiny capital, universe trim).

**Timeline:** **slightly improved** vs last week. Earliest realistic Stage-1 cutover = **2026-05-12** (Mon, ~2.5 weeks), conditional on `eb90fa3` deploying Mon 2026-04-27 pre-open and 8 proofs green by 2026-05-08. Last week's estimate was "early-to-mid May"; this is the firm version.

Full plan: `REAL_MONEY_STATUS_REFRESH.md`.

---

# 10. Next 14-day execution plan

**Window:** 2026-04-25 → 2026-05-08.

**Stays unchanged:** universe (22), ML weights, retrain cadence, freeze gate, confidence weights, stop ATR table, risk budgets, ALPHA_TOP_N=5, MAX_POSITIONS=8, tick=10s, bar boundary=true, horizon=18 bars, Exp 1A/Exp 2/Exp 3 prep, F-track guards.

**Observe next:** post-deploy week-1 metrics — pyramid_cut share (target ≤22%), stop_loss share (≤18%), trailing_stop avg PnL (≥$0), win rate (≥35%), expectancy (≥−$0.30), halt/freeze events (=0), alert wiring delivery (100%).

**Ships next:** `eb90fa3` Monday pre-open (8:30–9:00 ET).

**Prepared offline next:** Exp 3 execution variant + 30-day backtest scaffold; brain backup rotation; Stage-1 capital plan doc; replay-test CI gate; Phase C-1 design.

**Explicitly NOT changing:** strategy params during observation; universe; structural persistence; CI workflows; real capital movements.

**Before any real-money step:** all 12 gates from `REAL_MONEY_STATUS_REFRESH.md` and `NEXT_14_DAY_EXECUTION_PLAN.md` must be green.

| Decision | Trigger |
|---|---|
| Immediate next action | **Saturday: replay regression on `eb90fa3` + brain backup snapshot.** |
| Next deployment candidate | `eb90fa3` (no other candidate). |
| Next experiment candidate | Exp 3 execution variant (offline backtest first). Then Exp 5 stop-loss ATR re-tune. |
| Next hardening candidate | Brain backup rotation + replay regression in CI. |
| Next milestone decision point | **Fri 2026-05-08 close — Stage-1 readiness gate.** |

Full plan: `NEXT_14_DAY_EXECUTION_PLAN.md`.

---

# 11. Final verdict

## 1. Overall verdict

**READY IF SPECIFIC BLOCKERS ARE PATCHED.**

The platform itself is healthy and the next deploy is well-composed. We are not READY AS-IS because two P0 preflight items (replay regression on `eb90fa3` + brain backup) are still outstanding. We are far from HARD STOP — there are no open P0s with no fix in flight; every P0 is either RESOLVED or OFFLINE READY in `eb90fa3`.

## 2. Current live stack verdict

**KEEP AND REFINE.**

KEEP because: stable runtime, working experiments (Exp 1A + Exp 2), Exp 3 prep producing the signal it should, manifest coherence, post-300 evolution lifted cleanly. REFINE because: negative expectancy (−$0.59/trade), pyramid_cut drag (−$165 over 12 sessions), trailing-stop giveback. The refinement is `eb90fa3` itself.

## 3. Should anything be deployed this weekend?

**NO.**

## 4. If YES, exactly what?

n/a — verdict is NO.

## 5. If NO, exactly why not?

- No market-hours human visibility for a 6-behavior-change deploy.
- Two mandatory P0 preflight items not yet done (replay regression on `eb90fa3`, brain backup).
- Live stack is mildly negative but stable — no fire to put out.
- Exp 3 prep is still accumulating useful data on `ce06d41`.
- No external deadline forces a weekend deploy.
- Recommended window: **Monday 2026-04-27 pre-open**, with full preflight from `RC_DEPLOY_READINESS_RECHECK.md`.

## 6. Top 10 findings

1. **Live container is at `ce06d41`** (forensically verified). Repo HEAD is at `eb90fa3`. 8 commits offline-ready, 1144 LOC additions, 14 new tests, all P0/P1 hardening composed in one bundle.
2. **Live-window expectancy is −$0.59/trade** over 182 trades / 12 sessions. Negative but stable; cumulative P&L cost = −$108 (~0.10% of equity).
3. **Pyramid_cut is the dominant drag**: 31% of exits, −$165 over 12 sessions. G1/G2/G3 (offline-ready) targets this directly.
4. **Stop_loss is the second drag**: 19% of exits, −$68. Re-tune queued as Exp 5 post-deploy.
5. **Max_holding_period is the primary earner**: 22% of exits, **+$139** over 12 sessions; +89.5% win rate. The strategy makes money when it lets winners ride to time-limit.
6. **Confidence inversion is real**: 0.5–0.6 bucket = +$0.27 expectancy; ≥0.7 bucket = −$0.72 expectancy. Visible in both Friday and the full live window. Exp 3 hypothesis confirmed.
7. **Exp 1A is enforcing** (avg chop pyramid_cut bars=7.8) and **Exp 2 is enforcing** (only 3 PSQ/SH chop trades in 12 sessions, all early-window).
8. **No halt / freeze / drawdown trip in 12 sessions**. Drawdown vs peak = −0.227%, well within 20% kill. Container restart count = 0 since image rebuild.
9. **Manifest+learning_state perfectly coherent**: gen=124, total_trades=396, cumulative_pnl=−$621.92, ml_is_trained=true, feature_count=79, drift_events=0.
10. **No newer RC than `eb90fa3` is staged**, and the 8-commit bundle is logically coherent (governance + risk + mechanical + Exp 4) — not a kitchen-sink merge.

## 7. Top 5 remaining blockers to real-money readiness

1. **Deploy `eb90fa3`** — until then, per-trade notional cap, daily max-loss kill, alert wiring, canonical drawdown-kill, and G1/G2/G3 are all paper-only. Without these, no real capital can move responsibly.
2. **5+ clean post-deploy paper sessions** with all preflight proofs green (notional cap reject path verified, daily max-loss kill verified, alert delivery verified, drawdown-kill validator log verified, no regression in latency / brain save / retrain).
3. **Brain backup rotation** automated. Currently brain is volume-mounted, which protects against container restart but not against a corrupted save propagating instantly.
4. **Stage-1 capital plan documentation**: capital amount, per-trade cap as % of capital, daily max-loss as % of capital, max simultaneous positions, universe trim. Not yet written.
5. **Confidence-bucket inversion (Exp 3 hypothesis) understood but not yet acted on**. Until we either deploy an Exp 3 execution variant or otherwise resolve why high-confidence is loss-making, the strategy carries an unexplained algorithmic gap. Not deploy-blocking, but Stage-1-blocking.

## 8. Exact paths to all created reports

| # | Report | Path |
|---|---|---|
| 1 | Master pack | `/Users/marselkei/VS/intra/WEEKEND_STATE_AND_STRATEGY_PACK.md` |
| 2 | Bundle (evidence) | `/Users/marselkei/VS/intra/weekend_state_and_strategy_pack_bundle/` |
| 3 | Live state snapshot | `/Users/marselkei/VS/intra/CURRENT_LIVE_STATE_SNAPSHOT.md` |
| 4 | Friday post-close | `/Users/marselkei/VS/intra/FRIDAY_POSTCLOSE_REVIEW.md` |
| 5 | Weekly stack verdict | `/Users/marselkei/VS/intra/WEEKLY_STACK_VERDICT.md` |
| 6 | RC deploy re-check | `/Users/marselkei/VS/intra/RC_DEPLOY_READINESS_RECHECK.md` |
| 7 | Master issue ledger refresh | `/Users/marselkei/VS/intra/MASTER_ISSUE_LEDGER_REFRESH.md` |
| 8 | 14-day execution plan | `/Users/marselkei/VS/intra/NEXT_14_DAY_EXECUTION_PLAN.md` |
| 9 | Real-money status refresh | `/Users/marselkei/VS/intra/REAL_MONEY_STATUS_REFRESH.md` |
