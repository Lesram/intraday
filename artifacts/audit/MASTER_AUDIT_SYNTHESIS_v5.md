# Platform Deep-Audit — V5 Master Synthesis

**Date:** 2026-05-03
**Round:** v5 (closure regression Z2 + 3 new surfaces S/T/U)
**Branch:** `rc-1.5-curated` @ `d43dbec` (post wave 16 — H-1, H-2, Z-R-3, Z-R-4 closed)
**Production state:** paper trading active; brain gen=168, trades=498, ml_trained=true, healthy

---

## TL;DR

**21 new findings across 3 new surfaces; 0 regressions in waves 12-16.** V5 confirms
the wave 12-16 sweep held cleanly — Track Z2 found 0 production regressions across
30 per-finding verifications and 10 same-bug-class scans. But the new tracks
(S/T/U) surfaced the most operationally significant pattern in the audit cycle so
far:

**Three previously-shipped "fixes" did not actually deliver the behavior they
promised.** Track S found that wave-8c's J-3 fix stopped the crash but routes
every critical alert to `logger.warning` (the `get_running_loop()` call always
raises in worker threads, by definition). Track U found that V4's R-F-4 fix never
shipped — the bypass moved from line 1999 to 2064. Track S found that wave-16d's
H-1 unification works in-process but regresses across WebSocket reconnect gaps.

This is the V4 "audit catches its own work" pattern (V4 Pattern 5) playing out
again, this time with sharper teeth: each "fix" was applied at exactly one of
the necessary sites and the second site was missed, OR the fix changed the
shape of the bug without changing its consequence.

**Severity tally**

| Severity | Z2 | S | T | U | **Total** |
|---|---|---|---|---|---|
| Critical / P0 | 0 | 1 | 0 | 0 | **1** |
| High / P1 | 0 | 3 | 1 | 1 | **5** |
| Medium / P2 | 0 | 3 | 3 | 0 | **6** |
| Low / Latent / Bypass | 0 | 0 | 2 | 7 | **9** |
| **Track total** | **0** | **7** | **6** | **8** | **21** |

---

## Findings by track

### Track Z2 — Closure Regression (0 regressions)

47/47 wave 12-16 fixes verified intact in container. 10 same-bug-class scans clean.
Brain manifest exact match. Curated test suite 254/2 (both pre-existing pre-wave-8).

Sole observation: missing `POST_DEPLOY_BRAIN.txt` in `wave12e/` deploy-bundle dir
(artifact hygiene; the actual P-P0-1/P-P0-2 fix verified via `curl /metrics` →
HTTP 200 with 30 organism_* series).

### Track S — Stress & Failure-Mode (7 issues)

| ID | Severity | Finding |
|---|---|---|
| **S-J3-1** | 🔴 Critical | **Wave-8c J-3 "fix" still drops every alert**. `asyncio.get_running_loop()` raises in worker threads by definition; the except branch always fires and routes the alert to `logger.warning`. Affects `brain_persistence.py:300-316`, `live_engine.py:5740-5757`, `ml_signal.py:395-414`. Brain-save-blocked, feature-drift, and forensic-guard alerts have not been delivered to Slack/PagerDuty since the J-3 "fix" shipped. |
| **S-WS-GAP-1** | 🟠 High | Wave-16d H-1 unification holds in-process; regresses across WS gap. `_gap_fill_after_reconnect` reconciles DB but doesn't re-populate `_terminal_order_ids`. After every WS reconnect, the early-clear path is dead again until the next WS-delivered terminal status. |
| **S-NET-CB-1** | 🟠 High | `CircuitBreaker` class exists in `infra/resilience.py` but is **not wired to broker.submit_order**. The order path has retry-with-backoff but no breaker. If broker is degraded, every tick keeps trying. |
| **S-NET-T-1** | 🟠 High | `TradingClient` and `StockHistoricalDataClient` constructed in `data/alpaca_client.py:159-170` without explicit timeout. Relies on SDK defaults; the SDK's defaults are not documented as bounded. |
| S-OUTBOX-1 | 🟡 Med | N-C-3 lease 300s shorter than worst-case sequential batch (10 events × ~127s = 21 min). Broker idempotency mitigates re-submit, but observability gap remains. |
| S-CLK-1 | 🟡 Med | Drawdown cooldown in `governance.py:141-146` uses wall clock, not monotonic — NTP step shifts cooldown. |
| S-DISK-1 | 🟡 Med | `save_essential_state` writes directly to `brain_dir` (not via `.tmp_save/` swap) — partial state on disk-full. |

