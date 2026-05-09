# Live Audit Index

Generated: 2026-05-09T21:20:24Z
PR: PR #6
SHA: `db8675ebd6`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Organism | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Scripts | 1 | `scripts/runtime/write_runtime_snapshot.py` |
| Tests | 2 | `tests/test_organism_engine_scenarios.py`, `tests/test_phase3_candidate_shadow_telemetry.py` |
| Docs | 10 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_entry_breakdown.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_exit_breakdown.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_kpi_summary.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_model_quality.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_runtime_snapshot.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_signal_quality.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_trade_log.json`, `docs/engineering/paper_validation/2026-05-08-bff4e20/daily_trading_report.md` |

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

- 2 organism file(s) changed — require replay verification
