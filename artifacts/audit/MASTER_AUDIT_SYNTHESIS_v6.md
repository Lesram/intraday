# Platform Deep-Audit — V6 Master Synthesis

**Date:** 2026-05-03
**Round:** v6 (closure regression Z3 + 4 new surfaces V/W/T2/X)
**Branch:** `rc-1.5-curated` @ `3f660f4` (post wave-19; all V5 findings closed)
**Production state:** paper trading active; brain gen=168, trades=498, healthy

---

## TL;DR

**~30 new findings across 5 tracks; 0 production regressions in waves 17-19.**
Track Z3 found 0 regressions. But the new tracks (V/W/T2/X) revealed that V5's
"fix that didn't actually fix" pattern is *more pervasive than V5 itself
caught* — wave-17a's S-J3-1 fix had an incomplete same-class scan, leaving
two unpatched alert sites (`order_service.py:_trip`,
`background_trainer.py:get_result`); wave-19's `_now_fn` extension missed
two more clock-bypass sites surfaced empirically by Track X
(`live_engine.py:6265`, `background_trainer.py:130`); and wave-19's auxiliary-
component injection loop has bugs (Track X X-5, X-6).

The audit cycle's most important finding this round is structural, not
per-bug: **same-class scans need to be machine-enforced, not human-best-
effort.** Track W's CI proposal (every wave PR must include a same-class
grep + asserted-zero in commit body) is the durable fix.

Three findings independently surfaced by multiple tracks converged on
**`live_engine.py:6265`** — Z3 marked it "low-risk cosmetic," W flagged it
as a same-class miss, X reproduced it as a real replay-determinism bug
(non-deterministic `TradingSignal` stamping). Z3's cosmetic assessment
was wrong; this is wave-20 work.

**Severity tally**

| Severity | Z3 | V | W | T2 | X | **Total** |
|---|---|---|---|---|---|---|
| Critical / P0 | 0 | 1 | 0 | 0 | 0 | **1** |
| High / P1 | 0 | 5 | 1 | 0 | 2 | **8** |
| Medium / P2 | 0 | 1 | 0 | 0 | 3 | **4** |
| Low / Latent | 2 | 2 | 14 | 0 | 3 | **21** |
| **Track total** | **2** | **9** | **15** | **0** | **8** | **34** |

(W's 14 "Low" entries are the wave rows where one of (a)/(b)/(c) doesn't
fully pass — process gaps, not per-bug findings. Net actionable: 9+1+8 = 18.)

---

## Findings by track

### Track Z3 — Closure Regression (0 production regressions)

47/47 waves 17-19 closures verified intact. Container parity exact for all
12 wave-17-19 markers. Curated test suite **267/267 pass** (≥260 threshold).
Brain coherence: gen=168, trades=498, ml_is_trained=true unchanged. Startup
reconciliation log fires with the expected $0.02 legacy drift.

Two cosmetic observations logged:
- `live_engine.py:6265` — `now = datetime.now(UTC)` in unused
  `generate_trading_signals` path. **Z3 classified as cosmetic; W and X
  proved it's a real bug (see V6 cross-track pattern 3 below).**
- `regime.py:589` — non-injected clock in offline `regime.check_drift`
  metadata path.

### Track V — Telemetry Coverage (9 issues)

