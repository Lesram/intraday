# Master Audit Synthesis — V8

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `5bc4046` (V8 plan + prompts; baseline `79b38fb` after waves 28-31)
**Scope:** 8 parallel tracks — Z6, W3, AA2, BB2, DD2, HH2, NN, OO
**Predecessors:** V1-V7 = ~278 cumulative findings, ~220 closed, ~58 deferred entering V8.

---

## TL;DR

**Total V8 findings: 37 actionable + 6 meta-process** (upper bound of the 15-40 estimate).

| Severity | Count | Notable |
|---|---|---|
| Critical | 5 | DD2-1 safety-net bypass, NN-CRIT-2 strategies fully decorative, W3-G1 CI grep-timeout bypass, NN-CRIT-1 unmounted financial endpoints, OO CHAOS-GAP |
| High | 13 | AA2-NEW-1 trader-reads-audit, AA2-NEW-2 JWT-500-DoS, DD2-2 ML calibration axes mismatch, NN tick_telemetry zero-rows + 8 risk modules orphan, etc. |
| Medium | 14 | regime composability, Kelly bypass, mlops orphans, HSTS proxy, etc. |
| Low | 5 | shell-prompt parsing, EOD time bound, replay-clock leakage |

**Closure regression Z6: 0 regressions across waves 23-31.** Brain coherence verified (gen=168, trades=498, ml_is_trained=true). 179/179 tests pass.

**Wave-28/30/31/29 status:** All four post-V7 recommendations land cleanly when probed, but **wave-28 has 1 Critical bypass** (W3-G1, grep-timeout silent pass) and **wave-30 BB-8 reach is untestable until Monday open** (no fills since deploy).

**Audit-cycle hypothesis confirmed:** V8 found dramatically more reachability + strategy-logic findings than V7's lens disclosed. The cycle has been systematically under-investing in chaos, migration, and end-to-end strategy-logic verification.

---

## Cross-track patterns

V8 surfaced four patterns the V1-V7 cycle has been blind to:

### Pattern P1 — "Decorative subsystems"

Code that exists, has tests, but is gated off in production:
- **NN-CRIT-2**: 15 `BaseStrategy` subclasses (4,872 LOC) — `multi_strategy_live_scheduler` is mutex-OFF when organism is active (always in `.env`).
- **NN-CRIT-3**: 8 risk modules (`black_swan_protection`, `correlation_breakdown`, `margin_calculator`, …) entirely uninstantiated; live risk uses only `RiskManager`.
- **NN-MED-1**: `backend/mlops/` (~5k LOC, 7 modules) entirely orphan; only `__init__` re-exports.
- **NN-MED-3**: `backend/optimization/portfolio_optimizer.py` — entire module orphan.

**Implication:** ~10k+ LOC is "tested but decorative." Either delete (reduces audit surface) or wire (closes design gap).

### Pattern P2 — "Safety nets short-circuited"

Trading-safety code that the live tick path bypasses under specific states:
- **DD2-1 (HIGH, arguably Critical)**: `_pending_exit[sym]` 3-tick TTL (~30s) short-circuits ALL exit checks including hard stop_loss and max_loss safety nets at `live_engine.py:2154`. The unsold 70% of a partial-TP can blow through max_loss_pct unmonitored.
- **DD2-5**: Kelly's `_regime_eligible` branch bypasses wave-18's zero-vol refusal entirely when regime stats exist.
- **DD2-9**: EOD flatten silently disables globally on `zoneinfo` import failure (`pass` on except).
- **AA2-NEW-2**: `UserClaims(**payload)` crashes 500 (no try/except) — DoS vector.

**Implication:** Defensive code that doesn't run on every path is worse than no defensive code — gives false confidence.

### Pattern P3 — "Wrong-axis composition"

