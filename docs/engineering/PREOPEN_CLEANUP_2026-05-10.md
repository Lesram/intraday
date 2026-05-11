# Pre-Open Cleanup — May 11, 2026 Paper Session

Generated: 2026-05-10 22:45 PT / 2026-05-11 05:45 UTC

## Verdict

Technical readiness warnings from the final grand audit have been resolved or
reclassified as market-evidence/strategy-performance truths that must not be
faked before a live paper session.

The platform remains ready for guarded paper trading. This cleanup did not
change ranking, sizing, safety gates, promotion state, order behavior, or live
strategy logic.

## Cleanup Actions

1. Converted marker-only wave tests below the long-run target:
   - Before: `118/372 = 31.72%`.
   - After: `110/372 = 29.57%`.
   - Ratchet baseline updated at `artifacts/audit/v13/marker_only_baseline.json`.

2. Added Phase 9 pre-open evidence readiness smoke:
   - Script: `scripts/ci/phase9_preopen_evidence_readiness.py`.
   - Test: `tests/test_phase9_preopen_evidence_readiness.py`.
   - Output: `artifacts/phase9_preopen_readiness/phase9_preopen_readiness_report.json`.
   - Result: `ready=true`, `events_written=8`.
   - Strategies covered: `etf_intraday_momentum`, `orb_sip_v2`,
     `residual_mean_reversion`, `eod_reversal_shadow`.
   - This is synthetic implementation readiness only, not promotion evidence.

3. Pruned sent outbox rows after snapshot:
   - Snapshot: `artifacts/maintenance/20260511_preopen_cleanup/outbox_events_pre_cleanup.csv`.
   - Before: `outbox_events=910`, all `status=sent`.
   - After: `outbox_events=0`.
   - No pending/live outbox work was deleted.

4. Archived stale brain quarantine directories:
   - Snapshot list: `artifacts/maintenance/20260511_preopen_cleanup/corrupt_head_dirs_pre_cleanup.txt`.
   - Archive: `artifacts/maintenance/20260511_preopen_cleanup/brain_archive/`.
   - Current `organism_brain/` no longer contains `corrupt_head_*` directories.
   - Root stale `organism_brain.pre_v10_deploy_20260503_175525Z` was moved to the same archive.

5. Preserved reference for terminal failed orders:
   - Reference CSV: `artifacts/maintenance/20260511_preopen_cleanup/failed_orders_reference.csv`.
   - Rows were not deleted from `orders`; they are terminal history, not live exposure.

## Runtime Post-State

- Nonzero positions: `0`.
- Live-open orders: `0`.
- Outbox rows: `0`.
- Migration head: `20260503_000003`.
- Container deploy before this docs/tests cleanup commit:
  `284fd53809ec0e84f3e04c54f681cb4da1a272f8`.

## Honest Non-Cleared Strategy Truths

These are not technical hygiene warnings and were not changed pre-open:

- Current strategy is still not profitable:
  `n_trades=551`, `total_pnl=-763.1831`, `win_rate=0.3321`,
  `is_profitable=false`.
- First-class Phase 9 forward market events still require tomorrow's session.
  The synthetic readiness smoke proves capture readiness only.
- DB realized trade rows and brain trade-history rows still have different
  historical scopes. The `/api/v1/health/data-integrity` endpoint reports
  `accounting_status=ok` and explicitly marks the DB as a historical superset.

## Tomorrow's Operating Plan

1. Let paper trading run in guarded mode with Phase 9 engines shadow-only.
2. Do not promote any strategy intra-session.
3. At post-close, run the evidence warehouse, Phase 9 shadow evidence,
   portfolio construction, platform truth observer, and pre/post deploy sanity
   checks.
4. If Phase 9 first-class forward events are still zero after market close,
   treat that as a research-loop blocker and debug immediately.
