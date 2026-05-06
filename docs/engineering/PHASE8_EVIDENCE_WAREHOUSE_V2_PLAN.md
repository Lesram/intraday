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

P8.1 extends the same warehouse with optional read-only Postgres extracts from
the paper DB:

- DB orders.
- DB executions/fills.
- DB realized trades.

The DB extract is opt-in with `--include-db`. Default runs remain offline and
do not require Docker or Postgres.

P8.2 adds an accounting view derived from those DB extracts:

- Link each realized-trade lot to its open and close orders.
- Link each open/close order to execution quantity and VWAP.
- Surface missing order links, order/execution quantity deltas, realized
  return bps, and price-vs-order-fill bps.

This is still research-only. It creates evidence tables and reports; it does
not change paper/live trading decisions.

## Warehouse Tables

| Table | Purpose |
|-------|---------|
| `evidence_events` | One normalized row per live/shadow candidate event, with stable event IDs. |
| `evidence_outcomes` | Forward-return rows linked back to events where possible. |
| `trade_history` | Brain trade-history rows loaded for expectancy context. |
| `db_orders` | Read-only order ledger extract from paper Postgres. |
| `db_executions` | Read-only execution/fill extract from paper Postgres. |
| `db_realized_trades` | Read-only realized-trade accounting extract from paper Postgres. |
| `realized_trade_accounting` | Derived realized-lot to order/execution accounting join. |
| `warehouse_manifest` | Build metadata, counts, input paths, SHA, and no-promotion assertion. |

## Execution

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py
```

Read-only DB extract:

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py --include-db
```

Default outputs:

- `artifacts/phase8_evidence_warehouse/strategy_evidence.sqlite`
- `artifacts/phase8_evidence_warehouse/warehouse_summary.json`
- `artifacts/phase8_evidence_warehouse/PHASE8_EVIDENCE_WAREHOUSE_REPORT.md`

## Acceptance

- The builder is idempotent: rerunning it does not duplicate rows.
- Event IDs are stable for the same input event.
- Outcome rows link to event rows when timestamp, symbol, and event line match.
- DB extract is opt-in, SELECT/WITH-only, and preserves default offline behavior.
- Realized-trade accounting joins expose missing links and order/execution
  quantity deltas.
- The report states `promotion_authorized=false`.
- Focused tests pass.

## Next Slices

1. Add realized-vs-forward-return comparison.
2. Add post-close decision rules with minimum sample gates.
3. Add replay candidate export for ideas that pass evidence gates.
4. Add a Track C daily automation that builds the warehouse after close and
   refuses live promotion until replay and review pass.