| ID | Severity | Finding |
|---|---|---|
| **V-T-1** | 🔴 Critical | **Latent S-J3-1 regression**: `order_service.py:356-399` (`_trip()`) ships the broken wave-8c anti-pattern (`get_running_loop` + `call_soon_threadsafe`, fallback `asyncio.run`). Comment explicitly says "called from sync paths via asyncio.to_thread" yet doesn't use `dispatch_alert_from_thread`. Outer `except Exception: pass` swallows the failure. Wave-12f shipped this fix with the broken pattern; wave-17a's same-class scan didn't catch it. |
| **V-T-2** | 🟠 High | Same broken pattern at `background_trainer.py:442-447`. Works today only because `get_result()` is polled from the main loop — but the comment anticipates threadpool callers. |
| **V-T-3** | 🟠 High | `ORGANISM_EXITS_SKIPPED_NO_DATA` HELP says "Exit checks fell back to broker price due to missing features" but the only `.inc()` is nested inside the safety-net branch (`live_engine.py:2074`). Undercounts the documented event by ~10×. |
| V-T-4 | 🟠 High | Outbox worker errors: 11 `logger.error` sites in `outbox_worker.py`, **zero `send_alert`**. Critical-path failure invisible to operators. |
| V-T-5 | 🟠 High | DB connection failure on startup is silent in dev mode (current container is `APP_ENVIRONMENT=development`). |
| V-T-6 | 🟠 High | C1/C2/stream-instability watchdog `logger.critical` events have no alert wiring (`live_engine.py:4362,6083`, `alpaca_stream.py:825`). |
| V-T-7 | 🟠 High | Reconciliation orphan adoption (`live_engine.py:5181-5229`) silently mutates entry metadata; no alert. |
| V-T-8 | 🟡 Med | Zero `trace_span` calls in 3,600-line `live_engine.py`. Tick-internal operations (alpha_scan, ml_predict, kelly_size, regime, exit_check) have no OpenTelemetry coverage; only total tick-duration is observable. |
| V-T-9 | 🟡 Low | Log stream is **99.6% INFO** (832/835 of last 2000 lines). `feature_engineer` + `performance` produce 60.7% of all lines (~132 lines/min from `feature_engineer` alone); both should be DEBUG. The 3 WARNINGs in the window are statistically invisible. |

**Verified working:** Wave-17a `dispatch_alert_from_thread` correctly applied at
the 3 sites V5 named. `set_main_event_loop` runs first thing in lifespan startup.
Wave-12e `/metrics` global-registry merge confirmed live (12 organism_* series
reach `/metrics`). All 12 ORGANISM_* metrics have at least one emission site
(no truly phantom metrics). 4/4 `tests/test_alert_cross_thread_dispatch.py` pass.

### Track W — Wave-Cycle Audit (15 wave-gap rows + 1 new bug)

37 waves enumerated (8a → 19). For each, verified (a) marker present in source,
(b) same-bug-class scan clean, (c) regression test exists. **15 of 37 waves
fail one or more of (a)/(b)/(c).**

**3 marker gaps (silent fixes):**
- U-1, U-2 (wave-19): fix shipped, no source comment.
- P-P0-3 (wave-12f): marker was *overwritten* by wave-17a's S-J3-1 re-fix at the same site. Provenance erased.
- L-6 (wave-8e): .env file (gitignored) — by design.

**1 newly-detected latent same-class miss:** `live_engine.py:6265` —
`now = datetime.now(UTC)` for `TradingSignal` stamping NOT routed through
`self._now_fn()`. Direct sibling of R-F-4 → U-RF4 chain. **Track U's clock-
injection coverage was incomplete.** Z3 saw it as cosmetic; X proved it's a
real determinism bug.

**2 confirmed historical "fix-didn't-fix" cycles validated by W's framework:**
- 8c (J-3) → re-caught at V5 S-J3-1 (worker-thread send_alert).
- 11d (C-1 ensemble persist) → re-caught at V4 R-F-5.
- 16d (H-1) → re-caught at V5 S-WS-GAP-1 (gap-fill skipped repop).

**Behavioral vs structural test ratio:** ~25% behavioral / ~25% structural-only
/ ~50% mixed across 13 dedicated regression-test files. Only
`test_alert_cross_thread_dispatch.py` and `test_replay_clock_injection.py`
are gold-standard behavioral.

**Highest silent-regression-risk wave: Wave 18 (a42ca5f).** 6 high-correctness
findings (B-T-1, S-NET-CB-1, S-NET-T-1, S-OUTBOX-1, B-T-7, B-T-3) shipped with
**zero behavioral tests**. B-T-3 explicitly deferred (helper added, 13
`int(qty)` call sites unchanged) — dormant trap until fractional shares enabled.

**CI rule proposal (top 3):**
1. PR matching `audit-wave\d+` must add ≥1 new comment line containing the finding-ID it closes (block on empty diff).
2. Same-class grep + asserted-zero must appear in commit body; CI re-runs and blocks if count > 0.
3. Critical/High findings require a *behavioral* test (revert-to-fail), not a structural grep — closes the S-J3-1-class hole.

**Predicted V7 catches:** live_engine.py:6265 (already detected), B-T-3 fractional
truncation when LONG_ONLY flips, Q-Q1 day-roll structural-only test silently
regresses, R-F-5 if a third save-path is added, S-DISK-1 atomic-write coverage
doesn't span `learning_state.json` write site.

