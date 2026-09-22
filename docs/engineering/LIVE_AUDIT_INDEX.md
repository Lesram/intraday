# Live Audit Index

Generated: 2026-09-22T07:28:00Z
PR: n/a
SHA: `c9ad0dfc86`
Branch: `codex/session-evidence-repair`
Scope: **backend_logic**
Change scope: `base` (`ef3e895bd720524f433944725895d83e67d67905...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/infra/logging.py` |
| Organism | 0 | none |
| Scripts | 6 | `scripts/ci/generate_audit_index.py`, `scripts/ci/nightly_test_contract.py`, `scripts/ops/paper_daily_evidence.py`, `scripts/ops/paper_watchdog.py`, `scripts/ops/standdown_session_row.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 3 | `.github/workflows/artifact-reporting.yml`, `.github/workflows/nightly.yml`, `.github/workflows/paper-readiness.yml` |
| Tests | 11 | `tests/conftest.py`, `tests/test_api_fixture_isolation.py`, `tests/test_artifact_change_scope.py`, `tests/test_monday_ci_workflows.py`, `tests/test_nightly_test_contract.py`, `tests/test_paper_daily_evidence.py`, `tests/test_paper_watchdog.py`, `tests/test_runtime_snapshot_auth.py`, `tests/test_session_logging_contract.py`, `tests/test_strategies_automated_suite.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/SESSION_EVIDENCE_REPAIR.md` |

## Configuration resolution (not engine observation)

Source: `resolved_config_snapshot.json`
Evidence scope: `offline_source_and_process_defaults_not_runtime_observation`
These values describe this generator's configuration inputs. Offline runs can contain source defaults and test-process paths; they do not establish the installed paper configuration.

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

- Source/process defaults: `artifacts/runtime_defaults_snapshot.json`
- Expected configuration resolution: `artifacts/resolved_config_snapshot.json`
- Separate live-process evidence (check reachability and field provenance): `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- Displayed configuration is expected configuration, not observed engine state; inspect the separate live-process evidence and its reachability.
- 1 backend runtime file(s) changed — require targeted verification
