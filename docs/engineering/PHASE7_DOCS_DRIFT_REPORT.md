# Phase 7.9 Documentation Drift Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
Runtime SHA checked after deploy: `3fb3dd506e9e375205505cd11e126fe28bc355d4`
Post-deploy validation snapshot: 2026-05-06T16:18Z

## Verdict

The Phase 7 documentation set is usable, but only if older reports are treated
as dated evidence snapshots. Several Phase 7 reports were correct when written
and stale by the end of the phase because later slices changed runtime state,
position counts, telemetry counts, and deployed SHA.

The operating truth now lives in this chain:

1. `docs/engineering/PHASE7_CLOSE_REPORT.md`
2. `docs/engineering/LIVE_AUDIT_INDEX.md`
3. `artifacts/phase7/INTEGRATION_VALIDATION_REPORT.md`
4. `artifacts/task_report.json`
5. `artifacts/runtime_config_snapshot.json`

Do not use a mid-phase report as current runtime truth unless its SHA and
timestamp match the live container.

## Current Runtime Truth

Evidence source: authenticated `scripts/ci/phase7_integration_checkpoint.py`
and live read-only DB/container probes on 2026-05-06. Intraday rows and
positions can move after this snapshot while the paper engine is active.

| Signal | Current value |
|--------|---------------|
| Branch | `codex/v13-phase2-expectancy` |
| Host HEAD | `3fb3dd506e9e375205505cd11e126fe28bc355d4` |
| Container `GIT_SHA` | `3fb3dd506e9e375205505cd11e126fe28bc355d4` |
| Container build time | `2026-05-06T16:16:32Z` |
| Migration head | `20260503_000003` |
| Phase 5 telemetry | enabled; `66` JSONL rows |
| Phase 6 telemetry | enabled; `18` JSONL rows |
| Strategy health | `520` strategy trades, PnL `-793.3359`, win rate `0.3327`, Sharpe `-1.3959`, not profitable |
| Evidence verdict | `insufficient_shadow_sample`; no promotion justified |
| Open positions | `PSQ:60` locally at validation, refreshed after P7.6 sync fix |
| Data integrity | endpoint reachable but warning: `realized=954`, `brain=527` |
| Architecture | `_live_tick_inner=2691` LOC; 50 backend functions over 150 LOC |
| Test trust | 54 wave-style files, 369 wave-style tests, 119 marker-only, 41 mixed |

## Cross-Check Matrix

| Document | Status | Evidence | Action |
|----------|--------|----------|--------|
| `docs/architecture/mapss.md` | Updated with current-runtime note | It still serves as the long-form system map, but its first diagram named the old DB container and lacked final P7 truth. | Added current paper-runtime note and corrected DB container/table count. |
| `docs/engineering/PHASE7_ARCHITECTURE_BASELINE.md` | Historical baseline with addendum | It referenced baseline SHA `b18478b...`, 14 PASS, 0 strategy-evidence rows, and `_live_tick_inner=2802`. | Added post-P7 addendum pointing to close/current truth. |
| `docs/engineering/PHASE7_REPRODUCIBILITY_REPORT.md` | Historical evidence | It reviewed SHA `73c0ce3...`, not the final runtime SHA. | Keep as proof of that slice; do not treat as final deploy report. |
| `docs/engineering/PHASE7_OBSERVABILITY_REPORT.md` | Current for P7.6 behavior, dated for counts | It documents the serialization and stale-position bugs fixed in P7.6; position/order counts are naturally time-sensitive. | Current close report owns final counts. |
| `docs/engineering/PHASE7_DATA_INTEGRITY_REPORT.md` | Partially stale, risk still valid | It correctly states the DB ledger is not research-authoritative; counts moved from `921` realized rows after remediation to `945` after later fills. | Carry the accounting warning into Track A risk register. |
| `docs/engineering/PHASE7_SECURITY_SANITY_REPORT.md` | Current for access boundaries | Live security sanity is still 19 pass / 0 fail. | Keep; rerun after every API/RBAC change. |
| `docs/engineering/PHASE6_STRATEGY_EVIDENCE_WAREHOUSE_PLAN.md` | Current strategy process | Still correctly states shadow-only, no promotion, post-close warehouse path. | Becomes Track B starting point. |
| `docs/architecture/improve9.md` | Historical research memo | It is valuable context, not current operating truth. | Reference only when comparing strategy ideas. |

## Stale Claims Reconciled

- `PHASE7_ARCHITECTURE_BASELINE.md` says the first extraction had not landed.
  It has landed; `_live_tick_inner` is now `2691` LOC.
- `PHASE7_ARCHITECTURE_BASELINE.md` reports Phase 6 strategy-evidence rows as
  `0`. The current runtime has `17`.
- `PHASE7_ARCHITECTURE_BASELINE.md` reports zero open positions. The
  post-deploy validation snapshot has one broker-refreshed local position.
- `PHASE7_REPRODUCIBILITY_REPORT.md` states a reviewed SHA from the P7.5 slice,
  not final Track A.
- `docs/architecture/mapss.md` named PostgreSQL as `intra-db-1`; the paper DB
  container is `trading_platform_db_paper`.

## Operating Rule Going Forward

Every phase close must include a single current-runtime table with SHA, build
time, migration head, telemetry counts, strategy health, data-integrity status,
open exposure, test trust, and deploy parity. Mid-phase reports should stay in
place, but they should be read as evidence snapshots.
