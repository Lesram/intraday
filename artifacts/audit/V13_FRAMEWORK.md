# V13 Audit Framework — 7-Lens Convergence Cycle

**Date:** 2026-05-03
**Predecessors:** V1-V12 (49 V11 findings + 14 external + 10 V12 cleanup items)
**Author:** post-V12 cleanup (W84)
**Source:** V12 external auditor's recommendation #10 + Audit Cycle Health Assessment.

---

## Why shrink to 7 lenses

V11 closed 49 findings. V11's external auditor counted V8=8 lenses, V11=12 lenses, severity weight V8=148 → V10=105 → V11=158.  Lens expansion didn't track lower severity; it tracked relabeling of old evidence into new buckets.

V12 closed 21 findings + 7 V12-AUD cleanup items but still produced overlap: AAA, CCC, DDD, III all touch some version of "code-present, not deployed/wired/gated."  The 17-lens taxonomy is producing labels faster than operational truth.

**V13 collapses the 17 lenses into 7 outcome-grade tracks.  Each track must own at least one automated check or live probe; each track produces decisions, not just labels.**

---

## The 7 lenses

### 1. Deploy / Runtime Truth

**Owns:** Is the running container what the host code says?  Is the ledgered finding actually closed in production?

**Replaces (subsumes):** AA4, AAA, DD-DEPLOY, parts of UU3.

**Required automated checks:**
- Live HTTP probe of `/api/v1/health/deploy` → 200 with non-"unknown" GIT_SHA + matching host SHA.
- Live HTTP probe of `/api/v1/health/strategy` → 200 with `manifest` source.
- Live HTTP probe of `/api/v1/audit/chain-detail` → 200 with rows.
- Container vs host file byte parity for the top 5 hot-path files.
- BB5-F1 prune-loop log entry observed within 24h of container start.

**V13 success criterion:** every Critical/High closure must include a live-probe artifact in `artifacts/audit/v13/probes/<finding>.json`.

---

### 2. Trading Safety

**Owns:** Drawdown-kill, daily-loss halt, max-notional, hung-broker timeout, EOD flatten, replay throttle behavior.

**Replaces:** PP3, BB-RISK, parts of DD5.

**Required automated checks:**
- Behavioral test that fires drawdown-kill end-to-end (test_v12_w76 already does this).
- Behavioral test that asserts max-daily-loss halt on threshold breach.
- The currently-xfailed `test_replay_no_throttle_blocking` becomes V13 work-item #1 — fix the upstream entry-gate so the test passes.

**V13 success criterion:** zero xfailed tests in `tests/test_safety_*` and `tests/test_replay_*`.

---

### 3. Strategy Expectancy

**Owns:** Realized PnL, Sharpe, win rate, max drawdown.  The lens V12 W71 invented.

**Replaces:** *new in V12*; nothing yet to subsume.

**Required automated checks:**
- `manifest["strategy_expectancy"]` populated on every save (W71 already enforces).
- `/api/v1/health/strategy` `is_profitable` field present in payload.
- A new alert: hourly log line emits expectancy + flags if `last_50_win_rate < 0.30`.

**V13 success criterion:** the alert exists; an operator dashboard surfaces it; no merge-to-main without an expectancy gate that asserts `total_pnl >= floor`.

**Open question for product:** what's the floor?  Currently `-$634.90`; that's not a sustainable floor, but choosing one is product policy, not audit.

---

### 4. Data Integrity

**Owns:** Audit log chain integrity, outbox retention, brain backups, realized_trades vs brain.total_trades reconciliation, schema migrations.

**Replaces:** BB5, XX, parts of WW.

**Required automated checks:**
- Audit chain verify endpoint returns `valid=true`.
- Outbox prune loop fires within 24h of container start (W83 verified, monitor).
- Brain backup hourly cadence (24h after container start, ≥24 backups exist).
- Migration head matches expected per `scripts/ci/check_migrations.py`.
- realized_trades count vs brain.total_trades: variance < 5% OR reconciliation-by-design documented.

**V13 success criterion:** the realized-trades reconciliation finding (V12 EXT-3 documented_by_design) is either resolved or explicitly accepted as product policy.

---

### 5. Auth / RBAC

**Owns:** JWT issuance + decode, logout/blacklist, role enforcement, /test/ debug endpoint exposure, X-API-Key paths, password hashing.

**Replaces:** AA3, AA4, AA5, AAA-F1, AAA-F2.

