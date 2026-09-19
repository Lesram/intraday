# Phase 8 Evidence Warehouse V2 Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
Initial run SHA: `9459691c7d4e0d2b184ea5a269e19fd961a02b18`

## Verdict

P8.0, P8.1, P8.2, and P8.3 are complete as the first Track B evidence slices.
The platform now has an idempotent SQLite evidence warehouse builder that loads
Phase 5 candidate shadow telemetry, Phase 6 strategy evidence telemetry, Phase
6 outcome joins, organism brain trade history, optional read-only paper DB
orders/executions/realized trades, a derived realized-lot accounting join, and
first-pass filter/symbol research summaries into queryable tables.

This is evidence-only. It does not change live ranking, sizing, gates, order
submission, exits, or promotion state.

## Initial Warehouse Build

Command:

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py
```

P8.1 command:

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py --include-db
```

Outputs:

- `artifacts/phase8_evidence_warehouse/strategy_evidence.sqlite`
- `artifacts/phase8_evidence_warehouse/warehouse_summary.json`
- `artifacts/phase8_evidence_warehouse/PHASE8_EVIDENCE_WAREHOUSE_REPORT.md`

Initial loaded counts:

| Table | Rows |
|-------|------|
| `evidence_events` | `86` |
| `evidence_outcomes` | `186` |
| linked outcomes | `186` |
| `trade_history` | `531` |

Input split:

| Input | Rows |
|-------|------|
| Strategy evidence events | `20` |
| Candidate-filter shadow events | `66` |
| Invalid JSONL rows | `0` |

Loaded brain trade-history PnL: `-657.7249`.

## P8.1 DB Extract Build

Latest P8.2 read-only extract loaded:

| Table | Rows |
|-------|------|
| `db_orders` | `1466` |
| `db_executions` | `1551` |
| `db_realized_trades` | `973` |
| `realized_trade_accounting` | `973` |
| `filter_outcome_summary` | `3` |
| `symbol_evidence_summary` | `31` |
| `replay_candidate_export` | `1` |

Order status counts:

| Status | Rows |
|--------|------|
| `cancelled` | `5` |
| `expired` | `1` |
| `failed` | `4` |
| `filled` | `1452` |

Loaded DB realized-trades PnL: `-944.2431`.

Accounting join summary:

| Metric | Value |
|--------|-------|
| Missing open orders | `0` |
| Missing close orders | `0` |
| Order/execution quantity delta rows | `0` |
| Winning realized rows | `351` |
| Losing realized rows | `616` |
| Average realized return bps | `-2.5591` |

Research summary verdicts:

| Summary | Verdicts |
|---------|----------|
| Filter recommendations | `inconclusive_continue_shadow=2`, `reject_negative_expectancy=1` |
| Symbol verdicts | `aligned_negative_expectancy=3`, `aligned_positive_needs_replay=2`, `conflicting_forward_negative_realized_positive=3`, `conflicting_forward_positive_realized_negative=2`, `realized_only_missing_forward_outcomes=21` |
| Replay candidates | `1` |
| Promotion authorized rows | `0` |

Top filter signals:

| Filter | Joined outcomes | Avg directional bps | Positive rate | Recommendation |
|--------|-----------------|---------------------|---------------|----------------|
| `all_candidates` | `186` | `-1.8157` | `0.3763` | `inconclusive_continue_shadow` |
| `alpha_breakout_chop` | `168` | `-2.4686` | `0.3750` | `reject_negative_expectancy` |
| `conf_45_55` | `42` | `3.8163` | `0.5000` | `inconclusive_continue_shadow` |

Replay candidate export:

| Candidate | Type | Evidence | Required next step |
|-----------|------|----------|--------------------|
| `AMD` | `symbol` | `joined=48`, `realized_rows=38`, `forward_bps=0.8986`, `positive_rate=0.5625`, `realized_pnl=24.8107` | `replay_before_any_live_change` |

`QQQ` was not exported despite positive average forward bps and positive
realized PnL because its forward positive rate was only `0.40`; P8.4 requires
at least `0.50` for symbol replay candidates.

The DB extract is opt-in with `--include-db`, uses only SELECT/WITH queries,
and leaves default no-DB artifact builds unchanged.

## Track C Automation Entry

Command validated locally:

```bash
./venv/bin/python scripts/ci/run_phase8_postclose_evidence.py --include-db --require-db
```

Result: PASS with `events=90`, `accounting=973`, `replay_candidates=1`.

The GitHub `paper-postclose-audit` workflow now runs
`scripts/ci/run_phase8_postclose_evidence.py` in artifact mode. Local paper
post-close automation should run the same wrapper with `--include-db
--require-db` so it fails when live DB evidence is missing.

The wrapper also generates a replay plan from `replay_candidates.json`:

- `artifacts/phase8_replay_plan/replay_plan.json`
- `artifacts/phase8_replay_plan/PHASE8_REPLAY_PLAN.md`

Current replay plan candidate: `AMD`.

## Acceptance

| Criterion | Status |
|-----------|--------|
| Stable event IDs | PASS |
| Idempotent SQLite upsert | PASS |
| Outcome rows link to events | PASS |
| DB extract is opt-in and read-only | PASS |
| Realized-lot accounting join is populated | PASS |
| Filter and symbol research summaries are populated | PASS |
| Post-close report and replay-candidate export generated | PASS |
| Track C wrapper validates no-promotion guardrails | PASS |
| Replay plan generated from replay candidates | PASS |
| Promotion remains unauthorized | PASS |
| Focused tests | PASS: `tests/test_phase8_evidence_warehouse.py`, `tests/test_phase8_postclose_runner.py`, `tests/test_phase8_replay_plan.py` |

## Next Slice

Next Track C / Track B work:

1. Run AMD replay commands from `artifacts/phase8_replay_plan/PHASE8_REPLAY_PLAN.md`.
2. Review replay artifacts and define pass/fail thresholds.
3. Consider strategy-logic changes only after replay evidence is positive.
