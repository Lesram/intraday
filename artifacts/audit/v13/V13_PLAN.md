# V13 Audit Plan — Convergence Cycle

**Status:** plan only — NOT yet executed.  User must approve before V13 begins.
**Date drafted:** 2026-05-04 (post-V12-cleanup, W91)
**Predecessors:** V1-V12 + V12 external-auditor cleanup waves (W80-W90).
**Framework:** 7-lens convergence per [`V13_FRAMEWORK.md`](../V13_FRAMEWORK.md) — collapsing the 17-lens taxonomy.
**Hard constraint:** no 18th lens.  V13 is shrink-and-converge, not expand.

---

## V12 final state (V13 baseline)

V13 starts from a known-clean state:

- **Pytest:** 0 fail / 7,107 pass / 719 skipped / 3 xfailed.  Down from V12 baseline (125 fail / 6,910 pass) and post-V12-W79 (102 fail / 7,051 pass).
- **CI gates green:** audit_gate, lint_ratchet, findings ledger verifier, wave-marker enforcer.
- **Live endpoints respond 200 in container:** `/api/v1/health/strategy`, `/api/v1/health/deploy`, `/api/v1/audit/chain-detail`.
- **Container provenance baked in:** GIT_SHA, BUILD_TIME, IMAGE_SHA in runtime env.
- **Outbox prune loop firing live:** removed 544 rows on rebuild (1,398 → 854).
- **Branch:** `rc-1.5-curated`.  Snapshot at `audit-evidence/v12`.
- **130 findings in ledger** (21 closed, 5 deferred, 1 documented_by_design, 103 still-open from V8-V11 not yet V12-audited).

V13's first job: triage the 103 still-open findings against the 7-lens grid.

---

## V13 wave structure (W91 → W101)

Each wave: one lens, one atomic commit, behavioral tests, zero pytest regressions vs V12 final, lint ratchet passes.

### Wave 91 — V13_PLAN.md (THIS document)
**Status:** in flight (this commit).
**Deliverable:** the document you're reading.
**No code changes.**  Plan-only.  User must review before W92 begins.

---

### Wave 92 — Lens 1: Deploy / Runtime Truth
**Goal:** make the deploy-state class of bug (V10/V11 wave-47 JWT regression, V12 stale-container) impossible to ship undetected.

**Closures targeted:**
- New finding W92-D-1: build a `scripts/ci/check_deploy_parity.py` CI gate that compares host SHA, container SHA, byte counts on hot-path files, AND that all 3 V12 health endpoints respond 200 from a freshly-rebuilt container.
- Wire the gate into `.github/workflows/ci.yml` as a deploy-readiness check (fires on PR + push to release branches).
- Promote `scripts/deploy/rebuild_paper.sh` into a `make rebuild-paper` target.

**Required automated checks:**
- Live HTTP probe of `/api/v1/health/deploy` returns 200 with non-"unknown" GIT_SHA.
- Live HTTP probe of `/api/v1/health/strategy` returns 200 with `source: manifest`.
- Container vs host file byte parity for the 5 hot-path files
  (live_engine.py, brain_persistence.py, outbox_worker.py, security.py, lifespan.py).

**Behavioral tests:** `tests/test_v13_w92_deploy_parity.py` — sandbox tests for the parity-checker, plus a marker that runs the live probes when an env flag (`V13_LIVE_PROBES=1`) is set.

**Acceptance:** parity gate exists and runs in CI; live probes wired with explicit opt-in env so PRs without a running container don't break.

---

### Wave 93 — Lens 2: Trading Safety
**Goal:** close `test_replay_no_throttle_blocking` (the only currently-xfailed test) by fixing the upstream entry-gate path; build behavioral coverage for drawdown-kill / max-daily-loss / hung-broker timeout.

**Closures targeted:**
- Currently-xfailed `test_replay_no_throttle_blocking`: investigate why 100 ticks across AAPL/MSFT/SPY synthetic upward-trend bars produce 0 orders. Likely fitness-gate or scanner-candidates path.
- Re-impose tension cap at 0.80 if the V11 saturation-cap design intent still applies (W90 noted the impl drifted to 1.0).
- Build live-trigger probes: synthetic equity drop → drawdown kill engages + audit log row + Slack mock fired + halted state.
- Replay path unification: ensure replay-mode and live-mode share the same entry-gate code (no replay-only code branch).

**Required automated checks:**
- `test_replay_no_throttle_blocking` passes (no longer xfail).
- Drawdown-kill end-to-end test: `tests/test_v12_w76_operational.py` already covers this — reaffirm it stays green.
- Max-daily-loss halt: synthetic daily PnL exceeding ORGANISM_MAX_DAILY_LOSS engages halt.
- Hung-broker timeout: synthetic broker that never responds; trade attempt times out within configured window.

