# Pre-9D Implementation Audit

Generated: 2026-05-10
Branch: `codex/v13-phase2-expectancy`
Scope: Phase 9A/9B/9C implementation audit and pre-9D cleanup

## Verdict

Phase 9A through Phase 9C are ready to remain deployed as evidence-only infrastructure. I found no order-path or live-strategy behavior changes in this pre-9D cleanup pass, and I did not implement Phase 9D.

The main issue found during this audit was governance-tooling drift: the PR wave-marker gate was visible but still advisory, the PR template still described the old advisory state, the runtime snapshot omitted deploy provenance and shadow telemetry envs, and the live audit index did not classify `.github/` changes as CI/tooling evidence. Those are now fixed and covered by tests.

The remaining deliberate gap is Phase 9D itself: the `StrategyGovernor` exists and is tested, but it is not yet wired as the global live pre-order gate. That is the next implementation step and should be treated as a live-behavior change with full order-path replay/safety validation.

## Fixes Applied In This Audit

1. `scripts/ci/check_wave_markers.py`
   - Default long-lived branch checks now clamp to the V12 baseline commit `38d1b74` when appropriate.
   - Added `--all-history` for forensic checks of legacy pre-V12 wave commits.
   - Removed local ruff debt in the touched code path.

2. `.github/workflows/pr-verify.yml`
   - Removed `continue-on-error: true` from Wave-PR marker enforcement.
   - CI now treats the supported V12+ wave-marker range as a hard gate.

3. `.github/pull_request_template.md`
   - Updated the checklist text so it no longer falsely says marker enforcement is a future/manual-only check.

4. `scripts/runtime/write_runtime_snapshot.py`
   - Live process snapshot now captures `GIT_SHA`, `BUILD_TIME`, `IMAGE_SHA`, and Phase 5/6/9 shadow telemetry env toggles.

5. `scripts/ci/generate_audit_index.py`
   - `.github/` changes now classify as tooling/evidence rather than mixed/unknown scope.
   - The generated audit index now has a CI row.

6. Tests
   - Added/updated tests for the V12 baseline clamp, runtime deploy/env snapshot fields, and CI/tooling scope classification.

## Audit Evidence

Targeted cleanup tests:

```text
25 passed in 1.27s
```

Ruff on touched files:

```text
All checks passed!
```

Wave-marker gate:

```text
[OK] all wave-commit checks passed
```

Ledger/gate scripts:

```text
verify_findings_ledger.py: PASS
forbid_marker_only_critical_high.py: PASS
lint_ratchet.py: PASS
check_migrations.py: PASS, single head 20260503_000003
```

Phase 9 and evidence tests:

```text
58 passed in 1.64s
```

Broad organism/config/safety/replay regression set:

```text
189 passed, 4 warnings in 199.68s
```

Runtime and paper safety checks:

```text
Paper book: flat
Open orders: 0
Live container before this cleanup commit: c2713939a116dbbc207be39b343ce0b7cd0e54e0
Live process snapshot reachable: true
Phase 5 shadow telemetry env: true
Phase 6 strategy evidence env: true
Phase 9 shadow engines env: true
Exploration enabled: false
```

Evidence warehouse status:

```text
Events: 421
Strategy evidence events: 195
Candidate-filter shadow events: 226
Outcomes: 581
Replay candidates: 0
Current strategy league: alpha_baseline rejected
```

## What This Does Not Prove

- It does not prove the current trading strategy is profitable.
- It does not authorize promotion of Phase 9 shadow engines.
- It does not claim the platform is perfect.
- It does not wire the Phase 9D global governor gate.

## Pre-9D Go / No-Go

Pre-9D tooling/evidence cleanup is a GO after this pass.

Phase 9D should proceed only as a separate live-behavior PR/slice that wires `StrategyGovernor` into the order path and proves:

- Unknown strategy IDs cannot submit live orders.
- Shadow-only strategies cannot submit live orders.
- Tier-0/Tier-1 strategies cannot submit live orders.
- Existing `alpha_baseline` behavior remains unchanged except for explicit governor admission.
- Replay, safety invariants, runtime snapshot, audit index, and paper deploy validation are all green.
