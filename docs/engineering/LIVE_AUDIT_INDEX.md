# Live Audit Index

Generated: 2026-09-22T06:25:41Z
PR: n/a
SHA: `f7894af675`
Branch: `codex/session-evidence-repair`
Scope: **backend_logic**
Change scope: `base` (`ef3e895bd720524f433944725895d83e67d67905...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/infra/logging.py` |
| Organism | 0 | none |
| Scripts | 4 | `scripts/ci/nightly_test_contract.py`, `scripts/ops/paper_daily_evidence.py`, `scripts/ops/paper_watchdog.py`, `scripts/ops/standdown_session_row.py` |
| CI | 3 | `.github/workflows/artifact-reporting.yml`, `.github/workflows/nightly.yml`, `.github/workflows/paper-readiness.yml` |
| Tests | 9 | `tests/conftest.py`, `tests/test_api_fixture_isolation.py`, `tests/test_monday_ci_workflows.py`, `tests/test_nightly_test_contract.py`, `tests/test_paper_daily_evidence.py`, `tests/test_paper_watchdog.py`, `tests/test_session_logging_contract.py`, `tests/test_strategies_automated_suite.py`, `tests/test_v12_w84_governance_docs.py` |
| Docs | 1 | `docs/engineering/SESSION_EVIDENCE_REPAIR.md` |

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

- 1 backend runtime file(s) changed — require targeted verification
