# MONDAY DEPLOY — `eb90fa3`
**Target time:** Monday 2026-04-27, 8:30–9:00 ET (pre-open)
**Target commit:** `eb90fa369e2739f77c7b1789aa47bd8b83184912`
**Live commit (current):** `ce06d41`

This is a checklist. Tick each box. Do not skip. If any check fails, **STOP** and follow the rollback path at the bottom.

---

## Pre-deploy (8:30–8:45 ET)

```
[ ] 0. Take a sip of coffee. Read the bottom of this file (rollback) before you start.

[ ] 1. cd /Users/marselkei/VS/intra
[ ] 2. git fetch && git status
       Expect: clean worktree, on branch main
[ ] 3. git rev-parse HEAD
       Expect: eb90fa369e2739f77c7b1789aa47bd8b83184912
       (or eb90fa3 short — must match)
[ ] 4. docker ps --format 'table {{.Names}}\t{{.Status}}'
       Expect: intra-api-1 healthy, intra-redis-1 healthy, trading_platform_db_paper healthy
[ ] 5. curl -s http://localhost:8000/health
       Expect: {"status":"ok",...}
[ ] 6. ls artifacts/deploy_preflight_eb90fa3/organism_brain_backup_pre_eb90fa3_20260425/
       Expect: directory present, non-empty (brain backup taken Saturday)
[ ] 7. Note pre-deploy state to a sticky-note:
       generation = ___ (expect 124+)
       total_trades = ___ (expect 396+)
       cumulative_pnl = $___
       best_sharpe = ___
       (read from organism_brain/manifest.json)
```

## Deploy (8:45–8:50 ET)

```
[ ] 8. Confirm Slack/webhook URLs are in .env if alerts are wanted live
       (search .env for SLACK_WEBHOOK_URL or ALERT_WEBHOOK_URL — non-blocking if absent)
[ ] 9. docker-compose down api
       (only api — leave db and redis up; brain volume persists)
[ ] 10. docker-compose up -d --build api
        Wait ~60–90s for build + start.
[ ] 11. curl -s http://localhost:8000/health
        Expect: {"status":"ok","version":"1.0.0",...}
[ ] 12. docker ps --format 'table {{.Names}}\t{{.Status}}'
        Expect: intra-api-1 Up, healthy, restart count = 0
[ ] 13. docker inspect intra-api-1 --format '{{.RestartCount}}'
        Expect: 0
```

## Post-deploy verification (8:50–9:00 ET, before market open)

```
[ ] 14. tail -100 logs/application.log | grep -iE 'governance|drawdown|halt|frozen|alert'
        Expect to see:
          - "Governance state restored from brain"
          - "drawdown_kill_pct=0.2000 ..." (canonical resolver firing)
          - "alert wiring registered" (or graceful skip if URLs absent)

[ ] 15. ./venv/bin/python scripts/runtime/write_runtime_snapshot.py
        Then: cat artifacts/resolved_config_snapshot.json | head -20
        Expect: ORGANISM_DRAWDOWN_KILL_PCT=0.20, MAX_POSITIONS=8, ALPHA_TOP_N=5

[ ] 16. cat organism_brain/manifest.json
        Expect: gen, total_trades, cumulative_pnl unchanged from sticky-note in step 7
        (deploy must NOT wipe brain — the F1–F4 guards protect this)

[ ] 17. Diff verification:
        diff <(jq -S . artifacts/deploy_preflight_eb90fa3/manifest.json) \
             <(jq -S . organism_brain/manifest.json)
        Expect: only 'saved_at' and possibly 'total_runs' to differ (engine restart bumps total_runs).
        Critical fields (generation, total_trades, cumulative_pnl, best_sharpe,
        ml_is_trained, feature_count) must be IDENTICAL.

[ ] 18. Curl status (will require auth or use admin route):
        curl -s http://localhost:8000/api/v1/organism/status -H "Authorization: ..."
        Expect: governance.frozen=false, trading_halted=false, universe_size=22
```

