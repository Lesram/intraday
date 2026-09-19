# Live Audit Index

Generated: 2026-09-19T19:44:21Z
PR: PR #12
SHA: `0d1c93d53d`
Branch: `codex/monday-paper-readiness`
Scope: **backend_logic**
Change scope: `base` (`b2785b66bf39192273a115f002c498f2f159bdcb...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 6 | `backend/api/routes/market_data.py`, `backend/api/routes/paper_monitor.py`, `backend/api/routes/scanner.py`, `backend/api/routes_setup.py`, `backend/api/socketio_server.py`, `backend/infra/security.py` |
| Organism | 0 | none |
| Scripts | 10 | `scripts/ci/check_kpi_thresholds.py`, `scripts/ci/generate_artifacts.py`, `scripts/ops/paper_watchdog.py`, `scripts/ops/paper_watchdog.sh`, `scripts/research/paper_fill_reconciliation.py`, `scripts/runtime/INSTALL_BRAIN_BACKUP.md`, `scripts/runtime/backup/paper_database.py`, `scripts/runtime/com.intra.brain-backup.plist`, `scripts/runtime/rotate_brain_backup.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 5 | `.github/workflows/artifact-reporting.yml`, `.github/workflows/nightly.yml`, `.github/workflows/paper-postclose-audit.yml`, `.github/workflows/paper-readiness.yml`, `.github/workflows/pr-verify.yml` |
| Tests | 8 | `tests/test_artifact_workflow_contract.py`, `tests/test_monday_ci_workflows.py`, `tests/test_paper_backup_recovery.py`, `tests/test_paper_fill_reconciliation.py`, `tests/test_paper_monitor_access.py`, `tests/test_paper_watchdog.py`, `tests/test_position_reconciliation.py`, `tests/test_postclose_kpi_reporting.py` |
| Docs | 4 | `docs/engineering/MONDAY_CI_READINESS.md`, `docs/runbooks/PAPER_BACKUP_RECOVERY.md`, `docs/runbooks/PAPER_MONITORING.md`, `docs/runbooks/PAPER_UPTIME.md` |

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
  "drawdown_kill_pct": 0.1,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
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

- 6 backend runtime file(s) changed — require targeted verification
