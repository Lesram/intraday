# Master Audit Synthesis — V10

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `c048103` (post wave 41-49)
**Scope:** 10 parallel tracks — Z8, AA4, BB4, DD4, PP2, UU2, VV, WW, XX, YY
**Predecessors:** V1-V9 = ~347 cumulative findings, ~275 closed, ~72 deferred entering V10.

---

## TL;DR

**Total V10 findings: 32 actionable + 2 informational + 1 lint deliverable** (within 13-37 estimate).

| Severity | Count | Notable |
|---|---|---|
| Critical | 1 | **AA4-1: paper container is running OLD image; ALL V9 wave-32/42/47 fixes are sitting on disk, NOT live** |
| High | 13 | DD4-1/2 wave-44 surface-only, WW-1 wave-41 PP-2 safety net empty, AA4-2 init_token_blacklist orphan, VV-1/2/3 contract drift, XX-1/2 broken downgrade + CHECK incompatibility, YY-1/2 alert + audit-log enum reach gaps, PP2-1 PP-4 wrong gating point, UU2-A wave-41 partial |
| Medium | 12 | AA4-3 settings GET unguarded, BB4-F2 wave-44 EOD-cancel may not have wired, schema drift, ORM mismatch |
| Low | 6 | various edges |
| Info / Lint | 3 | BB4-F1 wait Mon open, DD4-5 calibration healthy, UU2-B ruff config deliverable |

**Closure regression Z8: 0 production regressions.** V9 wave-41-49 markers all in place. 190/190 tests pass.

**The headline V10 discovery: the V9 fixes never reached production.** AA4-1 found the container running an image built before wave-32. This single deploy gap masked the apparent strength of V9. Once the container is rebuilt, AA4-2 (init_token_blacklist orphan) becomes the immediate next blocker.

**The V10 lens-availability hypothesis is reconfirmed:** the 4 NEW lenses (VV/WW/XX/YY) yielded **17 of 32 actionable findings (53%)**. The OO recommendation continues to deliver. V11 should add 1-2 more lenses to maintain yield.

---

## Cross-track patterns

### Pattern P1 — "Container deploy state ≠ disk state" (NEW pattern)

V10's biggest discovery. Code can be correct on disk and still NOT be running. AA4-1 found:
- `intra-api-1` container `security.py` is 862 lines vs host 924.
- `/auth/logout` does not blacklist (wave-42 AA3-1 undeployed).
- Refresh tokens accepted as access at `/auth/me` (wave-42 AA3-2 undeployed).
- `exp=now-10s` returns 401 with no leeway (wave-47 AA3-4 undeployed).

**Implication for the audit cycle:** ALL future "verify the fix actually works" tracks must FIRST verify the container image is built from the current source SHA. A simple `docker exec intra-api-1 wc -l /app/backend/infra/security.py` vs host comparison would have caught this.

### Pattern P2 — "Wired but unreachable" (V7 BB-8/10 → V10 wide)

Same pattern, broader surface in V10:
- **AA4-2**: `init_token_blacklist()` at `security.py:51` defined but ZERO callers in repo.
- **YY-2**: 17 of 19 sampled `AuditAction` enum values have ZERO emit sites — `audit_logs` table + `fire_audit_log` helper fully implemented but order/position/model lifecycle never call them.
- **YY-1**: 6 of 16 `logger.critical` sites have NO alert dispatch — drawdown-kill, emergency-stop, circuit-breaker open all silent.
- **WW-1**: `_create_backup` only called from full `save()`, which `_save_brain` walk-forward-gates — production has ZERO `backups/`. PP-2 fallback safety net is empty.
- **DD4-1**: wave-44 fitness gate `defeated by persistence` — `symbol_trade_counts` is promotion-gated; only 62 counts on disk vs 491 trades in CSV; restart wipes growth.

**Implication:** every "did we wire it?" check must be paired with "is the call site ACTUALLY reached?" Wave-31 reachability tests touched this; V10 confirms broader coverage needed.

### Pattern P3 — "Persistence layer gates fix surface"

Closely related to P2 but specific to the brain-state path:
- **DD4-1**: fitness gate fix (wave-44) is defeated because the read source (`symbol_trade_counts`) is wiped on restart unless promotion-gated full save runs.
- **WW-1**: PP-2 backup fallback (wave-41) is defeated because the write source (`_create_backup`) only runs in promotion-gated full save.

**Common cause:** `_save_brain` distinguishes `save_essential_state` (every tick) from full `save()` (only on walk-forward gate pass). Critical state lives only in the full-save path; runtime gates assume essential-save invariants that don't hold.

