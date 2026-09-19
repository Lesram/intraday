# Live Audit Index

> Current resumption audit: [September 19 readiness report](../../reports/RESUMPTION_READINESS_AUDIT_2026-09-19.md). This index was generated at audited source SHA 4a8e0e7; the subsequent commit contains reports/evidence only. The report supersedes the historical-report auto-selection below for resumption decisions.
>
> Open risks: scheduled checks run stale main; runtime alert delivery is unconfigured; historical collection gaps; replay artifact false-pass defect; application login unavailable; shadow/ledger and cost-protocol differences; no enforced branch gates; insufficient forward evidence. Live container source/configuration freeze comparison passes, but protected in-memory API status is unavailable.

Generated: 2026-09-19T17:43:52Z
PR: [#10](https://github.com/Lesram/intraday/pull/10)
SHA: `4a8e0e713d`
Branch: `codex/resumption-readiness-2026-09-19`
Scope: **tooling/evidence_only**
Change scope: `range` (`--cached`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 0 | none |
| CI | 0 | none |
| Tests | 0 | none |
| Docs | 1 | `docs/engineering/LIVE_AUDIT_INDEX.md` |
| Reports | 1 | `reports/RESUMPTION_READINESS_AUDIT_2026-09-19.md` |
| Evidence | 24 | See `artifacts/changed_files.json` |

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

- No code changes in this PR — verify evidence artifacts are current
