# Master Audit Synthesis — V11 (Every-Corner Sweep)

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `9cd7d9a` (post wave 50-67)
**Scope:** 12 parallel tracks — Z9, AA5, BB5, DD5, HH3, PP3, TT3, UU3, AAA, CCC, DDD, III
**Predecessors:** V1-V10 = ~379 cumulative findings, ~290 closed entering V11.

---

## TL;DR

**Total V11 findings: 49 actionable** — exceeds the 10-30 estimate. The 4 NEW lenses (AAA, CCC, DDD, III) yielded **22 of 49 findings (45%)**, again validating V8 OO's lens-availability hypothesis.

**Key V11 reveal: V10 wave-47 silently broke ALL JWT auth in production for ~24 hours.** AA5-1 caught it. Already fixed in wave-67. Lesson: source-grep regression tests gave false confidence — the wave-47 test was looking for a literal string the code contained even when the code was broken.

| Severity | Count | Notable |
|---|---|---|
| Critical | 2 | **AA5-1** (FIXED wave-67) JWT decode broke all auth, **CCC-2** kill-switch divergence (paper has NO drawdown_kill wired) |
| High | 18 | AAA-F1 /test/* debug endpoints exposed, AAA-F2 orders RBAC bypass, DDD-1 ecdsa CVE, UU3-2 lint rule unenforced (3542 errors), III-F2 PII in logs, BB5-F1 outbox unbounded, DD5-1/2/3 strategy fixes incomplete, HH3-N-1 _live_tick_inner regressing, ... |
| Medium | 19 | various |
| Low | 10 | various |

**Already fixed during V11 (during audit, hot path):**
- **AA5-1** wave-67 — JWT decode (deploy hotfix; container rebuilt + verified live).
- **BB5-F4** wave-67 — migration applied; portfolio_history table now exists; ck_orders_status widened.

---

## Cross-track patterns

### Pattern P1 — "Source-grep tests give false confidence" (V11 NEW)

The wave-47 regression test asserted the literal string `"leeway=JWT_CLOCK_SKEW"` appeared in source. The code contained that string and the test passed — even though it broke production for every JWT-authenticated endpoint. **AA5-2 documents this as a pattern**: source-grep tests are anti-tests if they don't decode/exercise.

Same shape:
- Multiple wave-test files use AST-walks of source instead of behavioral checks.
- Wave-32/47/50 markers are "string in source" — pass even when the code path is broken.

**Action:** require behavioral tests for Critical/High wave fixes. Lint rule could ban marker-only tests.

### Pattern P2 — "Configuration sprawl creates silent risk-cap disablement" (CCC NEW lens)

**CCC-2 is the most operationally dangerous V11 finding.**

`ORGANISM_DRAWDOWN_KILL_PCT` carries 5 different values across the platform:
- code: 0.05
- dev compose: 0.05
- **prod compose: 0.08**
- `.env`: 0.20
- **paper compose: NOT WIRED**

`ORGANISM_MAX_DAILY_LOSS` and `ORGANISM_MAX_NOTIONAL` default to **0 (disabled)** in code. `.env` runs 5500/2000; prod-compose 50/200. **A missing `.env` file silently disables per-trade and daily-loss caps in paper.**

This is exactly the kind of failure mode that costs trading firms millions.

### Pattern P3 — "Lint rule shipped but not enforced" (V8 OO redux)

Wave-57 shipped the UU2-B ruff rule. UU3 found:
- 2 of 7 grandfather entries point at non-existent paths (typos: `realtime_risk_analytics.py` vs `analytics/realtime_risk_analytics.py`).
- `ruff check .` reports 3,542 errors — CI lint job cannot pass against this config — yet merges land. Pre-commit pins `ruff v0.1.6` (Nov 2023), out of sync with CI.
- Post-V10 wave-50-65 fixes leaked +9 NEW violations of the very rules wave-57 added (background_trainer +5, slo_monitor +2, others). The rule is not gating.

**Same V8 OO "wired but unreachable" pattern.** Cycle keeps reproducing it.

### Pattern P4 — "PII discipline absent at production" (III NEW lens)

`backend/utils/logger.py:195-212` has a structlog PII-scrubbing processor. Production runs stdlib via YAML — the scrubber is **never reached**. Emails + usernames logged cleartext at `auth.py:672/766/818/951`, `users.py:476/481/501/511/669/681`, `security.py:169`. Plus `audit_trail.log` writes outside the mount and is lost on restart.

### Pattern P5 — "Strategy fixes one layer up from the actual cause" (V11 DD5)

V10 wave-44 fixed DD3-5 (fitness gate missing data). V11 DD5-3 finds the wave-53 "decoupled persistence" fix is structurally identical to the promotion-gated path — `symbol_trade_counts_runtime` is just a SNAPSHOT of the promotion-gated counter, not a separate accumulator. **Same root-cause is intact.**

V10 wave-44 fixed DD3-1 (max_level keyed extraction). V11 DD5-1 finds chop-min-hold compares **ticks** to a constant named in **bars** — at 1-min bars, ticks ≫ bars, so the gate is functionally inert. Same population the gate should suppress (8 of 18 last-50 pyramid_cuts) is not being suppressed.

Three audit rounds in a row each found a deeper layer of the same bug.

### Pattern P6 — "Direct-access security bypasses RBAC" (AAA NEW lens)

AAA-F2: `backend/api/routes/orders.py:292-301` defines a LOCAL `require_trader` that **ignores roles** ("In production, would check roles/permissions"). Self-registered users (default `["user"]`) can place/cancel/modify orders. Wave-23b fixed this for organism/audit endpoints but missed orders.

AAA-F1: `/test/http-{401,403,422,500}` debug endpoints are exposed in the deployed paper image because the gate excludes when `APP_ENVIRONMENT != "development"` — paper runs AS development.

### Pattern P7 — "_live_tick_inner is regressing not refactoring" (HH3)

Pre-V8: 2510 LOC. Current: **2706 LOC** (+196 despite 2 stages extracted). New inline logic added in waves 29-65 (~280 LOC) outpaces extractions (~93 LOC).

`_reconcile_fills` (541 LOC) and `initialize` (489 LOC) are NEW god-methods V8/V10 missed.

---

## Findings table

### Critical (2)

| ID | Track | Summary | Status |
|---|---|---|---|
| AA5-1 | AA5 | Wave-47 broke ALL JWT auth (leeway kwarg) | **CLOSED wave-67** |
| CCC-2 | CCC | `ORGANISM_DRAWDOWN_KILL_PCT` divergence; paper compose not wired; daily-loss + notional caps default-disabled | wave 68 |

### High (18)

| ID | Track | Summary | Wave |
|---|---|---|---|
| AA5-2 | AA5 | Source-grep fake-positive tests pattern | 69 |
| AAA-F1 | AAA | /test/http-* debug endpoints exposed in paper image | **68 (URGENT)** |
| AAA-F2 | AAA | orders.py local require_trader ignores roles — self-reg users can trade | **68 (URGENT)** |
| BB5-F1 | BB5 | outbox_events unbounded (1393 rows, 60 days, no auto-prune) | 73 |
| BB5-F2 | BB5 | GDPR right-to-be-forgotten structurally unimplementable | 75 (defer) |
| CCC-1 | CCC | production.py validator demands wrong env var names | 69 |
| DD5-1 | DD5 | chop-min-hold gate compares ticks to bar-units → inert | 71 |
| DD5-2 | DD5 | live_engine carries private `_INVERSE_ETFS_CHOP_SUPPRESSED` parallel to wave-60 unification | 71 |
| DD5-3 | DD5 | wave-53 fitness-gate persistence is identity copy; DD4-1 issue intact | 71 |
| DDD-1 | DDD | ecdsa CVE-2024-23342 unpatched (transitive via python-jose) | 70 |
| DDD-2 | DDD | npm audit: 13 high / 7 moderate; axios SSRF/DoS, vite, mermaid | 70 (FE coordinated) |
| HH3-N-1 | HH3 | _live_tick_inner regressing not refactoring (+196 LOC since V8) | 74 (CI ratchet) |
| III-F1 | III | configure_structured_logging is dead code; production has no trace_id | 72 |
| III-F2 | III | PII (email/username) logged cleartext; scrubber unreachable in production | 72 |
| TT3-F1 | TT3 | ix_orders_attributes_gin idx_scan=0 — call sites use text extraction not @> | 73 |
| UU3-1 | UU3 | 2 of 7 grandfather entries point at non-existent paths (120+ violations leaked) | 69 |
| UU3-2 | UU3 | wave-57 lint rule unenforced (3542 errors); CI cannot pass | 69 |

### Medium (19)

(AA5-3, AAA-F3, AAA-F4, AAA-F5, AAA-F6, AAA-F7, BB5-F3, BB5-F4 (CLOSED), CCC-3, CCC-4, CCC-5, DD5-4, DD5-5, DDD-3, DDD-4, HH3-N-2, III-F3, III-F4, III-F5, TT3-F2, TT3-F3, UU3-3) — see per-track reports.

### Low / Info (10)

Z9-F1, Z9-F2, AA5-4, AAA-F8, HH3-N-3, PP3-1, PP3-2, PP3-3, BB5-F4 (CLOSED).

---

## Recommended wave sequence (waves 68-77)

### Wave 68 — URGENT: deploy-gate security (CRITICAL/HIGH)
- **AAA-F1**: gate `/test/http-*` endpoints to NOT register in paper-deployed image.
- **AAA-F2**: replace orders.py local `require_trader` with the canonical `require_roles("trader","admin")` from infra/security.
- **CCC-2**: align `ORGANISM_DRAWDOWN_KILL_PCT` across all compose files; ensure paper compose explicitly wires it; bump in-code defaults for risk caps to non-zero conservative values.

### Wave 69 — Lint rule + production-validator hygiene
- **UU3-1**: fix grandfather typos.
- **UU3-2**: pin pre-commit ruff version + ensure CI lint actually runs.
- **CCC-1**: fix production validator env var names.

### Wave 70 — Dependency CVE response
- **DDD-1**: pin ecdsa to safe version OR migrate to pyjwt[crypto].
- **DDD-2**: `cd frontend && npm audit fix` (with verification).
- **DDD-3**: pin requirements.txt with `==`.
- **DDD-4**: add `.github/dependabot.yml`.

### Wave 71 — Strategy follow-through (DD4 → DD5 deeper)
- **DD5-1**: chop-min-hold ticks→bars conversion.
- **DD5-2**: remove live_engine private inverse-ETF set; route through `is_inverse_etf()` helper.
- **DD5-3**: actually decouple `symbol_trade_counts_runtime` (separate accumulator).
- **DD5-4**: wire pyramider telemetry into manifest export.

### Wave 72 — Logging architecture
- **III-F1**: wire `configure_structured_logging` into lifespan startup.
- **III-F2**: PII scrubber for stdlib path (or migrate to structlog universally).
- **III-F4**: consolidate 3 logger abstractions to 1.
- **III-F5**: AuditLogger path inside `./logs:/app/logs` mount.

### Wave 73 — Performance + retention
- **TT3-F1**: migrate JSON queries from `->>'X'='Y'` to `@> '{"X":"Y"}'` for GIN.
- **TT3-F2**: cap `_all_trades` and `_evolution_log`.
- **TT3-F3**: emit slow-tick `logger.warning` line.
- **BB5-F1**: outbox retention policy + auto-prune worker.

### Wave 74 — API contract + architecture ratchet
- **AAA-F3**: unify idempotency header naming.
- **AAA-F6**: extra="forbid" on critical schemas.
- **AAA-F7**: pagination cap on /orders.
- **HH3-N-1**: CI ratchet on `_live_tick_inner` LOC.

### Wave 75 — Cleanup batch
- AA5-2 (behavioral test pattern; rename source-grep tests).
- AA5-3 (rate-limit dead branch).
- HH3-N-3 (Stage 1.3 prep wave).
- PP3-1/2/3.

### Wave 76 — Defer to V12: BB5-F2 (GDPR FK refactor) + Z9-F1 (stale literal).

---

## V12 forward-plan

V11 yielded 49 actionable findings — well above estimates because the 4 NEW lenses (AAA, CCC, DDD, III) found long-latent issues. Going forward:

**Retain all 17 lenses.** Add to V12:
- **DD-DEPLOY**: container vs source-SHA verification (catches AA4-1 / wave-47 hotfix-style issues).
- **EEE — Test quality**: behavioral vs source-grep ratio audit (catches AA5-2 pattern).
- **FFF — Operations runbook completeness**: every CRITICAL log → runbook entry?

**Yield expectation:** 5-15 findings if waves 68-75 close cleanly. The cycle should finally start to converge as the new lenses mature.

The user's observation that "issues are identified, fixes implemented, but the next V catches the same" remains structurally true — but with diminishing severity. V11 found 2 actually-critical issues (AA5-1 deploy hotfix, CCC-2 kill-switch). Without V11 these would have hurt operations.
