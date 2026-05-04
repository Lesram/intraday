# Master Issue Ledger

**Updated**: 2026-04-19
**Total items**: 28 (3 resolved, 8 offline ready, 5 live, 12 backlog/frozen)

## LIVE EXPERIMENTS

| ID | Title | Sev | Status | Deploy | Next |
|---|---|---|---|---|---|
| Exp1A | Chop 10-bar min-hold for pyramid_cut | — | **LIVE, KEEP** | ab54b2f | Continue observing |
| Exp2 | Suppress PSQ/SH entries in chop | — | **LIVE, HELPING** | ce06d41 | Continue observing |
| Exp3 | Confidence inversion instrumentation | — | **LIVE, PRODUCING DATA** | ce06d41 | Analyze for Exp3B |

## OFFLINE READY — HARDENING

| ID | Title | Sev | Status | Commit | Bundle with |
|---|---|---|---|---|---|
| G1 | Exit-level restore → WARNING + mark | P2 | OFFLINE READY | 15cc0a4 | Deploy 2 |
| G2 | Exit cooldown on success only | P2 | OFFLINE READY | 15cc0a4 | Deploy 2 |
| G3 | NaN/Inf/zero pyramid guard | P2 | OFFLINE READY | 15cc0a4 | Deploy 2 |
| H1 | Production risk-budget cap | P2 | OFFLINE READY | 679ffd2 | Deploy 2 |
| H2 | Feature drift guard (>20% → neutral) | P2 | OFFLINE READY | 679ffd2 | Deploy 2 |
| H5 | Settings API governance bypass | P3 | OFFLINE READY | c306074 | Deploy 2 |
| CAP | Per-trade notional cap (env disabled) | P2 | OFFLINE READY | bb5cbb5 | Deploy 2 |
| HALT | Daily max-loss circuit breaker (env disabled) | P2 | OFFLINE READY | bb5cbb5 | Deploy 2 |
| ALERT | Critical event Slack/webhook wiring | P2 | OFFLINE READY | 33d6138 | Deploy 2 |

## OFFLINE READY — EXPERIMENTS

| ID | Title | Sev | Status | Commit | Deploy timing |
|---|---|---|---|---|---|
| Exp4 | Trailing-stop widen in chop (5× ATR) | P3 | OFFLINE READY | b97f903 | Included in Deploy 2 (bundled) |

## ORGANISM COHERENCE

| ID | Title | Sev | Status | Action | Timing |
|---|---|---|---|---|---|
| DEAD-EXPL | Exploration routing dead code (~30 lines) | P3 | KNOWN | REMOVE | Next cleanup |
| DEAD-RUNNER | runner.py loaded but never called | P3 | KNOWN | REMOVE from lifespan | Next cleanup |
| NIGHTLY | Nightly scheduler disabled | P3 | DORMANT | REVIVE after 500 trades | Post Stage 1 |
| PROMO | Promotion pipeline dormant | P3 | DORMANT | Tied to nightly | Post Stage 1 |
| TRAINING | Training orchestrator dormant | P3 | DORMANT | Tied to nightly | Post Stage 1 |
| WALKFWD | Walk-forward.py offline only | P3 | DORMANT | Tied to nightly | Post Stage 1 |
| EVO-300 | Evolution freeze exits at trade 300 | P2 | IMMINENT (7 trades) | Allow, MONITOR | Next 1-2 sessions |
| CONSTANTS | Scattered constants, no central config | P3 | BACKLOG | Simplify later | Major refactor |

## REAL-MONEY BLOCKERS (not yet coded)

| ID | Title | Sev | Status | Effort | Prerequisite |
|---|---|---|---|---|---|
| ALERT-CFG | SLACK_WEBHOOK_URL not set in .env | P2 | CONFIG NEEDED | 1 min | Get webhook URL |
| EXPECT | Expectancy still negative (-$0.50) | P1 | OBSERVING | Weeks | Algorithm experiments |

## RESOLVED

| ID | Title | Resolved by |
|---|---|---|
| Wipe recurrence | Brain wipe at 02:08/02:58 UTC | Full Patch F (7d36b61) |
| Manifest sync | learning_state vs manifest drift | Patch B (50b2513) |
| Sharpe decay | walk_forward_gate best_sharpe collapse | Patch C (93593a2) |
