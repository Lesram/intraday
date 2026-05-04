# OPERATOR COMMAND SHEET
**As of:** 2026-05-03 (post-Wave-26)

> V7 GG-6 / Wave-26 (2026-05-03): this doc was 92 commits behind HEAD
> at the time of audit. The pre-V7 content below is preserved as
> historical context but is NOT current operational guidance.

## Current state (rc-1.5-curated branch)
- **Branch:** `rc-1.5-curated` (paper trading). Main is stale.
- **Repo HEAD:** see `git log -1 --oneline` — moves with each wave commit.
- **Brain:** `gen 168, 498 trades, ml_is_trained=true`. Cumulative PnL
  in learning_state.json reconciles to trade_history.csv within
  $0.10 (V5 B-T-2 fix).
- **Audit cycle:** V1 → V7 complete (~278 findings, ~187 closed).
  Wave 27 (HH structural refactors — pipeline-split
  `_live_tick_inner`, consolidate 7 settings entry-points, brain
  serializer registry) is the largest deferred work; do NOT plan
  it without a maintenance window since R-1 alone is 2,510 lines.

## Deploy procedure (post Wave-23)
```bash
docker-compose -f docker-compose.paper.yml build api
docker-compose -f docker-compose.paper.yml up -d --force-recreate api

# Verify healthy:
docker inspect intra-api-1 --format '{{.RestartCount}} {{.State.Health.Status}}'
# Expected: 0 healthy

# Verify brain coherent:
python3 -c "import json; m=json.load(open('organism_brain/manifest.json')); \
print({k: m[k] for k in ('generation','total_trades','ml_is_trained')})"
```

## Operational notes (post Wave-23/24)
- **`JWT_SECRET`** and **`REDIS_PASSWORD`** in `.env` are strong
  randoms (V7 AA-C-1 / AA-M-1). Rotate annually or on suspected
  compromise. Active sessions invalidate on rotation.
- **`require_admin` / `require_trader` / `require_api`** dependencies
  now actually enforce role checks (V7 AA-C-2 wave-23b).
- **Container hardening**: `cap_drop=ALL`, `no-new-privileges`,
  4G/2.0cpu limits, gid=10001 (V7 AA-H-4 wave-24).
- **Security headers** (HSTS / CSP / X-Frame / Referrer) on every
  response (V7 AA-H-1 wave-24).
- **Audit-wave PR template**: `.github/pull_request_template.md`
  (wave-26) requires finding-IDs, same-class grep, and behavioral
  test for every `fix(audit-wave...)` PR.

## V7 deferred items (wave 25b/27 work)
- **BB-8** LotTracker dead code wiring (production stream still uses
  the dead path).
- **BB-10 + AA-H-3** ComplianceAuditService wiring (audit_logs table
  is empty).
- **EE-4** pg_backup cron + restore script.
- **EE-5** DR runbooks for 6 scenarios (host disk full, Alpaca key
  revoke, WS multi-day outage, brain corruption, partition, outbox
  overflow).
- **HH R-1** pipeline-split `_live_tick_inner` (largest refactor).

## Historical context (pre-V7, NOT current)

The original eb90fa3 deploy on 2026-04-27 has long been superseded.
The brain has advanced from gen 124 → 168 (+44 generations, +102
trades). Wave 8 through Wave 26 have shipped on `rc-1.5-curated`
with steady deploys. See `MASTER_AUDIT_SYNTHESIS_v[1-7].md` for
the full per-round detail.

⚠️ V7 GG-7: `MONDAY_DEPLOY_eb90fa3.md` at repo root is a one-time
historical artifact. Do NOT use it as the live runbook.

## What to observe (5–10 sessions post-deploy)
| Metric | Baseline (ce06d41, 12 sessions) | Week-1 target |
|---|---|---|
| Pyramid_cut share | 31.3% | **≤ 22%** |
| Trailing_stop avg PnL | −$0.60 | **≥ $0** |
| Win rate | 31.3% | **≥ 35%** |
| Expectancy | −$0.59 | **≥ −$0.30** |
| Halt / freeze events | 0 | 0 |
| Alert wiring delivery on synthetic test | n/a | 100% |

## What must be true before real-money (Stage 1)
1. `eb90fa3` deployed clean
2. 5+ clean post-deploy sessions
3. Notional cap reject path verified live
4. Daily max-loss kill verified live
5. Alert wiring delivery verified
6. Drawdown-kill startup validator log line confirmed
7. No regression in execution latency / brain save / ML retrain
8. Expectancy ≥ neutral over 5 sessions
9. G1/G2/G3 reduces pyramid_cut share ≥30% relative
10. Exp 4 reduces trailing-stop giveback measurably
11. Brain backup rotation in place
12. Stage-1 risk parameter set documented (capital, per-trade cap %, daily max-loss %, max positions, universe trim)

All twelve must be green. Earliest realistic Stage-1 cutover: **2026-05-12 (Mon)**.

## What NOT to do this window
- No new audits / master plans / comprehensive reviews.
- No code changes during observation.
- No real capital movements.
- No remote pushes without explicit confirmation.
- No third-party voice added — close, don't expand, the review surface.

## Single source of truth references
- Master pack: `WEEKEND_STATE_AND_STRATEGY_PACK.md`
- PR review bundle: `docs/engineering/reviews/pr-deploy-eb90fa3-eb90fa3/`
- Preflight artifacts: `artifacts/deploy_preflight_eb90fa3/`
- Brain backup: `artifacts/deploy_preflight_eb90fa3/organism_brain_backup_pre_eb90fa3_20260425/`
- Monday run-book: `MONDAY_DEPLOY_eb90fa3.md`
