# Live Audit Index

> **Candidate evidence only:** source `c11cd17beb0117a3591fdf9af64c1aaaede51267`. Generated root configuration uses isolated test defaults, not the installed runtime. The approved paper activation will publish actual observed snapshots under `artifacts/paper_activation/2026-09-21/`. Natural-session acceptance remains pending.


Generated: 2026-09-21T08:54:14Z
PR: n/a
SHA: `c11cd17beb`
Branch: `codex/operations-evidence-integrity`
Scope: **backend_logic**
Change scope: `base` (`ffc0e5c0595bb21e1c71f0ba7e5d6f55af7fc189...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 19 | `backend/api/routes/risk.py`, `backend/api/routes/settings.py`, `backend/organism/background_trainer.py`, `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/governance.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py` |
| Organism | 16 | `backend/organism/background_trainer.py`, `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/governance.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/operator_cancellation.py`, `backend/organism/operator_controls.py` |
| Scripts | 6 | `scripts/ops/paper_daily_evidence.py`, `scripts/ops/paper_daily_host.py`, `scripts/ops/paper_watchdog.py`, `scripts/ops/standdown_session_row.py`, `scripts/phase2_freeze.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 38 | `tests/test_apr10_patch_f4_forensic_guard.py`, `tests/test_apr7_p0_p1_fixes.py`, `tests/test_apr8_patch_a_force_save.py`, `tests/test_audit_0_2_bg_trainer_same_holdout.py`, `tests/test_audit_2_3_2_5_promotion_evolution.py`, `tests/test_audit_patch_queue_a.py`, `tests/test_audit_patch_queue_b1.py`, `tests/test_audit_patch_queue_b2.py`, `tests/test_audit_patch_queue_f3.py`, `tests/test_audit_patch_queue_f4.py` |
| Docs | 6 | `docs/architecture/mapss.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/MONDAY_PREPARATION_2026-09-21.md`, `docs/engineering/OPERATIONS_EVIDENCE_RELEASE.md`, `docs/runbooks/PAPER_DAILY_EVIDENCE.md`, `docs/runbooks/PAPER_UPTIME.md` |

## Live constants

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

- 16 organism file(s) changed — require replay verification
