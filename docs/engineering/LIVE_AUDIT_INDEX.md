# Live Audit Index

Generated: 2026-09-23T07:07:46Z
PR: n/a
SHA: `bfc7c50ca3`
Branch: `codex/sept22-pipeline-repair`
Scope: **backend_logic**
Change scope: `base` (`f8bc52de1687f664278e8a8c032cb3aca4b39876...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 6 | `backend/infra/outbox_worker.py`, `backend/integrations/alpaca_broker.py`, `backend/integrations/alpaca_outbox.py`, `backend/organism/live_engine.py`, `backend/organism/market_scanner.py`, `backend/organism/streaming_data_provider.py` |
| Organism | 3 | `backend/organism/live_engine.py`, `backend/organism/market_scanner.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 4 | `scripts/ci/validate_checklist.py`, `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py`, `scripts/testing/performance_test.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 14 | `tests/test_adversarial_inputs_v7.py`, `tests/test_broker_ack_reconciliation.py`, `tests/test_developer_tool_credentials.py`, `tests/test_entry_freshness.py`, `tests/test_market_scanner.py`, `tests/test_market_scanner_provider_contract.py`, `tests/test_phase2_freeze.py`, `tests/test_pipeline_freshness_recovery.py`, `tests/test_pipeline_snapshot.py`, `tests/test_scanner_pipeline_integration.py` |
| Docs | 3 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/SESSION_PIPELINE_REPAIR.md` |

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
- 3 organism file(s) changed — require replay verification
