# Live Audit Index

Generated: 2026-05-10T21:47:17Z
PR: PR #6
SHA: `c2713939a1`
Branch: `codex/v13-phase2-expectancy`
Scope: **tooling/evidence_only**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 3 | `scripts/ci/check_wave_markers.py`, `scripts/ci/generate_audit_index.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 2 | `.github/pull_request_template.md`, `.github/workflows/pr-verify.yml` |
| Tests | 3 | `tests/test_artifact_change_scope.py`, `tests/test_runtime_snapshot_auth.py`, `tests/test_v12_w81_ci_cleanup.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PRE9D_IMPLEMENTATION_AUDIT_2026-05-10.md` |

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

- Evidence/tooling script changed only — no backend runtime or order-path behavior changed
