# Live Audit Index

Generated: 2026-09-22T07:40:43Z
PR: n/a
SHA: `99ce9632d5`
Branch: `codex/final-entry-freshness`
Scope: **backend_logic**
Change scope: `base` (`b5a39b12c5a92271843bae918ec2b476183beeba...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/organism/entry_evidence.py`, `backend/organism/entry_freshness.py`, `backend/organism/live_engine.py` |
| Organism | 3 | `backend/organism/entry_evidence.py`, `backend/organism/entry_freshness.py`, `backend/organism/live_engine.py` |
| Scripts | 2 | `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 7 | `tests/test_apr7_p0_p1_fixes.py`, `tests/test_entry_freshness.py`, `tests/test_entry_freshness_snapshot.py`, `tests/test_operator_controls.py`, `tests/test_phase2_freeze.py`, `tests/test_phase9_strategy_governance.py`, `tests/test_replay_simulator.py` |
| Docs | 1 | `docs/architecture/mapss.md` |

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
