# Live Audit Index

Generated: 2026-10-18T18:33:28Z
PR: n/a
SHA: `71d1669829`
Branch: `release/combined-audit-2026-10`
Scope: **backend_logic**
Change scope: `base` (`6a56d753...HEAD`)

## Changed files

Total distinct changed files: **91**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 25 | `backend/api/lifespan.py`, `backend/api/logging_setup.py`, `backend/api/routes/auth.py`, `backend/api/socketio_server.py`, `backend/infra/outbox_worker.py`, `backend/infra/repositories/orders.py`, `backend/infra/security.py`, `backend/infra/users.py`, `backend/integrations/alpaca_broker.py`, `backend/integrations/alpaca_outbox.py` |
| Scripts | 5 | `scripts/db/create_admin_user.py`, `scripts/db/phase7_data_integrity_remediation.py`, `scripts/generate_experiment_observation_report.py`, `scripts/ops/check_brain_pickles_signed.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 0 | none |
| Tests | 24 | `tests/test_apr8_patch_e_trained_state_guard.py`, `tests/test_audit_20261005_brain_crash_safety.py`, `tests/test_audit_20261005_close_accounting_unblock.py`, `tests/test_audit_20261005_outbox_dispatch_guards.py`, `tests/test_audit_20261005_session_log_hardening.py`, `tests/test_audit_20261005_surface_dispatch_lifecycle.py`, `tests/test_audit_20261005_surface_exit_safety.py`, `tests/test_audit_20261005_surface_external_close.py`, `tests/test_audit_20261005_surface_regime_isolation.py`, `tests/test_audit_20261005_surface_stream_history.py` |
| Docs | 7 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/OPERATIONS_EVIDENCE_RELEASE.md`, `docs/runbooks/PAPER_BACKUP_RECOVERY.md`, `docs/runbooks/PAPER_UPTIME.md`, `docs/setup/AUTHENTICATION.md`, `docs/setup/QUICK_START.md` |
| Artifacts/evidence | 30 | `artifacts/algorithm_improvements.junit.xml`, `artifacts/algorithm_improvements.log`, `artifacts/changed_files.json`, `artifacts/live_process_runtime_snapshot.json`, `artifacts/multi_tick_state.junit.xml`, `artifacts/multi_tick_state.log`, `artifacts/organism_engine_scenarios.junit.xml`, `artifacts/organism_engine_scenarios.log`, `artifacts/organism_live_engine.junit.xml`, `artifacts/organism_live_engine.log` |
| Reports | 0 | none |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **9** file(s).

### Full changed-file list

- `artifacts/algorithm_improvements.junit.xml`
- `artifacts/algorithm_improvements.log`
- `artifacts/changed_files.json`
- `artifacts/live_process_runtime_snapshot.json`
- `artifacts/multi_tick_state.junit.xml`
- `artifacts/multi_tick_state.log`
- `artifacts/organism_engine_scenarios.junit.xml`
- `artifacts/organism_engine_scenarios.log`
- `artifacts/organism_live_engine.junit.xml`
- `artifacts/organism_live_engine.log`
- `artifacts/phase2/candidate_param_freeze.json`
- `artifacts/replay_simulator.junit.xml`
- `artifacts/replay_simulator.log`
- `artifacts/replay_summary.json`
- `artifacts/resolved_config_snapshot.json`
- `artifacts/runtime_config_snapshot.json`
- `artifacts/runtime_defaults_snapshot.json`
- `artifacts/runtime_snapshot.log`
- `artifacts/runtime_snapshot_summary.json`
- `artifacts/safety_invariants.junit.xml`
- `artifacts/safety_invariants.log`
- `artifacts/self_evolution.junit.xml`
- `artifacts/self_evolution.log`
- `artifacts/semantic_invariants.junit.xml`
- `artifacts/semantic_invariants.log`
- `artifacts/semantic_invariants_summary.json`
- `artifacts/spec_drift.log`
- `artifacts/spec_drift_summary.json`
- `artifacts/task_report.json`
- `artifacts/test_summary.json`
- `backend/api/lifespan.py`
- `backend/api/logging_setup.py`
- `backend/api/routes/auth.py`
- `backend/api/socketio_server.py`
- `backend/infra/outbox_worker.py`
- `backend/infra/repositories/orders.py`
- `backend/infra/security.py`
- `backend/infra/users.py`
- `backend/integrations/alpaca_broker.py`
- `backend/integrations/alpaca_outbox.py`
- `backend/integrations/alpaca_stream.py`
- `backend/organism/brain_persistence.py`
- `backend/organism/ensemble_models.py`
- `backend/organism/live_engine.py`
- `backend/organism/live_engine_data.py`
- `backend/organism/live_engine_fills.py`
- `backend/organism/operator_cancellation.py`
- `backend/organism/phase2_gate.py`
- `backend/organism/regime.py`
- `backend/organism/streaming_data_provider.py`
- `backend/services/order_recovery_service.py`
- `backend/services/positions_service.py`
- `backend/utils/log_redaction.py`
- `backend/utils/logger.py`
- `backend/utils/secure_pickle.py`
- `docs/architecture/mapss.md`
- `docs/engineering/LIVE_AUDIT_INDEX.md`
- `docs/engineering/OPERATIONS_EVIDENCE_RELEASE.md`
- `docs/runbooks/PAPER_BACKUP_RECOVERY.md`
- `docs/runbooks/PAPER_UPTIME.md`
- `docs/setup/AUTHENTICATION.md`
- `docs/setup/QUICK_START.md`
- `scripts/db/create_admin_user.py`
- `scripts/db/phase7_data_integrity_remediation.py`
- `scripts/generate_experiment_observation_report.py`
- `scripts/ops/check_brain_pickles_signed.py`
- `scripts/runtime/write_runtime_snapshot.py`
- `tests/test_apr8_patch_e_trained_state_guard.py`
- `tests/test_audit_20261005_brain_crash_safety.py`
- `tests/test_audit_20261005_close_accounting_unblock.py`
- `tests/test_audit_20261005_outbox_dispatch_guards.py`
- `tests/test_audit_20261005_session_log_hardening.py`
- `tests/test_audit_20261005_surface_dispatch_lifecycle.py`
- `tests/test_audit_20261005_surface_exit_safety.py`
- `tests/test_audit_20261005_surface_external_close.py`
- `tests/test_audit_20261005_surface_regime_isolation.py`
- `tests/test_audit_20261005_surface_stream_history.py`
- `tests/test_external_close_lot_repair_postgres.py`
- `tests/test_fill_accounting_postgres.py`
- `tests/test_multi_tick_state.py`
- `tests/test_paper_daily_evidence.py`
- `tests/test_phase2_gate.py`
- `tests/test_phase3_attribution_report.py`
- `tests/test_phase7_data_integrity_remediation.py`
- `tests/test_safety_invariants.py`
- `tests/test_streaming_subscription_acknowledgement.py`
- `tests/test_v12_baseline_invariants.py`
- `tests/test_v13_w100_live_tick_coverage.py`
- `tests/test_wave50_fixes.py`
- `tests/unit/test_api_auth_routes_comprehensive.py`
- `tests/unit/test_streaming_data_provider.py`

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
- 9 organism file(s) changed — require replay verification