Two systems compose around the same name but on different distributions:
- **DD2-2**: ML calibration is *populated* by `raw_confidence` but *consumed* by `calibrated_confidence` — invisible mismatch compounds V7 DD-7 anti-predictivity.
- **DD2-6**: Inverse-ETF regime flip exists in `AlphaScanner._regime_alignment` only; Kelly, AdaptiveExitEngine, and the regime-transition cooldown all see the un-flipped market regime → SH/PSQ trades systematically under-sized + over-exited.
- **NN-HIGH-2**: `OrderStateMachine` + `OrderIntegrityService` orphan; order audit depends solely on `AuditsRepo` which the live engine never invokes.

**Implication:** Same-name interfaces don't guarantee same-distribution semantics.

### Pattern P4 — "Process-tool blind spots"

The audit cycle's own tools have gaps:
- **W3-G1 (CRITICAL)**: Wave-28's CI enforcer treats `grep timeout` (count = -1) as "skip the failure check" — pasting an evil grep that times out trivially bypasses the rule.
- **OO CHAOS-GAP**: 0 of 278 historical findings came from fault injection — V6 prompt proposed it, never shipped.
- **OO MIGRATION-GAP**: alembic.ini exists but `alembic/versions/` doesn't; 6+ schema-drift findings have no rollback story.
- **OO LEDGER-DRIFT**: ~126 findings exist in prose synthesis but never in FINDINGS_LEDGER.

**Implication:** The audit cycle has been auditing without auditing the auditors.

---

## Full findings table

### Critical (5)

| ID | Track | Summary | Wave |
|---|---|---|---|
| DD2-1* | DD2 | `_pending_exit` TTL bypasses hard stop_loss + max_loss for 30s (live trading safety) | 32 |
| W3-G1 | W3 | CI grep-timeout returns count=-1 → silent pass → wave-28 enforcement bypass | 32 |
| NN-CRIT-1 | NN | 3 financial `position_import` endpoints defined but unmounted in routes_setup.py | 33 |
| NN-CRIT-2 | NN | 15 `BaseStrategy` subclasses (4,872 LOC) decorative — mutex-OFF when organism active | 36 |
| OO CHAOS-GAP | OO | 0 of 278 findings from fault injection; chaos-shaped bugs caught only post-mortem | V9 |

\* DD2-1 was reported HIGH by the agent; up-graded to Critical in synthesis given live-trading safety-net bypass.

### High (13)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA2-NEW-1 | AA2 | `audit.py` uses `require_trader` not `require_admin` — trader tokens read forensic data | 32 |
| AA2-NEW-2 | AA2 | `UserClaims(**payload)` no try/except → 500 + stack-trace on malformed JWT (DoS) | 32 |
| DD2-2 | DD2 | ML calibration: populated by raw_confidence, consumed by calibrated_confidence | 33 |
| BB2-F1 | BB2 | Wave-30 BB-8 wired but `position_lots` 0 rows since deploy (markets closed) | Verify Mon |
| BB2-F2 | BB2 | 6 more dark tables: executions, positions, order_events, risk_violations, daily_ledger, tick_telemetry | 34 |
| HH2-N-1 | HH2 | `calculate_indicator` 614 LOC at routes/indicators.py:78 — new god-method V7 missed | 35 |
| HH2-N-2 | HH2 | `validate_order_pre_trade` 477 LOC at routes/orders.py:300 — security-adjacent god-method | 35 |
| NN-HIGH-1 | NN | `tick_telemetry` write target at live_engine:5780, zero rows (silent import-error) | 34 |
| NN-HIGH-2 | NN | OrderStateMachine + OrderIntegrityService orphan; live engine never invokes | 33 |
| NN-HIGH-3 | NN | SecurityMiddleware + 4 hardening helpers (rate limit, JWT verifier, input validator) never wired | 32 |
| NN-CRIT-3 | NN | 8 risk modules entirely uninstantiated (black_swan, correlation, margin, …) | 36 |
| OO MIGRATION-GAP | OO | alembic.ini exists, alembic/versions/ doesn't | 37 |
| OO STRATEGY-DROUGHT | OO | V2-V6 = 0 strategy findings; cycle blind to PnL-sensitive class | V9 |