**Wave verifications via S:** Q-Q5 cap holds (FIFO confirmed); H-1 holds in-process
but across-gap regression (S-WS-GAP-1); J-3 BROKEN (S-J3-1); N-C-3 lease window
narrower than worst case (S-OUTBOX-1).

### Track T — Numerical / Floating-Point (6 issues)

| ID | Severity | Finding |
|---|---|---|
| **B-T-1** | 🟠 High | `live_engine.py:1336` hard-codes `direction=1.0` in DB-replay reconstruction. **Any short trade gets restored with inverted `actual_return` / `correct_direction`**, poisoning the learner. Dormant under `LONG_ONLY=True` but a one-flag-flip from active. |
| **B-T-2** | 🟡 Med | The `-$634.92` vs CSV-recompute `-$634.90` 2¢ gap is **sum-of-rounded vs round-of-sum asymmetry**: `brain_persistence.py:1276` writes `round(t.pnl, 2)` per trade; `continuous_learner.py:256` accumulates raw float. Banker's rounding adds bias. State and CSV will never reconcile across restart. |
| B-T-3 | 🟡 Med | `int(qty)` on broker positions in 8+ live_engine sites truncates fractional shares to 0, blocking exit. Dormant today (whole-share entries) — trap for any future fractional-share path. |
| B-T-4 | 🟡 Latent | `streaming_data_provider.get_bar_age()` uses raw `time.time()`, escapes `_time_fn` injection. Dormant — replay doesn't exercise streaming today (Track U corroborates). |
| B-T-5 | 🟡 Latent | `walk_forward.py:389` falls back to `std=1.0` for single-pnl windows (synthesizes fake Sharpe) and lacks the `>1e-8` floor that `continuous_learner.py:403` has. |
| B-T-7 | 🟡 Med | `kelly_sizer.py:374-376` `atr_var = max(..., 1e-6)` floor lets near-zero-vol bars saturate Kelly to per-position max instead of refusing to size. |

**Verified safe by T:** IEEE-754 accumulator drift over 10k trades is ~1e-9
(synthetic test), well below the cent. Audit-F-19 family fix (`int(round(...))`)
in place at `governance.py:214`. Lot-tracker stays Decimal end-to-end. `_get_equity()`
reads broker-authoritative values (no accumulation).

### Track U — Replay-Live Divergence (8 bypass sites + R-F-4 still open)

| ID | Severity | Finding |
|---|---|---|
| **U-RF4** | 🟠 High | **R-F-4 from V4 still open** — fix never shipped. Bypass moved from line 1999 to `live_engine.py:2064`. `_bar_ts` drives `bars_held`; in any replay running faster than wall clock, every position's `bars_held` stays at 0, so horizon-timeout, FTF stop-tightening, and min-hold gates all behave wrong. |
| U-1 | 🟡 Bypass | `live_engine.py:1424, 3865` — tick-duration telemetry direct `datetime.now()`. |
| U-2 | 🟡 Bypass | `live_engine.py:4593, 4714` — order idempotency-key date prefix. |
| U-3 | 🟡 Bypass | `regime.py:164, 396, 424, 436, 555, 577` — regime state timestamps every tick. **In replay**, `regime_state.timestamp` reads `2026-05-03` (wall clock) while engine clock says `2024-01-15`. |
| U-4 | 🟡 Bypass | `governance.py:142, 206` — drawdown cooldown wall-clock anchor; consulted every tick via `is_trading_halted`. |
| U-5 | 🟡 Bypass | `governance.py:34` — daily change-budget reset key. |
| U-6 | 🟡 Bypass | `promotion.py:245` — stage min-duration check (and 5 stamp sites). |
| U-7 | 🟡 Bypass | `continuous_learner.py:327, 346` — retrain evaluation event timestamps. |

**Empirical demo from U:** 3-tick synthetic replay on 2024-01-15 bars; injected
clock at engine but `regime_state.timestamp.year == 2026` and
`governance._drawdown_triggered_at.year == 2026` while
`engine._now_fn().year == 2024`. **Bypass deterministically reproduces.**

**Coverage gap:** `_now_fn` / `_time_fn` injection patches only `OrganismLiveEngine`.
`RegimeDetector`, `GovernanceController`, `PromotionController`,
`ContinuousLearner`, `VersionedFeatureStore`, `DriftDetector`, `BrainPersistence`
all bypass.

---

## Cross-track patterns (V5)

### Pattern 1 — **"Fix that didn't actually fix"**

