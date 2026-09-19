# REAL-MONEY STATUS REFRESH — Stage 1 (tiny live capital)
**Audit time:** 2026-04-25T00:50Z
**Live commit:** `ce06d41`
**HEAD:** `eb90fa3`

The goal of Stage 1 is to deploy **the smallest possible amount of real capital** (e.g., $500–$2000) that still exercises live broker / live data / live alerting paths — i.e., real friction without real exposure to a strategy that hasn't yet shown profitability.

---

## What is already in place

| Item | State | Evidence |
|---|---|---|
| Paper trading runtime stable | YES | 12 sessions live on `ce06d41`, no halts, no freezes, restart count 0 |
| Brain persistence guards (F1–F4 + F-lite) | LIVE | guard helpers route all save() calls; trained-state overwrite refused; bypass audit instrumented |
| Manifest ↔ learning_state coherence | YES | both at gen 124, total_trades 396 |
| Brain backup convention | partial | brain volume mounted from host (`./organism_brain:/app/organism_brain`) — survives container restart, but no scheduled snapshot rotation yet |
| Drawdown-kill at 20% | LIVE | governance enforces; container env confirms `ORGANISM_DRAWDOWN_KILL_PCT=0.20` |
| Account ACTIVE on paper | YES | Alpaca PA3RLEN7T0N4 |
| Alpaca SDK + auth path | LIVE | functional, occasional SSL retries observed but no impact |
| Universe stable at 22 symbols | LIVE | including PSQ/SH inverse ETFs |
| Evolution freeze lifted (post-300) | LIVE | total_trades=396 > 300 floor |
| ML classifier+regressor trained, 79 features | LIVE | manifest confirms |
| Audit trail (trade_history.csv) | LIVE | 396 rows, with mfe/mae/regime/exit_reason — analysis-grade |
| Exp 1A + Exp 2 deployed and observed | LIVE | reduced pyramid_cut churn and PSQ/SH chop drag respectively |
| AGENTS.md / CONTROL_PLANE.md / mapss.md | LIVE | engineering operating contract in place |
| Two-step review bundle convention | partial | docs/engineering/reviews/pr-003-1756a154/ exists; pattern in use |
| CI pipeline (`pr-verify.yml`) | LIVE | path-based; spec-drift check exists |
| Daily post-close audit workflow | LIVE | `paper-postclose-audit.yml` runs 22:15 UTC |

---

## What still must be deployed (offline-ready, in `eb90fa3`)

These are P0/P1 to Stage 1 — they all sit in `eb90fa3` waiting for the next deploy:

| Capability | Why it's a Stage-1 prerequisite |
|---|---|
| **Per-trade notional cap** | Must cap any individual trade size; on real capital, even one mis-sized order can exceed the entire Stage-1 budget |
| **Daily max-loss circuit breaker** | Must auto-halt if cumulative day P&L crosses a configurable threshold; protects against death-by-1000-cuts |
| **H1 production risk-budget cap** | Caps risk-budget at 0.25% of equity (production weights) — hard ceiling distinct from Kelly recommendation |
| **H2 feature drift guard** | Refuses to use ML signal when features drift outside training distribution |
| **Canonical drawdown-kill resolution + startup validator** | Single source of truth for the 20% kill across env / dotenv / code default; validator logs at startup so we know what's actually loaded |
| **Compose drawdown-kill default alignment** | Closes a real env/code-default mismatch |
| **H5 settings API frozen/halted enforcement** | When governance is frozen/halted, settings writes must be refused — otherwise an operator can accidentally re-enable trading mid-incident |
| **Slack/webhook alert wiring** | Real capital requires real-time alerting; you can't be at the desk continuously |
| **G1/G2/G3 mechanical fixes** | Reduce pyramid_cut and cooldown drag; without these, Stage 1 starts with a known mechanical leak |
| **Exp 4 trailing-stop giveback control** | Reduces a (small) but observed giveback; bundled because it's already integrated and tested |

