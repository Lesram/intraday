# Live Audit Index

Generated: 2026-05-09T21:29:38Z
PR: PR #6
SHA: `2fd9a67b86`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 14 | `backend/organism/brain_persistence.py`, `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/continuous_learner.py`, `backend/organism/evidence/__init__.py`, `backend/organism/evidence/benchmark_report.py`, `backend/organism/evidence/null_models.py`, `backend/organism/evidence/strategy_league.py`, `backend/organism/kelly_sizer.py`, `backend/organism/live_engine.py`, `backend/organism/schema/__init__.py` |
| Organism | 14 | `backend/organism/brain_persistence.py`, `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/continuous_learner.py`, `backend/organism/evidence/__init__.py`, `backend/organism/evidence/benchmark_report.py`, `backend/organism/evidence/null_models.py`, `backend/organism/evidence/strategy_league.py`, `backend/organism/kelly_sizer.py`, `backend/organism/live_engine.py`, `backend/organism/schema/__init__.py` |
| Scripts | 0 | none |
| Tests | 1 | `tests/test_phase9_strategy_governance.py` |
| Docs | 4 | `docs/engineering/DEEP_RESEARCH_STRATEGY_ACTION_PLAN_2026-05-09.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/STRATEGY_AUTOPSY_2026-05-09.md`, `docs/engineering/STRATEGY_REBUILD_MASTER_ROADMAP_2026-05-09.md` |

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

- 14 organism file(s) changed — require replay verification
