# Comprehensive Pre-Open Platform Audit

**Date**: 2026-04-11 (weekend before Mon Apr 13 open)
**Mode**: read-only audit, no code changes, no deploys
**Next open**: Mon 2026-04-13 13:30 UTC

## Overall Verdict: READY AS-IS

No P0/P1 blockers found. No fixes needed before Monday open. Experiment 1A observation window should proceed uncontaminated.

---

## PHASE A — Source / Runtime / Deploy State

### What is LIVE right now
| Component | Value |
|---|---|
| Container | `intra-api-1` at commit `ab54b2f` (Exp1A), healthy, RestartCount=0, up 3h |
| Patches live | A, B, C, D, E, F-lite, F1-F4 (full structural stack) |
| Algorithm live | Experiment 1A only (chop 10-bar min-hold gate for pyramid_cut) |
| Brain | gen=45, trades=214, pnl=-513.93, best_sharpe=3.4363, ml_is_trained=true |
| Phase | production_frozen (214/300 to evolution freeze exit) |
| Account | ACTIVE, equity=$111,551.90, trading_blocked=false |
| Positions | flat (market closed) |
| APP_ENVIRONMENT | development (paper mode) |

### What is OFFLINE ONLY right now
| Commit | What | Status |
|---|---|---|
| `ce06d41` | Exp3 prep — confidence inversion side-by-side logging | Committed, not deployed |
| `d79cae0` | Exp2 — suppress PSQ/SH in chop | Committed, not deployed |
| `6754223` | Observation tooling script | Committed, not deployed (tooling, no rebuild needed) |

### What is READY BUT NOT DEPLOYED
All three offline commits above are tested and ready. They will deploy as a stack (or individually) after the Exp1A observation window.

### Repo cleanliness
- Branch: `main`, HEAD: `ce06d41`
- Tracked files: clean (only `scripts/empirical_no_trade_replay.py` untracked — pre-existing, not relevant)
- 3 commits ahead of live container — all intentionally offline
- Safe for audit/patch work

---

## PHASE B+C — Structural / Mechanical Audit

### Persistence / brain durability — ALL CLEAR ✅

| Check | Status | Evidence |
|---|---|---|
| save() guarded | ✅ | `_check_trained_overwrite_guard` + early lock-release path |
| save_essential_state() guarded | ✅ | Routed through `_write_manifest_guarded` (F2) |
| Unified manifest writer | ✅ | `_write_manifest_guarded` at `brain_persistence.py:715` |
| Force-save path | ✅ | `POST /organism/save?force=true` verified working |
| Manifest sync | ✅ | All 4 fields match: gen=45, trades=214, pnl=-513.93, best_sharpe=3.4363 |
| Read-back invariant | ✅ | Present at `brain_persistence.py:868`, zero fires |
| Suspicious-write instrumentation | ✅ | Present at `brain_persistence.py:880`, zero fires |
| Break-glass semantics | ✅ | Requires force+allow_reset+reset_reason triad |
| Forensic guard | ✅ | LiveEngine id fingerprints at `live_engine.py:351-352` |
| Bypass audit | ✅ | Exactly 2 `_write_json(MANIFEST_FILE)` callsites: guarded helper + safe migration |
| Guard fire count (all time) | ✅ | BLOCKED=0, SUSPICIOUS=0, FORENSIC=0, READBACK=0 |
| Wipe recurrence | ✅ | No wipe since F-lite deployed Apr 9. Manifest stable at gen=45/trades=214 |

### Runtime / ops integrity — ALL CLEAR ✅

| Check | Status | Evidence |
|---|---|---|
| Container health | ✅ | running, healthy, RestartCount=0 |
| Boot restore | ✅ | `Brain loaded: gen=45, runs=315, trades=214` |
| PREFLIGHT | ✅ | 16/18, 0 critical, 2 warnings |
| API health | ✅ | `/health` returns ok |
| Account | ✅ | ACTIVE, not blocked |
| Positions | ✅ | flat |
| Force-save available | ✅ | `POST /organism/save?force=true` endpoint live |

### Data integrity — ALL CLEAR ✅

| Check | Status | Evidence |
|---|---|---|
| Manifest vs learning_state | ✅ | All 4 fields synced |
| ML joblibs present | ✅ | 248KB + 168KB, dated Apr 9 23:25 |
| reference_feats.csv | ✅ | 20KB, dated Apr 9 23:25 |
| trade_history.csv | ✅ | 215 lines (header + 214 trades) = matches manifest.total_trades |
| equity_curve.csv | ✅ | 125KB, dated Apr 10 |
| evaluation_event_history.json | ✅ | 57KB, dated Apr 10 |
| diagnostics/ | ✅ | Present, dated Apr 10 |
| transfer_knowledge.json | ❌ MISSING | Known non-blocking gap from force_save_brain atomic swap |

### Error log analysis

| Category | Count | Severity | Notes |
|---|---|---|---|
| Websocket timeouts (Alpaca) | 6 | P3 | Auto-recovering keepalive ping timeouts. Normal Alpaca behavior. |
| DB session errors (login) | ~1800 | P3 | Historical from Mar 30 – Apr 1. Pre-existing, not organism-related. |
| Risk manager NoneType | 1 | P3 | Mar 30 only. Old bug, hasn't recurred. |
| Recent errors (post Apr 10 deploy) | 0 | ✅ | Clean since Exp1A deploy |

**No active errors since the Exp1A deploy. Error log is dominated by historical noise.**

### Experiment integrity — CLEAN ✅

