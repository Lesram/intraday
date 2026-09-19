# Master Action Matrix

## A. LEAVE LIVE NOW
| Item | Why |
|---|---|
| Exp1A (chop min-hold) | KEEP — pyramid_cut 75%→29%, hold time doubled, timeout exits 100% wr |
| Exp2 (inverse ETF gate) | KEEP — 8 entries blocked, zero PSQ/SH in chop |
| Exp3 prep (confidence logging) | KEEP — producing data, zero trade impact |
| Full Patch F stack | FROZEN — zero guard fires, zero wipe recurrence |

## B. SHIP NEXT
| Item | Expected value | Risk | Effort | Prerequisite |
|---|---|---|---|---|
| G1/G2/G3 mechanical fixes | Real-money prep | Low | Already committed at 15cc0a4 | Exp2 observation concludes |
| Review evolved_params.json | Understand what trade 300 will change | Zero | 10 min | Before trade 300 is reached |

## C. PREPARE OFFLINE
| Item | Why |
|---|---|
| Exp3B (revert to learning-mode confidence in chop) | If Exp3 data confirms ML contamination |
| Position-sizing cap ($5K max per entry) | Prevents IWM-class outliers (-$41.52) |
| Daily max-loss auto-halt | -$500/day circuit breaker for real-money readiness |

## D. FIX BEFORE REAL MONEY
| Item | Why | Effort |
|---|---|---|
| G1/G2/G3 | Mechanical hardening | Already coded |
| H1: Production risk-budget | Dead code — no per-trade risk cap in production | Medium |
| H2: Feature drift guard | XGBoost can crash on shape mismatch | Small |
| Per-trade notional cap | Prevent IWM-class outliers | Small |
| Daily max-loss halt | Circuit breaker | Medium |

## E. BACKLOG / REMOVE / SIMPLIFY
| Item | Action |
|---|---|
| Exploration routing (live_engine 2205-2235) | DELETE — dead code, ~30 lines |
| runner.py | REMOVE from lifespan loading — legacy, never called |
| __init__.py | IGNORE — empty placeholder, no harm |
| Enable nightly_scheduler | EVALUATE — designed feature that's never been turned on |
| H5: Settings API governance bypass | FIX — low priority for paper |
