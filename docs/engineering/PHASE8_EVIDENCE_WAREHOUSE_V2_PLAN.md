# Phase 8 Evidence Warehouse V2 Plan

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`

## Purpose

Phase 8 is Track B: turn paper-trading evidence into a research-grade decision
warehouse. Phase 8 must not promote live strategy behavior. Its job is to make
strategy decisions harder to fool: every candidate, rejection, fill, cost,
forward-return join, and post-close verdict should be traceable.

## First Slice

P8.0 adds an offline warehouse builder:

- Input: Phase 6 strategy evidence JSONL.
- Input: Phase 5 candidate-filter shadow JSONL.
- Input: Phase 6 outcome join CSV.
- Input: organism brain trade history CSV.
- Output: idempotent SQLite database under `artifacts/phase8_evidence_warehouse/`.
- Output: summary JSON and markdown report.

This does not touch the live engine, broker, order path, ranking, sizing,
safety gates, exits, or promotion state.

## Warehouse Tables

| Table | Purpose |
|-------|---------|
| `evidence_events` | One normalized row per live/shadow candidate event, with stable event IDs. |
| `evidence_outcomes` | Forward-return rows linked back to events where possible. |
| `trade_history` | Brain trade-history rows loaded for expectancy context. |
| `warehouse_manifest` | Build metadata, counts, input paths, SHA, and no-promotion assertion. |

## Execution

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py
```

Default outputs:

- `artifacts/phase8_evidence_warehouse/strategy_evidence.sqlite`
- `artifacts/phase8_evidence_warehouse/warehouse_summary.json`
- `artifacts/phase8_evidence_warehouse/PHASE8_EVIDENCE_WAREHOUSE_REPORT.md`

## Acceptance

- The builder is idempotent: rerunning it does not duplicate rows.
- Event IDs are stable for the same input event.
- Outcome rows link to event rows when timestamp, symbol, and event line match.
- The report states `promotion_authorized=false`.
- Focused tests pass.

## Next Slices

1. Add DB/broker order and fill extracts into the same warehouse.
2. Add cost/slippage fields and realized-vs-forward-return comparison.
3. Add post-close decision rules with minimum sample gates.
4. Add replay candidate export for ideas that pass evidence gates.
5. Add a Track C daily automation that builds the warehouse after close and
   refuses live promotion until replay and review pass.
