# Platform Deep-Audit — V10 Plan

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `35a1fe9` (post wave 32-49)
**Predecessor cumulative:** V1-V9 = ~347 audit items, ~275 closed, ~72 deferred entering V10.

## What's different about V10

V9 confirmed V8 OO's lens-availability hypothesis: each new lens yields 5-10 first-round findings. V9 NEW lenses (PP/UU/TT) yielded 47% of findings. V10 ships **4 NEW lenses** (per V8 OO + V9 forward-plan recommendations) plus deeper passes on V9-touched domains.

## V10 design principles

1. **Verify V9 fixes hold under 1 week of post-deploy stress.** Z8 closure regression + targeted re-probes.
2. **Drill into the NEW lenses V9 ran but didn't exhaust** (PP, UU, TT → PP2, UU2, deep TT integrated into other tracks).
3. **Ship 4 NEW lenses simultaneously** — VV (frontend/backend), WW (soak), XX (migration), YY (observability).
4. **Yield expectation: 5-25 findings.** Below 5 = cycle has converged; above 25 = expansion still warranted.
5. **Audit-only. Wave 50+ ships fixes.**

## Tracks (10 total)

| # | Track | Lens | Yield estimate | New vs V9 |
|---|---|---|---|---|
| 1 | **Z8** — closure regression on waves 41-49 | continuity | 0-2 | continuation |
| 2 | **AA4** — security Phase 3: replay protection, RBAC depth, signed-URL gaps | depth | 1-4 | depth-pass |
| 3 | **BB4** — data integrity Phase 3: verify wave-43 DD3-2 actually populates position_lots | depth | 1-3 | depth-pass |
| 4 | **DD4** — strategy logic Phase 4: fitness gate enforcement post-wave-44, pyramider Layer 2 | depth | 2-5 | depth-pass |
| 5 | **PP2** — chaos Phase 2: simulate SIGKILL on atomic save, watchdog under hung broker | depth | 1-3 | depth-pass |
| 6 | **UU2** — error-handling Phase 2: lint rule design + retroactive scan | depth | 1-3 | depth-pass |
| 7 | **VV** — frontend/backend contract drift (TS types vs pydantic) | **NEW** | 2-5 | OO recommendation |
| 8 | **WW** — multi-day operational soak (5x restart sequence) | **NEW** | 2-4 | OO recommendation |
| 9 | **XX** — migration round-trip on snapshot | **NEW** | 1-3 | OO recommendation |
| 10 | **YY** — observability completeness — what should page that doesn't? | **NEW** | 2-5 | V10 expansion |

Total expected: **13-37 findings**. The 4 NEW lenses are expected to yield ~10 between them (ranges sum to 7-17).

## V10-specific verification targets

V10 must:
- **Z8**: wave 41-49 markers + behavioral tests + same-class scans all green at HEAD.
- **AA4**: probe externally — token replay across server restart, JWT replay window, API-key/Bearer interaction edges.
- **BB4**: confirm `position_lots` row count > 0 since wave-43 deploy (the V9 BB3-F2 mystery).
- **DD4**: verify fitness gate ACTUALLY rejects per wave-44 DD3-5 — sample candidates with no recorded fitness must be blocked, not pass on default.
- **PP2**: kill -9 mid-save in a sandbox; assert backup fallback triggers; verify wave-46 watchdog actually fires under a deliberately-hung mock.
- **UU2**: design + propose ruff config for V11 enforcement; scan all `except Exception:` sites that survived wave-41 + tier them.
- **VV**: parse all FastAPI pydantic schemas; cross-reference with TS types in `frontend/src/types/` (or wherever); flag drift.
- **WW**: 5 sequential restarts in a sandboxed brain; verify gen / trades / ML state stays invariant.
- **XX**: alembic upgrade → downgrade → upgrade on a copy of production schema; compare row-by-row.
- **YY**: enumerate every `logger.error` / `logger.critical` call site; check whether Slack / PagerDuty wires fire for each; identify silent-error paths.

## Output structure

```
artifacts/audit/prompts/v10/
  V10_PLAN.md
  track_z8_closure_regression_waves41_49.md
  track_aa4_security_phase3.md
  track_bb4_data_integrity_phase3.md
  track_dd4_strategy_logic_phase4.md
  track_pp2_chaos_phase2.md
  track_uu2_error_handling_phase2.md
  track_vv_frontend_backend_contract_drift.md
  track_ww_multi_day_soak.md
  track_xx_migration_round_trip.md
  track_yy_observability_completeness.md

artifacts/audit/v10_reports/
  (8-10 per-track reports)

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v10.md
```

## Constraints (all tracks)

- Read-only on production. `curl`, `docker exec`, `pytest`, `psql` SELECTs ok.
- Chaos / soak / migration tracks may use a SCRATCH container. NEVER touch production.
- No mutations to live brain / DB.
- No git push.
- Do NOT write fixes during V10 — wave 50+ ships fixes.

## Quality bar

V10 success = the cycle's "fix didn't fix" pattern remains dead AND no new lens-availability gaps surface. If V10 finds < 5 actionable, the cycle has converged: drop to quarterly. If 5-15: continue at current cadence. If 15-25: expand again.

End-of-V10 success criteria:
- All 25 V9 wave fixes (41-49) independently verified.
- ≥3 V9 deferred items confirmed still-open OR newly-resolved.
- ≥1 finding from each NEW lens (VV/WW/XX/YY).
- Closure regression clean (Z8 returns 0-2).
