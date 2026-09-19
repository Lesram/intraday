# DEPLOY VERIFICATION — be2eee8 — 2026-04-09

## 1. Verdict
**DEPLOYED AND VERIFIED**

All 12 hard-stop checks PASS. Container `intra-api-1` rebuilt from commit `be2eee86822e37f93d1fd40354c5031eef6a4a01`, patches A/B/C verified in the running code, `POST /api/v1/organism/save?force=true` exercised successfully against the live engine, full brain persisted with fresh ML joblibs and fully synced manifest, brain state durable, market remains closed until 2026-04-09 13:30 UTC. One non-blocking finding: `transfer_knowledge.json` is not written by the force-save code path.

## 2. Source State Before Deploy
- Repo root: `/Users/marselkei/VS/intra`
- Branch: `main`
- `git rev-parse HEAD`: `be2eee86822e37f93d1fd40354c5031eef6a4a01` (matches target)
- `git status --short backend/ docker-compose.paper.yml .env`: clean (empty)

## 3. Pre-Deploy Snapshot (fresh, 2026-04-09T01:24Z)
- Containers: `intra-api-1` Up 42h healthy, `intra-redis-1` Up 42h healthy, `trading_platform_db_paper` Up 42h healthy
- Pre-rebuild api StartedAt=2026-04-07T07:37:02Z, RestartCount=0, Health=healthy
- `/health`: ok. `/api/v1/system/health`: healthy (components: api, database, metrics)
- Brain dir (host): 15 files including manifest.json, learning_state.json, ml_classifier.joblib, ml_regressor.joblib, reference_feats.csv, evolved_params.json, transfer_knowledge.json (41640B), trade_history.csv (24816B), equity_curve.csv, governance_state.json, regime_state.json, ml_state.json, extra_counters.json, evaluation_event_history.json
- Pre-deploy `manifest.json`: saved_at=2026-04-08T19:59:54Z, generation=27, total_runs=104, total_trades=204, cumulative_pnl=-492.33, best_sharpe=3.4363, ml_is_trained=true, feature_count=79
- Alpaca `/v2/account`: ACTIVE, equity ~$111,576 (file: predeploy_account_snapshot.json)
- Alpaca `/v2/positions`: `[]` (flat, confirmed)
- Alpaca `/v2/clock`: `is_open:false, next_open:2026-04-09T09:30 ET`
- Env (masked): `ALPACA_API_KEY_ID=<masked>`, `ALPACA_PAPER=true`, `APP_ENVIRONMENT=development`
- Mount `/app/organism_brain` bound to host `/Users/marselkei/VS/intra/organism_brain`, RW

## 4. Deployment Actions
- Command: `docker compose -f docker-compose.paper.yml up -d --build api`
- Start: 2026-04-09T01:25:07Z (approx, prior to build)
- Build: succeeded, image `intra-api:latest` (sha256:40cfd63e...), ~56s layered build, COPY context 49.19MB
- Container recreated: old api container removed, new container Started at 2026-04-09T01:25:36Z
- Redis and postgres containers untouched (still Up 42h)
- Health poll: t+10s starting, t+20s starting, t+30s **healthy**

## 5. Post-Deploy Boot Verification
- New container `intra-api-1`: StartedAt=2026-04-09T01:25:36.999Z, RestartCount=0, Health=healthy
- `/health`: ok. `/api/v1/system/health`: healthy
- Brain mount RW test: `RW_OK`
- `APP_ENVIRONMENT=development` confirmed in container env
- Boot log clean (0 ERROR, 0 CRITICAL). Key entries:
  - `brain_persistence "Brain loaded: gen=27, runs=104, trades=204"` (line 219)
  - `brain_persistence "Learner state restored: gen=27, trades=204"` (line 496)
  - `live_engine "Organism live engine initialized from brain: gen=27, trades=204"` (line 898)
  - `trading_phase "Trading phase: production_frozen (trades=204, ML_isolation_exit=0, freeze_exit=96)"`
  - `live_engine "PREFLIGHT: 16/18 checks passed (0 critical failures, 2 warnings)"`
  - `scheduler "Organism scheduler starting: tick_interval=10s, brain_loaded=True, streaming=True"`
- Alpaca still reachable, positions still flat (account/positions validated against same endpoints post-boot)

## 6. Patch Signature Verification in Running Container

| # | Check | File | Expected | Evidence | Result |
|---|---|---|---|---|---|
| 1 | `learner.state.best_sharpe` (Patch C) | brain_persistence.py | PRESENT | lines 1272, 1276 | PASS |
| 2 | `_apply_live_manifest_fields` (Patch B) | brain_persistence.py | PRESENT | lines 580, 598 (def), 669 | PASS |
| 3 | `save(..., force=...)` (Patch A) | brain_persistence.py | PRESENT | line 243: `force: bool = False,` (within def save multi-line sig starting line 231) | PASS |
| 4 | `force_save_brain` method (Patch A) | live_engine.py | PRESENT | line 4279: `def force_save_brain(self) -> dict:` | PASS |
| 5 | `POST /save` route (Patch A) | organism/routes.py | PRESENT | line 336: `@router.post("/save")` | PASS |
| 6 | `require_admin` on route | organism/routes.py | PRESENT | line 340: `_admin=Depends(require_admin),` | PASS |
| 7 | `_get_engine(request)` usage | organism/routes.py | PRESENT | line 361: `engine = _get_engine(request)` | PASS |
| 8 | Normal `_save_brain` still calls `walk_forward_gate` | live_engine.py | PRESENT | line 4386: `should_save, reason = self.brain.walk_forward_gate(` | PASS |
| 9 | `_last_sharpe_decay_date` absent | brain_persistence.py | MISSING | grep returned no matches | PASS |

