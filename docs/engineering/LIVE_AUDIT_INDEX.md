# Live Audit Index

Generated: 2026-09-19T19:15:53Z
PR: n/a
SHA: `75b1775fdf`
Branch: `codex/paper-partial-fill-accounting`
Scope: **backend_logic**
Change scope: `base` (`origin/intra-2.0-phase1...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py` |
| Organism | 3 | `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py` |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 2 | `tests/fixtures/paper_fill_accounting_forward_20260919.json`, `tests/test_live_engine_fill_accounting.py` |
| Docs | 0 | none |

## Live constants

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Day",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.05,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": false,
  "phase9_shadow_engines_enabled": false
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
