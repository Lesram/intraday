# Platform Deep-Audit — V7 Master Synthesis

**Date:** 2026-05-03
**Round:** v7 (10 tracks — largest in the audit cycle)
**Branch:** `rc-1.5-curated` @ `d44eace`
**Production state:** paper trading active; brain gen=168, trades=498, healthy

---

## TL;DR

**~80 new findings across 10 tracks.** V7 covered 8 surfaces V1-V6 had
never deeply audited (security, data integrity, test quality, **strategy
logic**, operational readiness, adversarial inputs, documentation
truthfulness, architecture). The strategic bet paid off: V7 is the
highest-yield round of the cycle, and the findings are categorically
more severe than prior rounds.

**Three findings rise above the rest in operational severity:**

1. **AA-C-1 (Critical security)** — Running container signs every JWT
   with the publicly-known string
   `dev_secret_key_minimum_32_chars_for_development_only`. The container's
   `JWT_SECRET_KEY` falls back to this default because `JWT_SECRET` is
   unset. Anyone with this string can forge any user token.

2. **AA-C-2 (Critical security)** — `require_roles()` factory returns a
   *function reference* instead of executing the role check. **12 organism
   admin endpoints + 6 audit endpoints lose their role gate.** Combined
   with self-registration granting `["user"]` role, any registered user
   can call `/halt-trading`, `/freeze-adaptation`, `/admin/training`,
   `/diagnostics/run` against the live $111k paper account.

3. **DD-1 (High strategy)** — `comp_breakout_readiness` returns **0.633
   on perfectly flat-price data**. `_safe_div(0, 0)` makes both
   `compression` and `near_resistance` saturate to 1.0. **The platform
   manufactures synthetic high-breakout score out of warmup / halted /
   quiet-tape data**, feeding the alpha scanner's 20-40% weighted
   breakout factor + Kelly's 1.5-2.0× breakout bonus. This is the
   single highest-impact strategy-logic bug ever surfaced by the audit
   cycle and likely costs real money in live trading.

**Plus two near-critical data integrity findings:**

- **BUG-10 (Critical) — `audit_logs` is empty.** Drawdown-kill,
  governance halt, daily-loss halt, order lifecycle, risk violations
  all fire alerts but write **zero rows**. There is no compliance trail.
- **BUG-8 (Critical) — `LotTracker` is dead code in production.**
  Lifespan starts `alpaca_stream.py`; `LotTracker.create_lot` is only
  called from `alpaca_stream_production.py`. Result: `position_lots`
  and `realized_trades` are **0 rows despite 1,369 orders**. Wave-13e's
  row-locking fix protects code that never runs.

**Severity tally**

| Severity | Z4 | W2 | AA | BB | CC | DD | EE | FF | GG | HH | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Critical / P0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | **4** |
| High / P1 | 0 | 1 | 4 | 3 | 0 | 3 | 3 | 3 | 3 | 3 | **23** |
| Medium / P2 | 0 | 2 | 5 | 4 | 0 | 5 | 5 | 5 | 5 | 4 | **35** |
| Low / Latent | 2 | 0 | 3 | 2 | — | 3 | 0 | 3 | 3 | 3 | **19** |
| **Track total** | **2** | **3** | **14** | **11** | proc | **11** | **8** | **11** | **11** | **10** | **~91** |

CC's deliverable is a coverage report (8,777 tests across 464 files;
backend/ at 26% line coverage, organism at 42%) plus 13 deterministic
regressions and 8 zero-coverage organism modules — process gaps, not
counted as bug severity.

---

## Findings by track (highlights)

### Track Z4 — Closure Regression (0 production regressions)

Waves 20-22 hold cleanly. 167/167 tests pass. Brain coherent.
`_now_fn` injection chain verified across all components. The only
out-of-scope note: `order_service.submit_order()` deprecated sync shim
still has the broken alert dispatch pattern at lines 989/1026 (V-T-1's
sibling, not V-T-1 itself).

### Track W2 — CI Rule Verification (3 ship gaps)

