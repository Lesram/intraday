# Live Audit Index

Generated: 2026-10-21T00:42:05Z
PR: n/a
SHA: `974348fa58`
Branch: `fix/indicator-corrections`
Scope: **backend_logic**
Change scope: `base` (`53bd8a1...HEAD`)

## Changed files

Total distinct changed files: **41**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 5 | `backend/organism/breakout_scanner.py`, `backend/organism/composite_indicators.py`, `backend/organism/live_engine.py`, `backend/organism/strategies/breakout.py`, `backend/organism/strategies/strategy_config.py` |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 6 | `tests/test_audit_0_5_pyramid_gates_idem_keys.py`, `tests/test_breakout_strategy.py`, `tests/test_fitness_gate_research_lock.py`, `tests/test_indicator_corrections_20261020.py`, `tests/test_v12_baseline_invariants.py`, `tests/test_v13_w100_live_tick_coverage.py` |
| Docs | 2 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md` |
| Artifacts/evidence | 28 | `artifacts/algorithm_improvements.junit.xml`, `artifacts/algorithm_improvements.log`, `artifacts/changed_files.json`, `artifacts/live_process_runtime_snapshot.json`, `artifacts/multi_tick_state.junit.xml`, `artifacts/multi_tick_state.log`, `artifacts/organism_engine_scenarios.junit.xml`, `artifacts/organism_engine_scenarios.log`, `artifacts/organism_live_engine.junit.xml`, `artifacts/organism_live_engine.log` |
| Reports | 0 | none |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **5** file(s).

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
- `artifacts/task_report.json`
- `artifacts/test_summary.json`
- `backend/organism/breakout_scanner.py`
- `backend/organism/composite_indicators.py`
- `backend/organism/live_engine.py`
- `backend/organism/strategies/breakout.py`
- `backend/organism/strategies/strategy_config.py`
- `docs/architecture/mapss.md`
- `docs/engineering/LIVE_AUDIT_INDEX.md`
- `tests/test_audit_0_5_pyramid_gates_idem_keys.py`
- `tests/test_breakout_strategy.py`
- `tests/test_fitness_gate_research_lock.py`
- `tests/test_indicator_corrections_20261020.py`
- `tests/test_v12_baseline_invariants.py`
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
