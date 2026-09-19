# Live Audit Index

Generated: 2026-09-19T20:38:07Z
PR: n/a
SHA: `502b3c7b95`
Branch: `codex/nightly-test-harness`
Scope: **tooling/evidence_only**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 0 | none |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 14 | `tests/test_monday_ci_workflows.py`, `tests/test_organism_integration_smoke.py`, `tests/test_phase2_freeze.py`, `tests/test_reachability_v8.py`, `tests/test_strategy_engine_comprehensive.py`, `tests/test_v12_baseline_invariants.py`, `tests/test_v12_w75_lint_ratchet.py`, `tests/test_v12_w77_findings_ledger.py`, `tests/test_v12_w81_ci_cleanup.py`, `tests/test_wave37_fixes.py` |
| Docs | 1 | `docs/engineering/NIGHTLY_TEST_HARNESS_2026-09-19.md` |

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

- No code changes in this PR — verify evidence artifacts are current
