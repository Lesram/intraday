# Live Audit Index

> **Corrective candidate evidence:** source `a3b0c9359211d5b99f03fde09be9dce973d9297d`. The failed activation is retained; the operational cutoff stays `2026-09-21T10:10:39.684894+00:00`. The resolved/legacy snapshots now describe expected configuration from the stopped old container, not observed engine state. Source-default and archived offline-test snapshots are separate. Actual corrective activation/startup acceptance remains pending.


Generated: 2026-09-21T10:39:54Z
PR: n/a
SHA: `a3b0c93592`
Branch: `codex/paper-baseline-verification-repair`
Scope: **backend_logic**
Change scope: `base` (`ffc0e5c0595bb21e1c71f0ba7e5d6f55af7fc189...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 20 | `backend/api/routes/risk.py`, `backend/api/routes/settings.py`, `backend/organism/background_trainer.py`, `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/governance.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py` |
| Organism | 17 | `backend/organism/background_trainer.py`, `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/governance.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/model_fingerprint.py`, `backend/organism/operator_cancellation.py` |
| Scripts | 7 | `scripts/ci/check_frontend_preview.py`, `scripts/ops/paper_daily_evidence.py`, `scripts/ops/paper_daily_host.py`, `scripts/ops/paper_watchdog.py`, `scripts/ops/standdown_session_row.py`, `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 39 | `tests/test_apr10_patch_f4_forensic_guard.py`, `tests/test_apr7_p0_p1_fixes.py`, `tests/test_apr8_patch_a_force_save.py`, `tests/test_audit_0_2_bg_trainer_same_holdout.py`, `tests/test_audit_2_3_2_5_promotion_evolution.py`, `tests/test_audit_patch_queue_a.py`, `tests/test_audit_patch_queue_b1.py`, `tests/test_audit_patch_queue_b2.py`, `tests/test_audit_patch_queue_f3.py`, `tests/test_audit_patch_queue_f4.py` |
| Docs | 6 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/MONDAY_PREPARATION_2026-09-21.md`, `docs/engineering/OPERATIONS_EVIDENCE_RELEASE.md`, `docs/runbooks/PAPER_DAILY_EVIDENCE.md`, `docs/runbooks/PAPER_UPTIME.md` |

## Expected configuration from the stopped container

Evidence scope: **configuration resolution only; the engine has not been observed**. The inspected `intra-api-1` is stopped and still uses the failed prior image/source. The candidate remains source `a3b0c9359211d5b99f03fde09be9dce973d9297d`, image `sha256:a276b7d98e10aa9823acf6f2d8cea7ba0a85cee673de131ad84e0166bfe057b8`. The existing generator resolved the allowlisted saved `Config.Env` values against candidate code defaults without starting the container, reading models or contacting the API/broker.

[Resolution receipt](../../artifacts/operations_evidence/baseline_repair_snapshot_resolution_receipt.json) binds both container and candidate identities, approved baseline, settings allowlist and original/new snapshot hashes. The inspected configuration was unchanged throughout capture; it must be rechecked at installation. This is not proof of installed candidate behavior.

```json
{
  "timeframe": "1Min",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold_trades": 200,
  "evolution_freeze_until_trades": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.1,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": true,
  "phase9_shadow_engines_enabled": false
}
```

## Snapshot evidence boundaries

- [Source defaults / offline test generation](../../artifacts/runtime_defaults_snapshot.json): retained unchanged; its `1Day` default is not the installed timeframe.
- [Expected resolved configuration](../../artifacts/resolved_config_snapshot.json) and [legacy flat view](../../artifacts/runtime_config_snapshot.json): `1Min` comes from the stopped container's saved configuration. Both remain explicitly unverified against engine memory.
- [Actual-process snapshot](../../artifacts/live_process_runtime_snapshot.json): retained unchanged and unreachable; it supplies no runtime policy or readiness certification. Fresh actual-process acceptance is required after corrective startup.
- [Original offline resolved snapshot](../../artifacts/operations_evidence/baseline_repair_snapshot_offline_test_original_resolved_config_snapshot.json) and [original offline legacy snapshot](../../artifacts/operations_evidence/baseline_repair_snapshot_offline_test_original_runtime_config_snapshot.json): exact byte archives of the earlier `1Day` test-generated outputs.

The unchanged full-pack generator can regenerate `1Day`/default snapshots in hosted CI. Those hosted outputs are offline test evidence, not this stopped-container configuration capture and not actual-process observation. Their source and provenance must be kept distinct from this receipt.

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- 17 organism file(s) changed — require replay verification
