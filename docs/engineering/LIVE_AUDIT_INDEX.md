# Live Audit Index

Generated: 2026-10-14T21:53:16Z
PR: n/a
SHA: `2759bdb00d`
Branch: `fix/ui-loop-and-execution-mode`
Scope: **backend_logic**
Change scope: `base` (`6a56d753...HEAD`)

## Changed files

Total distinct changed files: **50**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 9 | `backend/api/routes/admin_trading.py`, `backend/api/routes/scanner.py`, `backend/api/routes/watchlists.py`, `backend/data/alpaca_client.py`, `backend/infra/outbox_worker.py`, `backend/services/auto_breakout_scanner.py`, `backend/services/dashboard_market_data.py`, `backend/services/scanner_universe.py`, `backend/services/trading_execution_mode.py` |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 4 | `tests/test_admin_trading_execution_mode.py`, `tests/test_audit_20261005_ui_loop_and_execution_mode.py`, `tests/test_broker_ack_reconciliation.py`, `tests/test_outbox_shadow_mode.py` |
| Docs | 3 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/runbooks/PAPER_TRADING_ROLLOUT.md` |
| Artifacts/evidence | 25 | `artifacts/algorithm_improvements.junit.xml`, `artifacts/algorithm_improvements.log`, `artifacts/changed_files.json`, `artifacts/live_process_runtime_snapshot.json`, `artifacts/multi_tick_state.junit.xml`, `artifacts/multi_tick_state.log`, `artifacts/organism_engine_scenarios.junit.xml`, `artifacts/organism_engine_scenarios.log`, `artifacts/organism_live_engine.junit.xml`, `artifacts/organism_live_engine.log` |
| Reports | 0 | none |
| Configuration | 1 | `.env.example` |
| Other | 8 | `frontend/src/components/layout/AppSidebar.tsx`, `frontend/src/components/market/Scanner.tsx`, `frontend/src/components/market/WatchlistSymbolCard.tsx`, `frontend/src/features/ml-models/components/LifecycleDashboard.tsx`, `frontend/src/hooks/useWatchlists.ts`, `frontend/src/pages/ScannerPage.tsx`, `frontend/src/services/watchlistApi.ts`, `frontend/src/types/ml.ts` |

Organism subset of Backend: **0** file(s).

### Full changed-file list

- `.env.example`
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
- `artifacts/replay_simulator.junit.xml`
- `artifacts/replay_simulator.log`
- `artifacts/replay_summary.json`
- `artifacts/runtime_snapshot.log`
- `artifacts/runtime_snapshot_summary.json`
- `artifacts/safety_invariants.junit.xml`
- `artifacts/safety_invariants.log`
- `artifacts/self_evolution.junit.xml`
- `artifacts/self_evolution.log`
- `artifacts/semantic_invariants.junit.xml`
- `artifacts/semantic_invariants.log`
- `artifacts/semantic_invariants_summary.json`
- `artifacts/task-report.json`
- `artifacts/task_report.json`
- `artifacts/test_summary.json`
- `backend/api/routes/admin_trading.py`
- `backend/api/routes/scanner.py`
- `backend/api/routes/watchlists.py`
- `backend/data/alpaca_client.py`
- `backend/infra/outbox_worker.py`
- `backend/services/auto_breakout_scanner.py`
- `backend/services/dashboard_market_data.py`
- `backend/services/scanner_universe.py`
- `backend/services/trading_execution_mode.py`
- `docs/architecture/mapss.md`
- `docs/engineering/LIVE_AUDIT_INDEX.md`
- `docs/runbooks/PAPER_TRADING_ROLLOUT.md`
- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/components/market/Scanner.tsx`
- `frontend/src/components/market/WatchlistSymbolCard.tsx`
- `frontend/src/features/ml-models/components/LifecycleDashboard.tsx`
- `frontend/src/hooks/useWatchlists.ts`
- `frontend/src/pages/ScannerPage.tsx`
- `frontend/src/services/watchlistApi.ts`
- `frontend/src/types/ml.ts`
- `tests/test_admin_trading_execution_mode.py`
- `tests/test_audit_20261005_ui_loop_and_execution_mode.py`
- `tests/test_broker_ack_reconciliation.py`
- `tests/test_outbox_shadow_mode.py`

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
- 9 backend runtime file(s) changed — require targeted verification
