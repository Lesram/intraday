# Track W v6 — Wave-Cycle Audit (Fix Verification Process)

The V5 cross-track Pattern 1 ("fix that didn't actually fix") was load-bearing:
S-J3-1 alone meant 100% of forensic-guard alerts since wave-8c had been
silent in production. The audit cycle is currently the only defense.

Track W formalizes the defense as a process: for every fix wave (1 through 19),
verify (a) the fix marker is present in the code, (b) the same-bug-class is gone
from adjacent code, (c) a regression test exists. Surface waves where any of
those three conditions fails.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `3f660f4`.

## Method

### 1. Wave inventory

Build a complete table from `git log --grep="audit-wave"` and the
`FINDINGS_LEDGER.md`:

| Wave | Commit | Findings closed | Marker grep | Same-class scan | Regression test |
|---|---|---|---|---|---|
| 8a..16d | (per ledger) | (per ledger) | ? | ? | ? |
| 17a..19 | (per ledger) | (per ledger) | ? | ? | ? |

For each wave row:

#### (a) Marker grep
The commit message references finding IDs (e.g. "S-J3-1"). The fix should leave
a marker in the code (e.g. "V5 S-J3-1 / Wave-17a"). Grep for the marker:
- Wave 17a: `grep -rln "S-J3-1" backend/` — expect ≥3 sites (the 3 patched).
- Wave 18: `grep -rln "S-NET-CB-1" backend/` — expect ≥1.
- Each wave: at least one source-of-truth marker exists.

If 0 markers: bug. The fix is shipped without trace; future readers won't
know why the code looks the way it does.

#### (b) Same-bug-class scan
Each fix's same-class scan was already run in the closure-regression Z tracks.
This step verifies that scan is *current* — re-run it now and report deltas
since the wave's fix-commit. Examples:

- Wave 8c (J-3) class: `grep -rn "asyncio.create_task(send_alert" backend/` outside `dispatch_alert_from_thread`. Should be 0.
- Wave 10c (K-9) class: `grep -rn "datetime.utcnow()" backend/` outside tests/comments. Should be 0.
- Wave 17b (U-3..U-5) class: `grep -rn "datetime.now(UTC)" backend/organism/` should reveal only display sites.
- Wave 17d (B-T-2) class: `grep -rn "round(t.pnl, 2)" backend/`. Should be 0 in writer paths.
- Wave 18 (B-T-1) class: `grep -rn "direction=1.0" backend/organism/` outside LONG_ONLY-mandated sites.

If a wave's same-class count > 0 today: regression detected.

#### (c) Regression test
Each wave should have a test that fails if the fix is reverted. Inventory
existing tests by wave:
- Wave 17a: `tests/test_alert_cross_thread_dispatch.py` (exists).
- Wave 17b: `tests/test_replay_clock_injection.py` (exists).
- Wave 16d: `tests/test_remediation_wave_a.py::test_is_order_terminal_accepts_internal_uuid` (exists).
- ... continue for each wave.

If a wave has no regression test: this is the regression-risk hot zone.
Flag for wave-20 backfill.

### 2. Wave timing audit

For each wave, capture from `git log`:
- Was the fix verified post-deploy (commit message says "Deploy verified...")?
- Did Z2 / Z3 closure tracks find the wave-fix intact?
- Time elapsed between wave commit and current HEAD (= window during which
  the fix could have silently regressed).

Surface waves with the longest unverified window — those are the highest
"silent regression" risk for the next round.

### 3. Audit process metadata

V5's S-J3-1 was "in the code but didn't run". Audit the audit:
- For each wave, did we have a *behavioral* test or only a *structural* test
  (grep / inspect / source assertion)?
- Behavioral tests catch fix-didn't-fix bugs. Structural tests don't.
- Flag waves with structural-only tests.

### 4. Continuous-fix policy proposal

End the report with a concrete CI-rule proposal that would prevent a future
S-J3-1-class issue:
- "every wave PR must include a behavioral test that fails if the fix is reverted"
- "every wave PR must run the same-bug-class grep and assert 0 hits"
- "every wave PR must have at least one marker in the changed code"
- Plus any others the audit surfaces.

### 5. Cross-pollination check

V4 Pattern 5 + V5 Pattern 1 identified "audit catches its own work" as
ongoing. List the 3-5 most recent wave fixes that the *next* audit might
catch. (Predictive — pessimistic estimate.)

## Output

`artifacts/audit/v6_reports/track_w_wave_cycle_audit.md` with:
- Per-wave (a)/(b)/(c) verification table
- Wave timing risk-list (oldest unverified)
- Behavioral-vs-structural test ratio
- CI rule proposal
- "Waves at regression risk: N" + TL;DR

## Constraints

Read-only. `git log`, `grep`, `pytest` ok.

## Quality bar

Expect 5-15 wave rows where (a)/(b)/(c) doesn't fully pass. The point of
this track is to make the gap visible, not to fix it — that's wave 20+.

End with a one-paragraph summary.
