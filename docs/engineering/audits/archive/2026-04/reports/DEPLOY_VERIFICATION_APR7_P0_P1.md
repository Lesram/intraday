# Apr-7 P0/P1 Patch — Deploy Verification

## 1. Verdict
**HARD STOP.**

Reason: the Apr-7 P1 walk-forward best_sharpe daily-decay guard is
not restart-safe. The new `_last_sharpe_decay_date` field is a
transient Python instance attribute on `BrainPersistence`. It is not
written to the manifest, not serialized by any save path, and not
restored on load. Every container restart resets it to `""`,
re-arming the decay path on the same UTC day. Under the realistic
operational pattern (daily rebuilds, hot-fix redeploys, mid-session
restarts) the "once per UTC day" invariant the patch advertises does
not actually hold across the only event that matters here: a
redeploy. The original compounding-decay failure mode is therefore
only partially mitigated.

Per task Section 7: *"If you cannot prove restart survival ... If
the fix is incomplete for real restart conditions, mark HARD STOP."*

Rebuild and redeploy were **NOT performed**. No code, config,
brain state, or container state was modified by this task.

---

## 2. Source State Before Deploy
- Repo root: `/Users/marselkei/VS/intra`
- Branch: `main`
- HEAD SHA: `20189998679c72189af3d39b73d29019bff19d08`
- `git status --short` (relevant files only):
  ```
   M backend/organism/brain_persistence.py
   M backend/organism/live_engine.py
   M monitoring/memory_monitoring.json
  ?? tests/test_apr7_p0_p1_fixes.py
  ?? APR7_P0_P1_FIX_REPORT.md
  ?? apr7_p0_p1_fix_bundle/
  ```
- The two patched source files match the prior implementer's
  description (live_engine +48/-... lines, brain_persistence +45/-...
  lines). Patch is in working tree, **not committed**. The
  Apr-7 fix work was therefore "applied to source" but never
  committed and never deployed.
- Compose file: clean. `.env`: clean. `tests/` only adds the new
  Apr-7 test file. No contradictory dirty edits in deploy-relevant
  paths → would have been safe to proceed if not for Section 7.

## 3. Pre-Deploy Runtime Snapshot
- Containers (all healthy):
  - `intra-api-1` — Up 19h, RestartCount 0, StartedAt 2026-04-07T07:37:02Z
  - `intra-redis-1` — Up 20h
  - `trading_platform_db_paper` — Up 20h
- API `/health`: captured to bundle.
- Brain manifest (host = container, mount confirmed):
  ```json
  {
    "brain_format_version": 2,
    "saved_at": "2026-04-08T02:08:47.769066+00:00",
    "generation": 0,
    "total_runs": 214,
    "total_trades": 0,
    "cumulative_pnl": 0.0,
    "best_sharpe": 0,
    "ml_is_trained": false,
    "feature_count": 0
  }
  ```
  Note: `total_trades=0`, `generation=0`, `ml_is_trained=false` in the
  on-disk manifest contradicts the MEMORY.md narrative of "gen 9
  ~195 trades". This is an independent observation, not the deploy
  blocker. It suggests the persisted manifest no longer reflects
  in-memory runtime truth, or the in-memory state has been reset to a
  pristine snapshot. Surfaced for the parent agent.
- Alpaca account snapshot + positions snapshot: captured to bundle.

## 4. Deployment Actions Performed
**None.** Halted at Section 7 gate. No `docker compose build`, no
`docker compose up`, no container replacement. The `intra-api-1`
container observed in Section 3 is the same container that was
already running before this task started.

## 5. Post-Deploy Runtime Verification
N/A — no deploy.

## 6. Apr-7 Fix Signature Verification
The running container is **pre-patch** because no deploy was
performed. Direct evidence:

```
$ docker exec intra-api-1 grep -n "_last_sharpe_decay_date" \
    /app/backend/organism/brain_persistence.py
(no output — field absent)
```

In the host source (where the patch lives, uncommitted):

A. Tick counter fixes (`backend/organism/live_engine.py`):
1. `orders_submitted` increments — PRESENT, lines 1884, 1911, 2366
2. `signals_generated` set on real candidate path — PRESENT, line 2285
3. `trades_closed` / `exits_checked` — PRESENT, lines 1535, 1669, 1688
4. tick log uses these fields — PRESENT (lines 245-258 dataclass
   serialization, line 2912 logging call)

B. Watchdog truth-source fixes (`live_engine.py` lines ~3072-3110):
5. C1 watchdog reads `self._total_orders_submitted` instead of stale
   local zero counter — PRESENT, lines 3076-3082
