# Live Audit Index

Generated: 2026-09-23T05:55:24Z
PR: n/a
SHA: `332cb6babc`
Branch: `codex/sept22-pipeline-repair`
Scope: **backend_logic**
Change scope: `base` (`f8bc52de1687f664278e8a8c032cb3aca4b39876...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/organism/live_engine.py`, `backend/organism/market_scanner.py`, `backend/organism/streaming_data_provider.py` |
| Organism | 3 | `backend/organism/live_engine.py`, `backend/organism/market_scanner.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 2 | `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 10 | `tests/test_entry_freshness.py`, `tests/test_market_scanner.py`, `tests/test_market_scanner_provider_contract.py`, `tests/test_phase2_freeze.py`, `tests/test_pipeline_freshness_recovery.py`, `tests/test_pipeline_snapshot.py`, `tests/test_scanner_pipeline_integration.py`, `tests/test_v12_baseline_invariants.py`, `tests/test_v13_w100_live_tick_coverage.py`, `tests/unit/test_streaming_data_provider.py` |
| Docs | 2 | `docs/architecture/mapss.md`, `docs/engineering/SESSION_PIPELINE_REPAIR.md` |

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
