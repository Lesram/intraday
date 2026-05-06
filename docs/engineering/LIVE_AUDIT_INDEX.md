# Live Audit Index

Generated: 2026-05-06T01:36:46Z
PR: PR #6
SHA: `070d41d7f6`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/organism/brain_persistence.py`, `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Organism | 3 | `backend/organism/brain_persistence.py`, `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Scripts | 2 | `scripts/phase6_strategy_evidence_warehouse.py`, `scripts/runtime/write_runtime_snapshot.py` |
| Tests | 4 | `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase5_shadow_outcome_join.py`, `tests/test_phase5_shadow_telemetry_persistence.py`, `tests/test_phase6_strategy_evidence_warehouse.py` |
| Docs | 1 | `docs/engineering/PHASE6_STRATEGY_EVIDENCE_WAREHOUSE_PLAN.md` |

## Live constants

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Min",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.2,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true
}
```

## Snapshot files

- Defaults: `artifacts/runtime_defaults_snapshot.json`
- Resolved config: `artifacts/resolved_config_snapshot.json`
- Live process: `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- 3 organism file(s) changed — require replay verification
