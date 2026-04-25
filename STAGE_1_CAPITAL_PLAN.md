# Stage-1 Capital Plan — Tiny Live Capital

**Status:** PROPOSAL for operator review
**Author:** Saturday 2026-04-25 weekend sprint, S18
**Builds on:** REAL_MONEY_STATUS_REFRESH.md, MASTER_ISSUE_LEDGER, Track 1 forensics, Strategy Thesis Review

This is the actual document we need before any real-money step. Concrete numbers, decision criteria, success/failure thresholds, escalation gates.

---

## Stage-1 mission

**Stage-1's purpose is NOT to make money.** It is to validate that:
1. The platform behaves identically on real Alpaca capital as it did on paper.
2. The risk controls (drawdown-kill, notional cap, daily max-loss, alert wiring) actually fire under real conditions.
3. The operator (you) can monitor, intervene, and recover without panic.
4. Real fills, real spreads, real slippage match our backtest assumptions within tolerance.

**Profitability is NOT a Stage-1 success criterion.** Track 1 + Strategy Thesis Review confirmed the platform's edge is currently small at best. Stage-1 success is **operational validation**, not edge demonstration.

## Capital amount

| Tier | Amount | Notes |
|---|---|---|
| Stage-1 starting capital | **$500** | smallest amount that exercises real broker mechanics |
| Maximum at Stage-1 | $1,000 | upper bound for first 4 weeks |
| Lower bound for live mechanics to be meaningful | $300 | below this, position sizes round to 1 share and tests are degenerate |

Recommendation: **start at $500.** Add $250 only if 2 clean weeks have passed AND no risk-control issues.

## Per-trade risk caps

| Parameter | Stage-1 value | Paper value | Why |
|---|---|---|---|
| Per-trade notional cap | **$100** | $X (TBD; eb90fa3 introduces this) | 20% of $500 capital. If a single trade goes very wrong, we lose at most the notional. |
| Risk-budget per trade (% capital) | **0.5%** = $2.50 | 0.25% (production) | Tight. With 1.5× ATR stop, max position size will be small. |
| Max position size (% capital) | **20%** = $100 | 10% | Higher % allowed because notional cap is the binding constraint. |
| Max simultaneous positions | **2** | 8 | Two positions × $100 notional = $200 capital deployed at peak. Half capital is reserve. |
| Daily max-loss kill | **$25** = 5% of capital | TBD (eb90fa3) | Auto-halt if cumulative day P&L < −$25. Resume next session. |
| Drawdown-kill | **5%** = $25 from peak | 20% paper | Override the production 20% — at Stage-1 capital, 20% is too forgiving. |

Implementation note: these values need to be set via env vars at container start. Not all are currently configurable — some require small additions to the config layer. **Pre-deployment task: verify each of these has an env-var-or-config knob.**

## Universe trim

Stage-1 should NOT trade 22 symbols. The reasons:
- Slippage on smaller-volume names is unpredictable at small notional sizes
- Easier to spot anomalies in 8 symbols than 22
- Allows tighter monitoring

**Stage-1 universe (8 symbols):**
- SPY (broad market, deepest liquidity)
- QQQ (tech-heavy index)
- NVDA (single-name liquid)
- AAPL (single-name liquid)
- MSFT (single-name liquid)
- AMZN (single-name liquid)
- TSLA (single-name liquid + volatile, good stress-test)
- IWM (small-cap exposure)

Skipping in Stage-1: PSQ, SH (inverse ETFs — Exp 2 already minimal usage; not worth complexity at $500); LLY/AVGO/XOM/CAT (less liquid retail-side); XLE/XLK (sector ETFs — redundant with single-names).

## Pre-Stage-1 gates (must be GREEN before any real $)

