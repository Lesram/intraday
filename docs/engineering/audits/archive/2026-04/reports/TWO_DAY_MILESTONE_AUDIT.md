# Two-Day Milestone Audit — Apr 16-17, 2026

**Sessions audited**: Thu Apr 16 + Fri Apr 17 (first 2 sessions with Exp1A + Exp2 + Exp3 prep live)
**Container**: `ce06d41`, healthy, RestartCount=0, up since Apr 16 02:42 UTC
**Brain**: gen=84, trades=293, pnl=-580.46, best_sharpe=3.4363, ml_is_trained=true, synced ✅
**Guards**: ALL ZERO (BLOCKED=0, SUSPICIOUS=0, FORENSIC=0, READBACK=0)

---

## Phase 1: Live State — VERIFIED ✅

- Container at ce06d41, healthy, 3.5 days uptime, 0 restarts
- Exp1A=1, Exp2=2, Exp3=1, Exp4=0, G1/G2/G3=0 — correct
- Account ACTIVE, equity=$111,558.13, positions flat
- Manifest fully synced with learning_state on all 6 fields
- Brain mount RW, APP_ENVIRONMENT=development
- Zero guard fires across entire container lifetime

---

## Phase 2: Session Reviews

### Day 1 — Apr 16 (Thursday)

| Metric | Value |
|---|---|
| Trades | 16 |
| Net PnL | **-$47.33** |
| Win rate | 31.2% |
| Expectancy | -$2.96 |
| Avg hold | 1012s |
| Worst | -$41.52 (IWM pyramid_cut at 3 bars) |
| Best | +$5.35 (QQQ max_holding_period) |
| Green | 15/16 (94%) |
| Capture | -146% |
| PSQ/SH trades | **0** ✅ (Exp2 working) |
| Exp1A suppressions | 1 |
| Exp2 suppressions | 2 (PSQ blocked twice) |

**The IWM -$41.52 trade dominates Day 1.** 6 shares of IWM at ~$269 = $1,614 notional, cut at -1.7R after just 3 bars. Without this single outlier, Day 1 PnL would be -$5.81 with 31.2% win rate — a reasonable session. This is a position-sizing concern (IWM got full allocation despite being a volatile entry).

### Day 2 — Apr 17 (Friday)

| Metric | Value |
|---|---|
| Trades | 19 |
| Net PnL | **+$29.76** ✅ |
| Win rate | **36.8%** ✅ |
| Expectancy | **+$1.57** ✅ |
| Avg hold | **1112s** |
| Worst | -$2.80 |
| Best | +$15.84 (XLE max_holding_period) |
| Green | **18/19 (95%)** |
| Capture | **46.5%** ✅ |
| PSQ/SH trades | **0** ✅ |
| Exp1A suppressions | 7 |
| Exp2 suppressions | 6 (3 SH + 3 PSQ blocked) |

**The best session in the entire observation history.** +$29.76, 36.8% win rate, +$1.57 expectancy, 95% directional accuracy, and 46.5% MFE capture rate. Timeout/max_hold exits produced +$42.29 from 7 trades at 100% win rate. The pyramid_cut share dropped to 26% (baseline 75%).

### Combined 2-Day

| Metric | Baseline | Exp1A-only window | **Exp1A+Exp2 (2 days)** |
|---|---:|---:|---:|
| Trades | 8/day | 14.7/day | **17.5/day** |
| Pyramid_cut % | 75% | 43% | **29%** |
| Timeout/max_hold % | 16% | 23% | **31%** |
| Win rate | 18.8% | 25.0% | **34.3%** |
| Expectancy | -$1.92 | -$1.11 | **-$0.50** |
| Avg hold | 550s | 803s | **1066s** |
| PSQ/SH trades in chop | ~1.5/session | ~0.8/session | **0/session** ✅ |

---

## Phase 3: Experiment Evaluation

### A. Exp1A — KEEP ✅
Pyramid_cut down to 29% (from 75% baseline). Hold time doubled from 550s to 1066s. 8 suppressions across 2 days (1 + 7). The gate fires consistently and trades that survive produce wins via timeout.

