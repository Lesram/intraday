# Pre-9D Deep Audit

Generated: 2026-05-10
Branch: `codex/v13-phase2-expectancy`
Purpose: broadened audit before Phase 9D order-path governor wiring

## Executive Verdict

Phase 9D should not start from the previous checkpoint unchanged. A broader pre-9D pass found two evidence/schema issues that were safe in the narrow sense but would have made Phase 9D or the strategy research loop less trustworthy:

1. Persisted boolean-ish strings such as `"false"` were parsed with Python `bool()`, which treats non-empty strings as true.
2. Phase 9 shadow evidence could not nominate replay candidates because it fed `r_multiple=0.0` into a league rule that rejects non-positive average R. That is correct for promotion, but too strict for shadow-to-replay nomination because shadow candidates do not yet have stop-defined R.

Both are now fixed. No Phase 9D wiring, order-path promotion, ranking, sizing, gate, or live trading behavior was changed in this audit slice.

## Fixes Applied

### 1. Boolean Parsing Hardening

Files:

- `backend/organism/schema/candidate_signal.py`
- `backend/organism/schema/__init__.py`
- `backend/organism/candidate_shadow_telemetry.py`
- `tests/test_phase9_strategy_governance.py`
- `tests/test_phase3_candidate_shadow_telemetry.py`

Change:

- Added `parse_bool()`.
- `CandidateSignal.shadow_only` now normalizes boolean-like persisted values.
- `CandidateShadowEvent.live_pipeline_candidate` now parses `"false"`, `"0"`, `"no"`, etc. correctly.
- Added regression tests for persisted boolean strings.

Why it matters:

- Phase 9D will depend on exact semantics for `shadow_only` and live-pipeline flags.
- Ambiguous values remain conservative via defaults, but explicit false is now respected.

### 2. Shadow Replay Nomination Fix

Files:

- `backend/organism/evidence/strategy_league.py`
- `scripts/phase9_shadow_evidence.py`
- `tests/test_phase9_strategy_governance.py`

Change:

- `build_strategy_league()` now accepts `require_positive_avg_r`.
- Default remains `True`, preserving stricter real-trade/promotion behavior.
- `scripts/phase9_shadow_evidence.py` passes `require_positive_avg_r=False`, because shadow evidence has benchmark/null alpha but no stop-defined R multiple yet.
- Added regression test proving default real-trade behavior still rejects zero-R rows while shadow replay nomination can pass on benchmark/null alpha.

Why it matters:

- Phase 9C can now surface replay candidates when shadow evidence is statistically interesting.
- Promotion remains blocked; replay nomination still requires sample size, profit factor, positive benchmark/null alpha, and concentration checks.

## Static Live-Behavior Audit

Static scan results:

- Phase 9 research engines under `backend/organism/engines/` contain no order submission calls.
- `StrategyGovernor` remains side-effect free and is not yet wired into order placement.
- `candidate_shadow_telemetry.py` records JSONL evidence only.
- `PHASE9_SHADOW_ENGINES_ENABLED=true` only enables signal recording.
- `ORGANISM_ORB_LIVE_ENABLED`, `ORGANISM_EOD_LIVE_ENABLED`, and `ORGANISM_MEAN_REVERSION_LIVE_ENABLED` are unset in the live container, so defaults remain false.

Container env snapshot:

```text
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED=true
ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED=true
ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED=true
ORGANISM_EXPLORATION_ENABLED=false
```

## Runtime / Data Invariants Checked

Paper runtime:

```text
host HEAD: e8a49e6b48c2ecd52f40a00f092d39cd84d4b1d6 at audit start
container GIT_SHA: e8a49e6b48c2ecd52f40a00f092d39cd84d4b1d6
positions_nonzero=0
open_orders=0
migration=20260503_000003
```

Audit chain:

```text
/api/v1/audit/chain-detail?limit=10000
all_valid=True
row_count=1235
invalid_count=0
```

Data integrity:

```text
realized_trades=1082
orders=1535
executions=1686
outbox=910
brain_total_trades=558
brain_generation=204
brain_cumulative_pnl=-626.93
```

The DB-vs-brain count mismatch is not comparable scope according to `/api/v1/health/data-integrity`: DB lot accounting starts earlier and is a superset of brain strategy history. Accounting status is `ok`; this remains an operational nuance, not a Phase 9D blocker.

## Evidence Loop Status

Phase 8 post-close with DB evidence:

```text
events=421
outcomes=581
trades=559
db_orders=1535
db_realized_trades=1082
accounting=1082
replay_candidates=1
promotion_authorized=false
```

Current replay-only candidate:

```text
symbol: AMD
reason: forward_and_realized_symbol_evidence_aligned_positive
required_next_step: replay_before_any_live_change
promotion_authorized: 0
```

Phase 9 shadow evidence:

```text
raw_events=195
phase9_events=0
joined_outcomes=0
replay_candidates=0
promotion_authorized=false
```

Interpretation:

- Phase 8 evidence has one replay-only symbol candidate.
- Phase 9 engines have not yet produced market-session shadow events, so they cannot inform strategy promotion yet.
- Nothing here authorizes live behavior change.

## Validation Run

Focused evidence/schema tests:

```text
30 passed
61 passed
```

Static/lint/type checks:

```text
ruff touched files: PASS
compileall touched files: PASS
mypy --follow-imports=skip touched source files: PASS
repo-wide mypy: advisory FAIL due legacy backlog, not new touched-file debt
git diff --check: PASS
```

Governance/ledger gates:

```text
pytest --collect-only tests/: 6269 functions
forbid_marker_only_critical_high.py: PASS
verify_findings_ledger.py: PASS
lint_ratchet.py: PASS
check_migrations.py: PASS
check_wave_markers.py: PASS with V12 baseline clamp and advisory warnings only
```

Required organism/order/reconciliation regression set:

```text
214 passed, 5 warnings
```

Security sanity:

```text
19 passed, 0 failed
```

Integration checkpoint before commit/deploy:

```text
17 pass, 1 warn, 1 fail
```

The warning/failure were expected at that moment because the host working tree had new backend changes not yet committed/deployed:

- `repo_clean`: dirty working tree
- `hot_path_byte_parity`: container still on prior file bytes

Those must be rerun after commit and paper rebuild.

## Open Items Before Phase 9D

1. Commit and deploy this audit slice.
2. Rerun integration checkpoint after deploy; it must return `19 pass, 0 warn, 0 fail`.
3. Generate full artifact pack and live audit index on the final SHA.
4. Only then begin Phase 9D.

## Phase 9D Go Criteria

Phase 9D may start only after this audit slice is deployed and validated. The Phase 9D implementation must prove:

- Unknown `strategy_id` cannot place live orders.
- `shadow_only=true` cannot place live orders.
- Tier 0 and Tier 1 strategies cannot place live orders.
- `alpha_baseline` remains admitted exactly as current guarded behavior.
- Old ORB/EOD/MR live flags remain false unless explicitly promoted by replay evidence.
- Replay, safety invariants, security sanity, integration checkpoint, runtime snapshot, and deploy parity all pass.