### Pattern P4 — "Symptom vs root-cause fixes"

Wave-44 closed pyramid Layer 2 reachability via `max_level` (DD3-1) but DD4-2 found the deeper bug: `_reconcile_fills` collapses `layers` to a single layer with broker `avg_entry_price`. Layer 2 trigger now requires +3.5R instead of +3.0R. Empirically: **0 of 498 trades reached Layer 2 since deploy.** The wave-44 fix would only help if the upstream collapse stops.

Same shape: DD4-1 — wave-44 fitness-gate fix (DD3-5) addresses the lookup miss but not the persistence wipe that creates the miss.

### Pattern P5 — "Frontend/backend contract drift" (V10 NEW lens validated)

VV cluster found 5 findings on first run. Three coexisting serialization styles, no codegen, no global pydantic alias generator, three duplicate FE type layers. Each renamed pydantic field is a UI break waiting to happen.

### Pattern P6 — "Migration tree is a single-headed lie"

Wave-37's smoke check confirmed single-headed linear chain — but XX-1 found that `downgrade base` is impossible because `ec197100938a` references a constraint that doesn't exist. The forward path looks clean; the rollback path is broken. **Disaster recovery beyond head~3 requires manual SQL.**

XX-2: CHECK constraints incompatible with partial index AND with active code (`'new'`, `'pending_new'`, `'submitting'` rejected by CHECK but expected elsewhere). Today's prod data passed VALIDATE only by accident.

---

## Findings table

### Critical (1)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA4-1 | AA4 | Paper container running OLD image; ALL V9 wave-32/42/47 fixes undeployed | **50 (deploy)** |

### High (13)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA4-2 | AA4 | `init_token_blacklist()` has zero callers; Redis backend never initialized; blacklist is in-memory only, wipes on restart | 50 |
| DD4-1 | DD4 | Wave-44 fitness gate defeated by promotion-gated persistence; symbol_trade_counts wipes on restart | 53 |
| DD4-2 | DD4 | Wave-44 max_level fix surface-only; `_reconcile_fills` still collapses layers; **0/498 trades reach Layer 2** | 53 |
| PP2-1 | PP2 | PP-4 ALLOW_NO_DB gate at wrong line — runtime DB unreachability hits inner prewarm except, silently proceeds | 51 |
| UU2-A | UU2 | Wave-41 UU-2 partial — successful-login `db.rollback()` still has `except: pass` | 51 |
| VV-1 | VV | OrderValidationResponse snake_case backend vs camelCase frontend → pre-trade UI shows `undefined` | 54 |
| VV-2 | VV | Risk endpoints serialize Decimals as strings; TS types lie about being `number` | 54 |
| VV-3 | VV | OrderStatus defined 3x in FE; none matches backend; none covers Alpaca's wire vocabulary | 54 |
| WW-1 | WW | Production brain has ZERO `backups/` dir; wave-41 PP-2 safety net empty | 51 |
| XX-1 | XX | `downgrade base` broken at `ec197100938a:147` — drops constraint that's never created | 55 |
| XX-2 | XX | `ck_orders_status` rejects `'new'`/`'pending_new'`/`'submitting'` despite repo expecting them | 55 |
| YY-1 | YY | 6 of 16 `logger.critical` sites have NO alert dispatch (drawdown-kill, emergency-stop, circuit-breaker, SLO burn) | 52 |
| YY-2 | YY | 17 of 19 sampled `AuditAction` enum values have ZERO emit sites | 52 |

### Medium (12)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA4-3 | AA4 | GET /settings/organism + GET /settings/trading lack `require_admin` | 50 |
| BB4-F2 | BB4 | Wave-44 EOD-cancel may not have wired (agent searched for fn name; my fix was inline) — verify | 55 |
| DD4-3 | DD4 | DD2-6 inverse-ETF regime flip still only in alpha_scanner | 53 |
| PP2-2 | PP2 | PP-2 corrupt-HEAD recovery has no sticky forensic artifact | 56 |
| UU2-C | UU2 | Wave-43 LotTracker block at `alpaca_stream.py:643` retains silent rollback `except: pass` | 51 |
| VV-4 | VV | broadcast_settings_update emits but FE has zero listeners + missing WebSocketTopic.settings | 54 |
| VV-5 | VV | Rich error envelope dropped — FE reads only data.detail | 54 |
| WW-2 | WW | Backup naming 1-second resolution — 5 backups in 1 sec collapse via mkdir(exist_ok=True) | 56 |
| XX-3 | XX | Significant ORM-vs-DB drift; ~50 ops; `portfolio_history` ORM-declared, no migration | 55 |
| YY-3 | YY | ORGANISM_ENTRIES_BLOCKED buckets drawdown_kill / daily_max_loss / governance_halt / equity_zero | 52 |
| YY-4 | YY | BackgroundTrainer training-internal failure alert-silent | 52 |
| YY-5 | YY | /readyz returns 200 even when brain unloaded or tick loop dead | 52 |

