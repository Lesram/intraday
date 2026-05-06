# Phase 8 Evidence Warehouse V2 Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
Initial run SHA: `9459691c7d4e0d2b184ea5a269e19fd961a02b18`

## Verdict

P8.0 is complete as a first Track B slice. The platform now has an offline,
idempotent SQLite evidence warehouse builder that loads Phase 5 candidate
shadow telemetry, Phase 6 strategy evidence telemetry, Phase 6 outcome joins,
and organism brain trade history into queryable tables.

This is evidence-only. It does not change live ranking, sizing, gates, order
submission, exits, or promotion state.

## Initial Warehouse Build

Command:

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py
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

## Acceptance

| Criterion | Status |
|-----------|--------|
| Stable event IDs | PASS |
| Idempotent SQLite upsert | PASS |
| Outcome rows link to events | PASS |
| Promotion remains unauthorized | PASS |
| Focused tests | PASS: `tests/test_phase8_evidence_warehouse.py` |

## Next Slice

P8.1 should add order/fill/accounting extracts to the same warehouse:

1. Load DB orders and executions read-only.
2. Add broker/local fill identity fields.
3. Compare realized PnL, brain trade PnL, and forward-return evidence.
4. Produce a post-close decision report that separates evidence strength from
   live-promotion eligibility.