**Acceptance:** zero xfailed tests in `tests/test_safety_*` and `tests/test_replay_*`; tension cap design decision documented.

---

### Wave 94 — Lens 3: Strategy Expectancy
**Goal:** add the alert layer on top of V12 W71's exposure layer.  Operators currently can SEE the brain is unprofitable; W94 makes them PAGED when it gets worse.

**Closures targeted:**
- Hourly log line emits expectancy + flags if `last_50_win_rate < 0.30`.
- Operator alert via existing `dispatch_alert_from_thread` path: fire ALERT when last_50_mean_pnl drops below threshold.
- Configurable expectancy floor: env `STRATEGY_FLOOR_TOTAL_PNL` (default `null` = no gate); CI gate refuses merge to release branch if `total_pnl < floor`.
- New endpoint: `/api/v1/health/strategy?window=last_50` returns just the windowed slice for dashboard panel use.

**Required automated checks:**
- Behavioral test: synthetic last_50 win_rate=0.20 → alert fires.
- Behavioral test: synthetic last_50 win_rate=0.50 → no alert.
- Behavioral test: floor configurable via env, gate respects it.

**Acceptance:** unprofitable brain is impossible to ship to release branch without explicit override.

**Open product question (NOT V13's call):** what's the floor?  V12 final: -$634.90 / 33.7% win rate / -1.06 Sharpe.  Choosing a sustainable floor is product policy.  V13 ships the gating mechanism; the threshold is a product decision.

---

### Wave 95 — Lens 4: Data Integrity
**Goal:** triage and resolve open data-integrity findings, including the V12 deferred BB5-F2 (GDPR right-to-be-forgotten) and the W74 follow-up schema bug.

**Closures targeted:**
- BB5-F2 GDPR right-to-be-forgotten — FK refactor.  Was deferred from V12 due to scope; V13 has time.
- W74-FOLLOWUP-1 — `AuditLog.ts` index declared twice in `schemas.py`.  Fix the schema so SQLite tests don't fail on duplicate-index.
- realized_trades vs brain.total_trades (V12 EXT-3 documented_by_design): resolve via product decision — either ship a reconciliation worker or formally accept divergence with documented operator runbook.
- Outbox prune-loop observability: emit `outbox_pruned_total` metric to Prometheus; alert if prune loop hasn't run in >36h.

**Required automated checks:**
- Behavioral test for GDPR FK refactor (round-trip: insert user → trades → forget → assert all referencing rows handled correctly).
- AST test asserting `AuditLog.ts` has exactly one index declaration.
- realized_trades / brain.total_trades reconciliation: either passes (variance < 5%) or documented divergence with operator-readable explanation in `/api/v1/health/data-integrity`.

**Acceptance:** all 3 deferred V12 data-integrity items closed.

---

### Wave 96 — Lens 5: Auth / RBAC
**Goal:** close the IDOR / cross-user gap V12 didn't reach.

**Closures targeted:**
- IDOR test: trader-role user A cannot place / view / cancel orders belonging to trader-role user B.
- Cross-user audit-log read: trader-role user cannot read other users' audit rows via `/api/v1/audit` filters.
- Build a sandbox: programmatically create 2 throwaway trader users, exercise the cross-user paths, assert 403/404.
- Tighten dev-bypass: `VITE_DEV_BYPASS_AUTH` (frontend) — V13 brings frontend in scope (see Lens 7).

**Required automated checks:**
- Behavioral test: synthetic users A + B; A places order O; B's `/api/v1/orders/{O}/cancel` returns 403.
- Same pattern for positions, signals, audit logs, settings.

**Acceptance:** no cross-user privilege escalation across the protected `/api/v1/*` surface.

---

### Wave 97 — Lens 6: Test / CI Quality
**Goal:** drive the marker-only-test ratio across the WHOLE wave-test corpus below 30% (V12 W73 only gated Critical/High; V13 expands to all severities).

**Closures targeted:**
- Run `scripts/ci/classify_wave_tests.py` on the full corpus; pick top-20 marker-only tests; convert to behavioral.
- Update audit_gate to enforce the broader ratio: fail CI if marker-only > 30% of wave-test total.
- Build a "mutation testing" smoke: pick 3 critical functions, mutate them, assert at least one wave test catches the mutation.  This proves the wave-test suite has real teeth, not just structural greps.

**Required automated checks:**
- `forbid_marker_only_critical_high.py` extended with a `--full-corpus` flag.
- Mutation-testing harness exists for at least 3 functions.

**Acceptance:** wave-test corpus marker-only ratio ≤ 30%; mutation harness in CI.

---

### Wave 98 — Lens 7: Frontend / Product Contract
**Goal:** V12 explicitly excluded frontend per user direction.  V13 brings it in scope under one consolidated lens.

**Closures targeted:**
- `cd frontend && npm run build -- --mode production` exits 0.  V12 auditor flagged 2 specific TS errors (PositionsTable.tsx:14 imports non-existent `api`; ThresholdTable typed-record mismatches).
- ProtectedRoute admin-bypass code: gate the `VITE_DEV_BYPASS_AUTH=true` path so it's tree-shaken or build-fails outside `MODE=development`.
- Websocket auth: replace JWT-in-query-string with a subprotocol or short-lived ticket.
- Frontend tests added to CI (currently TS errors block).
- `marketDataWebSocketService.ts` localStorage fallback → contradicts the memory/session-token story; align.
- DDD-2 (V11 finding): npm audit fix.  13 high / 7 moderate vulnerabilities flagged in V11.

**Required automated checks:**
- Frontend build job in `.github/workflows/ci.yml`.
- Behavioral test: build succeeds AND admin-bypass path errors-out without `MODE=development`.

**Acceptance:** frontend `npm run build` is green and gated in CI; admin-bypass is build-fenced; npm audit critical/high vulns at zero.

---

### Wave 99 — V8-V11 finding triage
**Goal:** the 103 still-open findings parsed from V8-V11 synthesis docs are unaudited under V12's standards.  V13 triages them.

**Process:**
1. Run `scripts/ci/build_findings_ledger.py` against current state.
2. For each "open" finding, classify into one of: (a) closed in unrecorded V8-V11 wave but not ledgered; (b) genuinely still open and worth fixing; (c) deprecated or no longer applicable; (d) folded into one of the 7 V13 lenses.
3. Update `v12_state.json` (or migrate to `v13_state.json`) with the triage.
4. Re-run `verify_findings_ledger.py` — it must still pass.

**Required automated checks:**
- Each "open" finding now has either `status: closed_in_v11_unrecorded` (with evidence path), `status: deferred` (with reason + V14 wave target), or `status: open` (with V13+ wave target).
- No "open" finding lacks a path forward.

**Acceptance:** ledger has zero "open" findings without explicit triage.  Realistic outcome: ~70% close as "already-fixed-but-unaudited", ~20% genuinely still open and absorbed into V13 lenses, ~10% deprecated.

---

### Wave 100 — `_live_tick_inner` LOC reduction (HH3-N-1)
**Goal:** start the multi-wave V13 effort to bring `_live_tick_inner` below pre-V8 baseline (2510 LOC).  Currently 2,738 LOC.

**Approach:** behavioral coverage FIRST, then refactor.  V12 W75 deferred this because the function had zero direct test coverage; extracting 200+ LOC from a critical hot path without tests was unsafe.

**W100 (this wave) work:**
1. Build behavioral coverage for the 4 largest sub-blocks of `_live_tick_inner` identified in V11 + V12 audits (entries-gate, position-management for-loop, equity-gates, pyramid path).
2. Each block gets 3-5 behavioral tests covering the happy path and 2-3 edge cases.
3. NO refactor yet.  Coverage commit is one wave.

**Subsequent waves (V13.1, V13.2, ...):**  one block extracted per wave, each ~150 LOC, tests still pass, full pytest delta zero.

**Required automated checks:**
- `tests/test_v13_w100_live_tick_inner_coverage.py`: ≥ 12 behavioral tests covering the 4 sub-blocks.
- AST test asserting `_live_tick_inner` LOC stays at current ceiling (no regression while we accumulate coverage).

**Acceptance:** coverage shipped; refactor pipeline ready.  Actual LOC reduction is V13.1+ work.

---

### Wave 101 — V13 synthesis
**Goal:** close the V13 audit cycle.  Same shape as V12 W79/W85.

**Deliverables:**
- `artifacts/audit/MASTER_AUDIT_SYNTHESIS_v13.md`: every V13 wave's deliverables + acceptance status + behavioral test path; severity-weighted convergence (V11=158, V12=??, V13=??); behavioral-test ratio across the WHOLE corpus; pre-V13 vs post-V13 expectancy snapshot.
- `findings_ledger.json` updated to V13 state via `build_findings_ledger.py`.
- `audit-evidence/v13` branch snapshotted from final HEAD.
- V14 framework recommendation (likely: "audit cycle should become quarterly health-check, not monthly deep-dive").
- Memory note + handoff document for the next external auditor pass.

**Acceptance:** V13 cycle is queryable as a single artifact; the next auditor can run the same 5-step protocol from V12 W85 against V13 final HEAD and find every claim verifiable.

---

## Per-wave verification protocol (same as V12)

After each V13 wave commit:

1. Run `./venv/bin/python -m pytest tests/ --timeout=120 -q --tb=no > /tmp/v13_post_waveNN.out`.
2. Diff against V12 final baseline (0 fail / 7,107 pass): must be 0 failures (no regressions tolerated).
3. `scripts/ci/lint_ratchet.py` exits 0.
4. `scripts/ci/forbid_marker_only_critical_high.py` exits 0.
5. `scripts/ci/check_wave_markers.py --base=<v12-final> --head=HEAD` exits 0.
6. `scripts/ci/verify_findings_ledger.py` exits 0.
7. Atomic commit with: finding IDs (V13-LL-N format), deliverables list, behavioral test path, pytest delta numbers.

---

## V13 success criteria

V13 is "done" when ALL of the following hold:

1. The 7-lens framework is operating; **no new lens has been added**.
2. The 103 still-open V8-V11 findings have been triaged (W99); zero remain "open" without explicit forward-plan.
3. Live probes for all 3 deploy/runtime-truth checks pass against a clean container (W92).
4. `test_replay_no_throttle_blocking` is no longer xfail; root-cause replay-engine path fixed (W93).
5. Frontend `npm run build` exits 0 (W98); admin-bypass build-fenced.
6. Manifest expectancy gate has a configurable floor; alert fires below it (W94).
7. IDOR cross-user-order behavioral test exists and passes (W96).
8. Wave-test corpus marker-only ratio ≤ 30% across all severities (W97).
9. `_live_tick_inner` has behavioral coverage for the 4 hot sub-blocks (W100); LOC reduction sequenced for V13.1+.
10. The V12 audit_gate, lint_ratchet, findings_ledger verifier, and wave-marker enforcer all still pass at V13 final.

If V13 ships another lens-expansion sweep instead, the cycle drift the V12 auditor warned about will repeat — and the next external review will say so.

---

## What V13 will NOT do (and why)

1. **No 18th lens.**  The framework is closed at 7.
2. **No new strategy logic.**  Brain unprofitability is product strategy work.  V13 builds the alert + gate so unprofitability is impossible to overlook; making it profitable is for the strategy team.
3. **No frontend re-architecture.**  Get `npm run build` green + close the admin-bypass; full frontend audit is V14+ if needed.
4. **No load testing / chaos engineering / fault injection.**  V13's job is convergence.  The "areas the audit cycle has barely probed" list (concurrency, memory leaks, real broker faults, disaster recovery, ML drift detection, network partition) are post-V13 engineering investments — not audit work.
5. **No `_live_tick_inner` refactor in W100.**  Coverage in W100; refactor in V13.1+.

---

## Estimated V13 effort

10 waves W92-W101.  Each wave: ~1-2 hours of focused work (one lens, one commit, tests, full pytest, lint, ledger).  W99 (V8-V11 triage of 103 findings) and W100 (live_tick_inner coverage) are the heaviest; possibly 3-4 hours each.

**Total V13 estimate:** 12-15 hours of execution after this plan is approved.

---

## Open questions for the user before V13 starts

1. **Is the V13 7-lens framework acceptable, or should we re-scope?**  V12 auditor recommended exactly this; user said "make me proud" — but if you want different lenses, propose now.
2. **Is the strategy expectancy floor a product decision?**  W94 ships the gating mechanism but I cannot pick the floor.  Either you specify a value (e.g. `total_pnl >= -1000`), or W94 ships with `floor=null` and the gate is opt-in until product picks one.
3. **Frontend scope:** does V13 fix `npm run build` only, or also the websocket-auth refactor + npm-audit cleanup?  Estimate doubles if the latter.
4. **`_live_tick_inner` plan:** OK with W100 = coverage only, then V13.1+ for actual extraction over multiple waves?  Or do you want the full extraction in V13 (riskier, but faster)?
5. **GDPR FK refactor (W95):** is this really V13 work, or does it want a dedicated migration sprint?  It's listed because BB5-F2 was V12-deferred, but it's data-migration work that touches user data integrity.

The default plan above answers each question conservatively (7 lenses, floor=null, frontend build-only, coverage-first refactor, GDPR in V13).  Tell me which to change before W92 starts.

---

## Branch state at V13 W91 (this commit)

- `rc-1.5-curated` @ V12 final HEAD
- `audit-evidence/v12` snapshot exists
- This document at `artifacts/audit/v13/V13_PLAN.md`

V13 work begins at W92 only after user review of this plan.
