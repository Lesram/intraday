# Live Audit Index

Generated: 2026-05-11T05:50:25Z
PR: PR #8
SHA: `284fd53809`
Branch: `codex/phase9d-portfolio-construction`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/organism/evidence/portfolio_construction.py` |
| Organism | 1 | `backend/organism/evidence/portfolio_construction.py` |
| Scripts | 1 | `scripts/phase9d_portfolio_construction.py` |
| CI | 0 | none |
| Tests | 1 | `tests/test_phase9d_portfolio_construction.py` |
| Docs | 4 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PHASE9D_PORTFOLIO_CONSTRUCTION_IMPLEMENTATION.md`, `docs/engineering/STRATEGY_REBUILD_MASTER_ROADMAP_2026-05-09.md` |

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

- 1 organism file(s) changed — require replay verification