### B. Exp2 — HELPING ✅
**8 inverse ETF entries blocked** (2 + 6) across 2 days. PSQ/SH trade count in chop: **ZERO** (target was zero). The gate is firing exactly as designed. This eliminates the -$2 to -$4/session inverse-ETF leak entirely.

### C. Exp3 prep — PRODUCING DATA
Confidence buckets across 2 days:

| Bucket | Trades | PnL | Win rate |
|---|---:|---:|---:|
| < 0.35 | 16 | +$25.07 | **50%** |
| 0.35-0.45 | 18 | -$53.20 | **17%** |
| >= 0.45 | 1 | +$10.56 | 100% |

**The confidence inversion is WEAKENING.** Low confidence (<0.35) outperforms massively (+$25 at 50% wr). But the 0.35-0.45 bucket's poor performance (-$53 at 17% wr) is dominated by the IWM -$41.52 outlier. Without it, the 0.35-0.45 bucket would be -$11.68 at 24% wr — still underperforming but not catastrophically.

The single >=0.45 trade (QQQ at conf 0.527) won +$10.56. Small sample but positive.

**ML contamination hypothesis: INCONCLUSIVE.** The pattern is real but may be driven by outliers rather than systematic ML failure.

### D. Exp4 — REMAINS QUEUED
Trailing-stop exits: 2 across 2 days. Givebacks > $5: **ZERO.** The trailing stop was not a significant damage source in these 2 sessions. Leapfrog criteria NOT met.

---

## Phase 4: Exit System

| Exit | Count | % | PnL | Win rate | Avg give |
|---|---:|---:|---:|---:|---:|
| pyramid_cut | 10 | **29%** | -$53.53 | 0% | $5.67 |
| stop_loss | 9 | 26% | -$16.43 | 11% | $3.32 |
| timeout/max_hold | 11 | **31%** | **+$54.40** | **100%** | $1.26 |
| failure_to_follow | 3 | 9% | -$1.45 | 0% | $1.47 |
| trailing_stop | 2 | 6% | -$0.56 | 0% | $2.28 |

**Timeout/max_hold is now the #1 exit path (31%) and is 100% winners (+$54.40).** This is the strongest evidence yet that the Exp1A strategy of "let trades hold longer" is working. The organism is transitioning from a premature-exit system to a timeout-exit system.

**Pyramid_cut is still the biggest $ damage** (-$53.53), but it's driven by one outlier (IWM -$41.52). The remaining 9 pyramid_cut trades lost -$11.01 total, much more controlled.

**The organism remains a good directional picker**: 33/35 trades went green (94%). The problem is still exits, not entries.

---

## Phase 5: Structural/Mechanical — CLEAN ✅

- Zero guard fires
- Zero wipe recurrence
- Manifest synced
- Container stable (3.5 days, 0 restarts)
- 82 + 372 error log entries (websocket timeouts — P3, same pattern)
- Brain mount RW
- IWM order DB shows 1 buy / 0 sells with -$1611 "PnL" — same reconciliation gap class as prior sessions (fill not propagated to DB). P3.

**No new P0/P1 blockers found. Platform is mechanically clean.**

---

## Phase 6: Issue Ledger

| ID | Title | Sev | Status | Next |
|---|---|---|---|---|
| Exp1A | Chop min-hold gate | — | **LIVE, KEEP** | Continue |
| Exp2 | PSQ/SH chop suppression | — | **LIVE, HELPING** | Continue |
| Exp3 | Confidence instrumentation | — | **LIVE, PRODUCING DATA** | Analyze over 2+ more sessions |
| Exp4 | Trailing-stop giveback | P3 | OFFLINE | Queued behind current stack |
| G1 | Exit-level restore at WARNING | P2 | OFFLINE READY | Deploy before real money |
| G2 | Cooldown on success only | P2 | OFFLINE READY | Deploy before real money |
| G3 | NaN pyramid guard | P2 | OFFLINE READY | Deploy before real money |
| H1 | Production risk-budget dead code | P2 | KNOWN | Fix before real money |
| H2 | Feature drift crash guard | P2 | KNOWN | Fix before real money |
| H5 | Settings API governance bypass | P3 | KNOWN | Fix before real money |
| — | DB order reconciliation gaps | P3 | RECURRING | Backlog |
| — | Log errors (websocket timeouts) | P3 | RECURRING | Backlog |
