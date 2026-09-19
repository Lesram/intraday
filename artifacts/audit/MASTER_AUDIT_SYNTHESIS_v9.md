# Master Audit Synthesis — V9

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `ccba97f` (post wave 32-40)
**Scope:** 8 parallel tracks — Z7, W4, AA3, BB3, DD3, PP, UU, TT
**Predecessors:** V1-V8 = ~315 cumulative findings, ~250 closed, ~65 deferred entering V9.

---

## TL;DR

**Total V9 findings: 32 actionable + 1 diagnostic** (within 14-37 estimate; 14% reduction vs V8's 37 — measurable convergence).

| Severity | Count | Notable |
|---|---|---|
| Critical | 5 | PP-1/PP-2 brain-save not atomic + no backup fallback, PP-4 DB-down non-fatal in dev, UU-1 daily-loss alert dispatch broken (V5 S-J3-1 redux), UU-2 auth audit silent failure |
| High | 11 | AA3-1/2 logout no blacklist + refresh-as-access, BB3-F2 14 dark tables, DD3-1/2/3 pyramider Layer 2 unreachable + LotTracker partial-fill duplicates + pending-exit oversell race, PP-3/5/6 alert/universe/stream gaps, TT-1/2 tick budget + 33-min reconnect stall |
| Medium | 8 | AA3-3, BB3-F1, DD3-4/5, PP cleanup, TT-3/4, Z7-1 |
| Low/Info | 8 | W4-1/2/3 enforcer edges, AA3-4, BB3-F3/F4, TT-5, UU-3/4 |

**Closure regression Z7: 0 production regressions.** All 25 wave-32-40 markers verified, 147 tests pass, brain coherent (gen=168, trades=498), migration tree clean. Z7-1 (Medium) — wave-38 left ~20 orphan test files in `tests/unit/` that break `pytest --collect-only`.

**W4 verification: all three wave-32 W3-G1/G2/G3 fixes hold cleanly.** 3 Low residuals are NEW edge cases, not regressions.

**The fix-didn't-fix pattern is dead on the V8 surface.** Wave-32-40 are stable.

**Audit-cycle hypothesis CONFIRMED:** The 3 NEW lenses (PP chaos, UU error-handling, TT performance) yielded 15 of 32 findings (47%) — V8 OO's recommendation was correct. Add chaos/observability/perf lens to V10 retention.

---

## Cross-track patterns

### Pattern P1 — "Operator paging silently broken" (returning from V5 S-J3-1)

The cycle's most-recurrent finding class. UU-1 + PP-3 + UU-2 all show the same shape: an `except: pass` or fire-and-forget alert path drops failures, leaving operators uninformed.
- **UU-1** Critical: daily-max-loss halt's Slack alert uses bare `try/create_task/except: pass` — V5 S-J3-1 pattern recreated at a NEW site that wave-23 didn't migrate.
- **UU-2** Critical: login audit-log failure swallows `db.rollback()`. No audit row, no alert.
- **PP-3** High: alert dedup collapses N failures into 1; rate-limiter silently drops; no PagerDuty / no DLQ on Slack 5xx.

**Implication:** the "canonical alert helper" needs to be enforced via lint rule. Until it is, every new alert site is a relapse risk.

### Pattern P2 — "Persistence atomicity gaps"

Brain-save and audit-write paths have non-atomic write surfaces.
- **PP-1** Critical: `save_essential_state` writes 4 separate files (manifest.json, equity_curve.csv, epoch_metrics.csv, reference_feats.csv) with `df.to_csv` (NOT atomic). `backups/` directory missing on production container.
- **PP-2** Critical: `load()` exception → "starting fresh" with no auto-fallback. One OOM = lose 161 gens / 482 trades.
- **DD3-2** High: `LotTracker.create_lot` invoked once per `partially_filled` event with cumulative `filled_qty` → duplicate `position_lots` rows.
- **PP-4** Critical: in `APP_ENVIRONMENT=development` (paper runs as), DB-down is non-fatal — audit rows silently dropped.

**Implication:** atomicity is a class issue, not isolated bugs. Need atomic write helper (`write_atomic_via_rename`) + universal backup fallback.

### Pattern P3 — "JWT lifecycle holes"

V8 AA2 closed the trader-tier audit access. V9 AA3 opens 3 more deeper holes:
- **AA3-1** High: logout doesn't blacklist; the machinery exists but has zero call sites.
- **AA3-2** High: refresh tokens accepted as access tokens (no `token_type` check).
- **AA3-3** Medium: refresh tokens not single-use; old access tokens valid after re-login.

**Implication:** wave-23 added the JWT scaffold; AA3 found the call sites that were never wired. Same pattern as BB-8/BB-10 in V7 (wired-but-unreachable code).

### Pattern P4 — "State machine partial transitions"

Position lifecycle has 3 bugs all rooted in incomplete state-transition handling:
- **DD3-1** High: pyramider Layer 1 re-fires forever; Layer 2 unreachable. Layer-key vs level-key mismatch.
- **DD3-3** High: `_pending_exit` 3-tick TTL expires before broker fill on slow paths → exit re-fires for full qty (oversell race). `_exit_cooldown` not consulted on exit path.
- **DD3-4** Medium: EOD flatten doesn't cancel pending entries; 15:57 entries can fill past 16:00 with no exit infra.

**Implication:** the position state machine needs a unified guard layer. Wave-29's stage 0a was a partial step; wave-40 stages 1-1.2 don't address this.

### Pattern P5 — "Latency tail risk hides catastrophic outliers"

Both TT findings + PP-6 show the same shape: aggregate metrics look fine, tail hides 30+ second hangs.
- **TT-1** High: p99=13.0s, **max=26.7s on a 10s scheduler**. 2.68% over budget.
- **TT-2** High: 1987s and 1256s tick outliers (33 min and 21 min) co-located with WS keepalive timeouts. No `asyncio.wait_for` watchdog around tick body.
- **PP-6** High: `_data_stale` gate uses aggregate `last_update_time`; per-symbol stalls invisible.

**Implication:** need percentile-aware monitoring + per-symbol timeout watchdogs.

---

## Findings table

### Critical (5)

| ID | Track | Summary | Wave |
|---|---|---|---|
| PP-1 | PP | Brain-save not atomic; `backups/` dir missing on production container | 41 |
| PP-2 | PP | Brain `load()` exception falls through to "starting fresh" with no backup fallback | 41 |
| PP-4 | PP | DB-down non-fatal in `APP_ENVIRONMENT=development`; paper drops audit rows silently | 41 |
| UU-1 | UU | Daily-max-loss Slack alert uses bare `try/create_task/except: pass` (V5 S-J3-1 redux) | 41 |
| UU-2 | UU | Login audit-log failure swallows `db.rollback()`; compliance silent failure | 41 |

### High (11)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA3-1 | AA3 | `POST /auth/logout` returns 200 but doesn't blacklist JWT; stolen tokens valid for full TTL | 42 |
| AA3-2 | AA3 | Refresh tokens (7-day TTL) accepted as access tokens; `decode_token` no `token_type` check | 42 |
| BB3-F2 | BB3 | 14 of 17 substantive tables are dark; brain CSV is sole source of truth | 43 (root: DD3-2) |
| DD3-1 | DD3 | Pyramider Layer 1 re-fires indefinitely; Layer 2 unreachable (layer_count vs level key) | 44 |
| DD3-2 | DD3 | `LotTracker.create_lot` per `partially_filled` event uses cumulative qty → duplicate rows | 43 |
| DD3-3 | DD3 | `_pending_exit` 3-tick TTL expires before slow broker fills → exit re-fire oversell race | 43 |
| PP-3 | PP | Alert dispatch dedup + rate-limiter + Slack 5xx all silently drop | 41 (with UU-1) |
| PP-5 | PP | Universe scanner caches forever; persistent Alpaca movers failure → trade on stale | 45 |
| PP-6 | PP | `_data_stale` gate uses aggregate timestamp; per-symbol stalls invisible | 45 |
| TT-1 | TT | Tick budget routinely overrun (p99=13s on 10s scheduler) | 46 |
| TT-2 | TT | Stream reconnect can stall a tick for 33 minutes; no watchdog | 46 |

### Medium (8)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA3-3 | AA3 | Refresh tokens not single-use; old access tokens stay valid after re-login | 42 |
| BB3-F1 | BB3 | `orders.user_id` is varchar `'system'`; no FK link to `users.id` | 47 |
| DD3-4 | DD3 | EOD flatten doesn't cancel pending entries; 15:57 entries fill post-16:00 | 44 |
| DD3-5 | DD3 | `symbol_fitness = {}` empty in saved brain → 0.45 production gate defaults to 0.5, never rejects | 44 |
| TT-3 | TT | `attributes->>'source'='organism'` JSON predicate forces Seq Scan on `orders` | 47 |
| TT-4 | TT | 4 async methods in `AlpacaClient` call sync `time.sleep()` despite `_async_rate_limit` existing | 47 |
| Z7-1 | Z7 | Wave-38 left ~20 orphan test files in `tests/unit/` (pytest collection broken) | 48 |
| UU-3 | UU | Brain-save-blocked alert + lock-release double-swallow | 41 (with UU-1/2) |

### Low / Info (8)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA3-4 | AA3 | `JWT_CLOCK_SKEW = 60` is dead code; never passed to `jwt.decode` | 47 |
| BB3-F3 | BB3 | `executions/position_lots/realized_trades` use `ON DELETE CASCADE` against `orders.id` | 47 |
| BB3-F4 | BB3 | `orders.broker_order_id` non-unique index; small race window | 47 |
| TT-5 | TT | 6 unbounded brain-resident lists | 47 |
| UU-4 | UU | 14 cargo-culted `try/except: pass` around safe in-memory ops | 49 |
| W4-1 | W4 | Aliased `from pytest import fixture as fx; @fx` missed by literal-string scan | 48 |
| W4-2 | W4 | Positive-assertion grep convention drift surfaces 16 fails on real branch | 48 |
| W4-3 | W4 | `WAVE_COMMIT_RE` excludes `-` in suffix → `audit-wave99-w3g1-test` bypasses ALL enforcement | 48 |
| DD3-6 | DD3 | (Diagnostic) Day-1 +$69.35 was 1 AMD trade; rest near-zero edge | — observe |

---

## Recommended wave sequence (waves 41-49)

### Wave 41 — Critical safety + alerting (HIGHEST URGENCY)

**Why first:** PP-1/PP-2 are a single-OOM-kill = lose 161 generations bomb. UU-1/UU-2 silently break operator paging on the platform's most-critical events.

- **PP-1**: atomic brain-save (use `tempfile.NamedTemporaryFile` + `os.replace` for manifest.json + CSVs).
- **PP-2**: brain `load()` falls back to most-recent backup if HEAD is corrupt.
- **PP-4**: in `development` mode, DB-down still halts trading (mirror production gate). Add startup validator.
- **UU-1**: migrate daily-max-loss alert site to canonical `dispatch_alert_from_thread`.
- **UU-2**: surface auth-audit-log failure at WARNING + add Prometheus counter.
- **PP-3**: Slack 5xx → escalate to PagerDuty webhook + DLQ for retry.
- **UU-3**: brain-save-blocked alert + lock-release: log lock-release exception at WARNING.

**Risk:** Medium. Persistence and alert paths are sensitive. Replay-vs-live diff before deploy.
**Estimate:** 6-9 hours focused.

### Wave 42 — JWT lifecycle holes

- **AA3-1**: wire `blacklist_token` into `POST /auth/logout` handler.
- **AA3-2**: `decode_token()` enforces `token_type == "access"` on resource paths.
- **AA3-3**: refresh tokens enforce single-use (rotate jti on every refresh; old jti enters blacklist).

**Risk:** Medium. JWT logic touches every request path.
**Estimate:** 3-5 hours.

### Wave 43 — LotTracker partial-fill semantics

- **DD3-2 + DD3-3**: rewrite `_process_trade_update` to compute INCREMENTAL fill (`new_filled_qty - last_filled_qty`) per partially_filled event, NOT cumulative. Adds idempotency.
- **DD3-3 specifically**: consult `_exit_cooldown` on exit path so a stale `_pending_exit` doesn't trigger a re-fire.

**Risk:** **HIGH.** Touches the BB-8 wiring on the live trade-update path. Must replay-vs-live diff.
**Estimate:** 6-10 hours.

### Wave 44 — Strategy state machine fixes

- **DD3-1**: `MomentumPyramider.check_pyramid` keys on `level` not `layer_count`. Layer 2 path verified by behavioral test.
- **DD3-4**: EOD flatten cancels pending entries via broker `cancel_order` before submitting flatten exits.
- **DD3-5**: `symbol_fitness` rebuild on startup if empty; gate enforces 0.45 only when populated.

**Risk:** Medium. Strategy logic; need replay tests.
**Estimate:** 4-7 hours.

### Wave 45 — Universe + stream stale gates

- **PP-5**: universe scanner has TTL on candidate cache; missing-API alerts after N failures.
- **PP-6**: per-symbol `_data_stale` tracking; `check_and_recover_stale_stream` triggered on per-symbol staleness.

**Risk:** Low. Detection improvements, not behavior changes.
**Estimate:** 3-5 hours.

### Wave 46 — Tick budget + reconnect watchdog

- **TT-2**: `asyncio.wait_for(tick_body, timeout=15)` watchdog; on timeout, log + Prometheus counter.
- **TT-1**: profile + identify the 13s p99 contributor; address top-1 hot path.

**Risk:** Medium. Tick path is the heart of the system.
**Estimate:** 4-6 hours.

### Wave 47 — Medium / Low cleanup batch

- **BB3-F1**: `orders.user_id` migration to `users.id` FK (or document why varchar is intentional).
- **BB3-F3**: `executions/position_lots/realized_trades` ON DELETE → RESTRICT.
- **BB3-F4**: unique index on `(broker_order_id, symbol)`.
- **TT-3**: partial expression index on `orders((attributes->>'source'))` WHERE attributes IS NOT NULL.
- **TT-4**: `AlpacaClient` async methods → use `_async_rate_limit`.
- **TT-5**: bound the 6 unbounded lists at 10k entries (FIFO).
- **AA3-4**: pass `JWT_CLOCK_SKEW` as `leeway=` to `jwt.decode`.
- **AA3 cleanup**: remove throwaway test user `audit_aa3_test@example.com`.

**Risk:** Low.
**Estimate:** 3-5 hours.

### Wave 48 — Test infra + CI enforcer edges

- **Z7-1**: delete ~20 orphan test files in `tests/unit/` referencing deleted modules.
- **W4-1**: extend `_diff_test_count` to detect aliased fixture imports via AST.
- **W4-2**: document the positive-assertion grep convention; add wave-author note.
- **W4-3** (CRITICAL CI tool fix): widen `WAVE_COMMIT_RE` to accept hyphens in the suffix (`fix(audit-wave[0-9a-z-]+)`), so `audit-wave99-w3g1-test` is RECOGNIZED as a wave commit (and held to the wave-rule contract).

**Risk:** Low.
**Estimate:** 2-3 hours.

### Wave 49 — Diagnostic / cosmetic

- **UU-4**: remove cargo-culted try/except blocks (14 sites).
- **DD3-6**: DIAGNOSTIC ONLY — investigate AMD edge concentration; chop-min-hold gate suppression rate.

**Risk:** Trivial.
**Estimate:** 2-3 hours.

---

## V10 forward planning

V9 PP/UU/TT lenses each surfaced findings — **retain them in V10**. Combined with V8's NN/OO, the cycle now has 11 lenses:
- AA, BB, DD (continuity)
- HH (architecture)
- NN (reachability — V8 new)
- OO (meta — V8 new)
- PP (chaos — V9 new, ✅ proven)
- UU (error handling — V9 new, ✅ proven)
- TT (performance — V9 new, ✅ proven)
- W3/W4 (CI process)
- Z6/Z7 (closure)

V10 should:
- Run all 11 lenses with rotating depth.
- Add ≥1 NEW lens — candidates: **frontend/backend contract drift** (per V8 OO recommendation), **multi-day operational soak** (per V8 OO recommendation), **migration round-trip** on a real DB snapshot.
- Yield expectation: 8-25 findings (continued convergence).

If V10 finds < 8 = cycle has converged. Reduce frequency to quarterly.

---

## Audit-cycle update

V8 hypothesis: lens-availability lag is the recurring-finding driver.

V9 evidence:
- 47% of V9 findings came from the 3 NEW lenses (15 of 32). Same pattern as V8 (NN+OO yielded 16 of 37).
- Domain-deepening tracks (AA3, BB3, DD3) yielded 14 of 32 — productive but not new findings, mostly subtler edges.
- Continuity tracks (Z7, W4) yielded 4 of 32 — verifying recent fixes works.

**Confirmed: every new lens yields ~5-10 first-round findings. Adding 1 lens per round keeps the cycle productive.** Once we run out of useful lenses to add, the cycle is genuinely done.

V9 is the strongest evidence yet that the cycle's health is measurable, not just felt.
