# V12 Audit Plan — Consolidated from V11 + External Review

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `38d1b74`
**Predecessors:** V1-V11 (49 V11 findings, 5 closed, 44 open) + 1 external review

## Operating constraints (from user)

1. **Scope:** backend / platform / brain / trading. **Frontend explicitly OUT** for V12.
2. **Pristine track:** atomic wave commits with finding IDs. Zero regressions tolerated. Full pytest delta after each wave.
3. **Real behavioral tests, not phantom markers.** Every fix below has a behavioral test path (calls live code, mints state, asserts runtime behavior). No `inspect.getsource` / `"X" in src` as primary assertion for any wave-test in V12.
4. **Make the codebase perfect:** address everything in scope; what we defer is documented + ledgered, not silently dropped.

## What V12 consolidates

### From V11 still-open (44 findings)
- Critical: CCC-2 (already closed wave-68 — promote to verified-live)
- High open: AA5-2, BB5-F1, BB5-F2, CCC-1, DD5-1, DD5-2, DD5-3, DDD-1, HH3-N-1, III-F1, III-F2, TT3-F1, UU3-1, UU3-2 *(+DDD-2 frontend, deferred)*
- Medium/Low: 19+10 = 29 remaining

### From external review (NEW high-impact)
1. **Brain unprofitability** — manifest lacks PnL/Sharpe/winrate/drawdown; trade history shows −$634, 33.7% win across 498 trades. *Critical product gap missed by 11 audits.*
2. **Marker-only test classifier** — auditor measured 85/154 (55.2%) wave tests are source-grep only. The wave-47 JWT failure was symptomatic of the dominant style.
3. **realized_trades=0 vs brain.total_trades=498** — source-of-truth divergence between DB table and brain CSV.
4. **Audit log schema mismatch** — table has `hash_chain` only; independent SQL chain verification blocked.
5. **Drawdown-kill never observed firing** in audit_logs / Slack across 24h window.
6. **Pyramid Layer 2 empirically unproven** — no `pyramid_level` field in trade history.
7. **Deploy verification endpoint absent** — no source SHA / migration head / build time exposed.
8. **Findings ledger absent** — V1-V11 deferral state lives in prose, not machine-readable.
9. **`_live_tick_inner` LOC = 2707** confirmed (vs pre-V8 2510).
10. **God-method watchlist incomplete** — 26 functions >150 LOC not in V8 list.

### Out of scope for V12 (deferred to V13)
- DDD-2 npm audit (frontend)
- Frontend admin auto-login bypass (`ProtectedRoute.tsx`)
- VV frontend contract drift (backend response shape stays)

## Wave structure (V12 waves 70–79)

Each wave: (1) implement, (2) write behavioral test, (3) full pytest delta vs baseline, (4) commit with finding IDs + same-class grep + count, (5) update v12_state.json.

### Wave 70 — Setup & baseline
**Deliverables:**
- `artifacts/audit/v12/V12_PLAN.md` (this doc)
- `artifacts/audit/v12/v12_state.json` (machine-readable findings ledger)
- `artifacts/audit/v12/v12_baseline.json` (pre-V12 expectancy + test classification + pytest count)
- `scripts/ci/classify_wave_tests.py` (marker-only vs behavioral classifier)
- `tests/test_v12_baseline_invariants.py` (locks the baseline so we can prove zero regressions)
**Behavioral test:** classifier runs cleanly, produces JSON, flags a known marker-only test.
**Acceptance:** baseline JSON committed; classifier outputs reproducible; pytest delta = 0.

### Wave 71 — STRATEGY EXPECTANCY GATE [auditor #1]
**Deliverables:**
- Add `total_pnl`, `mean_pnl`, `median_pnl`, `win_rate`, `sharpe_ratio`, `max_drawdown`, `n_trades` fields to `manifest.json` writer
- Compute on every brain save from `trade_history.csv`
- New endpoint: `GET /api/v1/health/strategy` — returns same fields plus last-50-trade window
- Hourly logger in continuous_learner: emit one INFO line with the metrics
- Startup banner in lifespan: print metrics once
**Behavioral tests (`tests/test_v12_strategy_expectancy.py`):**
- Synthetic 100-trade history → save → reload manifest → assert all 7 fields match expected values
- Hit `/health/strategy` against running app (httpx) → assert 200 + all fields
- Force a manifest save with empty history → assert all fields = 0/null with no crash
**Acceptance:** manifest at-rest carries the 7 fields; API endpoint live; startup banner observable; behavioral tests run live code.