Three V5 findings show a fix that was applied but doesn't deliver the
promised behavior:

- **S-J3-1**: wave-8c's J-3 fix wraps the alert path in a try/except that
  catches `RuntimeError`. But `get_running_loop()` always raises that error
  in worker threads — by definition, since worker threads have no running
  loop. The fix stopped the crash; the alert is silently lost on every
  invocation.
- **U-RF4**: V4's R-F-4 fix never shipped. The bypass moved from line 1999
  to 2064 across post-V4 commits but was never replaced with `self._now_fn()`.
  Track Z2 didn't catch this because R-F-4 wasn't on the wave 12-16 closure list.
- **S-WS-GAP-1**: wave-16d's H-1 unification works in-process. But the gap-fill
  path on WS reconnect doesn't re-populate `_terminal_order_ids`. The fix
  works for the steady-state path; the gap-window path regresses.

**This is V4 Pattern 5 ("audit catches its own work") with sharper teeth.**
Single-site fixes need a sweep at write-time, not at next-audit-time.

**Recommended remediation:** every wave fix should ship with an explicit
"covered sites" list; CI should enforce it. The grep already exists for
some classes (datetime.utcnow → 0 hits); extend to alert-from-worker-thread
and `_now_fn`-bypass classes.

### Pattern 2 — **Injection coverage is partial**

Track U: `_now_fn` injection patches 1 of 5+ tick-reachable components.
Track T B-T-4: `streaming_data_provider.get_bar_age()` escapes the same
injection.

The replay engine assumed "if I monkey-patch the engine's `_now_fn`, the
whole tick is replay-clock-aware." That assumption is wrong; auxiliary
components have their own clocks.

**Recommended remediation:** every component constructed inside a tick
that takes external state (clock, RNG, broker) should accept those as
constructor params. Replay seeds them; live uses defaults.

### Pattern 3 — **Persistence boundary asymmetry**