### Medium (14)

| ID | Track | Summary | Wave |
|---|---|---|---|
| W3-G2 | W3 | _diff_test_count filters to `tests/` only; misses conftest fixture additions | 32 |
| AA2-NEW-3 | AA2 | HSTS only emits when `request.url.scheme == "https"`; no X-Forwarded-Proto support | 32 |
| BB2-F3 | BB2 | Hash-chain integrity check clean (informational) | — |
| DD2-3 | DD2 | `detect_market_regime` save/restore `_history` skips churn computation in cross-asset path | 34 |
| DD2-4 | DD2 | Regime argmax has no hysteresis band; one-bar slope flips at threshold | 34 |
| DD2-5 | DD2 | Kelly `_regime_eligible` bypasses unconditional Kelly path zero-vol refusal | 34 |
| DD2-6 | DD2 | Inverse-ETF regime flip only in AlphaScanner; Kelly/Exits/Cooldown see un-flipped | 34 |
| DD2-7 | DD2 | `_is_learning_mode` recomputed every read; mid-tick reconciliation race | 35 |
| HH2-N-3 | HH2 | `size_positions` 424 LOC at kelly_sizer.py:175 — sizing-kernel god-method | 36 |
| NN-MED-1 | NN | backend/mlops/ ~5k LOC entirely orphan | 38 |
| NN-MED-2 | NN | 6/14 backend/ml/ modules orphan | 38 |
| NN-MED-3 | NN | backend/optimization/portfolio_optimizer.py orphan | 38 |
| NN-MED-4 | NN | backend/brokers/{alpaca_production, broker_failover}.py orphan | 38 |
| OO LEDGER-DRIFT | OO | ~126 findings in prose synthesis but not in FINDINGS_LEDGER | 32 (process) |

### Low (5)

| ID | Track | Summary | Wave |
|---|---|---|---|
| W3-G3 | W3 | SAMECLASS_BLOCK_RE doesn't strip `$ ` / `> ` shell-prompt prefixes | 32 |
| DD2-8 | DD2 | Pure-breakout fallback uses abs(predicted_return) — neutral ML feeds long entry | 35 |
| DD2-9 | DD2 | EOD flatten has no upper time bound; broker rejects retry indefinitely | 35 |
| DD2-10 | DD2 | runner.py:104, routes.py:677,704 bypass `_now_fn` injection | 35 |
| OO MODULE-NAMED-TEST-GAP | OO | Top-13 modules by LOC have zero module-named test files | V9 |

---

## Recommended wave sequence (waves 32-40)

Build on the V8 findings; reverse-priority based on (severity × reach × ease).

### Wave 32 — "Trading-safety + CI bypass" (HIGHEST URGENCY)

**Why first:** DD2-1 is a live-trading safety-net bypass; W3-G1 defeats the entire wave-28 enforcement.

- **DD2-1**: Restructure `_pending_exit` short-circuit so hard stop_loss + max_loss STILL evaluate during the cooldown window. Add behavioral test that simulates partial TP + drawdown spike during the 3-tick TTL.
- **W3-G1**: Treat `count = -1` (timeout / error) as `count > 0` (failure) in required mode. Update tests/test_w3_synthetic_*.py.
- **W3-G2 + W3-G3**: Widen `_diff_test_count` scope; strip shell-prompt prefixes in SAMECLASS_BLOCK_RE.
- **AA2-NEW-1**: Change `audit.py` 6 endpoints from `require_trader` to `require_admin`.
- **AA2-NEW-2**: Wrap `UserClaims(**payload)` in try/except → 401 not 500.
- **AA2-NEW-3**: Honor `X-Forwarded-Proto` for HSTS emission.
- **NN-HIGH-3**: Wire `SecurityMiddleware` + 4 hardening helpers into FastAPI middleware stack OR delete if intentionally orphan.