### Wave 72 — DD5 strategy root-cause fixes
**DD5-1** chop-min-hold ticks→bars conversion in `live_engine.py:3026-3030`
- Replace `_bars_held = self._tick_count - _entry_tick` with bar-count delta from bar-boundary tracker
**DD5-2** delete `_INVERSE_ETFS_CHOP_SUPPRESSED` (live_engine:4021), route through `is_inverse_etf()` helper
**DD5-3** separate accumulator `symbol_trade_counts_runtime` from promotion-gated `evolved_params.symbol_trade_counts`
**Behavioral tests (`tests/test_v12_dd5_strategy.py`):**
- DD5-1: simulate 30 ticks within one minute (same bar) → assert chop-suppression engages on tick #1, not tick #11
- DD5-2: AST scan of live_engine.py → assert `_INVERSE_ETFS_CHOP_SUPPRESSED` symbol absent; functional test: `is_inverse_etf("RWM")` and `is_inverse_etf("DOG")` both True
- DD5-3: with `_FREEZE_300_TRADES = True`, record 50 synthetic trades → assert runtime counter = 50, evolved_params counter unchanged
**Acceptance:** all 3 root-cause bugs fixed; tests prove behavioral fix, not marker presence.

### Wave 73 — Test discipline (behavioral conversion)
**Convert all Critical/High wave-test files from marker-only to behavioral:**
- Run classifier from wave-70 to enumerate target tests
- For each Critical/High closure (AA5-1, BB5-F4, CCC-2, AAA-F1, AAA-F2, plus older waves), upgrade marker-only assertions to behavioral
- Add `scripts/ci/forbid_marker_only_critical_high.py` — fails CI if a test in `tests/test_wave*_fixes.py` for a Critical/High finding has only source-grep assertions
- Wire into `.github/workflows/ci.yml`
**Behavioral tests:**
- Run classifier on a synthetic marker-only test → assert flagged
- Run classifier on a behavioral test → assert not flagged
- The CI gate itself: behavioral test that runs the CI script against fixtures
**Acceptance:** zero Critical/High wave tests are marker-only; CI gate present.

