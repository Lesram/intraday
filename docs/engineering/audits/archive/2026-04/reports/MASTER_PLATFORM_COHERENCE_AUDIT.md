# Master Platform Coherence Audit

**Date**: 2026-04-19
**Scope**: Full platform audit — 38 organism files, all integrations, deployment, brain state
**Container**: ce06d41, healthy, 3.5 days uptime, 0 restarts
**Brain**: gen=84, trades=293, pnl=-580.46, ml_is_trained=true, synced ✅

## Overall Verdicts

**Platform**: READY AS-IS (for paper)
**Coherence**: PARTIALLY COHERENT — core trading loop is tight and well-wired, but ~9 files are dormant/dead/partially-wired (nightly_scheduler, promotion, training, runner, walk_forward, composite_indicators indirect, ensemble_models optional, __init__ empty, exploration routing dead)
**Organism**: PARTIALLY FUNCTIONAL — ML training + calibration + entry/exit loop all active. Evolution is frozen (293/300 trades). Nightly retraining is disabled. Promotion pipeline is dormant.

## ⚠️ IMMINENT EVENT: Evolution Freeze Exit at 300 trades

**The system is 7 trades from crossing the 300-trade evolution freeze boundary.** When this happens:
- `apply_evolved_params()` will fire for the first time in live trading
- Scanner thresholds, Kelly scaling, and exit adjustments will be updated from the evolved_params snapshot
- This is the FIRST TIME the organism's parameter evolution has been active

**Impact**: parameter values may change abruptly, affecting entry filtering, position sizing, and exit behavior. The current evolved_params.json should be inspected before this event occurs.

**Recommendation**: This is NOT a blocker but should be monitored closely. The first session after crossing 300 trades should be observed for unusual behavior.

---

## Phase 1: Live State — VERIFIED ✅

| Item | Status |
|---|---|
| Container | ce06d41, healthy, restarts=0, up 3.5 days |
| Exp1A | LIVE (1 match) |
| Exp2 | LIVE (2 matches) |
| Exp3 prep | LIVE (1 match) |
| Exp4 | OFFLINE (0 matches) |
| G1/G2/G3 | OFFLINE (0 matches) |
| Brain sync | ALL ✅ (gen=84, trades=293, pnl=-580.46, best_sharpe=3.4363) |
| Guards | ALL ZERO |
| Mount | RW ✅ |
| ENV | development (paper) |

Repo HEAD is `b97f903` (main), 2 commits ahead of live (`ce06d41`). The 2 extra commits are Exp4 + G1/G2/G3 — correctly offline.

**Working tree has 4 modified files** from the stash pop after the ce06d41 deploy checkout. These are the Exp4/G1/G2/G3 changes that exist on main but NOT in the deployed container. Non-blocking.

---

## Phase 2: Organism Feature Status

### 25 ACTIVE files — the core trading loop works

The live tick loop (live_engine.py) calls 25 modules every tick or on schedule. The signal generation → confidence → sizing → entry/exit pipeline is fully wired and functioning.

### 4 PARTIALLY WIRED files

| File | Status | Details |
|---|---|---|
| self_evolution.py | **FROZEN AT 293/300** | Evolution parameters loaded but NOT applied until trade 300. 7 trades away from activation. |
| continuous_learner.py | BACKGROUND ONLY | Used for model validation in background_trainer, not for direct retraining. Actual training happens in ml_signal.train(). |
| walk_forward.py | OFFLINE TOOL | Only used by nightly_scheduler/training.py. Live gating uses simpler `brain.walk_forward_gate()`. |
| ml_signal effective_confidence | CONDITIONAL | Used in production mode (current), bypassed in learning mode. Calibration tables populated with 293 trades of data. |

### 5 DORMANT files (loaded but not active)

| File | Why | Risk |
|---|---|---|
| nightly_scheduler.py | `ORGANISM_NIGHTLY_ENABLED` not set in .env | No nightly retraining or promotion |
| promotion.py | Only triggered after nightly training | Promotion pipeline inactive |
| training.py | Only called from nightly_scheduler | Walk-forward + promotion orchestration inactive |
| runner.py | Legacy pre-scheduler runner loaded in lifespan but never called | Should be removed |
| replay_simulator.py | CLI tool, no imports | Correct — offline only |

### 4 DEAD CODE items

