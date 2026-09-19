# Platform Deep-Audit — V11 Plan (EVERY-CORNER SWEEP)

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `11c2275` (post wave 50-65)
**Goal:** by Monday, every corner of the platform has been analyzed.

## What's different about V11

V8 OO showed lens-availability lag drives recurring findings. V9/V10 each shipped 3-4 NEW lenses and yielded ~50% of findings from them. V11 ships **4 more** + drills deeper on all 13 existing lenses.

## V11 design principles

1. **Verify V10 + deferred fixes (waves 50-65) actually work post-rebuild.**
2. **Re-audit the 8 V10-touched domains at one level deeper.**
3. **Ship 4 NEW lenses (AAA, CCC, DDD, III) covering corners V1-V10 never touched.**
4. **Yield expectation: 10-30 findings.** Below 10 = the cycle has converged.
5. **Audit-only.** Wave 67+ ships fixes.

## Tracks (12 total)

| # | Track | Lens | New vs V10 |
|---|---|---|---|
| 1 | **Z9** — closure regression on waves 50-65 | continuity | continuation |
| 2 | **AA5** — security Phase 4: supply chain, container image scan, multi-tenancy, secrets-in-env | depth | depth-pass |
| 3 | **BB5** — data lifecycle: TTL/retention, GDPR right-to-be-forgotten, archive paths, transactional boundaries under load | depth | depth-pass |
| 4 | **DD5** — strategy Phase 5: DD4 fix follow-through (post-Mon data), regime hysteresis on fast-flip days | depth | depth-pass |
| 5 | **HH3** — architecture Phase 3: post-HH R-1 stages, identify next god-class after live_engine | depth | depth-pass |
| 6 | **PP3** — chaos Phase 3: actual SIGKILL drills, network partition, real recovery | depth | depth-pass |
| 7 | **TT3** — performance Phase 3: post-watchdog real-load profile, hot-path cProfile | depth | depth-pass |
| 8 | **UU3** — error-handling Phase 3: ratchet validation + post-V10 sample compliance | depth | depth-pass |
| 9 | **AAA** — API contract: every endpoint's auth + error surface + rate-limit + idempotency + request validation | **NEW** | every-corner |
| 10 | **CCC** — Configuration sprawl: env-var inventory + .env vs settings.py vs docker-compose drift + secrets handling | **NEW** | every-corner |
| 11 | **DDD** — Dependency posture: pip-audit deep + Dockerfile base-image scan + transitive CVE depth + npm audit | **NEW** | every-corner |
| 12 | **III** — Logging architecture: structured vs free-text + sampling + log-level discipline + PII in logs + retention | **NEW** | every-corner |

Total expected: **10-30 findings**. The 4 NEW lenses target unaudited corners; the 8 depth tracks should yield diminishing returns.

## V11-specific verification targets

- **Z9**: every wave 50-65 marker present + behavioral tests pass + container has the post-rebuild code.
- **AA5**: pip-audit + container image scan via `docker scout` or trivy if available, multi-tenancy probe (does user A see user B's orders?), env-var leak scan in container.
- **BB5**: every table's retention policy (TTL? archive?), GDPR scenarios (delete user → cascade?), txn boundary review under concurrent load.
- **DD5**: pull Monday's first ~10 trades from trade_history.csv, verify position_lots+realized_trades matches exactly, look for new edges (flat-flip days).
- **HH3**: scan for new god-classes, post-wave-40 _live_tick_inner residual size.
- **PP3**: actual SIGKILL on /tmp/pp3_sandbox, verify atomic save + backup + load chain.
- **TT3**: cProfile a real tick, identify top-3 cumtime functions, propose optimization targets.
- **UU3**: ruff check on the 7 grandfather-ratchet'd files (count violations); sample 5 post-V10 commits for compliance.
- **AAA**: enumerate all 197 routes; classify auth requirement, idempotency, rate-limit; flag mismatches.
- **CCC**: catalog all env vars referenced; cross-reference settings.py + docker-compose.yml + .env; flag drift.
- **DDD**: `pip-audit --strict --vulnerability-service=osv` (deeper than V8/V10), Dockerfile base scan, frontend npm audit.
- **III**: structured-vs-free-text count, sample log lines for PII (email, password hashes, JWT contents), log retention check.

## Output structure

```
artifacts/audit/prompts/v11/V11_PLAN.md (this file) + 12 track prompts
artifacts/audit/v11_reports/ (12 per-track reports)
artifacts/audit/MASTER_AUDIT_SYNTHESIS_v11.md
```

## Constraints (all tracks)

- Read-only on production.
- Chaos / soak tracks may use SCRATCH `/tmp/`; never touch prod state.
- No git push.
- No fixes during V11 — wave 67+ ships fixes.

## Quality bar

If V11 finds **<10 actionable**: cycle has converged on the current 17-lens system. Move to quarterly cadence.
If V11 finds **10-25**: continue at current cadence; ship V12 with 1-2 more lenses.
If V11 finds **>25**: expansion still warranted; consider doubling lens count for V12.