**V6 W's CI rules never shipped to enforcement:**
- No PR template exists (rule #3's intended human surface).
- Zero of W's 3 CI rules in any of 8 workflows.
- `scripts/ci/check_wave_invariants.py` referenced by W doesn't exist.
- Wave 20/21/22 compliance: 1-1.5 / 3 each — IDs cited but no same-class
  grep + asserted-zero (the direct counter to V5 Pattern 1).

V6 W predicted V7 catches; V7 V-T-3 / X-4 / X-8 pattern (incomplete
same-class scans) keeps recurring because rule #2 is unenforced.

### Track AA — Security & Trust (14 findings, 2 Critical)

| ID | Severity | Finding |
|---|---|---|
| **AA-C-1** | 🔴 Critical | Container signs JWTs with public default `dev_secret_key_minimum_32_chars_for_development_only` (32-char validator accepts it; `JWT_SECRET` env var unset). |
| **AA-C-2** | 🔴 Critical | `require_roles()` returns function reference instead of executing role check. 18 endpoints lose role gate. |
| AA-H-1 | 🟠 High | `SecurityHeadersMiddleware` exists but never imported; no HSTS/CSP/X-Frame on any response. |
| AA-H-2 | 🟠 High | 5 endpoints public without auth (`/scanner/symbols`, `/observability/metrics|trading|dashboard|alerts`). |
| AA-H-3 | 🟠 High | `AuditAction.USER_LOGIN/LOGIN_FAILED/LOGOUT/CONFIG_UPDATED` enums never invoked — auth events not audit-logged. |
| AA-H-4 | 🟠 High | Container: no cap_drop, no read_only, no security_opt, no resource limits; runs uid=10001 but **gid=0 (root)**. |
| AA-M-1 | 🟡 Med | Redis password is the documented default `changeme_redis`. |
| AA-M-2 | 🟡 Med | Rate limiter keys on never-populated `request.state.user_id` → defaults to per-IP, defeating per-user limits. |
| AA-M-3..5 | 🟡 Med | `/settings/organism|trading|ml`, `/settings/restart-engine`, `/risk/emergency-stop` lack role enforcement (compounds AA-C-2). |
| AA-L-1..3 | 🟢 Low | Various TLS / log redaction nits. |

### Track BB — Data Integrity (11 findings, 2 Critical)

| ID | Severity | Finding |
|---|---|---|
| **BUG-10** | 🔴 Critical | `audit_logs` is **empty**. ComplianceAuditService.log() only invoked by viewer route. Drawdown-kill / governance halt / daily-loss halt / order lifecycle / risk violations all fire alerts but write zero rows. |
| **BUG-8** | 🔴 Critical | `LotTracker` is dead code. Lifespan starts `alpaca_stream.py`; LotTracker.create_lot only called from `alpaca_stream_production.py`. `position_lots` + `realized_trades` = 0 rows despite 1,369 orders. |
| BUG-1/2/3 | 🟠 High | `orders` table missing CHECK constraints on `qty>0`, `filled_qty<=qty`, status, side, tif, order_type. State machine has 14+ status values but DB accepts any 20-char string. |
| BUG-6 | 🟡 Med | `order_events.order_id` ORM declares `ondelete="CASCADE"`; migration created the FK without cascade. |
| BUG-7 | 🟡 Med | Outbox claim bumps lease but doesn't change status. Concurrency depends entirely on Alpaca's client_order_id dedupe. |
| BUG-9 | 🟡 Med | `scheduled_reconciliation` detects DB-vs-broker drift but only logs to stdout. |
| BUG-11 | 🟡 Med | `save_essential_state` writes 7+ files to `brain_dir` with no all-or-nothing semantic (S-DISK-1 partial fix at per-file level only). |

### Track CC — Test Quality & Coverage

- **8,777 tests across 464 files**.
- backend/ overall: **26% line coverage**. backend/organism/: **42%**.
  `live_engine.py` (2,450 statements, 6,401 LOC): **21%**.
- **8 organism modules at 0% coverage** (attribution, feature_store,
  nightly_scheduler, promotion, runner, scheduler,
  streaming_data_provider, training).
- V3 Track M comparison: 3 of 6 historically untested modules still
  zero (`nightly_scheduler`, `training`, `transfer_learning`).
- 3-run flake test: **0 flakes detected** in 296-test curated subset.
  But 13 deterministic regressions (5 replay-simulator timeouts, 3
  ML-confidence-leakage tests still asserting pre-May-1 contract, 5
  economic-validation, 1 watchdog).
- 8 slow tests confirmed (5 replay-sim at 15s timeout, 3 ML-training).
- 224 files carry redundant `@pytest.mark.asyncio` decorators (asyncio_mode=auto).
- 10 files use `asyncio.run` inside test bodies (anti-pattern).
- Test smells (20-sample): 14 instances in 5 patterns.
- Highest-leverage: pin pytest-cov + pytest-xdist; nightly coverage-ratchet CI gated on `live_engine.py` not regressing.

### Track DD — Strategy Logic (11 findings, 3 High — first audit ever)

| ID | Severity | Finding |
|---|---|---|
| **DD-1** | 🟠 High | `comp_breakout_readiness` returns 0.633 on flat-price data. `_safe_div(0, 0) = 0` saturates compression + near_resistance to 1.0. **Manufactures synthetic high-breakout score from warmup/halted/quiet bars.** |
| **DD-2** | 🟠 High | Regime detector default `atr_ratio = 0.02` when ATR columns missing. Intraday `atr_high_thresh ≈ 0.002` — default is **10× the high-vol threshold**. Any DataFrame missing ATR misclassifies as high_vol, raising entry gates and changing Kelly's regime_scale. |
| **DD-4** | 🟠 High | Kelly's regime-stratified path (`get_regime_kelly`) bypasses spread-cost gate, ML-confidence floor, breakout floor. Once a regime accumulates ≥10 trades, **any candidate sizes from regime_kelly regardless of current edge**. |
| DD-3 | 🟠 High | SPY cross-asset features use positional `iloc[-len(df):]` slicing — silent misalignment when SPY/stock lengths differ (e.g. halt). |
| DD-5..8 | 🟡 Med | Unconditional historic Kelly on zero-edge candidates; regime tie-break dict-iteration-order; system-level anti-predictivity not surfaced; pure-breakout entries mis-tagged "alpha+breakout". |
| DD-9..11 | 🟢 Low | Sector "Unknown" gate bypass; unreachable drawdown_floor=0.10; ATR warmup uses close-diff. |

**Verified clean:** B-T-7 / B-T-5 fixes work; pre-V3 SMA normalization
fixed; no per-symbol training leak; exit precedence deterministic; no
`.shift(-N)` lookahead anywhere; training labels correctly drop trailing
H bars.

### Track EE — Operational Readiness (8 findings)

| ID | Severity | Finding |
|---|---|---|
| **EE-1** | 🟠 High | Compose healthcheck targets `/healthz` (shallow). Container `(healthy)` while `/readyz` returns 503. |
| **EE-3** | 🟠 High | `redis-server --bind 127.0.0.1` refuses cross-container traffic. Broker SLI permanently red. One-character fix. |
| **EE-4** | 🟠 High | Single manual pg dump exists; no cron, no restore script, no integrity check; `DATABASE_RECOVERY.md` references wrong db user/name. |
| EE-2 | 🟡 Med | V4 P-P2 sentinel still: `/api/v1/observability/health/ready` returns `{"ready":false,"status":"unknown"}` HTTP 200. |
| EE-5 | 🟡 Med | 6 DR scenarios without runbooks; `INCIDENT_RESPONSE.md` has placeholder phone numbers. |
| EE-6 | 🟡 Med | Graceful shutdown has no per-component timeout; outbox stop doesn't drain. |
| EE-7 | 🟡 Med | api container has no memory/CPU limit; redis + postgres lack log rotation. |
| EE-8 | 🟡 Med | Two readiness-latency SLI gauges fail every 10s with `'MetricsRegistry' object has no attribute 'create_gauge'`. |

### Track FF — Adversarial Inputs (11 findings)

| ID | Severity | Finding |
|---|---|---|
| **FF-1** | 🟠 High | `submit_symbol_order` does NOT call `validate_order`. `qty=0`, `qty=-1`, symbol-injection all reach the outbox unchecked. |
| **FF-2** | 🟠 High | Idempotency-key cache returns prior result without verifying body matches. Different (symbol, side, qty) reusing the same key silently returns the cached response. |
| **FF-3** | 🟠 High | WS `_process_trade_update` `float(order_data.get("filled_qty", 0))` raises TypeError on JSON `null`; outer except drops the message silently → state divergence. |
| FF-4..8 | 🟡 Med | Empty body 502; negative MAX_NOTIONAL silently disables cap; empty/duplicate ORGANISM_LIVE_SYMBOLS; negative volume/price/non-monotonic timestamps; near-zero entry price → `actual_return ≈ 1e302`. |
| FF-9..11 | 🟢 Low | Unbounded WS update_queue; `timestamp=None` silently drops symbol; etc. |

**Verified clean:** no tick-loop crash from adversarial input; no
NaN-phantom 0-PnL; no WS hang on malformed JSON.

**Deliverable:** `tests/test_adversarial_inputs_v7.py` with 4 xfail-strict
tests that ratchet — closure of FF-1/2/3/4 will trip XPASS in CI.

### Track GG — Documentation Truthfulness (11 drift items)

| ID | Severity | Finding |
|---|---|---|
| **GG-6** | 🟠 High (operator-blocking) | OPERATOR_COMMAND_SHEET.md claims `eb90fa3` is HEAD; actual HEAD is **92 commits ahead** at d44eace. Brain numbers (gen 124, 396 trades) lag live (gen 168, 498). |
| **GG-9** | 🟠 High | README "Quick Setup" has 2 broken commands: `cd algotrading_platform`, `./scripts/run_ci_locally.sh`. Pins Python 3.11 while Docker uses 3.12. |
| **GG-7** | 🟠 High | MONDAY_DEPLOY_eb90fa3.md is one-time deploy artifact still living at repo root; OPERATOR_COMMAND_SHEET still names it as live runbook. |
| GG-3 | 🟡 Med | mapss.md Appendix E omits 4 Ferrari-v1 modules `live_engine.py:56-58` actually imports. |
| GG-4 | 🟡 Med | mapss.md lists `staleness_detector.py` under organism/ — actual location backend/ml/. |
| GG-2 | 🟡 Med | mapss.md "37 modules" — table 36, disk 40. Three numbers, all disagree. |
| GG-8/10/11 | 🟡 Med | README references 9 non-existent files; FINDINGS_LEDGER internally inconsistent; live_engine module docstring omits Ferrari scanners. |
| GG-1/5 | 🟢 Low | No CLAUDE.md in repo; 9 improve*.md docs unarchived. |

**Strong points:** audit-marker hygiene **excellent** (8 of 65 sampled,
all reference real related code, no orphans); AGENTS.md most accurate;
all sampled function docstrings match.

### Track HH — Architecture (10 structural findings)

- **`live_engine.py` is 6,401 LOC** (memory said 3,600 — 78% bloat).
- **`OrganismLiveEngine`**: 37 methods, 104 attributes, 17 collaborators,
  **374-line `__init__`**, single **2,510-line `_live_tick_inner` method**
  with 13 commented steps already begging for pipeline split.
- **`OrganismBrain` god-class**: 2,119 LOC, 48 methods, 13 hand-paired
  `_save_X`/`_load_X` (registry candidate).
- **One real cycle:** `api.routes.models ↔ ml.lifecycle`. Organism cycle-free.
- **Layering violations:** 4 sites; worst is `infra.guardrails →
  services.quote_manager`. `organism/routes.py` (882 LOC, 22 endpoints) is
  the only APIRouter outside `backend/api/`.
- **Configuration sprawl:** 7 settings entry-points, **383 `os.getenv` calls**.
- **136 lazy imports in `organism/`**, ~70 could be eager (X-1 pattern).
- **Strategy duplication:** `backend/strategies/` (4,872 LOC, 15
  BaseStrategy subclasses) shares zero interface with `backend/organism/`.
- **Inheritance is universally shallow** (correct — composition dominates).
  Class size, not hierarchy, is the debt.

**Top-5 ROI refactors:** R-1 pipeline-split `_live_tick_inner` (HIGH),
R-2 consolidate 7 config entry-points (HIGH), R-3 brain serializer
registry (HIGH), R-4 move organism/routes.py to api layer (MED), R-5
shared `safe_alert` + `atomic_io` helpers (MED).

---

## Cross-track patterns (V7)

### Pattern 1 — **Auth + Audit + Compliance trio is broken**

Three tracks converge on the same operational gap:
- **AA-C-1**: JWT secret is the public default.
- **AA-C-2**: 18 admin endpoints lose role check.
- **AA-H-3**: Auth events never audit-logged.
- **BB BUG-10**: `audit_logs` table empty.
- **BB BUG-8**: `position_lots` / `realized_trades` empty (no accounting trail).

For a paper-trading platform actively running ~$111k of equity, this is
the most operationally severe finding configuration in the audit cycle.
Anyone with the published JWT default secret can: forge a token →
authenticate → call any admin endpoint (gate ineffective) → trigger
state changes that aren't audit-logged → leave no compliance trail.

### Pattern 2 — **Strategy logic was the unaudited blind spot**

V1-V6 audited *that the system runs the strategy correctly* but never
audited *whether the strategy is right*. V7 DD found 11 issues
including DD-1 (manufactures breakout score from flat data) — the kind
of bug that quietly costs money in live trading even when every infra
metric is green.

The Ferrari v1 mean-reversion engine, ORB, EOD, alpha factors, regime
classification, Kelly's regime path, exit precedence — all needed
auditing. None had been.

### Pattern 3 — **Process enforcement gap (W2 confirms V6 Pattern 1)**

V5 Pattern 1 ("fix that didn't actually fix") and V6 Pattern 1
("same-class scans need machine enforcement") were each accompanied by
remediation proposals. **None of those proposals shipped to CI.**
Track W2 confirmed: 0 of 3 W rules in any workflow, no PR template,
the script W referenced doesn't exist. Wave 20-22 each had partial
compliance (1-1.5 / 3) by discipline alone. The pattern keeps
recurring because the rules aren't enforced.

### Pattern 4 — **Dead code with live-looking telemetry**

- BB BUG-8: `LotTracker` is dead in production; its tests (wave-13e
  N-H-2 row-locking + V6 T2 invariants) all green; the code is never
  exercised.
- BB BUG-10: `audit_logs` table exists, ORM declared, schema correct.
  Looks live to a code reviewer; never written to.
- HH: `backend/strategies/` (4,872 LOC) — 15 BaseStrategy subclasses;
  audit confirms barely wired.
- DD-7: System-level anti-predictivity (memory's `corr=−0.112`) — not
  surfaced anywhere in acceptance.

The audit cycle's per-fix verification has good marker hygiene but
weak reachability verification. A test passing doesn't mean production
exercises the path.

### Pattern 5 — **Documentation drift accelerates after a deploy**

GG found that `OPERATOR_COMMAND_SHEET.md` is 92 commits behind HEAD,
brain numbers in docs lag by 70+ trades, README references 9
non-existent files, mapss.md omits 4 Ferrari-v1 modules, FINDINGS_LEDGER
is internally inconsistent. All of this happened across the 22 fix
waves V1-V6 shipped — the audits update the ledger but the operator-
facing docs don't catch up.

### Pattern 6 — **`live_engine.py` is the gravitational center of pain**

Every V7 track touched it:
- HH: 6,401 LOC, 2,510-line method, 374-line `__init__`.
- CC: 21% line coverage on 2,450 statements.
- DD: 5 of 11 findings live in or near it.
- FF: 4 of 11 findings are in its dependents.
- AA: most exposed admin endpoints route to it.
- BB: most state-mutation paths originate here.

R-1 (pipeline-split `_live_tick_inner`) is the single highest-ROI
structural refactor. Every future audit will be 30-50% more efficient
once that split lands.

---

## Recommended fix waves

### Wave 23 (URGENT — security: ship within 24-48 hours)

| Phase | Findings | Effort | Risk |
|---|---|---|---|
| **23a** | AA-C-1 — set strong `JWT_SECRET` in `.env`; rotate; verify container reads it | 30 min | Low |
| **23b** | AA-C-2 — fix `require_roles()` factory: factory must return a callable that calls inner check, not return inner reference | 1 hr | Low |
| **23c** | AA-H-2 — add auth requirement to 5 public endpoints | 1 hr | Low |
| **23d** | AA-M-1 — generate strong `REDIS_PASSWORD`; rotate | 30 min | Low |
| **23e** | EE-3 — `redis-server --bind 0.0.0.0` (cross-container) — one-char fix | 5 min | Low |

Wave 23 is **stop-the-bleeding**. The `JWT_SECRET` default + `require_roles`
bug are the worst auth posture I've ever seen in a financial system.

### Wave 24 (HIGH — strategy + data integrity)

- DD-1 — `comp_breakout_readiness` flat-data fix (refuse-to-score,
  not synthesize-zero, when both numerator and denominator are zero)
- DD-2 — regime detector ATR-missing guard (return UNKNOWN, not 0.02 default)
- DD-3 — SPY cross-asset positional slicing (use index-based alignment)
- DD-4 — Kelly regime-stratified path: enforce spread-cost + ML-confidence + breakout floors
- BB BUG-8 — wire `LotTracker.create_lot` from the live `alpaca_stream.py` path (or align production-stream usage)
- BB BUG-10 — wire `ComplianceAuditService.log()` calls to drawdown-kill, governance halt, daily-loss halt, order lifecycle, risk violations
- AA-H-1 — register `SecurityHeadersMiddleware`
- AA-H-3 — invoke `AuditAction.USER_LOGIN/LOGIN_FAILED/LOGOUT/CONFIG_UPDATED` on those events
- AA-H-4 — container hardening (cap_drop, read_only, security_opt, gid)
- AA-M-3..5 — add role enforcement to `/settings/*`, `/risk/emergency-stop`

### Wave 25 (MED — operational + data integrity polish)

- BB BUG-1/2/3 — orders table CHECK constraints
- BB BUG-6 — `order_events` cascade migration
- EE-1 — healthcheck deepens to `/readyz`
- EE-2 — fix `/api/v1/observability/health/ready` (V4 P-P2 sentinel)
- EE-4 — pg_backup cron + restore script + integrity check
- EE-5 — runbooks for 6 DR scenarios; remove placeholder phone numbers
- EE-7 — container resource limits + log rotation for redis/postgres
- EE-8 — fix MetricsRegistry.create_gauge attribute error (SLI gauges)
- FF-1 — wire `validate_order` into `submit_symbol_order`
- FF-2 — verify body matches on idempotency-key cache hit
- FF-3 — handle JSON null in `_process_trade_update`

### Wave 26 (MED — process + tests + docs)

- W2 ship rules — PR template, `scripts/ci/check_wave_markers.py`,
  same-class grep CI, behavioral test count delta CI
- CC — pin pytest-cov + pytest-xdist in requirements; nightly
  coverage-ratchet CI gated on live_engine.py
- CC — fix 13 deterministic regressions (5 replay-sim timeouts; 3
  ML-confidence-leakage; 5 economic-validation; 1 watchdog)
- GG — update OPERATOR_COMMAND_SHEET.md to current HEAD; remove
  MONDAY_DEPLOY_eb90fa3.md from repo root
- GG — fix README quick-setup commands; pin Python 3.12
- GG — update mapss.md to absorb Ferrari-v1 modules
- GG — reconcile FINDINGS_LEDGER internal inconsistencies

### Wave 27 (HIGH-ROI structural refactor)

- HH R-1 — pipeline-split `_live_tick_inner` (2,510 lines → 13 stages)
- HH R-2 — consolidate 7 settings entry-points
- HH R-3 — brain serializer registry (replace 13 hand-paired methods)

### Defer to V8 / longer-horizon

- HH R-4..R-6 (organism/routes.py move, shared helpers, strategy framework reconciliation)
- DD-5..DD-11 (medium / low strategy)
- FF-4..FF-11 (medium / low adversarial)
- GG-1/5 (CLAUDE.md, improve*.md archival)

---

## What V7 validated about the audit process

1. **The "first audit of X" pattern reliably finds bugs.** Every NEW
   surface in V7 yielded findings disproportionate to the audit effort.
   AA: 14, BB: 11, DD: 11, EE: 8, FF: 11, GG: 11, HH: 10. Only CC
   (test quality) and Z4 (closure) were lighter — by design.
2. **Strategy logic auditing was overdue.** DD-1 is the kind of bug
   that costs money silently. 6 rounds of infra auditing should not
   come before *one* round of strategy auditing on a trading platform.
3. **Security debt accrues quickly without explicit auditing.** AA-C-1
   and AA-C-2 weren't introduced this round — they've been live for
   weeks. Every prior audit had AA-shaped budget but spent it on infra.
4. **The audit catches dead code, but tests don't.** BB BUG-8 (LotTracker
   dead in prod) had passing tests in wave-13e + V6 T2. Reachability
   should be a separate audit concern.
5. **Process proposals don't ship without enforcement.** V5 Pattern 1,
   V6 Pattern 1, W2's confirmation — three rounds of "we should add
   CI rules" without the rules shipping. Wave 26 needs to ship them
   *and verify they ran on subsequent waves*.

---

## Final state

```
Production: rc-1.5-curated @ d44eace, paper trading active, brain coherent
Wave 20-22 closures: 0 production regressions across 21 verifications
Tests (curated): 167/167 (V7 also adds 25 from FF + 26 from T2)

v1: 30  → all closed
v2:  8  → all closed
v3: 58  → all closed
v4: 52  → all closed
v5: 21  → all closed
v6: ~18 → all closed (V-T-8 deferred)
v7: ~91 → open
```

**Total platform findings cycle: 30 + 8 + 58 + 52 + 21 + 18 + 91 = ~278
audit items.** ~187 closed, **~91 open** — the largest open backlog
since V1.

V7 is the highest-yield, highest-severity round of the cycle. The
operational state was healthy before V7 and remains healthy after V7
(no waves shipped yet). But the truth surfaced is alarming:

- The platform's auth posture is effectively absent.
- The strategy manufactures synthetic signal from flat data.
- The compliance/accounting trail is empty.
- The CI rules that would have prevented the recurring "fix didn't fix"
  pattern haven't shipped despite three rounds of recommending them.

V7 is the audit cycle's "the iceberg is bigger than we thought" moment
— the analog of V3's 58 findings on uncharted infrastructure surfaces,
but on surfaces that matter more.

---

## V8 prompt additions to consider

For the next round (after wave 23-27 ships):

**Track Z5:** closure regression for waves 23-27.

**Track AA v8:** verify wave 23 auth fixes shipped — JWT secret rotation,
require_roles factory fix, audit log invocations. **Plus:** penetration
test from outside the container.

**Track DD v8:** re-audit strategy logic with the wave-24 fixes; add
backtest validity (in-sample vs out-of-sample split discipline) and
performance attribution accuracy.

**Track BB v8:** verify wave-24 audit_log + LotTracker fixes are
actually writing rows under live load (not just shipped).

**Track HH v8:** verify R-1 pipeline-split landed; measure the
post-refactor god-class size delta.

**New tracks v8 might add:**
- **Track KK — Compliance Readiness:** if this platform ever needed to
  pass an SEC/FINRA audit, what would block? Trade reporting, audit
  retention, customer protection.
- **Track LL — Disaster Recovery Drill:** actually simulate a recovery.
  Stop the container, restore from backup, verify the brain loads.
- **Track MM — Multi-Tenant Readiness:** if a second account/strategy
  were added, what assumes single-user / single-account?

---

## Audit reproducibility

```
artifacts/audit/
  AUDIT_PROCESS.md
  PROMPT_LESSONS_v1.md
  FINDINGS_LEDGER.md             # to be updated with V7 entries
  MASTER_AUDIT_SYNTHESIS.md      # v1
  MASTER_AUDIT_SYNTHESIS_v2.md   # v2
  MASTER_AUDIT_SYNTHESIS_v3.md   # v3
  MASTER_AUDIT_SYNTHESIS_v4.md   # v4
  MASTER_AUDIT_SYNTHESIS_v5.md   # v5
  MASTER_AUDIT_SYNTHESIS_v6.md   # v6
  MASTER_AUDIT_SYNTHESIS_v7.md   # this file
  WAVE16_PLAN.md
  prompts/
    v1/  v2/  v3/  v4/  v5/  v6/  v7/
  v3_reports/  v4_reports/  v5_reports/  v6_reports/  v7_reports/
```