```
[ ] G1. RC-1.5 deployed Monday. 5+ clean post-deploy paper sessions.
[ ] G2. Pyramid_cut share post-deploy <= 8% of exits (validates the gate-fix
       diagnosis was correct).
[ ] G3. RC-2 deployed (regime classifier fix + ML weight drop) and 3+ clean
       sessions on RC-2.
[ ] G4. Notional-cap reject path verified live (synthetic test — submit
       order > cap, observe rejection in logs).
[ ] G5. Daily max-loss kill verified live (replay-only test of halt path).
[ ] G6. Alert wiring verified — Slack/webhook receives test event.
[ ] G7. Drawdown-kill startup validator log line confirmed at every container
       start (canonical resolver).
[ ] G8. Brain backup rotation active and producing daily snapshots
       (launchd verified).
[ ] G9. No regression in execution latency / brain save cadence / ML
       retrain over 2-week window.
[ ] G10. Stage-1 risk parameter knobs implemented and tested
       (notional cap = $100, daily max-loss = $25, drawdown kill = 5%,
       max positions = 2, universe override).
[ ] G11. Stage-1 transition checklist written (this document section
       below) and reviewed.
[ ] G12. Operator (you) availability confirmed for first week of live
       capital — daily morning checks, ability to halt/intervene.
```

All twelve must be checked. **Earliest realistic Stage-1 start: 4 weeks from RC-1.5 deploy = ~2026-05-25.**

## Stage-1 transition checklist (what you do day-of)

```
=== Pre-cutover (the day before) ===
[ ] Brain backup taken (verified in artifacts/)
[ ] Paper account performance summarized for the prior 2 weeks
[ ] All G1-G12 gates green
[ ] Set ALPACA_PAPER=false in .env
[ ] Set Stage-1 risk parameter env vars
[ ] Set ORGANISM_UNIVERSE_OVERRIDE=SPY,QQQ,NVDA,AAPL,MSFT,AMZN,TSLA,IWM
[ ] docker-compose down api
[ ] Transfer $500 from bank to Alpaca live account
[ ] Verify Alpaca live account ACTIVE and PDT-flagged-safely

=== Cutover morning (8:25 ET) ===
[ ] Verify .env has live keys (not paper)
[ ] curl https://api.alpaca.markets/v2/account → status="ACTIVE"
[ ] docker-compose up -d --build api
[ ] curl localhost:8000/health
[ ] Watch logs for "Alpaca account: live" or equivalent confirmation
[ ] Wait for first tick

=== First tick (9:30 ET) ===
[ ] Watch first 10 minutes attentively
[ ] Verify positions populate from REAL broker (not paper)
[ ] Verify drawdown-kill = 0.05 in resolved config
[ ] Verify max_positions = 2 in resolved config

=== End of day ===
[ ] Capture P&L (whatever it is — could be negative, that's fine)
[ ] Verify all positions closed by EOD flatten
[ ] Capture any ERROR or unusual log lines
[ ] Write end-of-day-1 note
```

## Daily Stage-1 monitoring (first 4 weeks)

Every weekday, by 9:30 ET:

```
[ ] curl localhost:8000/health
[ ] check container restart count (must = 0 today)
[ ] cat organism_brain/manifest.json — verify gen, total_trades increase
[ ] grep ERROR logs/application.log | wc -l — note count
[ ] check Alpaca account: equity, drawdown vs Stage-1 starting capital
[ ] verify positions count <= 2
```

By 4:30 ET (post-close):

```
[ ] Today's PnL: $___
[ ] Today's trades: ___
[ ] Today's halt events: ___ (must be 0 unless intentional)
[ ] Today's pyramid_cut share: ___% (target <= 8%)
[ ] Today's stop_loss share: ___% (track for Exp 5)
[ ] Today's win rate: ___%
[ ] Brain backup ran (organism_brain_archive/<today's date> exists)
```

## Stage-1 success criteria (4-week window)

| Metric | Pass | Fail | Decide |
|---|---|---|---|
| **Halt events** | 0 unintentional halts | Any unexpected halt | Investigate, possibly extend Stage-1 |
| **Cumulative loss** | >= −$50 (10% of capital) | < −$50 | Stop, review |
| **Worst single-day** | >= −$25 (daily max-loss kill bound) | < −$25 (gate failed!) | **CRITICAL — STOP IMMEDIATELY** |
| **Position-count violations** | 0 | Any >2 simultaneous | Fix risk controls before continuing |
| **Notional-cap violations** | 0 | Any > $100 | Fix risk controls |
| **Brain backup gaps** | 0 missed daily | Any missed | Investigate (probably benign but verify) |
| **Latency degradation** | per-tick <= 2s (paper baseline ~1s) | > 5s consistently | Investigate |
| **Real-vs-paper expectancy delta** | Within 50% of paper | Real >> paper losing | Investigate slippage / spread / fill assumptions |

