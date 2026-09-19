# Live Audit Index

Generated: 2026-09-19T21:02:16Z
PR: n/a
SHA: `79a898697e`
Branch: `codex/paper-corrections-candidate`
Scope: **backend_logic**
Change scope: `base` (`3fa2199df04d75ea0552a5aa08d1f59ba844b211...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 5 | `backend/integrations/alpaca_data.py`, `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/streaming_data_provider.py` |
| Organism | 4 | `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 1 | `scripts/phase3_attribution_report.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 8 | `tests/fixtures/paper_fill_accounting_forward_20260919.json`, `tests/test_live_engine_fill_accounting.py`, `tests/test_monday_ci_workflows.py`, `tests/test_phase3_attribution_report.py`, `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/unit/test_alpaca_data_comprehensive.py`, `tests/unit/test_paper_data_freshness.py`, `tests/unit/test_streaming_data_provider.py` |
| Docs | 1 | `docs/engineering/LIVE_AUDIT_INDEX.md` |

## Live constants

**Evidence scope:** These are isolated mock/test settings for the combined proposal. They are not the stopped paper runtime or an activated candidate. The API remains held; the July cutoff is unchanged. The prebuilt image is source-bound and verified without application startup. Primary prospective research reports are proposed at 6 bps round trip using report-process-only configuration; native/runtime costing remains unchanged. See `reports/PAPER_CORRECTIONS_ACTIVATION_PROPOSAL_2026-09-19.md` and `artifacts/corrections_candidate/`.

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

- 4 organism file(s) changed — require replay verification