### Wave 74 — Data integrity
**realized_trades vs brain.total_trades reconciliation**
- Investigate divergence (498 vs 0). Likely: brain CSV is engine's view; realized_trades is DB-side. Reconcile or document.
- If reconcilable: add a backfill migration / runtime sync
- If by-design: add JOIN-able audit query, document
**Audit log schema integrity (BB5-F1 + auditor #4)**
- Add migration: expose `prev_hash` + `current_hash` columns derived from `hash_chain` (or recompute view)
- Add `/api/v1/audit/verify_chain_full` returning row-by-row chain status
**BB5-F1 outbox retention**
- Add prune worker: 30-day retention, runs nightly
- Add /metrics counter for outbox depth
**Behavioral tests:**
- Insert N audit rows, mutate one mid-stream, assert chain endpoint flags the gap
- Insert outbox rows older than retention, run prune, assert old rows gone, recent kept
- realized_trades reconciliation: run sync, assert count matches brain ±tolerance OR documented variance
**Acceptance:** chain verification queryable from SQL OR behavioral endpoint; outbox bounded; trade counts reconciled.

### Wave 75 — Code health (LOC + lint)
**HH3-N-1 _live_tick_inner LOC reduction**
- Extract: pre-trade-gates block, exit-evaluation block, fill-reconciliation block as named methods
- Target: below pre-V8 baseline of 2510 LOC
**God-method watchlist completion**
- Re-run AST scan, file each function >150 LOC as a finding (ledgered in v12_state.json)
- Top offenders extracted: `run_backtest` (373), `save` (209), `_save_brain` (161), `apply_to_learner` (152)
**UU3-1 / UU3-2 lint baseline**
- Fix grandfather typos
- Either get `ruff check` to exit 0 with current rules, or scope rules down with explicit `# noqa` baseline file + CI ratchet
**Behavioral tests:**
- AST line-count test on `_live_tick_inner`: assert <2510
- AST god-method test: assert no NEW function >150 LOC since baseline
- CI lint job: actually exits 0 on a clean checkout
**Acceptance:** _live_tick_inner under target; lint passes locally + CI; ratchet script gates regressions.

### Wave 76 — Operational validation
**Drawdown-kill end-to-end probe**
- Build `tests/test_v12_drawdown_kill_e2e.py`: force equity drop past threshold via test-only injection, assert audit_log row + Slack mock fired + container halted state
**Backup cadence proof**
- Build `tests/test_v12_backup_cadence.py`: simulate 3 hourly tick cycles, assert 3 backup files in organism_brain/backups/
**Pyramid Layer 2 empirical proof**
- Add `pyramid_level` field to `RealizedTrade` and `trade_history.csv` writer
- Build `tests/test_v12_pyramid_layer_reachability.py`: simulate L0→L1→L2 via test fixtures, assert all 3 levels recorded
**Behavioral tests:** the three above are the validation.
**Acceptance:** every operational claim from V11 + auditor has a live behavioral probe.

### Wave 77 — Audit findings ledger
**Build `artifacts/audit/findings_ledger.json`**
- Parse all `MASTER_AUDIT_SYNTHESIS_v*.md` synthesis docs
- One record per V1-V11 finding: `{id, version, severity, title, status, wave_closed, behavioral_test_path, deferral_reason}`
- Reconcile against per-track reports
**Build `artifacts/audit/findings_ledger.md`** (human-readable rollup)
**Build verification script:** `scripts/ci/verify_findings_ledger.py`
- Asserts every "closed" finding has a non-empty `behavioral_test_path`
- Asserts every "deferred" has a non-empty `deferral_reason`
- Detects orphan IDs (in commit message but not in ledger)
**Behavioral tests:**
- Parser unit test on a synthesis fixture
- Verification script run against fixture missing a behavioral_test_path → assert exits 1
**Acceptance:** all V1-V11 findings ledgered; verification script wired into CI.

### Wave 78 — Deploy verification (DD-DEPLOY lens)
**Add `/api/v1/health/deploy` endpoint**
- Returns: source SHA, migration head, build time, runtime config hash, container hostname, image SHA
**Startup log emits same line**
**Build `scripts/ci/check_deploy_state.py`** — comparing host SHA vs container SHA
**Behavioral tests:**
- Hit endpoint, assert all 6 fields present + non-empty
- Force SHA mismatch fixture, assert `check_deploy_state.py` exits 1
**Acceptance:** deploy state queryable + CI-checkable.

### Wave 79 — V12 synthesis
**Build `artifacts/audit/MASTER_AUDIT_SYNTHESIS_v12.md`**
- Every V12 wave: deliverables + acceptance status + behavioral test path
- Severity-weighted convergence: V8=148, V9=129, V10=105, V11=158, **V12=??**
- Behavioral-test ratio: pre-V12 = 55.2% marker-only; post-V12 target = 0% for Critical/High
- Pre-V12 vs post-V12 expectancy snapshot
- Deferral list (with reasons + V13 wave assignments)
**Update memory + V12 handoff**
**Acceptance:** clean synthesis; deferred list machine-tracked; ready for next external auditor pass.

## Behavioral test commitments

**No V12 wave-test will rely on `inspect.getsource(...)` or `"X" in src` as the only assertion.**

Acceptable patterns:
- Mint real state (token, DB row, brain save), assert observed effect
- Hit live endpoints with httpx + assert response codes/shapes
- Run AST scans (these are structural, but assert on PARSED structure not string presence — different from marker-grep)
- Mock at module boundary, assert the function-under-test's behavior

Marker assertions allowed only as SECONDARY signal alongside behavioral.

## Per-wave commit / verification protocol

After each wave:
1. Run `./venv/bin/python -m pytest tests/ --timeout=15 -q --tb=no > /tmp/v12_post_waveNN.out`
2. Diff against baseline: `comm -13 baseline_fails.txt postwave_fails.txt` → must be empty
3. Atomic commit: `fix(audit-waveNN): V12 <track> — <finding-IDs> + behavioral tests`
4. Update `artifacts/audit/v12/v12_state.json` (status=closed for finding IDs in this wave)
5. Touch `MEMORY.md` if a durable lesson emerged

## Scope discipline

If during execution we discover:
- An issue that fits V12 scope → file as new V12 finding, ledger it, address in current/next wave
- An issue that's frontend → ledger only, defer to V13
- An issue that breaks something → STOP, fix, do not continue

## Success criteria for V12

V12 is "done" when:
- Every Critical/High V11 finding is either CLOSED with behavioral test, or explicitly DEFERRED with reason in ledger
- Strategy expectancy is queryable + logged (closes auditor #1)
- All Critical/High wave tests are behavioral, none marker-only
- Full pytest delta vs V12 baseline = zero regressions
- Findings ledger machine-tracked
- `_live_tick_inner` <= pre-V8 baseline LOC
- CI lint exits 0
- Drawdown-kill, backup cadence, pyramid L2 each have a behavioral probe that runs in CI
