# Live Audit Index

Generated: 2026-05-06T15:05:32Z
PR: PR #6
SHA: `c322693472`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 5 | `backend/api/routes/data_integrity_health.py`, `backend/api/routes/deploy_health.py`, `backend/api/routes/orders.py`, `backend/api/routes/strategy_health.py`, `backend/organism/routes.py` |
| Organism | 1 | `backend/organism/routes.py` |
| Scripts | 1 | `scripts/ci/phase7_security_sanity.py` |
| Tests | 1 | `tests/test_phase7_security_sanity.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PHASE7_SECURITY_SANITY_REPORT.md` |

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
  "bar_boundary_entry_only": true
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

- 1 organism file(s) changed — require replay verification
