# Live Audit Index

Generated: 2026-05-05T02:48:33Z
PR: PR #6
SHA: `5fd85bfb67`
Branch: `codex/v13-phase2-expectancy`
Scope: **tooling/evidence_only**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Tests | 1 | `tests/test_phase3_orb_shadow_outcome.py` |
| Docs | 2 | `docs/engineering/PHASE3_ORB_SHADOW_OUTCOME_REPORT.md`, `docs/engineering/PHASE3_STRATEGY_RESEARCH_PLAN.md` |

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

- No code changes in this PR — verify evidence artifacts are current