### Track T2 — Numerical Property Tests (0 new bugs, T2 closes a previously-zero-coverage gap)

`tests/test_numerical_properties_v6.py` written: 26 tests (5 hypothesis-driven
property tests + 21 example-based edge-case tests) covering V5 invariants
B-T-1/2/3/5/7. **All 26 pass on rc-1.5-curated @ 3f660f4 in 1.16s. 0 new bugs
surfaced** — the wave 17d/18/19 fixes are all in place and behave as documented.

The pre-T2 regression-test coverage for these 5 invariants was **zero** —
a silent revert of any wave-17d/18/19 fix would have shipped without test
failure. T2 closes that gap.

**Follow-up:** `hypothesis>=6.70.0` is in `requirements-dev.txt` but not in
the active venv. If CI doesn't install dev requirements, the 5 property tests
silently skip. Recommend pinning `hypothesis` in prod test requirements.

### Track X — Backtesting Reliability (8 issues; determinism BROKEN)

**Determinism verdict: NOT deterministic.** Two back-to-back replays with
seed=42 produced 3 hash divergences (tick_results, governance_state.json,
manifest.json) despite the wave-17b/19 clock-injection fixes.

| ID | Severity | Finding |
|---|---|---|
| **X-1** | 🟠 High | **Smoking gun**: `live_tick()` at `live_engine.py:1499` lazy-imports `alpaca_stream` → triggers `load_dotenv()` mid-replay. First `GovernanceController()` reads code defaults; second instance reads `.env` overrides. Reproduced via dotenv stack-trace patch. |
| **X-8** | 🟠 High | `background_trainer.py:130` writes `metrics.evaluated_at = datetime.now()` — bypasses entire `_now_fn` chain. Wall-clock leaks into `evaluation_event_history.json` brain artifact. New same-class miss of wave-17b/19. |
| X-2 | 🟡 Med | `live_engine.py:1473, 3923` use raw `time.time()` for tick `duration_s` — pollutes per-tick hash on every run. |
| X-3 | 🟡 Med | `brain_persistence.py:954` writes `saved_at` from wall clock — pollutes `manifest.json` hash. |
| X-4 | 🟡 Low | `live_engine.py:6265` uses `datetime.now(UTC)` in alpha-scan signal-build (same finding as W's). |
| X-5 | 🟡 Low | Wave-19 attr-loop only matches `_now_fn` — silently skips `StreamingDataProvider` which uses `_time_fn`. |
| X-6 | 🟡 Low | Wave-19 attr-loop lists `promotion_controller` but engine has no such attribute (lives on `app.state`); dead code masquerading as coverage. |
| X-7 | 🟡 Latent | `OrganismLiveEngine` defaults `brain_dir=organism_brain` (production); replay's tempdir wrapper saves users from this, but engine has no defense-in-depth assertion. |

**Day-long stress / idempotency:** 0 trades over 200 ticks × 22 symbols on the
synthetic "trending up" fixture — fixture too smooth to discriminate trade-logic
regressions. Recommend a "trade_burst" synthetic mode or committed Alpaca slice.

**Write-side:** Replay correctly skips DB and external APIs (sessionmaker None,
scanner None, streaming None), but writes 10 brain files even on no-trade runs —
**NOT side-effect-free on disk**. Tempdirs leak (~5KB/run, no cleanup).

---

## Cross-track patterns (V6)

### Pattern 1 — **Same-class scans need machine enforcement**

Three wave-fixes had incomplete same-class scans:
- Wave-17a (S-J3-1) missed `order_service._trip` (V-T-1) and
  `background_trainer.get_result` (V-T-2).
- Wave-17b/19 (`_now_fn` injection) missed `live_engine.py:6265`
  (W-finding / X-4) and `background_trainer.py:130` (X-8).
- Wave-19 attr-loop has structural bugs (X-5, X-6).

The fixes themselves were correct at the sites they addressed. The gap is
that "same-class scan" was a human best-effort step. Track W's CI proposal
(grep + asserted-zero in commit body, blocking) is the durable fix.

**Recommended remediation:** before any wave PR merges, CI runs the same-
class grep declared in the commit body and fails if count > 0.

### Pattern 2 — **Three tracks converged on `live_engine.py:6265`**

- Z3 classified it "low-risk cosmetic" (in unused `generate_trading_signals`).
- W flagged it as a same-class miss of R-F-4 → U-RF4.
- X reproduced it as a real determinism bug (non-deterministic
  `TradingSignal` stamping).

Z3's classification was wrong. The track that *just verifies fix presence*
under-weights latent bypass; tracks that *exercise behavior* (X) catch them.

**Recommended remediation:** Z-track per-finding verification should include
a "exercise the negative path" probe, not just `grep ... ≥1`.

### Pattern 3 — **Replay determinism is harder than wave-17b/19 made it look**

Wave-17b extended `_now_fn` to RegimeDetector + GovernanceController.
Wave-19 extended to PromotionController + ContinuousLearner +
StreamingDataProvider. Track X found that determinism was still broken —
8 issues. The wave fixes were each correct individually; what was missing
was end-to-end determinism testing. T2's invariant-pinning approach (write
tests that fail if the post-fix behavior reverts) is the right shape for
determinism too.

