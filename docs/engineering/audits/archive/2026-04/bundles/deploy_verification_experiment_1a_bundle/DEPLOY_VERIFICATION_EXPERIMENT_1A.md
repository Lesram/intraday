# Deploy Verification — Experiment 1A (chop min-hold gate)

**Date**: 2026-04-11 01:53–01:55 UTC
**Target**: `ab54b2f` (Experiment 1A on top of Full Patch F 7d36b61)
**Verdict**: DEPLOYED AND VERIFIED

## Pre-Deploy
- HEAD: `ab54b2f`, backend/ clean
- Container: 19h uptime, healthy, RestartCount=0
- Brain: gen=45, trades=214, best_sharpe=3.4363, ml_is_trained=true
- Alpaca: ACTIVE, equity=$111,551.90, positions flat
- Market: closed, next open Mon 2026-04-13 09:30 ET (13:30 UTC)

## Deployment
- `docker compose -f docker-compose.paper.yml up -d --build api`
- Start 01:53:48Z, build 01:54:59Z, healthy 01:55:14Z (86s total)

## Post-Deploy
- API: healthy. Container: healthy, RestartCount=0
- Boot log: `Brain loaded: gen=45, runs=315, trades=214`
- Trading phase: `production_frozen (trades=214, freeze_exit=86)`
- PREFLIGHT: 16/18, 0 critical
- Scheduler loop started
- Zero ERROR/CRITICAL

## Signature Checks (5/5 PRESENT)

| Check | Result | Evidence |
|---|---|---|
| Chop min-hold gate exists | PRESENT | `_CHOP_MIN_HOLD_BARS = 10` at live_engine.py:1936 |
| Threshold = 10 bars | PRESENT | same line |
| stop_loss unchanged | PRESENT | adaptive_exits.py:395,397 |
| horizon_timeout/max_hold unchanged | PRESENT | adaptive_exits.py:508,516 |
| Suppression log present | PRESENT | `Exp1A: pyramid_cut suppressed` at live_engine.py:1944 |

Full Patch F signatures also intact (forensic guard, write-manifest-guarded, break-glass, read-back invariant).

## Observation Window

**Start**: 2026-04-13 13:30 UTC (Mon market open)
**Duration**: 3–5 sessions (Mon Apr 13 – Wed/Fri Apr 16/18)
**Target trades**: ~30–40 (at current ~8/day pace)

### Metrics tracked

| Metric | Baseline (Apr 7-10) | Target |
|---|---|---|
| `Exp1A: pyramid_cut suppressed` count | 0 (didn't exist) | >0 confirms gate is firing |
| pyramid_cut exit count | 24/32 (75%) | should decrease |
| timeout/max_hold exit count | 5/32 (16%) | should increase |
| stop_loss count | 3/32 (9%) | may increase slightly |
| win rate | 18.8% | target >30% |
| expectancy/trade | -$1.92 | target >$0 |
| avg hold time | 550s (9 min) | target >900s (15 min) |
| worst single-trade loss | -$12.69 (PSQ stop) | monitor |

### Success criteria
- Win rate improvement from 18.8% to >25%
- Expectancy improvement from -$1.92 to >-$0.50 (ideally positive)
- At least 10 suppressed pyramid_cut events in logs (confirming the gate fires)
- No increase in max single-trade drawdown beyond 2x baseline (-$25)

### Failure criteria (triggers experiment rollback)
- Net PnL per session worse than -$50 (vs -$15 baseline)
- Max single-trade loss > $30
- System instability (errors, crashes, stuck positions)

## No further changes during observation
Code is frozen until the observation window concludes.