**Required automated checks:**
- `/api/v1/auth/login` mints JWT; `/api/v1/auth/me` accepts it.
- `/api/v1/auth/logout` blacklists; subsequent `/auth/me` with same token → 401.
- `/test/http-401` → 404 in deployed paper image.
- A trader-role token cannot place orders for another user (IDOR check).

**V13 success criterion:** behavioral test for IDOR (cross-user order placement) is added; current absence is a V13 gap.

---

### 6. Test / CI Quality

**Owns:** Marker-only-vs-behavioral classifier, lint ratchet, audit gate, wave-marker enforcer, pytest baseline.

**Replaces:** UU3, OO, W3-G* lineage.

**Required automated checks:**
- `audit_gate` CI job exits 0 (V12 W73, currently passing).
- `lint_ratchet` step exits 0 (V12 W75 + W81, currently passing).
- `check_wave_markers.py` exits 0 against the V12+ commit range (V12 W81, passing).
- `verify_findings_ledger.py` exits 0 (V12 W77, passing).
- Full pytest suite: failing count ≤ committed baseline.

**V13 success criterion:** drive marker-only ratio for *all* wave tests (not just Critical/High) below 30%.  V12 W73 only gates Critical/High; V13 expands.

---

### 7. Frontend / Product Contract

**Owns:** Frontend production build, API/UI contract drift, dev-bypass code, websocket auth, observable trade-execution UX.

**Replaces:** VV, parts of DDD.

**V12 explicitly excluded frontend per user direction; V13 includes it.**

**Required automated checks:**
- `cd frontend && npm run build -- --mode production` exits 0.
- `frontend/src/components/**` has no hard-coded `admin@example.com` / `admin123` outside dev-only build-flagged paths.
- WebSocket auth uses subprotocol or short-lived ticket, not query-string JWT.

**V13 success criterion:** frontend production build is green; the auditor's flagged ProtectedRoute admin auto-login bypass under `VITE_DEV_BYPASS_AUTH=true` is either removed or build-fenced to dev-only.

---

## What V13 should NOT do

- **No new lens introduction.**  17→7 is the contract.  Adding an 18th would prove the auditor right that this cycle drifts.
- **No "fix the 105 still-open findings parsed from V8-V11" sweep.**  Triage them against the V13 7-lens grid; many will fold into the new tracks.  Most are likely already-fixed-but-unaudited V11-era closures.
- **No expansion of the lint baseline ceiling** without a concurrent shrink commit.  Use `lint_ratchet.py --shrink-baseline` for genuine cleanup.

---

## V13 wave structure proposal

| Wave | Lens | Goal |
|---|---|---|
| W86 | Deploy / Runtime Truth | Build container-vs-host-SHA gate; live-probe artifacts directory |
| W87 | Trading Safety | Fix `test_replay_no_throttle_blocking` (the only currently-xfailed test) |
| W88 | Strategy Expectancy | Hourly log + alert if `last_50_win_rate < 0.30` |
| W89 | Data Integrity | realized_trades reconciliation OR explicit product policy |
| W90 | Auth / RBAC | IDOR cross-user-order test; tighten dev-bypass build flag |
| W91 | Test / CI Quality | Drive marker-only ratio across whole wave-test corpus below 30% |
| W92 | Frontend / Product Contract | Get `npm run build` green; gate the admin-bypass path |
| W93 | V13 synthesis | New synthesis doc; severity-weighted convergence; ledger update |

Each wave: one atomic commit, behavioral tests, zero regressions vs V12 baseline.  V13 baseline locks the V12 final state.

---

## V13 success criteria summary

V13 is "done" when:

1. The 7-lens framework is operating; no new lens has been added.
2. Every still-open V11-era finding parsed from synthesis docs has been triaged against the 7 lenses and either closed-with-behavioral-test, reclassified into a V13 lens, or explicitly retired with reason.
3. Live probes for all 5 deploy/runtime-truth checks pass against a clean container.
4. `test_replay_no_throttle_blocking` is no longer xfailed.
5. Frontend `npm run build` exits 0.
6. Manifest expectancy gate has a configurable floor; an alert fires if the brain crosses it.
7. The V12 audit_gate, lint_ratchet, and findings_ledger verifier all still pass.

If V13 ships another 14-lens prose sweep, the auditor's prediction will have come true.  The honest goal of V13 is convergence, not coverage.