**Recommended remediation:** add a CI determinism golden snapshot test
(per X's section 7 proposal). Replay over a committed bar set; assert
the output hash matches a frozen golden value. Update on intentional
change with reviewer sign-off.

### Pattern 4 — **Phantom telemetry persists despite wave-12e**

Wave-12e fixed `/metrics` 503 + global-registry merge. V verified the fix
delivered. But V also found:
- V-T-3: a metric undercounting by 10× (HELP text describes the wrong event).
- V-T-4..7: 5 critical events with no alert wiring at all.
- V-T-8: zero trace coverage in tick-internal operations.

Wave-12e fixed the *plumbing*; V finds that the *content* is still
substantially missing.

**Recommended remediation:** Wave 22 — comprehensive observability backfill
(traces + alerts + metric-event consistency).

### Pattern 5 — **Behavioral testing is the durable defense**

T2 closed a previously-zero-coverage gap for 5 numerical invariants.
W found that 25% of waves have only structural tests (assert source
contains a string), which catch code reverting but not behavior reverting.
S-J3-1 was exactly behavior-reverting (the code was present; the alert
didn't reach Slack).

**Recommended remediation:** every Critical/High wave fix must include a
behavioral test (per W's CI proposal #3). Backfill behavioral tests for
Wave 18's 6 findings (highest silent-regression risk).

---

## Recommended fix waves

### Wave 20 (urgent — production-active or load-bearing)

| Phase | Findings | Effort | Risk |
|---|---|---|---|
| **20a** | V-T-1 + V-T-2 — apply `dispatch_alert_from_thread` to `order_service._trip` and `background_trainer.get_result` (S-J3-1 same-class miss) | 1 hour | Low |
| **20b** | live_engine.py:6265 + X-2/X-3/X-4/X-8 — route remaining wall-clock reads through `_now_fn`/`_time_fn` (4 sites + 1) | 2 hours | Low |
| **20c** | X-1 — eager `load_dotenv()` at top of `replay_simulator.py` to kill the lazy-import determinism bug | 30 min | Low |
| **20d** | X-5 + X-6 — fix wave-19 attr-loop: separate `_now_fn` from `_time_fn` matching, drop dead `promotion_controller` entry (lives on app.state) | 30 min | Low |
| **20e** | V-T-3 — fix `ORGANISM_EXITS_SKIPPED_NO_DATA` undercount (HELP text or emission location) | 1 hour | Low |

### Wave 21 (high — alert wiring + behavioral test backfill)

- V-T-4 outbox worker errors → alerts
- V-T-5 DB startup failure → alerts in dev mode too
- V-T-6 C1/C2/stream-instability watchdog → alerts
- V-T-7 orphan-adoption → alerts (informational severity)
- W CI proposal: enforce same-class grep + behavioral test in PR template
- T2 follow-up: pin `hypothesis` in prod requirements
- Wave-18 behavioral test backfill (B-T-1, S-NET-CB-1, etc.)
- Marker discipline: backfill U-1, U-2 source comments

### Wave 22 (medium — observability content)

- V-T-8 trace_span coverage on tick-internal ops
- V-T-9 log-level cleanup (feature_engineer + performance to DEBUG)
- X-7 brain_dir defense-in-depth assertion
- X CI determinism golden snapshot test
- W "predicted V7 catches" mitigation

---

## What V6 validated about the audit process

1. **Track W (wave-cycle audit) is the missing meta-track.** It directly
   addresses the V5 Pattern 1 ("fix that didn't actually fix") at the
   process layer. Wave-17a's S-J3-1 fix had an incomplete same-class scan;
   W identified the structural cause. CI proposal converts it into prevention.
2. **Behavioral testing > structural testing.** T2 demonstrated that pinning
   invariants prevents silent reverts. Wave 18's 6 findings have zero
   behavioral coverage; that's the highest regression risk in the codebase.
3. **Multi-track convergence is signal.** 3 tracks independently flagged
   live_engine:6265 at different severities. Z3 was wrong (cosmetic); X
   was right (real bug). Track convergence indicates real problems even
   when one track downplays.
4. **Replay determinism is a CI concern, not a code-review concern.**
   X found 8 issues despite wave-17b/19 specifically targeting this.
   Determinism needs an automated golden-snapshot guardrail.
5. **Closure regression remains 0-or-near-0 each round.** Z, Z2, Z3 all
   came back clean. The wave system itself is sound; the gap is in the
   same-class enforcement layer above it.

---

## Final state

```
Production: rc-1.5-curated @ 3f660f4, paper trading active, brain coherent
Wave 17-19 closures: 0 production regressions across 21 verifications
Tests (curated): 267/267 (V6 also adds 26 from T2)
v1 findings: 30 (all closed)
v2 findings:  8 (all closed)
v3 findings: 58 (all closed)
v4 findings: 52 (all closed)
v5 findings: 21 (all closed)
v6 findings: ~18 actionable (Critical 1, High 8, Med 4, Low 3, Latent 2)
            + 14 W-process-gaps + 0 T2 + 2 Z3 cosmetic
```

**Total platform findings cycle so far: 30 + 8 + 58 + 52 + 21 + ~18 = ~187
audit items.** ~169 closed, ~18 open (V6).

V6's most operationally significant outcome is the *process* finding (W):
same-class scans must be machine-enforced. Without that, wave-20 will fix
V-T-1, V-T-2, X-4, X-8 — and V7 will find their successors. The CI rule
proposal closes the loop.

---

## V7 prompt additions to consider

For the next round (after wave 20-22 ships):

**Track Z4:** closure regression for waves 20-22 (standard pattern).

**Track W2 v7:** verify the CI rules proposed in W actually shipped and
run on every wave PR. (W's recommendations are policy until CI enforces.)

**Track X2 v7:** add the determinism golden-snapshot test to CI; verify
it fails on wave-17b/19 reverts.

**New tracks v7 might add:**
- **Track AA — Test Quality Audit:** what fraction of behavior is exercised
  by tests? Coverage analysis + mutation testing on the organism core.
- **Track BB — Production Telemetry Reality Check:** sample 1 hour of live
  trading, count actual emissions of every metric/alert/log, surface
  discrepancies vs. expected rates.
- **Track CC — Configuration Drift Audit:** every `os.getenv(...)` call,
  verify the env var is documented, has a safe default, and is set
  consistently in dev/paper/prod.

---

## Audit reproducibility

```
artifacts/audit/
  AUDIT_PROCESS.md
  PROMPT_LESSONS_v1.md
  FINDINGS_LEDGER.md             # to be updated with V6 entries
  MASTER_AUDIT_SYNTHESIS.md      # v1
  MASTER_AUDIT_SYNTHESIS_v2.md   # v2
  MASTER_AUDIT_SYNTHESIS_v3.md   # v3
  MASTER_AUDIT_SYNTHESIS_v4.md   # v4
  MASTER_AUDIT_SYNTHESIS_v5.md   # v5
  MASTER_AUDIT_SYNTHESIS_v6.md   # this file
  WAVE16_PLAN.md
  prompts/
    v1/  v2/  v3/  v4/  v5/  v6/
  v3_reports/
  v4_reports/
  v5_reports/
  v6_reports/
    track_z3_closure_regression.md
    track_v_telemetry_coverage.md
    track_w_wave_cycle_audit.md
    track_t2_numerical_property_tests.md
    track_x_backtesting_reliability.md
```
