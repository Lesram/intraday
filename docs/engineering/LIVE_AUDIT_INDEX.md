# Live Audit Index

Generated: 2026-05-11T01:22:26Z
PR: n/a
SHA: `27381ff6fc`
Branch: `codex/platform-truth-audit-fixes`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 5 | `backend/api/routes/deploy_health.py`, `backend/infra/runtime_identity.py`, `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py`, `backend/organism/routes.py` |
| Organism | 3 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/live_engine.py`, `backend/organism/routes.py` |
| Scripts | 2 | `scripts/ci/platform_truth_observer.py`, `scripts/phase8_evidence_warehouse.py` |
| CI | 0 | none |
| Tests | 6 | `tests/test_organism_maintenance_routes.py`, `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase8_evidence_warehouse.py`, `tests/test_phase9_strategy_governance.py`, `tests/test_platform_truth_observer.py`, `tests/test_v12_w82_dockerfile_env.py` |
| Docs | 3 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PLATFORM_TRUTH_AUDIT_FIX_REPORT_2026-05-10.md` |

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
  "phase9_shadow_engines_enabled": true
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
