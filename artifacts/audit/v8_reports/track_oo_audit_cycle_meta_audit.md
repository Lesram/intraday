# Track OO — Audit-Cycle Meta-Audit (V8)

**Date:** 2026-05-03
**Branch:** `rc-1.5-curated` @ `5bc4046`
**Scope:** the audit cycle itself, V1-V7 (~278 cumulative findings, 49 wave commits, 22 audit reports across 7 rounds).

This track does not look at platform code. It looks at the *cycle's lens*:
which surfaces the cycle has never probed, where finding-class budget has
been spent, where scans have caught things and where they haven't, and where
the meta-process (commit hygiene, finding-tracking) is leaking signal.

---

## Section 1 — Untested-domain list (what V1-V7 NEVER tested)

For each domain, "tested" means: a track instrumented or empirically
exercised the behavior, not merely mentioned the keyword in passing.

| Domain | V1-V7 status | Severity if user-facing |
|---|---|---|
| **Chaos engineering** (kill -9 the api container mid-trade; cut Postgres mid-fill; SIGKILL Redis during outbox dispatch) | NEVER tested. Track S did *static* failure-mode analysis (timeouts, missing breakers) and Track G did *post-mortem* on reconciliation incidents, but no track has run runtime kill/partition/disk-full injection against the live container. V5 prompt for V6 explicitly proposed "fault-injection harness" — not shipped. | CRITICAL — paper running ~$111k. The Track G v1 / V4-RF series of reconciliation bugs all surfaced *because* operators happened to restart at the wrong moment; there is no systematic test for that class. |
| **Load / concurrency under burst** (1000 concurrent WS messages; 100 parallel /api/* requests during live tick; alert dispatcher under flood) | NEVER tested. Track J found static concurrency bugs (event-loop blocks, fire-and-forget GC); Track Q sampled live RSS/FDs at idle. No track injected concurrent load. | HIGH — most observability findings (V-T-3 undercount, P-P0-2 phantom metrics) would only show real cost under load. |
| **Timezone edge cases** (DST spring-forward/fall-back at 02:00 ET, leap second, holiday-on-Saturday) | PARTIALLY. Track K-7 noted "holiday/early-close set overlap on Saturday-July-4" as untested edge. The only DST mention in any test (`test_adversarial_inputs_v7.py`) is a *comment* asserting DST-immunity via inspection — no actual transition is exercised. No leap-second test. No clock-step / NTP-jump test (S-CLK-1 was static-flagged, never run). | HIGH — daily-loss / drawdown / governance-cooldown all anchor on wall clock; an untested DST roll could leave a halt on for an extra hour or skip the daily reset entirely. |
| **PnL accounting under wash sales / dividend ex-dates / corporate actions** | NEVER tested. Track BB BUG-8 found `LotTracker` was dead in production and `realized_trades` empty — but neither V1-V7 nor the existing test suite covers wash-sale rules, dividend reinvestment, ex-date PnL, stock splits, or symbol delisting. `tests/test_pyramid_cost_basis.py` exercises lot accounting under simple closes only. | HIGH for any future live cutover. SH/PSQ inverse ETFs distribute periodically; QQQ pays dividends. None tested. |
| **Alpaca API failure modes — 5xx / 429 / malformed-JSON / partial-WS** | NEAR-ZERO. The only Alpaca failure tested is a generic `subscribe_quotes` exception (`test_market_data_service.py`). No 429-rate-limit replay, no truncated-WS-frame replay, no JSON-with-NaN, no Alpaca downtime simulation. Track FF-3 (WS null filled_qty) is the *only* adversarial input test that actually fires through the WS path. | CRITICAL — the entire trading path is one Alpaca degradation away from a state divergence; none of the audit cycle has empirically probed how the system behaves when the broker misbehaves. |
| **Frontend ↔ backend contract drift** | STATIC ONLY. Track O found 7 issues by reading TS interfaces vs Pydantic models. No automated schema-diff (schemathesis / openapi-diff / pydantic-to-typescript) runs in CI; every drift is one-shot human work, repeated every audit. | MEDIUM — kill-switch banner won't toggle (V4 O-3) is exactly the consequence; without automation, recurrence is guaranteed. |
| **Observability failure** (Prometheus down → does the engine crash? Jaeger blocked → does tick latency double? log-shipper full → does the disk fill?) | NEVER tested. Wave-12e fixed the registry split-brain, but no track has tested what happens when the *consumer* of telemetry is broken/missing. | MEDIUM — silent degradation + cascading failure risk. |
| **Migration rollback / round-trip** | NEVER tested. The repo has `alembic.ini` but **no `alembic/` directory exists**. ORM changes ship as raw schema edits (BB BUG-1/2/3, BB BUG-6, N-H-1 are all symptoms). No track has applied → rolled back → re-applied a migration. | HIGH — schema drift between ORM and DB is already a known finding class (N-H-1, BB BUG-6), and there is no rollback story. |
| **Multi-day brain coherence** (restart 5 times in 5 days, does state stay invariant? gen counter monotonic? trade history append-only across restarts?) | NEVER tested as a sequence. Z, Z2, Z3, Z4 each verify *one* closure regression but not *cumulative* coherence over multiple operational days. R-F-1 (CSV-erasure of `is_reconciliation_artifact`) is exactly the bug class a multi-day soak would have caught. | HIGH — the cycle's longest-running latent bug (R-F-1 erasure) was a multi-day-coherence bug. |

**Eight domains are wholly untested. Two are barely tested. The cycle's
278 findings have been generated entirely by static + single-tick + post-
mortem techniques.** Every "fix that didn't actually fix" finding (V5
Pattern 1) is a case where a static check passed but a *runtime* test
would have caught the gap.

---

## Section 2 — Finding-class histogram + under-invested classes

Counted from the 7 master synthesis docs and FINDINGS_LEDGER. Approximations
(some findings span classes).

| Class | V1 | V2 | V3 | V4 | V5 | V6 | V7 | **Total** | Investment |
|---|---|---|---|---|---|---|---|---|---|
| Strategy logic / signal correctness | 8 | 3 | 0 | 0 | 0 | 0 | 11 | **22** | UNEVEN — 8 in V1, then NOTHING for 5 rounds, then 11 in V7 (DD). Most sensitive class on a trading platform; barely audited. |
| Data integrity / persistence boundary | 4 | 5 | 6 | 12 | 3 | 1 | 11 | **42** | well-covered |
| State persistence / restore | 6 | 5 | 6 | 8 | 0 | 0 | 0 | **25** | well-covered (V1-V4) |
| Concurrency / async / event-loop | 0 | 0 | 7 | 4 | 1 | 0 | 0 | **12** | adequate |
| Time / clock / replay-determinism | 1 | 0 | 9 | 2 | 9 | 8 | 0 | **29** | OVER-AUDITED — 5 rounds straight. Diminishing returns since V5; V6 X track found 8 issues but mostly cosmetic-class. |
| Security / auth | 0 | 0 | 3 | 0 | 0 | 0 | 14 | **17** | UNEVEN — 0 for 5 rounds, then 14 in V7 AA. AA-C-1 (public JWT default) had been live for weeks. |
| API surface / FE-BE contract | 0 | 0 | 12 | 7 | 0 | 0 | 0 | **19** | adequate |
| Architecture / structure | 0 | 0 | 0 | 0 | 0 | 0 | 10 | **10** | first-look in V7 |
| Observability / telemetry | 0 | 0 | 0 | 15 | 0 | 9 | 0 | **24** | adequate |
| Performance / resource | 0 | 0 | 0 | 8 | 0 | 0 | 0 | **8** | UNDER — single track-Q, no follow-up. No memory-growth-over-days, no FD-leak-over-days, no DB-pool-exhaustion-under-burst. |
| Test quality / coverage | 0 | 0 | 1 | 0 | 0 | 0 | proc | **~1** | UNDER — V7 CC produced a coverage report (26% line cov on backend/, 21% on live_engine.py) but found 0 *bugs*. The 13 deterministic regressions CC did surface are not counted as findings in the cycle. |
| Documentation drift | 0 | 0 | 0 | 0 | 0 | 0 | 11 | **11** | first-look in V7 GG; recurrence guaranteed by no automation |
| Dead code / reachability | 0 | 0 | 13 | 0 | 0 | 0 | 0 | **13** | UNDER (until V8 NN) — single round; V7 BB BUG-8 (LotTracker dead) shows the class is still active. |
| Numerical / floating-point | 0 | 0 | 0 | 0 | 6 | 0 | 0 | **6** | thin |
| Adversarial / fuzz | 0 | 0 | 0 | 0 | 0 | 0 | 11 | **11** | first-look in V7 |
| Process / wave-cycle audit | 0 | 0 | 0 | 0 | 0 | 15 | 14 | **29** | adequate |
| **CHAOS / fault-injection runtime** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **NEVER AUDITED** |
| **Load / burst** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **NEVER AUDITED** |
| **Migration round-trip** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **NEVER AUDITED** |

**Most under-invested live classes (in order):**
1. Chaos / runtime fault-injection (0 of 278) — biggest lens-gap.
2. Load / burst (0 of 278).
3. Migration round-trip (0 of 278).
4. Test quality bugs (≤1 of 278; CC produced *process* output, not findings).
5. Performance / resource over time (8 of 278; single-pass).
6. Strategy logic 5-round drought between V1 and V7 (22 total but bursty).

**Most over-invested classes:**
1. Time / clock / replay-determinism (29; diminishing yield since V5).
2. Process / wave-cycle audit (29; useful but recursive — auditing the auditors is now structurally net-positive only if the resulting CI rules ship and stick, which V7 W2 showed is not happening reliably).

---

## Section 3 — Discovery-latency stats

Compressed-time caveat: this entire cycle ran 2026-05-01 through 2026-05-03,
so wall-clock latency between flag and fix is hours, not days. The
meaningful metric is *audit-rounds elapsed* between first flag and final
fix.

| Finding | First flagged | First "fixed" | Re-flagged? | Final closure |
|---|---|---|---|---|
| `lifespan.shutdown` no force_save | V1 | Phase 1 (V1-fix) | No | closed-v2 |
| Reconciliation pollution | V1 #2 | Phase 4 (V1-fix) | YES — V2 GAP-3..5; V4 R-F-1, R-F-6, R-F-7, R-F-8 | closed wave-13ad (V4) |
| `_now_fn` injection chain | V3 R-F-4 | not shipped V3-V4 | YES — V5 U-RF4 (re-flagged after fix didn't ship); V6 X-1, X-4, X-8 | closed wave-20b (V6) |
| J-3 alert dispatch | V3 J-3 | wave-8c (V3-fix) | YES — V4 P-P0-3; V5 S-J3-1; V6 V-T-1, V-T-2 | closed wave-20a (V6) — **4 audit rounds to converge** |
| H-1 ID-namespace | V3 H-1 | wave-16d (V4-fix) | YES — V5 S-WS-GAP-1 | partial close (gap-fill site fixed wave-17c) |
| LotTracker dead | V3 M-3 (proxy) | hold | YES — V7 BB BUG-8 | closed wave-30 (V8 prep) — **5 rounds elapsed before wiring** |
| `audit_logs` empty | not flagged | n/a | n/a | flagged V7 BB BUG-10, closed wave-30 |
| Public JWT default | not flagged | n/a | n/a | flagged V7 AA-C-1, closed wave-23a |
| `comp_breakout_readiness` flat | not flagged | n/a | n/a | flagged V7 DD-1, closed wave-24 |

**Stats (audit-rounds elapsed):**
- Median rounds-to-converge for re-flagged findings: **3** (J-3 chain, R-F series, H-1).
- Worst: J-3 took **4 rounds** (V3 → V4 → V5 → V6) before all sites were patched.
- Findings *currently* still open from V1: **0** — but V1 only audited 7 surfaces; V3 H-1 was effectively the longest-open (V3 → wave-16d).
- Findings currently still flagged-and-deferred: **~58 V7 items** (per FINDINGS_LEDGER), most non-urgent: HH R-1/R-2/R-3 structural refactors, GG doc drift, EE runbooks, DD-5..11 medium strategy, FF-4..11 medium adversarial.

**Re-flag distribution by class:**
| Class | Re-flagged at least once |
|---|---|
| Time / clock / `_now_fn` | 100% (every round V3-V6 found new sites) |
| Alert dispatch from worker thread | 100% (wave-8c → V4 → V5 → V6) |
| Reconciliation pollution | 67% (V1 → V2 GAP series → V4 R-F series) |
| Persistence boundary | 60% (R-F-1 / B-T-2 / N-C-2 share shape) |
| Strategy logic | 0% (V7 DD findings all first-time) |
| Security | 0% (V7 AA findings all first-time) |

The *re-flag rate is determined by class*. Cross-cutting classes (clock,
alert, reconciliation) recur because each new module added re-introduces
the bug; first-look classes (strategy, security) don't recur because the
audit cycle hadn't covered them yet — but will once they're under continuous
maintenance.

---

## Section 4 — Same-class scan effectiveness

V6 W introduced same-class scans as a wave-PR requirement. V7 W2 verified
shipping: *0 of 3 W rules in any workflow, no PR template, the script W
referenced doesn't exist*. Wave 28 (post-V7) tightened CI rules from warn
→ required, after V7 W2 confirmed they hadn't been enforcing.

**Empirical hit rate of same-class scans:**

Of V7's ~91 actionable findings, how many were caught by an explicit same-
class scan vs found a fresh way?

| Source of finding | V7 count | % |
|---|---|---|
| Same-class extension of prior finding | **~12** (V-T-1/V-T-2 = J-3 sibling; FF-1 = ORM check sibling of BB-1/2/3; AA-M-3..5 = require_roles sibling of AA-C-2; HH god-class = M-3 expansion) | **~13%** |
| Fresh class first audited | **~79** (AA, BB-8/10, DD all 11, EE all 8, FF first-look, GG first-look, HH first-look) | ~87% |

**Scan-yield is dominated by new-class introduction, not by extending
prior classes.** The 13% same-class extension rate is exactly what you'd
expect when "same-class scan" is a *human best-effort* step (V6 Pattern 1).

**Wave-28 enforcement should change this number going forward.** If the
CI rule actually blocks PRs that don't include a same-class grep + asserted-
zero, the V8+ same-class hit rate should rise toward 30-50%, leaving
"fresh class" as the dominant remaining yield. V8 W3 is the right track
to verify this.

**Caveat:** Tracks W and W2 themselves were process audits, not bug audits.
Their findings flag the *absence* of scans, not the *failure* of scans.
The actual grep-vs-grep miss rate (where a scan was attempted and missed
a sibling site) is closer to the V5/V6 "fix-didn't-fix" pattern: J-3 had
3 sites at V3, scan caught 1, the other 2 were re-flagged in V5/V6.

---

## Section 5 — Test-vs-finding correlation: under-tested high-risk modules

Test-LOC vs source-LOC for the top backend files (running script from
prompt + extending it):

| Module | Src LOC | Test LOC | Ratio | Findings against module |
|---|---|---|---|---|
| `live_engine` | 6,479 | 0 (no `tests/test_live_engine.py`) | **0.00** | every track touched it; HH-1 noted it's the gravitational center; CC measured 21% line coverage (via integration tests, not direct) |
| `risk_manager` | 2,621 | 0 | 0.00 | K-3 daily window UTC; S findings on circuit breaker |
| `models` (ORM) | 2,444 | 0 | 0.00 | N-H-1, N-H-2, N-M-1, N-M-2, BB-1/2/3, BB-6 |
| `orders` | 2,122 | 0 | 0.00 | H-1, H-2, FF-1, FF-2, BB BUG-8 |
| `brain_persistence` | 2,119 | 0 | 0.00 | R-F-1, R-F-5, X-3, S-DISK-1 |
| `feature_engineering` | 2,065 | 0 | 0.00 | DD-1 (`comp_breakout_readiness` flat-data), DD-3 (SPY iloc) |
| `model_manager` | 1,988 | 0 | 0.00 | C-1 (RF/LGBM persist) — eventually closed wave-11d |
| `indicators` | 1,984 | 0 | 0.00 | none yet (likely V8/V9 surface) |
| `order_service` | 1,882 | 0 | 0.00 | V-T-1 critical (S-J3-1 sibling) |
| `ensemble_model` | 1,846 | 0 | 0.00 | C-1 axis-8 |
| `pipeline` | 1,753 | 0 | 0.00 | none yet |
| `feature_store` | 1,092 | 0 | 0.00 | none yet — but CC noted it's at 0% coverage, V8 NN reachability candidate |
| `auth` | 1,087 | 0 | 0.00 | AA-C-1, AA-C-2 |

**Every top-13 backend module by LOC has 0 dedicated test files** (file-name
match). The top-named module with non-zero ratio in the survey is
`self_evolution` at ratio 0.21 (1,254 / 261).

This is not an indictment of test count (8,777 tests exist across 464
files per V7 CC). Tests exercise modules through *integration paths*,
not module-named files. But the pattern is real:

- **Modules where audit found ≥10 findings** (`live_engine`, `models`,
  `brain_persistence`, `orders`, `auth`, `feature_engineering`) **all have
  0 module-named test files**.
- **The two highest-LOC modules outside the audit-finding hot list**
  (`indicators`, `pipeline`) **also have 0 module-named test files** —
  near-certain V8/V9 finding-pool.

**Under-tested high-risk modules (recommended priority for V9 test
backfill):**

| Module | Why high-risk |
|---|---|
| `live_engine.py` | 6,401 LOC, 21% line coverage, every track touches it |
| `brain_persistence.py` | 2,119 LOC, 13 hand-paired save/load methods, CSV-roundtrip bugs (R-F-1, B-T-2) recurring |
| `auth.py` | 1,087 LOC, AA-C-1 + AA-C-2 (two of the cycle's most severe findings); needs penetration test, not unit tests |
| `feature_engineering.py` | 2,065 LOC, DD-1 (flat-data manufactured score) shows the math itself can be wrong even when the plumbing is correct |
| `orders.py` + `order_service.py` | 4,000+ combined LOC, every adversarial / lifecycle finding lives here, dispatched alerts known broken |
| `indicators.py` | 1,984 LOC, never audited — high probability of V8/V9 yield |

---

## Section 6 — Process meta-findings

### 6.1 Commit-message structure trend

Wave commit subjects (49 commits, wave-8a → wave-31):

- Average subject length: **75 characters** (min 48, max 122).
- Length is roughly stable across waves; slight upward drift when more
  IDs are bundled (wave-13ad and wave-25 hit 100+).
- Format `fix(audit-waveNN[a-z]): <theme> — close <ID list>` is consistent
  from wave-8a onward (V3-fix). **No drift over time.**
- Commit body length (lines including bullets): variable, mostly 35-65
  lines. No bloat detected.

**Verdict: commit hygiene is GOOD and STABLE.** This is one of the cycle's
durable strengths.

### 6.2 Wave-PR closing more or fewer findings

| Wave era | Avg findings closed per wave |
|---|---|
| Waves 8-11 (V3-fix) | ~3.5 (each wave letter is a single-class focus) |
| Waves 12-15 (V4-fix) | ~5.5 (cross-track bundles) |
| Waves 17-19 (V5-fix) | ~7 |
| Waves 20-22 (V6-fix) | ~8 |
| Waves 23-27 (V7-fix) | ~6.5 (front-loaded urgent in 23) |
| Waves 28-31 (post-V7) | ~3 (residual / structural; partial fixes) |

**Trend: peaked at V5/V6, declining as backlog shifts to deferred /
structural / multi-hour items.** Healthy. The cycle is converging on
hard-class items rather than gushing easy fixes.

### 6.3 Time-to-deploy-after-audit

Compressed wall-clock makes this hard to compute meaningfully — the
entire 7-round cycle ran in ~52 hours. But **fix-after-audit gap** is
near-zero (2-5 hours from synthesis-to-first-wave-commit) across V3, V4,
V5, V6, V7. **No deceleration.**

### 6.4 Findings-tracking integrity

- `grep -rh "Finding-ID:\|finding=" artifacts/audit/v*_reports/` → **0**.
- `grep "Closes:" docs/audit/*` → directory does not exist; **0**.
- `git log --grep="Closes\|closes"` → **29** commits.
- `grep -E "audit-wave"` git log → **49** commits.

**Mismatch: 49 wave commits, only 29 mention "Closes".** The other 20
either bundle multiple closes by inline ID list (wave-13ad style) or
ship without explicit "Closes" syntax. There is no machine-readable
finding-ID → wave-commit mapping anywhere except the FINDINGS_LEDGER
markdown table (which is human-edited).

**Distinct finding-IDs cited in FINDINGS_LEDGER: 152** (rough script
count). V1-V7 cumulative findings stated: ~278. Even allowing for medium/
low items aggregated as "BB-1/2/3" or "DD-5..11", **the gap (278 - 152 =
~126)** is the volume of findings *that exist in synthesis docs but never
got an explicit row in FINDINGS_LEDGER*.

This is the meta-finding: **the ledger is not the source of truth**;
synthesis docs are. A synthesis doc can drop a finding silently in the
next round (if it's not re-flagged) and no one notices.

### 6.5 Findings opened-but-silently-closed

Spot-checks:
- V3 M-2 (`is_exploration` pathway never True) — no wave commit closes it; ledger shows no closure entry; pathway likely still exists.
- V3 M-9 (nightly training never auto-starts) — same; no closure tracked.
- V5 B-T-3 (`int(qty)` 8+ sites) — wave-18 closed by adding helper, but the comment "13 int(qty) call sites unchanged" in W indicates the body of the finding was not actually closed; ledger marks it closed.
- V7 GG-1/2/3/4/5/8/10/11 — all marked deferred to V8; V8 plan doesn't track them as a discrete deliverable.

**Silent-drift estimate: ~10-20 findings/round drift from ledger.** The
cycle's nominal "closed" count overstates real closure by a small but
non-zero margin.

### 6.6 Same-class enforcement

V6 W proposed CI rules; V7 W2 confirmed not shipped; wave-28 *did* ship
(per V8 plan). **Same-class scan now runs in CI from wave-28 onward,
which means V8 is the first round where the rule has been live during
the prior fix wave.** V8 W3 should empirically verify the rule actually
blocks bad PRs. Until then, the gap exists.

---

## Section 7 — Recommended new tracks for V9

Ranked by leverage:

### V9 Track PP — Chaos / Fault-Injection Runtime Harness (HIGHEST LEVERAGE)

**What:** Build a programmatic harness that, against a paper-mode container,
injects: (a) Postgres SIGKILL mid-tick; (b) Redis SIGSTOP for 30s during
outbox dispatch; (c) Alpaca WS disconnect mid-fill; (d) disk-full on
`organism_brain/` mid-save; (e) NTP clock-step ±10 minutes; (f) memory
pressure (cgroup limit) under brain-save burst. Verify the engine
recovers without state divergence.

**Why:** The cycle's three most operationally severe finding *classes*
(R-F-1 reconciliation pollution, S-J3-1 alert drop, B-T-2 PnL drift) are
all chaos-class bugs that the cycle caught only after they manifested.
A single chaos finding can preempt 2-3 future rounds of post-mortem
findings.

**Estimated yield:** 5-15 first-round findings; 60-80% likely to be
already-deferred V7 issues confirmed in motion (S-DISK-1, S-CLK-1, etc.)
+ 3-5 fresh.

### V9 Track QQ — Migration Round-Trip + Schema-Drift Audit (HIGH LEVERAGE)

**What:** Treat `alembic` as if it existed (it doesn't — `alembic.ini`
present but no `alembic/versions/` directory). For every ORM-vs-DB drift
(N-H-1, BB-6, BB-1/2/3 are the visible tip), document the missing
migration. Stand up a CI step that: applies all migrations to an empty
DB, dumps schema, diffs against ORM `Base.metadata`, fails on drift.

**Why:** The schema drift class has produced 6+ findings across V4 (N-H-1),
V7 (BB-1/2/3, BB-6) with no automation in sight. The class is mechanically
detectable and currently un-instrumented.

**Estimated yield:** 5-10 fresh; class is unambiguous so noise floor low.

### V9 Track RR — Multi-Day Operational Soak + Brain Coherence (MEDIUM LEVERAGE)

**What:** Run the paper container 5 consecutive trading days with daily
restarts (intentional, scheduled). After each restart, snapshot brain
state, trade history, position lots, audit log. Diff cumulative invariants:
gen monotonic, trade_history append-only, no ID re-use, no `direction`
flip, `is_reconciliation_artifact` flag survives roundtrip, cumulative
PnL = sum-of-trades within tolerance.

**Why:** R-F-1 is a multi-day-coherence bug that ate the audit-G v2 work.
B-T-2 is the same shape. The cycle has not yet operated *as if it cared*
about cumulative state across operational days. Z-tracks verify single-
wave closures; this would be the multi-day analog.

**Estimated yield:** 3-7 fresh; mostly mid-severity but very durable.

---

## Section 8 — Tracks to retire (low-yield)

### Retire: Track T2 (Numerical Property Tests)

**Reason:** T2 v6 found *0 bugs* (it shipped 26 pass tests as test backfill
infrastructure). The numerical-invariant class is now well-instrumented
via property tests; adding more tracks at this layer hits diminishing
returns. **Fold T2's coverage role into a maintenance lane** (i.e. require
property-test coverage when shipping a new numerical helper) rather than
a recurring audit track.

### Retire (or merge): Track Z / Z2 / Z3 / Z4 (closure regression)

**Reason:** Z-tracks have produced **0 production regressions** across
V4 (47/47), V5 (47/47), V6 (47/47), V7 (47/47). They reliably surface
cosmetic items (regime.py:589 in Z3) and test-fixture drift (Z-R-1/R-2)
but no platform regressions. **Fold Z into a CI smoke gate** ("the wave
just shipped; for every closure-marker-comment, grep returns the comment")
and stop spending a track-slot on it. Saves ~2-4 hours of audit work per
round at minimal risk.

### Retire (or merge): Track W2 (CI rule verification)

**Reason:** W2 is a one-shot "did the rules ship?" check. After wave-28
ships the rules, V8 W3 verifies they actually block bad PRs. W2's lens is
now subsumed by W3 + the next round's same-class scan results.

### Keep but de-prioritize: any time/clock track

5 rounds of clock auditing have produced 29 findings, but yield-per-round
is now in the cosmetic range (V6 X mostly-bypass, regime.py:589). The
class is well-instrumented. Keep one *light* sweep per 3-5 rounds rather
than every round.

---

## Meta-findings

There are **6 meta-findings** in this track:

1. **CHAOS-GAP** — In 7 rounds of ~278 findings, zero runtime fault-injection
   tests have been performed. Three of the cycle's most operationally
   severe finding classes (reconciliation pollution, alert silent-drop,
   PnL drift) are chaos-class bugs caught only in retrospect. **Severity:
   CRITICAL** if the platform ever leaves paper. **V9 Track PP is the
   highest-leverage single recommendation in this report.**

2. **MIGRATION-GAP** — `alembic.ini` exists; no `alembic/versions/`
   directory exists. Schema changes ship as ORM edits with no migration
   round-trip ever exercised. 6+ findings already in this class
   (N-H-1, BB-1/2/3, BB-6). **Severity: HIGH.** V9 Track QQ.

3. **STRATEGY-LOGIC-DROUGHT** — V1 had 8 strategy findings; V2-V6 had
   0; V7 DD had 11 (including DD-1, the cycle's single highest-impact
   strategy bug). The cycle audited *that the system runs* for 5 rounds
   before auditing *whether the strategy is right*. On a financial
   platform, this is the wrong investment ordering. **Recommend: every
   round must include at least one strategy-correctness track.**

4. **LEDGER-vs-SYNTHESIS DRIFT** — FINDINGS_LEDGER cites ~152 distinct
   IDs; synthesis docs claim ~278 cumulative. ~126 findings exist in
   prose but not in any machine-readable closure tracker. Silent-close
   risk (~10-20/round) is the consequence. **Severity: MEDIUM.**
   Recommend: every wave commit must `Closes:` every finding-ID it
   addresses; CI grep tags untracked IDs.

5. **SAME-CLASS-EFFECTIVENESS-GAP** — Same-class scans caught only ~13%
   of V7 findings as extensions; 87% were fresh-class. Until wave-28's
   CI rule, scans were human best-effort and missed sibling sites
   (J-3 cycle: 4 rounds to converge). **Wave-28 should change this; V8
   W3 must verify.**

6. **MODULE-NAMED-TEST-GAP** — Every top-13 backend module by LOC
   (live_engine, models, brain_persistence, orders, auth, etc.) has zero
   module-named test files. Coverage exists via integration paths but
   discoverability for test-backfill is poor. The 13 deterministic
   regressions V7 CC found mostly live in modules without dedicated
   test files. **Severity: MEDIUM.** Recommend: V9 backfill at least one
   `tests/test_<module>_focused.py` per top-LOC module to anchor
   future regression tests.

**Recommended V9 tracks: 3** (PP chaos, QQ migration, RR multi-day soak).
**Tracks to retire: 2-3** (T2 fold-in, Z fold-into-CI, W2 sunset).

---

## TL;DR

After 7 rounds and ~278 findings, the audit cycle's blind spots cluster
at runtime: **zero chaos / fault-injection tests, zero load tests, zero
migration round-trips, zero multi-day coherence soaks** — every finding
has come from static analysis, single-tick exercise, or post-mortem.
Three of the cycle's most severe classes (reconciliation pollution,
alert silent-drop, PnL drift) are chaos-shaped bugs caught only in
retrospect. The class budget is over-spent on time/clock (29 findings
across 5 rounds) and under-spent on strategy logic (a 5-round drought
between V1 and V7 left DD-1 in production for weeks) and security (same
gap; AA-C-1 was live for weeks before V7 saw it). The ledger-to-synthesis
drift (~126 findings in prose but not tracked in FINDINGS_LEDGER) and the
13% same-class-scan effectiveness rate are the durable process gaps.
**Highest-leverage V9 recommendation: ship a chaos-injection harness
(Track PP) — a single round of it would likely preempt 2-3 future rounds
of post-mortem findings.**