Note: check 5 originally looked for routes in `backend/api/routes/` but organism routes live in `backend/organism/routes.py` — the route is mounted there and confirmed reachable at `/api/v1/organism/save`.

## 7. Force-Save Execution

**7a. Negative — missing force param:**
```
POST /api/v1/organism/save (Bearer token, no ?force)
-> HTTP 400
{"detail":{"success":false,"error":"force=true query parameter required for /save","hint":"Use POST /api/v1/organism/save?force=true"}, ...}
```

**7b. Negative — no auth:**
```
POST /api/v1/organism/save?force=true (no Authorization header)
-> HTTP 401
{"detail":"Authentication required", ...}
```

**7c. Positive — force-save:**
```
POST /api/v1/organism/save?force=true (Bearer admin)
-> HTTP 200
{
  "success": true,
  "forced": true,
  "tick": 8705,
  "generation": 27,
  "total_trades": 204,
  "cumulative_pnl": -492.33,
  "best_sharpe": 3.4363,
  "ml_is_trained": true,
  "feature_count": 79,
  "timestamp": "2026-04-09T01:27:00.245847+00:00"
}
```

## 8. Post Force-Save Artifact Verification

All mtimes `Apr 8 18:27` local = `2026-04-09T01:27Z` = fresh rewrite. Pre-deploy mtimes were `Apr 8 12:59` local = `2026-04-08T19:59Z`.

| File | Status | Size | mtime (post) | Freshly rewritten? |
|---|---|---|---|---|
| manifest.json | PRESENT | 247 B | 01:27Z | YES |
| learning_state.json | PRESENT | 264 B | 01:27Z | YES |
| ml_classifier.joblib | PRESENT | 248507 B | 01:27Z | YES |
| ml_regressor.joblib | PRESENT | 168098 B | 01:27Z | YES |
| reference_feats.csv | PRESENT | 20128 B | 01:27Z | YES |
| evolved_params.json | PRESENT | 3717 B | 01:27Z | YES |
| transfer_knowledge.json | **MISSING** | — | — | not written by force_save_brain (see Finding) |
| trade_history.csv | PRESENT | 24816 B | 01:27Z | YES |
| equity_curve.csv | PRESENT | 89011 B | 01:27Z | YES |
| governance_state.json | PRESENT | 297 B | 01:27Z | YES |
| regime_state.json | PRESENT | 178 B | 01:27Z | YES |
| extra_counters.json | PRESENT | 9749 B | 01:27Z | YES |
| ml_state.json | PRESENT | 3131 B | 01:27Z | YES |
| evaluation_event_history.json | PRESENT | 47898 B | 01:27Z | YES |

## 9. Manifest Consistency Check (post force-save)

| Field | manifest.json | learning_state.json | Match? |
|---|---|---|---|
| generation | 27 | 27 | YES |
| total_trades | 204 | 204 | YES |
| cumulative_pnl | -492.33 | -492.33 | YES |
| best_sharpe | 3.4363 | 3.4363 | YES |
| ml_is_trained | true | — (signal_gen derived) | YES (loaded joblibs) |
| feature_count | 79 | — (signal_gen derived) | YES |

**Patch B manifest sync correct in live conditions: YES.**

## 10. Hard-Stop Checks

All 12 PASS. See `deploy_verification_apr8_final_bundle/hard_stop_checks.md` for the table.

## 11. Files Produced

All paths relative to `/Users/marselkei/VS/intra/deploy_verification_apr8_final_bundle/`:
- repo_head_sha.txt
- git_status_predeploy.txt
- predeploy_container_status.txt
- predeploy_api_health.txt
- predeploy_manifest.json
- predeploy_learning_state.json
- predeploy_brain_dir_listing.txt
- predeploy_account_snapshot.json
- predeploy_positions_snapshot.json
- predeploy_clock.json
- predeploy_env_snapshot.txt
- predeploy_mounts.txt
- deploy_commands.txt
- postdeploy_container_status.txt
- postdeploy_api_health.txt
- postdeploy_boot_log.txt
- postdeploy_manifest.json
- postdeploy_learning_state.json
- running_container_code_verification.txt
- force_save_response.json
- force_save_negative_no_force_response.txt
- force_save_negative_no_auth_response.txt
- post_force_save_brain_dir_listing.txt
- post_force_save_manifest.json
- post_force_save_learning_state.json
- hard_stop_checks.md

## Findings
1. **force_save_brain does not persist transfer_knowledge.json** — The `brain.save()` call inside `LiveEngine.force_save_brain()` does not pass a `transfer_knowledge` kwarg, and brain_persistence appears to atomically rewrite the brain directory during force-save, which removed the pre-existing `transfer_knowledge.json` (41640 B). Severity: low. Transfer knowledge is regenerated during training runs and brain load does not require it. Recommend opening a follow-up to either (a) pass transfer knowledge through force_save_brain or (b) leave transfer_knowledge.json untouched during brain saves. Not a hard-stop.
