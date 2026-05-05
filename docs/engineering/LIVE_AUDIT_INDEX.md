# Live Audit Index

Generated: 2026-05-05T05:58:41Z
PR: PR #6
SHA: `b69a12d40a`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Organism | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Scripts | 3 | `scripts/phase3_ml_target_redesign.py`, `scripts/phase3_timeframe_scout.py`, `scripts/runtime/write_runtime_snapshot.py` |
| Tests | 3 | `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase3_ml_target_redesign.py`, `tests/test_phase3_timeframe_scout.py` |
| Docs | 4 | `docs/engineering/PHASE3_CANDIDATE_SHADOW_TELEMETRY_REPORT.md`, `docs/engineering/PHASE3_ML_TARGET_REDESIGN_REPORT.md`, `docs/engineering/PHASE3_STRATEGY_RESEARCH_PLAN.md`, `docs/engineering/PHASE3_TIMEFRAME_SCOUT_REPORT.md` |

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