| Item | Details |
|---|---|
| `__init__.py` | Empty placeholder |
| diagnostic_checks.py | Only registers checks via side-effect import — functions not called directly |
| Exploration routing (live_engine.py:2205-2235) | Routes candidates to a dead queue. Comment confirms: "no executor ever processed it." ~30 lines of dead routing logic. |
| ensemble_models.py | Soft optional import in ml_signal.py; falls back to single-model. Present but not critical path. |

**Note**: composite_indicators.py is actually USED (ml_features.py:380-384 imports and calls `compute_composite_indicators`), wrapped in try/except. The explorer incorrectly flagged it as dead.

---

## Phase 3: Confidence Formula — ACTUALLY ACTIVE

At 293 trades in production_frozen phase:

```
1. raw_confidence = abs(p_up - 0.5) * 2                    # ML model output
2. calibrated = raw * calibration_map[bin]                   # empirical correction
3. effective = min(calibrated, empirical_win_rate_in_bin)     # if ≥10 samples/bin
4. production confidence = 0.50*effective + 0.30*breakout + 0.20*tension
5. Gate: if confidence < 0.25 → reject; if < 0.40-0.45 → exploration (dead queue, silently dropped)
```

Calibration tables ARE populated with 293 trades of outcome data. The system IS using ML-calibrated confidence for entry decisions. This is the production path, not a fallback.

---

## Phase 4: What the Organism is ACTUALLY Learning

| Capability | Active? | Evidence |
|---|---|---|
| ML model retraining | ✅ YES | background_trainer retrains every RETRAIN_INTERVAL bars (~180 bars = ~3h) |
| Model acceptance gate | ✅ YES | acceptance_gate in continuous_learner validates new models |
| Calibration updates | ✅ YES | Every closed trade updates calibration_counts at line 3931 |
| Brain persistence | ✅ YES | 787 saves, manifest synced |
| Parameter evolution | ❌ FROZEN | Unfreezes at trade 300 (7 trades away) |
| Nightly retraining | ❌ DISABLED | ORGANISM_NIGHTLY_ENABLED not set |
| Promotion pipeline | ❌ DORMANT | Only runs after nightly training |

**Bottom line**: The organism trains ML models and calibrates confidence, but it does NOT evolve parameters or run nightly retraining. These features exist in code but are dormant. The system is learning (ML) but not evolving (parameters).

---

## Phase 5: Top Platform-Level Problems

### 1. Evolution freeze exits in ~7 trades (P2)
When trade 300 is reached, `apply_evolved_params()` fires for the first time. This could change scanner thresholds, Kelly scaling, and exit parameters. The current `evolved_params.json` should be reviewed to understand what values will be applied.

### 2. Nightly scheduler disabled (P3)
The organism was designed with a nightly retraining + walk-forward + promotion loop. It's not running. This means the system only does intra-session ML retraining (every ~3h), not the deeper overnight analysis. Not blocking but missing from the design intent.

### 3. Exploration routing is dead code (P3)
~30 lines of candidate routing logic that sends below-threshold candidates to a queue nobody processes. Should be deleted.

### 4. Runner.py loaded but unused (P3)
Legacy module loaded in lifespan but never called. Should be removed.

### 5. Expectancy still negative (P2 for real-money)
Cumulative expectancy across all sessions is improving but not yet sustainably positive.

---

## Phase 6: Structural/Mechanical — CLEAN ✅

- Zero guard fires (all 4 types)
- Zero wipe recurrence
- Manifest synced
- Container stable 3.5 days
- Brain mount RW
- No new P0/P1 blockers found

The structural work (Full Patch F) is genuinely frozen and observation-only.

---

## Phase 7: Algorithm Edge Summary

### What works
- Entry directional accuracy: 88-95% of trades go green (last 2 sessions)
- Timeout/max_hold exits: 100% win rate, now the #1 exit path (31%)
- Exp2 inverse-ETF suppression: 8 entries blocked, zero PSQ/SH trades in chop

### What leaks
- Pyramid_cut still loses 100% when it fires (29% of trades)
- Position sizing allows outlier losses (IWM -$41.52)
- Confidence inversion may exist but evidence is inconclusive
- Trailing_stop occasionally gives back large MFE (but not consistently enough to prioritize)

### Current edge trajectory
```
Baseline:     -$1.92/trade, 18.8% wr, 550s hold
Exp1A-only:   -$1.11/trade, 25.0% wr, 803s hold
Exp1A+Exp2:   -$0.50/trade, 34.3% wr, 1066s hold
Best session: +$1.57/trade, 36.8% wr (Apr 17)
```

The trajectory is positive. Expectancy improving session-over-session.
