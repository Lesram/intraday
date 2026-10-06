# Live Audit Index

Generated: 2026-10-06T19:58:12Z
PR: n/a
SHA: `f8b0c5fc54`
Branch: `fix/brain-crash-safety`
Scope: **backend_logic**
Change scope: `base` (`6a56d753...HEAD`)

## Changed files

Total distinct changed files: **34**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 5 | `backend/api/lifespan.py`, `backend/organism/brain_persistence.py`, `backend/organism/ensemble_models.py`, `backend/organism/live_engine.py`, `backend/utils/secure_pickle.py` |
| Scripts | 1 | `scripts/ops/check_brain_pickles_signed.py` |
| CI | 0 | none |
| Tests | 2 | `tests/test_apr8_patch_e_trained_state_guard.py`, `tests/test_audit_20261005_brain_crash_safety.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/runbooks/PAPER_BACKUP_RECOVERY.md` |
| Artifacts/evidence | 24 | `artifacts/algorithm_improvements.junit.xml`, `artifacts/algorithm_improvements.log`, `artifacts/changed_files.json`, `artifacts/live_process_runtime_snapshot.json`, `artifacts/multi_tick_state.junit.xml`, `artifacts/multi_tick_state.log`, `artifacts/organism_engine_scenarios.junit.xml`, `artifacts/organism_engine_scenarios.log`, `artifacts/organism_live_engine.junit.xml`, `artifacts/organism_live_engine.log` |
| Reports | 0 | none |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **3** file(s).

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
- `artifacts/task_report.json`
- `artifacts/test_summary.json`
- `backend/api/lifespan.py`
- `backend/organism/brain_persistence.py`
- `backend/organism/ensemble_models.py`
- `backend/organism/live_engine.py`
- `backend/utils/secure_pickle.py`
- `docs/engineering/LIVE_AUDIT_INDEX.md`
- `docs/runbooks/PAPER_BACKUP_RECOVERY.md`
- `scripts/ops/check_brain_pickles_signed.py`
- `tests/test_apr8_patch_e_trained_state_guard.py`
- `tests/test_audit_20261005_brain_crash_safety.py`

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