## First-tick observation (9:00–9:30 ET, market open)

```
[ ] 19. Watch logs/application.log live for first 5 minutes:
        tail -f logs/application.log
        Look for:
          - tick_count incrementing
          - regime detection running
          - alpha_scanner / breakout_scanner producing scores
          - any ERROR / CRITICAL = STOP, investigate

[ ] 20. After ~5 min of trading, verify a trade has fired or a non-fire decision is logged:
        grep -E 'order|fill|entry|exit|skipped' logs/application.log | tail -20

[ ] 21. After 30 min, run a quick health check:
        - container.RestartCount still 0
        - logs free of unexpected ERROR
        - manifest.json saved_at is recent (within last few minutes)
        - account state at Alpaca: positions populated as expected
```

## Synthetic verification of new capabilities (during the day, low priority)

These can be run after lunch or after the close — they exercise the new code paths but are not entry-blocking.

```
[ ] 22. Notional-cap reject path:
        Construct a synthetic test order that exceeds the per-trade notional cap;
        verify rejection appears in logs with reason = "notional_cap_exceeded".
        (Use scripts/ if available, or do this in a unit test with the live config.)

[ ] 23. Daily max-loss kill path:
        Simulate (in a test, not live) a sequence of losses crossing the threshold;
        verify halt event fires.

[ ] 24. Alert wiring delivery:
        Trigger a synthetic governance frozen=true event;
        verify Slack/webhook receives the alert (if URLs configured).

[ ] 25. Drawdown-kill canonical resolver:
        Already verified by step 14. Document the actual log line.
```

## Post-close (16:00 ET)

```
[ ] 26. Capture post-deploy session metrics:
        ./venv/bin/python scripts/runtime/write_runtime_snapshot.py
        cat organism_brain/manifest.json
        cat organism_brain/learning_state.json
        Note: trades_today, pnl_today, halt_events, exit_reason mix.

[ ] 27. Write a one-paragraph note in artifacts/deploy_preflight_eb90fa3/
        DAY_1_POST_DEPLOY_NOTE.md:
          - Did the deploy go clean?
          - Did the canonical resolver log fire?
          - Did the brain stay coherent?
          - Did any new code path raise an issue?
          - Did pyramid_cut share drop vs baseline (yes/no/inconclusive)?

[ ] 28. Commit the day-1 note locally. Do NOT push without confirmation.
```

---

## Rollback path (if any check fails)

If at any point a check fails or the platform behaves unexpectedly:

```
1. Stop trading immediately:
   curl -X POST http://localhost:8000/api/v1/governance/halt -H "..."
   (or set governance frozen via the admin route)

2. Stop the api container:
   docker-compose down api

3. Restore brain from backup:
   cp -r artifacts/deploy_preflight_eb90fa3/organism_brain_backup_pre_eb90fa3_20260425/* organism_brain/

4. Revert to ce06d41:
   git checkout ce06d41
   docker-compose up -d --build api

5. Verify health:
   curl http://localhost:8000/health
   docker inspect intra-api-1 --format '{{.RestartCount}}'

6. Note what failed in artifacts/deploy_preflight_eb90fa3/ROLLBACK_NOTE.md
   so we can address it offline before retrying.
```

---

## What this deploy resolves (one shot)

- 5 P0 real-money blockers (RM-1 to RM-5, RM-7)
- 3 P1 mechanical drag fixes (G1, G2, G3)
- 1 strategy experiment (Exp 4)
- 1 P1 governance fix (H5 settings API)
- 1 P1 config alignment (compose drawdown-kill default)

Bundle composition: 8 commits, +1144 / −13 LOC, 14 new tests (43/43 changeset tests pass).

Reference: `docs/engineering/reviews/pr-deploy-eb90fa3-eb90fa3/LIVE_AUDIT_INDEX.md`
