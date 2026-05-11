# Live Audit Index

Generated: 2026-05-11T00:23:15Z
PR: PR #6
SHA: `d7062debbd`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/organism/eod_scanner.py`, `backend/organism/mean_reversion_scanner.py`, `backend/organism/orb_scanner.py` |
| Organism | 3 | `backend/organism/eod_scanner.py`, `backend/organism/mean_reversion_scanner.py`, `backend/organism/orb_scanner.py` |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 3 | `tests/test_eod_scanner.py`, `tests/test_mean_reversion_scanner.py`, `tests/test_orb_scanner.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PRE9D_LEGACY_SCANNER_CAUSAL_AUDIT_2026-05-10.md` |

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

- 3 organism file(s) changed — require replay verification