**Risk:** Medium. DD2-1 fix changes the live trading hot path — needs replay-vs-live diff before deploy. Other items are surgical.

**Estimate:** 6-10 hours focused work.

### Wave 33 — "Reachability + ML calibration"

- **NN-CRIT-1**: Mount `position_import` endpoints in `routes_setup.py` (or delete the route file).
- **DD2-2**: Align ML calibration axes — populate AND consume on the same confidence variable (raw or calibrated, pick one). Touches `record_prediction_outcome` + `calibrate_confidence`.
- **NN-HIGH-2**: Wire `OrderStateMachine` + `OrderIntegrityService` into the order-fill path OR delete.

**Risk:** Medium-High. DD2-2 affects the system-level anti-predictivity finding — needs careful re-measurement post-deploy.

**Estimate:** 4-6 hours.

### Wave 34 — "Regime + dark-table writers"

- **DD2-3 + DD2-4**: Regime detector — wire churn into cross-asset path; add hysteresis band on argmax.
- **DD2-5**: Make Kelly's `_regime_eligible` branch ALSO apply zero-vol refusal.
- **DD2-6**: Move inverse-ETF regime flip up to a single interface (`get_effective_regime(symbol)`) consumed by Kelly/Exits/Cooldown/AlphaScanner uniformly.
- **NN-HIGH-1**: Fix `tick_telemetry` import (`backend.infra.database` → `backend.infra.db`) — this is the inline TODO.
- **BB2-F2**: Audit each of the 6 dark tables — wire (if intended live) or schema-drop (if dead).

**Risk:** High. DD2-6 is a multi-site refactor that affects every SH/PSQ position sizing decision.

**Estimate:** 8-12 hours.

### Wave 35 — "Architecture + minor logic"

- **HH2-N-1, HH2-N-2**: Split `calculate_indicator` (614 LOC) and `validate_order_pre_trade` (477 LOC) into ~50 LOC blocks each.
- **DD2-7**: Cache `_is_learning_mode` per tick (compute once at tick entry, freeze for the rest of the tick).
- **DD2-8**: Pure-breakout fallback gate on `direction != 0`.
- **DD2-9**: Add upper-time bound to EOD flatten retry; alert on broker reject.
- **DD2-10**: Replace `datetime.now(UTC)` in runner.py + routes.py with `_now_fn` injection.

**Risk:** Low. Architectural decomposition + small fixes.

**Estimate:** 6-9 hours.

### Wave 36 — "Decorative subsystem cleanup"

- **NN-CRIT-2**: Decision: delete `backend/strategies/` (all 15 BaseStrategy subclasses) OR wire into the `multi_strategy_live_scheduler`. Default = delete (4,872 LOC of audit surface gone). Stakeholder approval required.
- **NN-CRIT-3**: 8 orphan risk modules — same delete-or-wire decision.
- **HH2-N-3**: Split `size_positions` (424 LOC).

**Risk:** Low if delete (with full git-archive). High if wire (introduces new live code paths).

**Estimate:** 3-5 hours (delete path); 12-20 hours (wire path).

### Wave 37 — "Migration system bootstrap"

- **OO MIGRATION-GAP**: Initialize `alembic/versions/` with the current schema as the baseline migration. Document upgrade/downgrade procedures. Add CI step that verifies schema matches HEAD migration.

**Risk:** Medium. Schema-snapshot baseline is sensitive.

**Estimate:** 4-6 hours.

### Wave 38 — "ML / mlops / brokers cleanup"

- **NN-MED-1, 2, 3, 4**: Same delete-or-wire decision for mlops, ml subset, optimization, brokers production+failover.

**Risk:** Low (delete path).

**Estimate:** 2-4 hours.

### Waves 39-40 — "HH R-1 continuation"

Per `docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md` + HH2 plan-feedback:

- Wave 39: prep — uplift `entries_blocked` to `self._entries_blocked`.
- Wave 40: extract Stage 0.5 (stale-data gate, 20 LOC) + batch stages 1/1.1/1.2.

