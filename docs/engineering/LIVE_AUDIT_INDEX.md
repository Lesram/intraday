# Live Audit Index

Generated: 2026-05-12T05:06:32Z
PR: PR #8
SHA: `12fdd95b8a`
Branch: `codex/phase9d-portfolio-construction`
Scope: **tooling/evidence_only**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 1 | `scripts/ci/phase9_preopen_evidence_readiness.py` |
| CI | 0 | none |
| Tests | 5 | `tests/test_phase9_preopen_evidence_readiness.py`, `tests/test_v13_w100_live_tick_coverage.py`, `tests/test_v13_w94_strategy_floor.py`, `tests/test_v13_w95_data_integrity.py`, `tests/test_v13_w96_idor.py` |
| Docs | 4 | `docs/engineering/FINAL_GRAND_AUDIT_2026-05-10.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/PHASE9D_FINAL_GRAND_AUDIT_PROMPT_2026-05-10.md`, `docs/engineering/PREOPEN_CLEANUP_2026-05-10.md` |

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

- Evidence/tooling script changed only — no backend runtime or order-path behavior changed