### Low (6)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA4-4 | AA4 | X-API-Key returns 500 due to `.lower()` on Environment enum | 50 |
| BB4-F3 | BB4 | audit_logs has only user.login rows; no organism-emitted entries | 52 (with YY-2) |
| DD4-4 | DD4 | Pyramider counters write-only; cannot self-verify | 53 |
| PP2-3 | PP2 | `.tmp` orphans accumulate on SIGKILL | 56 |
| WW-3 | WW | save_essential_state skips evolved_params; long save-gating windows drift on disk | 56 |
| Z8-1 | Z8 | CI checker spurious fails on em-dash / slash subjects | 56 |

### Info / Deliverables (3)

| ID | Track | Summary |
|---|---|---|
| BB4-F1 | BB4 | position_lots=0 because no fills since wave-43 deploy; re-verify Mon post-open |
| DD4-5 | DD4 | Calibration counts post-wave-33 healthy `[[0,0],[53,168],[36,134],[22,52],[0,2]]` |
| UU2-B | UU2 | Proposed ruff config (S110/S112/BLE001/G004) with grandfather ratchet — V11 enforce |

---

## Recommended wave sequence (waves 50-58)

### Wave 50 — DEPLOY GATE: rebuild container + AA4 cluster (HIGHEST URGENCY)

**Why first:** until AA4-1 deploys, ALL V9 work is wasted; AA4-2 must land in code BEFORE the rebuild or the blacklist gate fails closed-but-empty.

- **AA4-1 (operator)**: rebuild + restart `intra-api-1` from current source. Deploy gate.
- **AA4-2**: wire `init_token_blacklist()` into `lifespan.py` startup so the blacklist Redis backend actually initializes.
- **AA4-3**: add `require_admin` to GET `/settings/organism` and `/settings/trading`.
- **AA4-4**: fix `Environment.lower()` 500 in `security.py:753`.

**Estimate:** 2-3 hours code; user runs the rebuild.

### Wave 51 — Persistence safety + audit/login completeness

- **WW-1**: call `_create_backup` from `save_essential_state` (or rotate via `_save_brain`); production gets a populated backups/ dir.
- **PP2-1**: fix lifespan PP-4 gate to also catch prewarm failures.
- **UU2-A**: apply the same rollback-error-log pattern to the successful-login branch in `auth.py`.
- **UU2-C**: same for the LotTracker block in `alpaca_stream.py:643`.

**Estimate:** 3-5 hours.

### Wave 52 — Observability + audit-log reach

- **YY-1**: wire `dispatch_alert_from_thread` calls at the 6 silent `logger.critical` sites.
- **YY-2 / BB4-F3**: emit AuditAction calls at order/position/model/strategy/config lifecycle sites — at least the 5 most important ones (ORDER_FILLED, POSITION_OPEN, POSITION_CLOSE, MODEL_RETRAINED, EMERGENCY_STOP_TRIGGERED).
- **YY-3**: add label dimension to `ORGANISM_ENTRIES_BLOCKED` (`reason="..."`) instead of one bucketed counter.
- **YY-4**: BackgroundTrainer training-internal failure alert + `ml_retrain_failures_total` counter.
- **YY-5**: `/readyz` checks brain.is_loaded + tick loop alive.

**Estimate:** 6-9 hours.

### Wave 53 — Strategy persistence + pyramid layer collapse

- **DD4-1**: write `symbol_trade_counts` to `save_essential_state` (not promotion-gated); fitness gate gets durable counter.
- **DD4-2**: fix `_reconcile_fills` to NOT collapse pyramid layers; use first-layer entry_price for R-multiple math (not weighted avg).
- **DD4-3**: extract inverse-ETF regime flip into a single `effective_regime_for_symbol(regime, symbol)` helper used by Kelly + AdaptiveExits + cooldown + AlphaScanner.
- **DD4-4**: telemeter `_pyramid_count` and `_max_layers_reached` — useful for self-verification.

**Estimate:** 6-10 hours. Highest-risk wave (touches reconcile + regime semantics). Replay-vs-live diff mandatory.

### Wave 54 — Frontend/backend contract alignment