**Risk:** Medium. Replay-vs-live diff mandatory after each.

**Estimate:** 6-10 hours.

---

## V9 forward planning (per OO recommendations)

After wave 32-40 lands, V9 should run with these track types:

### NEW (per OO):
- **PP — Chaos / Fault-Injection** (highest leverage). Kill DB mid-trade, drop network, pause clock, inject latency. The cycle's three most severe historical bugs were chaos-shaped.
- **QQ — Migration Round-Trip**. After wave-37 ships alembic/versions, exercise apply→rollback→re-apply on a snapshot.
- **RR — Multi-Day Operational Soak**. Restart 5 times across 5 days; brain coherence check at every step.

### Retire (per OO):
- **T2** (0 bugs in V6).
- **Z / Z2 / Z3 / Z4** — fold into CI smoke (0 production regressions across 4 rounds).
- **W2** — subsumed by W3.

### Continue:
- Z6 (closure regression — keeps Critical, low cost).
- W3 (CI enforcement verification — keeps Critical, must check every round).
- AA / BB / DD / HH (core domains; rotate depth per round).
- NN (new lens; expect diminishing returns; re-run if wave-32+ deletes ≥10k LOC).
- OO (meta — annual at most).

---

## Closure regression (Z6) — clean

Per Track Z6:
- 0 regressions across waves 23-31.
- All per-finding markers verified at expected sites.
- 179/179 tests pass (167 prior + 12 new reachability v8).
- Brain coherence: gen=168, total_trades=498, ml_is_trained=true.
- Live `audit_logs`: 15 rows with valid hash_chain; orders has 7 CHECK constraints.

---

## V8 success criteria — met

Per V8_PLAN.md the success criteria were:
- ✅ All 4 recommendations independently verified to actually function.
  - Wave-28 CI: works with 1 Critical bypass (W3-G1).
  - Wave-30 BB-10: 15 audit_logs rows live, login path works.
  - Wave-30 BB-8: wired in container, **reach untestable until Mon open**.
  - Wave-31 reachability: 12/12 tests pass.
  - Wave-29 stage 0a: byte-for-byte parity verified.
- ✅ ≥3 V7 deferred items confirmed still-open (or reflagged with new context).
  - DD-7 anti-predictivity reflagged as DD2-2 (calibration axis mismatch — root cause).
  - Many V7-flagged orphan modules confirmed still orphan.
- ✅ ≥1 finding the audit cycle "should have caught earlier".
  - HH2-N-1 (calculate_indicator 614 LOC), HH2-N-2 (validate_order_pre_trade 477 LOC).
  - NN-CRIT-2 (4,872 LOC of decorative strategies — should have been NN-equivalent in V1).
- ✅ Closure regression clean (Z6 returns 0 regressions).

---

## Audit-cycle hypothesis (revisited)

Pre-V8 hypothesis (post-V7): four root causes of recurring audits — scope expansion, process enforcement lag, structural debt, easy-first sequencing.

V8 evidence:
- **Process enforcement lag**: still partially true. W3-G1 shows wave-28's enforcement has a Critical bypass.
- **Structural debt**: confirmed and DEEPER than V7 disclosed. NN found 47% of plain logic classes have no callers outside file/tests; 213 of 453 orphan; ~10k+ LOC decorative.
- **Easy-first sequencing**: confirmed. DD2 found 10 strategy findings post-V7's 11. The "diminishing returns" V7 hoped for did not materialize.
- **Scope expansion**: NN + OO are NEW lenses that found new classes. The cycle is genuinely converging on individual surfaces but the SURFACE-COUNT is still growing.

**Updated hypothesis:** the cycle's real problem is **lens-availability lag** — V1-V7 used the same 5-6 lenses; V8's two new lenses (NN + OO) found 16 findings between them. V9 should ship 1-2 more new lenses (PP chaos, QQ migration) to keep yield up.

The audit cycle is doing its job; it just needs to keep adding instruments.