## Stage-2 graduation criteria

After 4 clean Stage-1 weeks (all success criteria met):

| Item | Threshold |
|---|---|
| **Capital increase** | $500 → $5,000 (10×) |
| **Per-trade notional cap** | $100 → $1,000 (10×) |
| **Daily max-loss** | $25 → $250 (10×) |
| **Drawdown-kill** | 5% → 8% (relax slightly) |
| **Max positions** | 2 → 4 |
| **Universe** | 8 → 16 (add LLY, AVGO, XOM, CAT, GOOGL, META, AMD, COST) |
| **Tick interval** | 10s (unchanged) |

After 4 clean Stage-2 weeks: consider Stage-3 ($25K, full universe, full caps from H1/H2).

## Stage-1 stop conditions (when to halt and reassess)

**Hard stops** (immediate action):
- Drawdown reaches 5% (kill triggers automatically)
- Single day loses > $25 (daily kill triggers automatically)
- Any unexpected container restart during market hours
- Any unauthorized trade (position not initiated by the strategy)
- Brain corruption detected (manifest reset, learning_state divergence)
- Alpaca account flagged for any reason (PDT violation, etc.)

**Soft stops** (review by end of week):
- Two consecutive days with halt events
- Cumulative loss > 5% week-over-week
- Latency degradation > 3× paper baseline
- Three or more failed alert deliveries

## Operator readiness checklist (you, not the platform)

```
[ ] You commit to checking the platform every weekday morning by 9:30 ET
[ ] You commit to checking again post-close by 4:30 ET
[ ] You have your phone configured to receive Slack/webhook alerts
[ ] You have a written rollback plan you can execute under stress
[ ] You have a maximum-pain-tolerance number ($X) where you stop, no
    matter what the platform metrics say
[ ] You have someone (or me) you can talk to if something goes wrong
[ ] You're not going to be on vacation in week 1-2 of Stage-1
[ ] You've slept on the decision and it still feels right in the morning
```

This last point matters. **Stage-1 capital is real money you might lose.** It's not the same as paper. Make sure you've sat with that before pulling the trigger.

## Pre-Stage-1 — what's NOT yet ready

To make this plan executable, the platform needs:

| Gap | Effort to close | Owner |
|---|---|---|
| `ORGANISM_UNIVERSE_OVERRIDE` env var | ~1 hour code | RC-2 work |
| `ORGANISM_DRAWDOWN_KILL_PCT` already exists ✓ | done | — |
| `ORGANISM_MAX_POSITIONS` already exists ✓ | done | — |
| Per-trade notional cap env-configurable (eb90fa3 has it; verify env name) | verify only | done |
| Daily max-loss env-configurable | verify | TBD — eb90fa3 includes the feature; check env knob |
| Stage-1 risk parameter set documented in CLAUDE.md | done (this file) | — |
| Live-mode confirmation log line at startup | ~30 min | Add to startup |
| Real-money switch in monitoring | ~30 min | Add visual indicator |

**Total effort to close gaps: ~4 hours.** Goal completion: by week 3 post-RC-1.5.

## Decision: when to actually pull the trigger

The honest framing: **Stage-1 isn't blocked by engineering anymore.** The remaining gates (G1-G12) are observation and verification, not code. The decision is yours, based on:

- Are you ready operationally? (24×7 mindset for first week)
- Are you ready financially? ($500 you're truly OK losing)
- Are the platform metrics on RC-1.5 + RC-2 actually stable for 2-4 weeks?

If all three are yes, schedule the cutover. If any one is no, wait. Don't force it.

There is no glory in being first to live capital. There is no penalty in waiting another month. The only failure is rushing.
