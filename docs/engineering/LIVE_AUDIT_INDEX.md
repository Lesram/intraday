# Live Audit Index

Generated: 2026-10-05T18:59:07Z
PR: n/a
SHA: `452c78f8d8`
Branch: `fix/surface-regime-isolation`
Scope: **backend_logic**
Change scope: `base` (`8fbe733d...HEAD`)

## Changed files

Total distinct changed files: **4**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 2 | `backend/organism/live_engine.py`, `backend/organism/regime.py` |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 1 | `tests/test_audit_20261005_surface_regime_isolation.py` |
| Docs | 1 | `docs/architecture/mapss.md` |
| Artifacts/evidence | 0 | none |
| Reports | 0 | none |
| Configuration | 0 | none |
| Other | 0 | none |

Organism subset of Backend: **2** file(s).

### Full changed-file list

- `backend/organism/live_engine.py`
- `backend/organism/regime.py`
- `docs/architecture/mapss.md`
- `tests/test_audit_20261005_surface_regime_isolation.py`

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
- 2 organism file(s) changed — require replay verification
