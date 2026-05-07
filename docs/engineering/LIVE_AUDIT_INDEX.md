# Live Audit Index

Generated: 2026-05-07T23:54:05Z
PR: PR #6
SHA: `68a48d7cd4`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/organism/candidate_shadow_telemetry.py` |
| Organism | 1 | `backend/organism/candidate_shadow_telemetry.py` |
| Scripts | 3 | `scripts/phase3_candidate_filter_fill_replay.py`, `scripts/phase3_candidate_filter_replay.py`, `scripts/phase8_replay_plan.py` |
| Tests | 4 | `tests/test_phase3_candidate_filter_fill_replay.py`, `tests/test_phase3_candidate_filter_replay.py`, `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase8_replay_plan.py` |
| Docs | 1 | `docs/engineering/LIVE_AUDIT_INDEX.md` |

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

- 1 organism file(s) changed — require replay verification
