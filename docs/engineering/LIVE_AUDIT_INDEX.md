# Live Audit Index

Generated: 2026-05-10T17:25:59Z
PR: PR #6
SHA: `8e3ba92dfc`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Organism | 2 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py` |
| Scripts | 4 | `scripts/ci/generate_audit_index.py`, `scripts/deploy/rebuild_paper.sh`, `scripts/runtime/write_runtime_snapshot.py`, `scripts/phase9_shadow_evidence.py` |
| Tests | 3 | `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase5_shadow_outcome_join.py`, `tests/test_phase9_shadow_evidence.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/STRATEGY_REBUILD_MASTER_ROADMAP_2026-05-09.md` |

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
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": true,
  "strategy_evidence_telemetry_enabled": true,
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

- 2 organism file(s) changed — require replay verification
