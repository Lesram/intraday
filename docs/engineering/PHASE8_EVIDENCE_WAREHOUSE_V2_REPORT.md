# Phase 8 Evidence Warehouse V2 Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
Initial run SHA: `9459691c7d4e0d2b184ea5a269e19fd961a02b18`

## Verdict

P8.0 and P8.1 are complete as the first Track B evidence slices. The platform
now has an idempotent SQLite evidence warehouse builder that loads Phase 5
candidate shadow telemetry, Phase 6 strategy evidence telemetry, Phase 6
outcome joins, organism brain trade history, and optional read-only paper DB
orders/executions/realized trades into queryable tables.

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

Latest P8.1 read-only extract loaded:

| Table | Rows |
|-------|------|
| `db_orders` | `1461` |
| `db_executions` | `1543` |
| `db_realized_trades` | `971` |

Order status counts:

| Status | Rows |
|--------|------|
| `cancelled` | `5` |
| `expired` | `1` |
| `failed` | `4` |
| `filled` | `1451` |

Loaded DB realized-trades PnL: `-944.2431`.

The DB extract is opt-in with `--include-db`, uses only SELECT/WITH queries,
and leaves default no-DB artifact builds unchanged.

## Acceptance

| Criterion | Status |
|-----------|--------|
| Stable event IDs | PASS |
| Idempotent SQLite upsert | PASS |
| Outcome rows link to events | PASS |
| DB extract is opt-in and read-only | PASS |
| Promotion remains unauthorized | PASS |
| Focused tests | PASS: `tests/test_phase8_evidence_warehouse.py` |

## Next Slice

P8.2 should turn the loaded evidence into accounting-aware research views:

1. Add broker/local fill identity joins.
2. Add explicit cost/slippage fields.
3. Compare realized PnL, brain trade PnL, and forward-return evidence.
4. Produce a post-close decision report that separates evidence strength from
   live-promotion eligibility.