Track T B-T-2: `cumulative_pnl` written as round-of-sum, CSV written as
sum-of-rounded. After restart, the two never reconcile. This is the same
*shape* of bug as V4 R-F-1 (CSV doesn't carry `is_reconciliation_artifact`)
— state crossing the persistence boundary changes semantics.

**Recommended remediation:** for every cross-boundary state, define a
canonical form and a one-way mapping. Round-trip property test.

### Pattern 4 — **Floor / fallback masks edge case**

Track T B-T-5: `walk_forward` Sharpe falls back to `std=1.0` for single-pnl
windows — synthesizes a fake Sharpe number rather than refusing to grade.
B-T-7: `kelly_sizer.atr_var` floor `1e-6` lets near-zero-vol bars saturate
Kelly to per-position max instead of refusing to size.

In both cases, the floor turns "I don't have enough data" into "here's a
made-up number". The downstream consumer can't distinguish.

**Recommended remediation:** distinguish "insufficient data → return None"
from "computed → return value". Don't synthesize.

### Pattern 5 — **Dormant trap (LONG_ONLY masking)**

Track T B-T-1: short-trade DB reconstruction hard-codes `direction=1.0`.
Trap for any future short-policy enable.

This is similar to V3 M-2..M-8 ("wired but never executed") — code that
appears correct because the path that exercises it is currently disabled.

**Recommended remediation:** assert `LONG_ONLY=True` at the affected
site, or fix the code so it works when LONG_ONLY flips.

---

## Recommended fix waves

### Wave 17 (urgent — production-active or imminent failures)

| Phase | Findings | Effort | Risk |
|---|---|---|---|
| **17a** | S-J3-1 — alert delivery from worker thread (capture main loop reference at engine init) | 1-2 hours | Low (3 file edits + test) |
| **17b** | U-RF4 (R-F-4 finally) + 4 highest-impact U sites (regime.py, governance.py, live_engine.py:2064) | 2-3 hours | Low |
| **17c** | S-WS-GAP-1 — gap-fill must re-populate `_terminal_order_ids` | 1-2 hours | Low |
| **17d** | B-T-2 — pick canonical form for `cumulative_pnl` (round-of-sum) and recompute on load | 1-2 hours | Low |

### Wave 18 (high — correctness)

- B-T-1: short-trade DB reconstruction (assert LONG_ONLY + comment, OR fix)
- S-NET-CB-1: wire CircuitBreaker to broker.submit_order
- S-NET-T-1: explicit timeout on TradingClient / StockHistoricalDataClient
- S-OUTBOX-1: bump claim-lease to 30 minutes (or document the constraint)
- B-T-7: Kelly atr_var floor → refuse-to-size below threshold
- B-T-3: int(qty) → if-fractional-warn-and-skip + comment (or support fractional)

### Wave 19 (medium — cleanup)

- U-1..U-7 (remaining bypass sites)
- B-T-4: streaming_data_provider get_bar_age → use _time_fn
- B-T-5: walk_forward std fallback → return None instead of fake-Sharpe
- S-CLK-1: drawdown cooldown → monotonic
- S-DISK-1: save_essential_state → atomic-rename via tmp dir
- Z2 artifact-hygiene: backfill missing wave12e POST_DEPLOY_BRAIN.txt

---

## What V5 validated about the audit process

1. **Track Z2 (closure regression) is light-weight and high-value.** 0
   regressions across 13 sub-waves of recent fixes. Continue running each
   round.
2. **New-surface tracks keep paying off.** S/T/U found 21 issues across
   surfaces V1-V4 didn't directly probe. Each round's discovery cost is
   roughly proportional to number of tracks; per-track yield is consistent.
3. **The "audit catches its own work" pattern is now load-bearing.**
   Three V5 findings (S-J3-1, U-RF4, S-WS-GAP-1) are fix-didn't-fix bugs.
   The audit cycle is the only defense — without it these would be silent
   in production.
4. **Per-finding closure verification is necessary but not sufficient.**
   Z2 verified each fix is "in the code". S verified the fix actually
   *works* under load. Both are needed.

---

## Final state

```
Production: rc-1.5-curated @ d43dbec, paper trading active, brain coherent
Wave 12-16 closures: 0 regressions across 30 verifications
Tests (curated): 254/2 (both pre-existing pre-wave-8)
v1 findings: 30 (all closed)
v2 findings: 8 (all closed)
v3 findings: 58 (all closed except R-F-4 = U-RF4, now resurfaced)
v4 findings: 52 (all closed except where V5 reopened them)
v5 findings: 21 — open, prioritized for waves 17-19
```

**Total platform findings cycle: 30 + 8 + 58 + 52 + 21 = 169 audit items.**
~148 closed, 21 open (V5).

V5's organism-level finding (Pattern 1, "fix that didn't actually fix") is
the most operationally significant of the cycle so far. The audit process
itself is the safety net for incomplete-fix risk; without it, S-J3-1 alone
would have meant 100% of forensic-guard / brain-save-blocked alerts since
wave-8c shipped were silent.

---

## V6 prompt additions to consider

For the next round (after wave 17-19 ships):

**Track S v6:** add a **fault-injection harness** — programmatically inject
WS disconnect / DB timeout / Redis outage and verify the system's
recorded behavior matches the audit's expectations. Track S is currently
static + synthetic; v6 should be runtime.

**Track U v6:** add a **divergence CI test** — pick a deterministic bar
set, run replay + live-with-injected-clock, diff every intermediate
state, fail CI on any unexpected difference.

**Track T v6:** add **property-based tests** for numerical invariants:
- `cumulative_pnl_state == cumulative_pnl_csv` after roundtrip
- `Sharpe(empty)` is None (not synthesized)
- `Kelly(zero_var)` is None (not max-saturated)

**New tracks v6 might add:**
- **Track V — Telemetry Coverage**: are the post-wave-12e ORGANISM_*
  metrics actually meaningful (incremented at the right moments)? Phantom
  metrics 2.0.
- **Track W — Wave-Cycle Audit**: every fix wave commit, verify (a) the
  fix is present, (b) the same-bug-class is gone elsewhere, (c) a CI
  test prevents regression. The "fix-didn't-fix" pattern motivates this.

---

## Audit reproducibility

```
artifacts/audit/
  AUDIT_PROCESS.md
  PROMPT_LESSONS_v1.md
  FINDINGS_LEDGER.md             # to be updated with V5 entries
  MASTER_AUDIT_SYNTHESIS.md      # v1
  MASTER_AUDIT_SYNTHESIS_v2.md   # v2
  MASTER_AUDIT_SYNTHESIS_v3.md   # v3
  MASTER_AUDIT_SYNTHESIS_v4.md   # v4
  MASTER_AUDIT_SYNTHESIS_v5.md   # this file
  WAVE16_PLAN.md
  prompts/
    v1/  v2/  v3/  v4/  v5/
  v3_reports/
  v4_reports/
  v5_reports/
    track_s_stress.md
    track_t_numerical.md
    track_u_replay_live_divergence.md
    track_z2_closure_regression.md
```
