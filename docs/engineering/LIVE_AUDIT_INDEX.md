# Live Audit Index

Generated: 2026-09-25T05:14:09Z
PR: n/a
SHA: `7e63a494b9`
Branch: `codex/session-streaming-readiness`
Scope: **backend_logic**
Change scope: `base` (`a69949a216fdcb6a7f210933f885b3cabafd1ae0...HEAD`)

## Changed files

Total distinct changed files: **29**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 6 | `backend/api/routes/health.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_data.py`, `backend/organism/pipeline_diagnostics.py`, `backend/organism/scheduler.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 4 | `scripts/diagnostics/profile_paper_pipeline.py`, `scripts/ops/paper_watchdog.py`, `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 10 | `tests/test_entry_freshness.py`, `tests/test_paper_watchdog.py`, `tests/test_phase2_freeze.py`, `tests/test_pipeline_diagnostics.py`, `tests/test_pipeline_freshness_recovery.py`, `tests/test_pipeline_profile.py`, `tests/test_pipeline_snapshot.py`, `tests/test_readiness_contract.py`, `tests/test_scanner_streaming_integration.py`, `tests/test_v13_w100_live_tick_coverage.py` |
| Docs | 2 | `docs/architecture/mapss.md`, `docs/engineering/STREAMING_READINESS_REPAIR.md` |
| Artifacts/evidence | 4 | `artifacts/monday_readiness/frozen_surface_reference.json`, `artifacts/phase2/candidate_param_freeze.json`, `artifacts/phase2/param_freeze.json`, `artifacts/streaming_readiness_repair/plan.json` |
| Reports | 2 | `reports/session_review_2026-09-24/SESSION_REVIEW.md`, `reports/session_review_2026-09-24/metrics.json` |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **5** file(s).

### Full changed-file list

- `.github/workflows/paper-readiness.yml`
- `artifacts/monday_readiness/frozen_surface_reference.json`
- `artifacts/phase2/candidate_param_freeze.json`
- `artifacts/phase2/param_freeze.json`
- `artifacts/streaming_readiness_repair/plan.json`
- `backend/api/routes/health.py`
- `backend/organism/live_engine.py`
- `backend/organism/live_engine_data.py`
- `backend/organism/pipeline_diagnostics.py`
- `backend/organism/scheduler.py`
- `backend/organism/streaming_data_provider.py`
- `docs/architecture/mapss.md`
- `docs/engineering/STREAMING_READINESS_REPAIR.md`
- `reports/session_review_2026-09-24/SESSION_REVIEW.md`
- `reports/session_review_2026-09-24/metrics.json`
- `scripts/diagnostics/profile_paper_pipeline.py`
- `scripts/ops/paper_watchdog.py`
- `scripts/phase2_freeze.py`
- `scripts/runtime/write_runtime_snapshot.py`
- `tests/test_entry_freshness.py`
- `tests/test_paper_watchdog.py`
- `tests/test_phase2_freeze.py`
- `tests/test_pipeline_diagnostics.py`
- `tests/test_pipeline_freshness_recovery.py`
- `tests/test_pipeline_profile.py`
- `tests/test_pipeline_snapshot.py`
- `tests/test_readiness_contract.py`
- `tests/test_scanner_streaming_integration.py`
- `tests/test_v13_w100_live_tick_coverage.py`

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
- 5 organism file(s) changed — require replay verification
