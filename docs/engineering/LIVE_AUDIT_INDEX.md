# Live Audit Index

Generated: 2026-09-19T20:33:56Z
PR: n/a
SHA: `c66bb2d812`
Branch: `codex/paper-data-freshness`
Scope: **backend_logic**
Change scope: `base` (`02ba1afff73e1f05902b9fe71f13170d618d6d5e...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/integrations/alpaca_data.py`, `backend/organism/streaming_data_provider.py` |
| Organism | 1 | `backend/organism/streaming_data_provider.py` |
| Scripts | 0 | none |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 4 | `tests/test_monday_ci_workflows.py`, `tests/unit/test_alpaca_data_comprehensive.py`, `tests/unit/test_paper_data_freshness.py`, `tests/unit/test_streaming_data_provider.py` |
| Docs | 0 | none |

## Live constants

**Evidence scope:** The constants below are the isolated mock/test snapshot generated for this proposal, including the test `1Day` setting. They are not the stopped paper runtime or an installed candidate. The separate actual provider probe used configured IEX/`1Min`/500 in an ephemeral read-only container (`artifacts/data_freshness_proposal/actual_readonly_provider_probe.json`); it did not activate the engine. Original-runtime and maintenance-hold observations are under `artifacts/data_freshness/`. Activation, cohort approval and fresh installed-runtime evidence remain pending.

Source: `resolved_config_snapshot.json`

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
