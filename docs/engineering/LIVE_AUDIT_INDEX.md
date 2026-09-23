# Live Audit Index

Generated: 2026-09-23T07:57:20Z
PR: PR #28
SHA: `3f20cea30b`
Branch: `codex/sept22-pipeline-repair`
Scope: **backend_logic**
Change scope: `range` (`f8bc52de1687f664278e8a8c032cb3aca4b39876`)

## Changed files

Total distinct changed files: **320**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 7 | `backend/infra/outbox_worker.py`, `backend/integrations/alpaca_broker.py`, `backend/integrations/alpaca_outbox.py`, `backend/organism/freeze_contract.py`, `backend/organism/live_engine.py`, `backend/organism/market_scanner.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 10 | `scripts/ci/generate_audit_index.py`, `scripts/ci/validate_checklist.py`, `scripts/ops/paper_daily_evidence.py`, `scripts/ops/paper_daily_host.py`, `scripts/phase2_freeze.py`, `scripts/phase2_gate.py`, `scripts/phase3_attribution_report.py`, `scripts/research/paper_fill_reconciliation.py`, `scripts/runtime/write_runtime_snapshot.py`, `scripts/testing/performance_test.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 17 | `tests/test_active_freeze_contract.py`, `tests/test_adversarial_inputs_v7.py`, `tests/test_artifact_change_scope.py`, `tests/test_broker_ack_reconciliation.py`, `tests/test_developer_tool_credentials.py`, `tests/test_entry_freshness.py`, `tests/test_market_scanner.py`, `tests/test_market_scanner_provider_contract.py`, `tests/test_phase2_freeze.py`, `tests/test_pipeline_freshness_recovery.py` |
| Docs | 3 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/SESSION_PIPELINE_REPAIR.md` |
| Artifacts/evidence | 281 | `artifacts/algorithm_improvements.junit.xml`, `artifacts/algorithm_improvements.log`, `artifacts/changed_files.json`, `artifacts/live_process_runtime_snapshot.json`, `artifacts/monday_readiness/frozen_surface_reference.json`, `artifacts/multi_tick_state.junit.xml`, `artifacts/multi_tick_state.log`, `artifacts/organism_engine_scenarios.junit.xml`, `artifacts/organism_engine_scenarios.log`, `artifacts/organism_live_engine.junit.xml` |
| Reports | 1 | `reports/comprehensive_audit_findings.jsonl` |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **4** file(s).

### Full changed-file list

- `.github/workflows/paper-readiness.yml`
- `artifacts/algorithm_improvements.junit.xml`
- `artifacts/algorithm_improvements.log`
- `artifacts/changed_files.json`
- `artifacts/live_process_runtime_snapshot.json`
- `artifacts/monday_readiness/frozen_surface_reference.json`
- `artifacts/multi_tick_state.junit.xml`
- `artifacts/multi_tick_state.log`
- `artifacts/organism_engine_scenarios.junit.xml`
- `artifacts/organism_engine_scenarios.log`
- `artifacts/organism_live_engine.junit.xml`
- `artifacts/organism_live_engine.log`
- `artifacts/phase2/candidate_param_freeze.json`
- `artifacts/phase2/param_freeze.json`
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
- `artifacts/session_pipeline_repair/active_configuration_reference.json`
- `artifacts/session_pipeline_repair/active_preservation.json`
- `artifacts/session_pipeline_repair/audit_index_complete_inventory.json`
- `artifacts/session_pipeline_repair/audit_index_complete_inventory.log`
- `artifacts/session_pipeline_repair/audit_index_complete_inventory.xml`
- `artifacts/session_pipeline_repair/audit_index_independent_review.json`
- `artifacts/session_pipeline_repair/audit_index_repair_implementation.json`
- `artifacts/session_pipeline_repair/audit_index_repair_plan.json`
- `artifacts/session_pipeline_repair/broker_ack_accepted_candidate.json`
- `artifacts/session_pipeline_repair/broker_ack_accepted_candidate.log`
- `artifacts/session_pipeline_repair/broker_ack_accepted_candidate.xml`
- `artifacts/session_pipeline_repair/broker_ack_final.json`
- `artifacts/session_pipeline_repair/broker_ack_final.log`
- `artifacts/session_pipeline_repair/broker_ack_final.xml`
- `artifacts/session_pipeline_repair/broker_ack_first.json`
- `artifacts/session_pipeline_repair/broker_ack_first.log`
- `artifacts/session_pipeline_repair/broker_ack_first.xml`
- `artifacts/session_pipeline_repair/broker_ack_implementation.json`
- `artifacts/session_pipeline_repair/broker_ack_independent_proof.log`
- `artifacts/session_pipeline_repair/broker_ack_independent_proof.xml`
- `artifacts/session_pipeline_repair/broker_ack_independent_review.json`
- `artifacts/session_pipeline_repair/broker_ack_lint_delta.json`
- `artifacts/session_pipeline_repair/broker_ack_plan.json`
- `artifacts/session_pipeline_repair/broker_ack_required.json`
- `artifacts/session_pipeline_repair/broker_ack_required.log`
- `artifacts/session_pipeline_repair/broker_ack_required.xml`
- `artifacts/session_pipeline_repair/broker_ack_required_fixed.json`
- `artifacts/session_pipeline_repair/broker_ack_required_fixed.log`
- `artifacts/session_pipeline_repair/broker_ack_required_fixed.xml`
- `artifacts/session_pipeline_repair/broker_ack_review_final.json`
- `artifacts/session_pipeline_repair/broker_ack_review_final.log`
- `artifacts/session_pipeline_repair/broker_ack_review_final.xml`
- `artifacts/session_pipeline_repair/candidate_freeze_builder.py`
- `artifacts/session_pipeline_repair/candidate_freeze_receipt.json`
- `artifacts/session_pipeline_repair/combined.json`
- `artifacts/session_pipeline_repair/combined.log`
- `artifacts/session_pipeline_repair/combined.xml`
- `artifacts/session_pipeline_repair/combined_corrected.json`
- `artifacts/session_pipeline_repair/combined_corrected.log`
- `artifacts/session_pipeline_repair/combined_corrected.xml`
- `artifacts/session_pipeline_repair/config_and_reconciliation.json`
- `artifacts/session_pipeline_repair/config_and_reconciliation.log`
- `artifacts/session_pipeline_repair/config_and_reconciliation.xml`
- `artifacts/session_pipeline_repair/expanded_committed_freeze.json`
- `artifacts/session_pipeline_repair/expanded_committed_freeze.log`
- `artifacts/session_pipeline_repair/expanded_freeze_verifier.py`
- `artifacts/session_pipeline_repair/expanded_helper_static.json`
- `artifacts/session_pipeline_repair/expanded_isolated_test_runner.py`
- `artifacts/session_pipeline_repair/expanded_pack_acceptance_review.json`
- `artifacts/session_pipeline_repair/expanded_scope_freeze.json`
- `artifacts/session_pipeline_repair/expanded_scope_freeze.log`
- `artifacts/session_pipeline_repair/expanded_static/security_bandit_base.log`
- `artifacts/session_pipeline_repair/expanded_static/security_bandit_delta.json`
- `artifacts/session_pipeline_repair/expanded_static/security_bandit_head.log`
- `artifacts/session_pipeline_repair/expanded_static/security_gitleaks_redacted.json`
- `artifacts/session_pipeline_repair/expanded_static/security_gitleaks_redacted.log`
- `artifacts/session_pipeline_repair/expanded_static/security_ruff_delta.json`
- `artifacts/session_pipeline_repair/expanded_static/security_scan_receipt.json`
- `artifacts/session_pipeline_repair/expanded_static/static_disposition.json`
- `artifacts/session_pipeline_repair/expanded_static/static_review.json`
- `artifacts/session_pipeline_repair/expanded_static_reproducer.py`
- `artifacts/session_pipeline_repair/final_dependency_scope_note.json`
- `artifacts/session_pipeline_repair/final_expanded_freeze.json`
- `artifacts/session_pipeline_repair/final_expanded_freeze.log`
- `artifacts/session_pipeline_repair/final_expanded_head_verification.json`
- `artifacts/session_pipeline_repair/final_expanded_secret_disposition.json`
- `artifacts/session_pipeline_repair/final_followup_candidate_contract.json`
- `artifacts/session_pipeline_repair/final_followup_candidate_contract.log`
- `artifacts/session_pipeline_repair/final_followup_candidate_contract.xml`
- `artifacts/session_pipeline_repair/final_head_verification.json`
- `artifacts/session_pipeline_repair/final_secret_scan.json`
- `artifacts/session_pipeline_repair/final_secret_scan.log`
- `artifacts/session_pipeline_repair/final_secret_scan_receipt.json`
- `artifacts/session_pipeline_repair/followup_config_broker.json`
- `artifacts/session_pipeline_repair/followup_config_broker.log`
- `artifacts/session_pipeline_repair/followup_config_broker.xml`
- `artifacts/session_pipeline_repair/followup_delivery_manifest.json`
- `artifacts/session_pipeline_repair/followup_pack_acceptance_review.json`
- `artifacts/session_pipeline_repair/followup_root_contract.json`
- `artifacts/session_pipeline_repair/followup_root_contract.log`
- `artifacts/session_pipeline_repair/followup_root_contract.xml`
- `artifacts/session_pipeline_repair/followup_static/security_bandit_base.log`
- `artifacts/session_pipeline_repair/followup_static/security_bandit_delta.json`
- `artifacts/session_pipeline_repair/followup_static/security_bandit_head.log`
- `artifacts/session_pipeline_repair/followup_static/security_gitleaks_redacted.json`
- `artifacts/session_pipeline_repair/followup_static/security_gitleaks_redacted.log`
- `artifacts/session_pipeline_repair/followup_static/security_ruff_delta.json`
- `artifacts/session_pipeline_repair/followup_static/security_scan_receipt.json`
- `artifacts/session_pipeline_repair/followup_static/static_disposition.json`
- `artifacts/session_pipeline_repair/followup_static/static_review.json`
- `artifacts/session_pipeline_repair/freeze_and_stale_exit.json`
- `artifacts/session_pipeline_repair/freeze_and_stale_exit.log`
- `artifacts/session_pipeline_repair/freeze_and_stale_exit.xml`
- `artifacts/session_pipeline_repair/freeze_authority_independent_acceptance.json`
- `artifacts/session_pipeline_repair/freeze_authority_independent_review.json`
- `artifacts/session_pipeline_repair/freeze_authority_independent_review.log`
- `artifacts/session_pipeline_repair/freeze_authority_independent_review.xml`
- `artifacts/session_pipeline_repair/freshness_implementation.json`
- `artifacts/session_pipeline_repair/freshness_review.json`
- `artifacts/session_pipeline_repair/freshness_review_stale_exit_addendum.json`
- `artifacts/session_pipeline_repair/freshness_stale_exit.xml`
- `artifacts/session_pipeline_repair/freshness_targeted.xml`
- `artifacts/session_pipeline_repair/full.json`
- `artifacts/session_pipeline_repair/full.log`
- `artifacts/session_pipeline_repair/full_expanded_candidate.json`
- `artifacts/session_pipeline_repair/full_expanded_candidate.log`
- `artifacts/session_pipeline_repair/full_review_followup.json`
- `artifacts/session_pipeline_repair/full_review_followup.log`
- `artifacts/session_pipeline_repair/full_stable_source.json`
- `artifacts/session_pipeline_repair/full_stable_source.log`
- `artifacts/session_pipeline_repair/hygiene_acceptance.json`
- `artifacts/session_pipeline_repair/hygiene_acceptance.log`
- `artifacts/session_pipeline_repair/hygiene_acceptance.xml`
- `artifacts/session_pipeline_repair/index.json`
- `artifacts/session_pipeline_repair/index.log`
- `artifacts/session_pipeline_repair/index_expanded_candidate.json`
- `artifacts/session_pipeline_repair/index_expanded_candidate.log`
- `artifacts/session_pipeline_repair/index_stable_source.json`
- `artifacts/session_pipeline_repair/index_stable_source.log`
- `artifacts/session_pipeline_repair/initial_full_replay_summary.json`
- `artifacts/session_pipeline_repair/initial_full_semantic_invariants_summary.json`
- `artifacts/session_pipeline_repair/initial_full_spec_drift_summary.json`
- `artifacts/session_pipeline_repair/initial_full_task_report.json`
- `artifacts/session_pipeline_repair/initial_full_test_summary.json`
- `artifacts/session_pipeline_repair/intra-scanner-implementation-plan.json`
- `artifacts/session_pipeline_repair/intra-scanner-implementation.json`
- `artifacts/session_pipeline_repair/intra-scanner-provider-red.log`
- `artifacts/session_pipeline_repair/intra-scanner-provider-red.xml`
- `artifacts/session_pipeline_repair/intra-scanner-safe-test.py`
- `artifacts/session_pipeline_repair/intra-scanner-targeted.log`
- `artifacts/session_pipeline_repair/intra-scanner-targeted.xml`
- `artifacts/session_pipeline_repair/intra-scanner-volume-regression.log`
- `artifacts/session_pipeline_repair/intra-scanner-volume-regression.xml`
- `artifacts/session_pipeline_repair/isolated_test_runner.py`
- `artifacts/session_pipeline_repair/pack_acceptance_review.json`
- `artifacts/session_pipeline_repair/plan.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/implementation.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/independent_review.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/initial_implementation.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/initial_tests.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/manifest.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/plan.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/candidate_image/followup_builder/tests.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/evidence_manifest.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/evidence_secret_check.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/freeze.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/implementation.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/independent_review.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/plan.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/red.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/red.xml`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/report_redaction.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/root_plan.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/ruff.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/targeted.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/credential_hygiene/targeted.xml`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/implementation.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/independent_review.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/plan.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/ruff.json`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/targeted.log`
- `artifacts/session_pipeline_repair/post_commit_evidence/freeze_contract/targeted.xml`
- `artifacts/session_pipeline_repair/post_commit_evidence/stale_attribution.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/active_scanner_config.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/base_offline.log`
- `artifacts/session_pipeline_repair/provider_contract_probe/base_result.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/candidate_offline.log`
- `artifacts/session_pipeline_repair/provider_contract_probe/candidate_result.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/candidate_snapshot_age.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/capture.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/most_actives.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/movers.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/plan.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/report.json`
- `artifacts/session_pipeline_repair/provider_contract_probe/snapshots.json`
- `artifacts/session_pipeline_repair/provider_restart_implementation.json`
- `artifacts/session_pipeline_repair/provider_restart_independent_review.json`
- `artifacts/session_pipeline_repair/provider_restart_lint_delta.json`
- `artifacts/session_pipeline_repair/provider_restart_plan.json`
- `artifacts/session_pipeline_repair/provider_restart_red.log`
- `artifacts/session_pipeline_repair/provider_restart_red.xml`
- `artifacts/session_pipeline_repair/provider_restart_regression.log`
- `artifacts/session_pipeline_repair/provider_restart_regression.xml`
- `artifacts/session_pipeline_repair/provider_restart_ruff.json`
- `artifacts/session_pipeline_repair/provider_restart_stable.log`
- `artifacts/session_pipeline_repair/provider_restart_stable.xml`
- `artifacts/session_pipeline_repair/provider_restart_targeted.log`
- `artifacts/session_pipeline_repair/provider_restart_targeted.xml`
- `artifacts/session_pipeline_repair/review_followup_freeze.json`
- `artifacts/session_pipeline_repair/review_followup_plan.json`
- `artifacts/session_pipeline_repair/root_scope_review.json`
- `artifacts/session_pipeline_repair/root_snapshot.json`
- `artifacts/session_pipeline_repair/root_snapshot.log`
- `artifacts/session_pipeline_repair/root_snapshot.xml`
- `artifacts/session_pipeline_repair/scanner_complete_outcome_final.json`
- `artifacts/session_pipeline_repair/scanner_complete_outcome_final.log`
- `artifacts/session_pipeline_repair/scanner_complete_outcome_final.xml`
- `artifacts/session_pipeline_repair/scanner_complete_outcome_implementation.json`
- `artifacts/session_pipeline_repair/scanner_empty_bookkeeping_red.json`
- `artifacts/session_pipeline_repair/scanner_empty_bookkeeping_red.log`
- `artifacts/session_pipeline_repair/scanner_empty_bookkeeping_red.xml`
- `artifacts/session_pipeline_repair/scanner_explicit_outcome.json`
- `artifacts/session_pipeline_repair/scanner_explicit_outcome.log`
- `artifacts/session_pipeline_repair/scanner_explicit_outcome.xml`
- `artifacts/session_pipeline_repair/scanner_integration_initial.log`
- `artifacts/session_pipeline_repair/scanner_integration_initial.xml`
- `artifacts/session_pipeline_repair/scanner_integration_second.log`
- `artifacts/session_pipeline_repair/scanner_integration_second.xml`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome.json`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome.log`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome.xml`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome_final.json`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome_final.log`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome_final.xml`
- `artifacts/session_pipeline_repair/scanner_malformed_outcome_implementation.json`
- `artifacts/session_pipeline_repair/scanner_outcome_final.json`
- `artifacts/session_pipeline_repair/scanner_outcome_final.log`
- `artifacts/session_pipeline_repair/scanner_outcome_final.xml`
- `artifacts/session_pipeline_repair/scanner_outcome_implementation.json`
- `artifacts/session_pipeline_repair/scanner_outcome_independent_review.json`
- `artifacts/session_pipeline_repair/scanner_outcome_integration.json`
- `artifacts/session_pipeline_repair/scanner_outcome_integration.log`
- `artifacts/session_pipeline_repair/scanner_outcome_integration.xml`
- `artifacts/session_pipeline_repair/scanner_review.json`
- `artifacts/session_pipeline_repair/scanner_transport_bookkeeping_red.json`
- `artifacts/session_pipeline_repair/scanner_transport_bookkeeping_red.log`
- `artifacts/session_pipeline_repair/scanner_transport_bookkeeping_red.xml`
- `artifacts/session_pipeline_repair/security_bandit_base.log`
- `artifacts/session_pipeline_repair/security_bandit_delta.json`
- `artifacts/session_pipeline_repair/security_bandit_head.log`
- `artifacts/session_pipeline_repair/security_gitleaks_redacted.json`
- `artifacts/session_pipeline_repair/security_gitleaks_redacted.log`
- `artifacts/session_pipeline_repair/security_ruff_delta.json`
- `artifacts/session_pipeline_repair/security_scan_receipt.json`
- `artifacts/session_pipeline_repair/static_review.json`
- `artifacts/session_pipeline_repair/w100_combined_initial.log`
- `artifacts/session_pipeline_repair/w100_combined_initial.xml`
- `artifacts/session_pipeline_repair/w100_final.log`
- `artifacts/session_pipeline_repair/w100_final.xml`
- `artifacts/session_pipeline_repair/w100_implementation.json`
- `artifacts/session_pipeline_repair/w100_initial.log`
- `artifacts/session_pipeline_repair/w100_initial.xml`
- `artifacts/session_pipeline_repair/w100_plan.json`
- `artifacts/session_pipeline_repair/w100_prior_hosted.json`
- `artifacts/session_pipeline_repair/w100_ruff.json`
- `artifacts/session_pipeline_repair/w100_second.log`
- `artifacts/session_pipeline_repair/w100_second.xml`
- `artifacts/session_pipeline_repair/w100_third.log`
- `artifacts/session_pipeline_repair/w100_third.xml`
- `artifacts/spec_drift.log`
- `artifacts/spec_drift_summary.json`
- `artifacts/task_report.json`
- `artifacts/test_summary.json`
- `backend/infra/outbox_worker.py`
- `backend/integrations/alpaca_broker.py`
- `backend/integrations/alpaca_outbox.py`
- `backend/organism/freeze_contract.py`
- `backend/organism/live_engine.py`
- `backend/organism/market_scanner.py`
- `backend/organism/streaming_data_provider.py`
- `docs/architecture/mapss.md`
- `docs/engineering/LIVE_AUDIT_INDEX.md`
- `docs/engineering/SESSION_PIPELINE_REPAIR.md`
- `reports/comprehensive_audit_findings.jsonl`
- `scripts/ci/generate_audit_index.py`
- `scripts/ci/validate_checklist.py`
- `scripts/ops/paper_daily_evidence.py`
- `scripts/ops/paper_daily_host.py`
- `scripts/phase2_freeze.py`
- `scripts/phase2_gate.py`
- `scripts/phase3_attribution_report.py`
- `scripts/research/paper_fill_reconciliation.py`
- `scripts/runtime/write_runtime_snapshot.py`
- `scripts/testing/performance_test.py`
- `tests/test_active_freeze_contract.py`
- `tests/test_adversarial_inputs_v7.py`
- `tests/test_artifact_change_scope.py`
- `tests/test_broker_ack_reconciliation.py`
- `tests/test_developer_tool_credentials.py`
- `tests/test_entry_freshness.py`
- `tests/test_market_scanner.py`
- `tests/test_market_scanner_provider_contract.py`
- `tests/test_phase2_freeze.py`
- `tests/test_pipeline_freshness_recovery.py`
- `tests/test_pipeline_snapshot.py`
- `tests/test_scanner_pipeline_integration.py`
- `tests/test_streaming_provider_lifecycle.py`
- `tests/test_v12_baseline_invariants.py`
- `tests/test_v13_w100_live_tick_coverage.py`
- `tests/unit/test_alpaca_outbox_comprehensive.py`
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
- 4 organism file(s) changed — require replay verification
