# Live Audit Index

Generated: 2026-09-19T18:17:51Z
PR: PR #11
SHA: `d6c5534be6`
Branch: `codex/fix-artifact-reporting`
Scope: **tooling/evidence_only**
Change scope: `base` (`intra-2.0-phase1...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 1 | `scripts/ci/generate_artifacts.py` |
| CI | 3 | `.github/workflows/artifact-reporting.yml`, `.github/workflows/paper-postclose-audit.yml`, `.github/workflows/pr-verify.yml` |
| Tests | 2 | `tests/test_artifact_workflow_contract.py`, `tests/test_generate_artifacts.py` |
| Docs | 1 | `docs/engineering/ARTIFACT_REPORTING.md` |

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
  "drawdown_kill_pct": 0.1,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": true,
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

- Evidence/tooling script changed only — no backend runtime or order-path behavior changed
- Authenticated application status was unavailable. The displayed values are resolved container configuration, not independently verified in-memory values.
- Scheduled monitoring still follows the old default branch. KPI coverage, issue permissions, and alert delivery remain separate repairs.
- Trading-evidence reconciliation and the strategy verdict remain unresolved; this tooling repair establishes no trading edge.

## September 19 repair evidence

Audited source: `d6c5534be6faa5205852a1ce0f52d5610469f188`. The evidence-only commit that follows records this source version; the generated file counts above describe its seven source, test, workflow, and documentation changes.

- Task report and counts: `artifacts/task_report.json` — 280 local tests passed, zero failed.
- Full pack: `artifacts/repair_validation/full_pack.json` — 216 organism/safety/replay/semantic tests passed under OS isolation.
- Focused reporting tests: `artifacts/repair_validation/focused.xml` — 58 passed.
- Freeze tests: `artifacts/repair_validation/freeze_tests.xml` — 6 passed; `freeze_after.json` records the unchanged decision surface.
- Independent review: `artifacts/repair_validation/review.json`.
- GitHub source check: `artifacts/repair_validation/github_source_check.json` — 58 focused tests passed and results uploaded.
- Snapshot provenance: `artifacts/repair_validation/runtime_refresh.json`. Isolated test snapshots are archived separately under `artifacts/repair_validation/isolated_snapshots/`.
- Current resumption audit: [PR #10](https://github.com/Lesram/intraday/pull/10).