6. C4 watchdog updated on full brain save — PRESENT (existing path)
7. C4 watchdog updated on save_essential_state path — PRESENT
8. Watchdog baselines seeded on startup/restart — PRESENT, lines
   977-983 (`_watchdog_last_order_tick`, `_watchdog_last_brain_save_tick`,
   `_watchdog_last_total_orders` all seeded explicitly with the
   comment `Apr-7 P0: seed watchdog baselines so a fresh boot does
   NOT...`)

C. Walk-forward gate fix (`backend/organism/brain_persistence.py`):
9. Daily decay rate-limited — PRESENT in host source, lines 1235-1247
10. New `_last_sharpe_decay_date` field — PRESENT in host source,
    line 141; touched only at lines 1235 and 1238

Running container: **all 10 markers ABSENT** (pre-patch image).

## 7. Restart-Survival Check for the Sharpe Guard
See `deploy_verification_apr7_p0_p1_bundle/sharpe_decay_restart_survival_check.md`
for the full audit. Summary:

- Field: `BrainPersistence._last_sharpe_decay_date`, Python instance
  attribute, initialized to `""` in `__init__`.
- Storage: in-memory only.
- Manifest: NOT written to `self._manifest`.
- Save paths: NOT written by `save_essential_state`, NOT written by
  full `save`.
- Load paths: NOT restored by `load` / `from_persistence_dict` / any
  manifest hydration.
- Empirical restart test: NOT executed because the patch is not even
  in the running container yet, so an empirical test would only
  measure the pre-patch image. The static audit is conclusive on its
  own: there is no code path that writes the field to disk, therefore
  no code path can read it back.

**Restart-safe: NO.**

Failure mode that survives the patch:
- Day starts. Tick-rate decay no longer fires (good — P1 intent).
- Walk-forward gate fails once. Decay fires. Field set to today.
- Operator restarts container (rebuild, hot-fix, oom, scheduled
  refresh — pick any). Field resets to `""`.
- Walk-forward gate fails again. Decay fires AGAIN. Same UTC day.
- Repeat per restart. The compounding collapse the patch was
  written to prevent is reachable again — just at restart cadence
  instead of tick cadence.

## 8. Brain State Preservation
N/A for "before vs after deploy" because no deploy occurred. The
on-disk brain state was read once and not modified by this task.

Independent finding (already noted in Section 3): the on-disk brain
manifest is in a pristine-looking state (`total_trades=0`,
`generation=0`, `ml_is_trained=false`) that does not match the
MEMORY.md narrative for this platform. This is unrelated to the
Apr-7 patch, but the parent agent should investigate before the next
session because Section 9's "trades remaining to ML isolation /
evolution freeze" math depends on the true counter.

## 9. Current Phase / Readiness
Using the on-disk manifest at face value:
- `total_trades = 0`
- Phase: learning (well below 200-trade ML isolation boundary)
- Trades to ML isolation exit: 200
- Trades to evolution freeze exit: 300
- Next session crossing 200-trade boundary: NO, by a wide margin

If the MEMORY.md figure (~195 trades) is the true in-memory count,
the next session **could** cross 200 — but I cannot verify that from
the on-disk state, and I am not authorized to introspect or mutate
in-process state in this task. Flagged for parent agent.

## 10. Hard-Stop Checks (PASS/FAIL)
See `deploy_verification_apr7_p0_p1_bundle/hard_stop_checks.md`.

| # | Check | Result |
|---|---|---|
| 1 | deploy completed successfully | NOT RUN |
| 2 | running container healthy | PASS |
| 3 | Apr-7 tick-counter fixes in container | FAIL (not deployed) |
| 4 | Apr-7 watchdog fixes in container | FAIL (not deployed) |
| 5 | daily-decay fix in container | FAIL (not deployed) |
| 6 | daily-decay guard restart-safe | **FAIL** (root blocker) |
| 7 | brain state survived deploy | N/A |
| 8 | APP_ENVIRONMENT correct | PASS |
| 9 | Alpaca account ACTIVE | PASS |
| 10 | no blocker for next session | **FAIL** |

## 11. Files Produced
All under `deploy_verification_apr7_p0_p1_bundle/`:
- `repo_head_sha.txt`
- `git_status_predeploy.txt`
- `predeploy_container_status.txt`
- `predeploy_state.json` (full container State)
- `predeploy_mounts.txt`
- `predeploy_api_health.txt`
- `predeploy_brain_dir.txt`
- `predeploy_brain_manifest.json`
- `predeploy_account_snapshot.json`
- `predeploy_positions_snapshot.json`
- `sharpe_decay_restart_survival_check.md`
- `hard_stop_checks.md`

Not produced (intentionally — no deploy):
- `deploy_commands.txt`, `postdeploy_*`, `running_container_code_verification.txt`
  (the running container is pre-patch; deploying it would have
  shipped a known-incomplete fix, which Section 7 forbids).