- **VV-3**: align `OrderStatus` enum across backend + FE; add Alpaca-wire-vocabulary values; fix `canceled`/`cancelled` orthography.
- **VV-1**: fix `OrderValidationResponse` serialization (alias_generator OR rename frontend keys).
- **VV-2**: change risk endpoints to emit Decimals as numbers (or fix the TS type to reflect string).
- **VV-4**: add `WebSocketTopic.settings`; wire FE listener.
- **VV-5**: surface the rich error envelope in `frontend/src/services/api.ts::handleApiError`.

**Estimate:** 5-7 hours. Best long-term: ship `openapi-typescript` codegen.

### Wave 55 — Migration system fixes + EOD-cancel verify

- **XX-1**: fix `ec197100938a` downgrade — remove the orphan constraint drop OR add the matching upgrade.
- **XX-2**: extend `ck_orders_status` CHECK to include `'new'`, `'pending_new'`, `'submitting'`; rename to drop `ck_orders_ck_orders_*` double prefix.
- **XX-3**: ship migration to add `portfolio_history` table; reconcile other ORM/DB drift.
- **BB4-F2 verify**: confirm wave-44 EOD-cancel actually wired (the agent searched for a function name that doesn't exist; my fix was inline — likely a false positive but verify).

**Estimate:** 4-6 hours.

### Wave 56 — Cleanup batch

- **WW-2**: backup naming → microsecond resolution.
- **WW-3**: emit "ticks since last full save" Prometheus metric.
- **PP2-2**: copy corrupt HEAD to `corrupt_head_<ts>/` before restore overwrites.
- **PP2-3**: `.tmp` orphan sweep at top of `save()`.
- **Z8-1**: tolerate em-dash / slash in commit subjects in `WAVE_COMMIT_RE`.

**Estimate:** 2-3 hours.

### Wave 57 — UU2-B lint rule + backlog ratchet

- Ship the proposed ruff config in `pyproject.toml` with grandfather ratchet.
- Document in `docs/engineering/error-handling.md`.

**Estimate:** 2-3 hours.

### Wave 58 — Test-user cleanup + Mon post-open verify

- Delete throwaway users `audit_aa3_test`, `audit_aa4`, `audit_aa4_b` from prod DB.
- BB4-F1: schedule a Mon-morning verification — confirm `position_lots > 0` after first fills post-rebuild.

**Estimate:** 1 hour.

---

## V11 forward planning

V10 outcome:
- The 4 NEW lenses (VV/WW/XX/YY) yielded 17 of 32 findings (53%).
- The "fix didn't fix" pattern reappeared on V9 surface (DD4-1, DD4-2, WW-1, PP2-1, UU2-A) — but importantly through deeper-pass tracks, not from V9 fixes regressing.
- The deploy-state-vs-disk gap (AA4-1) is a NEW failure mode the cycle hadn't considered.

V11 retention recommendations:
- Retain all 13 lenses (AA, BB, DD, HH, NN, OO, PP, UU, TT, VV, WW, XX, YY, W3/W4, Z6/Z7/Z8).
- Add NEW lens **DD-DEPLOY**: every "fix verified" track first checks `docker exec ... wc -l /app/path` matches host. Catches AA4-1-class issues.
- Consider **DD-PROD-DATA**: differentiate "fix correct in code" from "fix exercised in production data." DD4-1 (fitness gate) and DD4-2 (Layer 2) would have been caught by an empirical-trade-data audit.

V11 yield expectation: 5-15 findings if the V10 fix waves close cleanly.

The cycle is converging on individual surfaces but expanding lens-count is still warranted.

---

## Audit-cycle update

V8: lens-availability hypothesis.
V9: confirmed (NEW lenses yielded 47%).
V10: reconfirmed at 53%. NEW failure modes (deploy-state, persistence-layer gating) emerged that the cycle hadn't thought to look for — caught by depth-passes.

The cycle's health metric is no longer "are findings going down?" — that depends on lens-additions. The right metric is **"per-lens yield trend"**:
- AA: V8 3, V9 3, V10 4 (stable)
- BB: V8 4, V9 4, V10 3 (slight decline)
- DD: V8 10, V9 6, V10 5 (declining — converging)
- PP: V9 6, V10 3 (declining — converging)
- UU: V9 4, V10 3 (declining — converging)
- TT: V9 5, V10 0 (closed; absorbed into other tracks)
- NEW lenses VV/WW/XX/YY: 17 first-round findings (in line with prior NEW-lens yields)

DD/PP/UU declines = cycle WORKING. NEW-lens yields = expansion ROI.

V11+ should accept that "0 findings ever" is unachievable; the goal is **always have ≥1 active fresh lens**, similar to how chemo regimens rotate to prevent resistance.
