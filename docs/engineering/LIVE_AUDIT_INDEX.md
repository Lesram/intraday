# Live Audit Index

Generated: 2026-09-19T20:58:11Z
PR: n/a
SHA: `274d0c47ea`
Branch: `codex/paper-corrections-candidate`
Scope: **backend_logic**
Change scope: `base` (`02ba1afff73e1f05902b9fe71f13170d618d6d5e...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 5 | `backend/integrations/alpaca_data.py`, `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/streaming_data_provider.py` |
| Organism | 4 | `backend/organism/continuous_learner.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/streaming_data_provider.py` |
| Scripts | 1 | `scripts/phase3_attribution_report.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 21 | `tests/fixtures/paper_fill_accounting_forward_20260919.json`, `tests/test_live_engine_fill_accounting.py`, `tests/test_monday_ci_workflows.py`, `tests/test_organism_integration_smoke.py`, `tests/test_phase2_freeze.py`, `tests/test_phase3_attribution_report.py`, `tests/test_phase3_candidate_shadow_telemetry.py`, `tests/test_reachability_v8.py`, `tests/test_strategy_engine_comprehensive.py`, `tests/test_v12_baseline_invariants.py` |
| Docs | 2 | `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/NIGHTLY_TEST_HARNESS_2026-09-19.md` |

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