**All of these are `eb90fa3` content.** A clean deploy of `eb90fa3` resolves the entire offline-ready hardening backlog in a single shot.

---

## What still must be proven (after `eb90fa3` deploy)

The deploy adds capability; the **observation phase that follows the deploy** is what makes Stage 1 safe. The proofs we need:

1. **5+ clean post-deploy paper sessions** with no halts, no manifest corruption, no governance-config mismatches at startup.
2. **Notional cap reject path fires correctly** — synthetic test: try to send an order > cap, observe rejection in logs and metrics.
3. **Daily max-loss kill fires correctly** — synthetic test or replay: simulate a sequence of losses crossing the threshold; observe halt event.
4. **Alert wiring delivers** — fire a synthetic alert event, confirm Slack/webhook receives it.
5. **Canonical drawdown-kill startup validator logs the correct value (0.20)** — visible in container logs at startup.
6. **No regression in trade execution latency, brain save cadence, or ML retrain cycle.**
7. **Expectancy is at least neutral** over the first 5 post-deploy sessions, with G1/G2/G3 reducing pyramid_cut share by ≥30%.
8. **Exp 4 trailing-stop giveback** shows measurably reduced giveback in chop (specific to trailing_stop exits, where the per-share MFE-vs-realized gap shrinks).

Until those eight proofs come back green, **no real capital should be moved.**

---

## What remains blocked (cannot be addressed before deploy)

These do not block the deploy itself but block Stage 1 capital:

- **Brain backup rotation** is not yet automated. Currently brain is host-mounted, so it survives restarts, but a corrupted save propagates instantly. We need a scheduled `cp -r organism_brain organism_brain_$(date +%F)` rotation, ideally on the post-close hook.
- **Replay regression in CI** is not gating PR merges. We can run it manually at deploy time but the long-term protection requires CI integration.
- **Real-money position sizing policy** is not yet documented (Stage-1 budget, per-trade cap as % of budget, max simultaneous positions). The `MAX_OPEN_POSITIONS=8` from the paper config is too high for $1K-$2K capital — at that size you can support maybe 2 positions with non-trivial size.
- **Tax / accounting / wash-sale tracking** for real capital is not in scope for paper but will be in scope for real.
- **Confidence-bucket inversion (Exp 3 hypothesis)** is not yet acted on — but this is *not* a Stage-1 blocker; it's a profitability question. Stage 1 is about safety + plumbing, not about edge.

---

## Timeline assessment

| Question | Answer |
|---|---|
| Did the timeline improve this week? | **Slightly improved.** `eb90fa3` is now fully composed (8 commits, 1144 LOC, 14 new tests) — the offline-ready stack is complete and tested, where last week it was partially-tested. |
| Did the timeline stay flat? | n/a |
| Did the timeline slip? | **No.** No new P0s emerged; no regressions discovered. The strategic blocker (deploy `eb90fa3`) is well-defined and ready. |
| What is the earliest realistic Stage-1 capital date? | **2026-05-12 (Mon, ~2.5 weeks)** — assuming `eb90fa3` deploys Mon 2026-04-27 pre-open and the 8 proofs come back green within 10 sessions. |

This is a tightening of last week's "early-to-mid May" estimate by ~5 days because the bundle is more complete than expected.

---

## Stage-1 specifics (reference, when we get there)

When the proofs come back green and Stage 1 begins:

- **Capital:** start at $500–$1,000.
- **Per-trade notional cap:** $200 absolute or 20% of capital, whichever lower.
- **Daily max-loss kill:** $50 or 5% of capital, whichever lower (much tighter than 20%).
- **Max open positions:** 2 (override `MAX_OPEN_POSITIONS=8`).
- **Universe:** consider trimming to top 8 most-liquid symbols only (not the full 22) to reduce concentration risk and slippage variance.
- **Minimum runtime:** 4 weeks at Stage 1 before considering Stage 2 (graduate to $5K with relaxed caps).

These are notes for the eventual Stage-1 cutover, not action items for this weekend.
