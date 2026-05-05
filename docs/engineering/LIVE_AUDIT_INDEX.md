# Live Audit Index

Generated: 2026-05-05T06:53:24Z
PR: PR #6
SHA: `c07417bdad`
Branch: `codex/v13-phase2-expectancy`
Scope: **tooling/evidence_only**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 2 | `scripts/phase4_candidate_shadow_analysis.py`, `scripts/phase4_shadow_target_model.py` |
| Tests | 3 | `tests/test_artifact_change_scope.py`, `tests/test_phase4_candidate_shadow_analysis.py`, `tests/test_phase4_shadow_target_model.py` |
| Docs | 4 | `docs/engineering/PHASE3_STRATEGY_RESEARCH_PLAN.md`, `docs/engineering/PHASE4_CANDIDATE_SHADOW_ANALYSIS_REPORT.md`, `docs/engineering/PHASE4_SHADOW_ADVANCEMENT_PLAN.md`, `docs/engineering/PHASE4_SHADOW_TARGET_MODEL_REPORT.md` |

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

- Evidence/tooling script changed only — no backend runtime or order-path behavior changed