| Check | Status | Evidence |
|---|---|---|
| Exp1A is ONLY live algorithm change | ✅ | `CHOP_MIN_HOLD_BARS=10` at live_engine.py:1936 confirmed via docker exec grep |
| Exp2 NOT in live container | ✅ | grep for `inverse_etf_suppressed_chop` returns empty |
| Exp3 NOT in live container | ✅ | grep for `confidence_bt_only` returns empty |
| Observation tooling is read-only | ✅ | `generate_experiment_observation_report.py` is a standalone script, not runtime code |
| No hidden branch drift | ✅ | 3 offline commits are clearly identified and non-deployed |

---

## PHASE D — Algorithm / Trading Edge Audit

### Current evidence (from Apr 7-10 baseline, 32 real trades)

| Metric | Value | Assessment |
|---|---|---|
| Expectancy/trade | −$1.92 | Negative — learning mode, not edge-positive yet |
| Win rate | 18.8% | Low |
| Payoff ratio | 1.08 | Near 1:1 — insufficient to compensate for low win rate |
| Main leak | Pyramid_cut exits (24/32, 0% wr, −$63.80) | Proven, Exp1A targets this |
| Second leak | PSQ/SH in chop (6 trades, 0% wr, −$28.54) | Proven, Exp2 prepared |
| Third leak | Confidence inversion (high conf = 0% wr) | Likely, Exp3 prep instrumenting |

### Is Exp1A still the correct live experiment?
**YES.** The pyramid_cut exit mechanism is the dominant leak ($63.80 of $61.37 total loss). Exp1A's 10-bar min-hold gate targets the 13 premature exits that account for $42.27 of that loss. No higher-value experiment was discovered in the weekend lab.

### Is Exp2 still the correct next deployment?
**YES.** PSQ/SH in chop (0% win rate, $28.54 loss) is the second-largest independent leak. Orthogonal to Exp1A.

### Is confidence inversion still the correct revised Exp3?
**YES, but with a nuance.** The inversion evidence (confidence ≥0.45 = 0% win rate over 4 trades) is a small sample. The Exp3 prep instrumentation will produce definitive data once deployed. If confirmed, the fix (revert to learning-mode confidence weights in chop) would be Exp3B.

### Any newly discovered higher-value experiment?
**NO.** The three-experiment stack (1A exits → 2 inverse suppression → 3 confidence investigation) remains the correct priority order. No new evidence has appeared since the weekend lab.

---

## PHASE E — Test Coverage Audit

### Coverage summary

| Area | Tests | Files | Status |
|---|---|---|---|
| Persistence patches (A/B/C/D/E/F) | 67 | 9 files | ✅ Comprehensive |
| Experiment 1A | 8 | 1 file | ✅ Adequate |
| Experiment 2 | 7 | 1 file | ✅ Adequate |
| Experiment 3 prep | 8 | 1 file | ✅ Adequate |
| Organism regression (live_engine, scenarios, multi_tick, safety, evolution) | 107 | 5 files | ✅ Regression coverage |
| **Total** | **~197** | **~16 files** | |

### Under-tested areas (non-blocking)
- Exit fragmentation (multi-leg unwind mechanics) — not directly tested, but the behavior is captured in trade_history for post-hoc analysis
- Scanner breadth filtering — tested indirectly via regression suite, not via dedicated unit tests
- Regime detection accuracy — no standalone tests for regime detector correctness

### Flaky tests
- `test_replay_simulator.py::test_replay_no_throttle_blocking` — pre-existing flaky, confirmed against baseline `2018999`. Not organism-related.

### Is any missing test a pre-open blocker?
**NO.** The 197-test suite covers all persistence paths, all experiment logic, and the organism regression surface. No critical area is untested.

---

## PHASE F — Real-Money Readiness Audit

See `REAL_MONEY_GAP_MAP.md` for full detail. Summary:

| Category | Current | Target | Gap |
|---|---|---|---|
| Expectancy | −$1.92/trade | >+$0.50/trade sustained | LARGE — need positive edge first |
| Risk control | ATR stops + EOD flatten | + daily max loss + position limits | MEDIUM |
| Kill switch | `POST /organism/halt` + governance | + automated drawdown halt | SMALL |
| Monitoring | GET endpoints + manual checks | + alerting channels + dashboards | MEDIUM |
| Capital rollout | Paper only | Staged: $5K → $25K → $50K | NOT STARTED |

**Stage**: 0 (paper only). Not ready for real money. Need ≥3 consecutive weeks of positive expectancy first.

---

## Issue Registry

| ID | Severity | Type | Description | Action | Timing |
|---|---|---|---|---|---|
| 1 | P3 | data | `transfer_knowledge.json` missing from force_save_brain atomic swap | Add to force_save file list | Backlog |
| 2 | P3 | ops | 2383 historical error log lines (mostly Mar 30 login noise) | Log rotation / cleanup | Backlog |
| 3 | P3 | monitoring | "No alert channels configured" warnings on pre/post diagnostics | Wire Slack/email alerting | Backlog |
| 4 | P3 | algorithm | Confidence inversion (high conf = 0% wr) — needs data | Exp3 instrumentation ready | After Exp1A |
| 5 | P3 | algorithm | PSQ/SH systematic loss in chop | Exp2 ready | After Exp1A |
| 6 | P3 | algorithm | Opening-range entries 0% wr (5 trades) | Widen block from 30→60 min | After Exp2 |
| 7 | P3 | ops | PREFLIGHT 2 warnings (not 0) | Investigate what the 2 warnings are | Backlog |

**No P0 or P1 issues found.**
