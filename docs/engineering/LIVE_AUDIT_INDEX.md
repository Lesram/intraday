# Live Audit Index

Generated: 2026-05-10T22:27:42Z
PR: PR #6
SHA: `e8a49e6b48`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 4 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/evidence/strategy_league.py`, `backend/organism/schema/__init__.py`, `backend/organism/schema/candidate_signal.py` |
| Organism | 4 | `backend/organism/candidate_shadow_telemetry.py`, `backend/organism/evidence/strategy_league.py`, `backend/organism/schema/__init__.py`, `backend/organism/schema/candidate_signal.py` |
| Scripts | 1 | `scripts/phase9_shadow_evidence.py` |
| CI | 0 | none |
| Tests | 2 | `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_phase9_strategy_governance.py` |
| Docs | 1 | `docs/engineering/PRE9D_DEEP_AUDIT_2026-05-10.md` |

## Live constants

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Min",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.2,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": true,
  "strategy_evidence_telemetry_enabled": true,
  "phase9_shadow_engines_enabled": true
}
```

## Snapshot files

- Defaults: `artifacts/runtime_defaults_snapshot.json`
- Resolved config: `artifacts/resolved_config_snapshot.json`
- Live process: `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- 4 organism file(s) changed — require replay verification
