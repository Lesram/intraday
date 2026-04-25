# MONDAY DEPLOY — RC-1.5 curated
**Target time:** Monday 2026-04-27, 8:30–9:00 ET (pre-open)
**Target branch:** `rc-1.5-curated`
**Target commit:** `090076a` (or whatever HEAD is on `rc-1.5-curated` Monday morning — verify in step 3)
**Live commit (current):** `ce06d41`
**Fallback target:** `eb90fa3` (per `MONDAY_DEPLOY_eb90fa3.md`)

This is a checklist. Tick each box. If any check fails, **STOP** and follow the rollback path at the bottom.

---

## What this deploy ships

### Behavior changes (live):
1. **Composite-gate fix** (RC-1.5 commit `a4c5e9b`): production gate now uses composite confidence (0.50×ml + 0.30×breakout + 0.20×tension) instead of `ml_signal.effective_confidence`. Forensically supported: 132 of 182 live trades (73%) had composite < 0.45 and accounted for −$106 of −$108 loss.

### Telemetry-only additions (no live behavior change):
2. **Shadow regime detector** (commit `5825be9`): logs what regime classifier with `intraday_trend_sensitivity=0.50` would decide, alongside live regime. Disagreement events logged.
3. **Shadow composite formula** (commit `5825be9`): logs what composite with `0.20 ml + 0.50 breakout + 0.30 tension` weights would produce. Disagreement events on gate decision logged.

### Infrastructure additions (no behavior change):
4. **Brain backup rotation** (commit `fc766b5`): script + launchd plist + docs. Optional install per `scripts/runtime/INSTALL_BRAIN_BACKUP.md`.
5. **Tension proxy single-source-of-truth** (commit `1c4174f`): identical formula as before, refactored. No live behavior change.
6. **Replay simulator delay_fill option** (commit `1c4174f`): off by default, doesn't affect live.

Everything from `eb90fa3` is included (it's the merge base): G1/G2/G3, Exp 4, H1/H2, notional cap, daily max-loss, alert wiring, H5 governance, canonical drawdown-kill, compose alignment.

## Pre-deploy (8:30–8:45 ET)

```
[ ] 0. Take a sip of coffee. Read the bottom of this file (rollback) before you start.

[ ] 1. cd /Users/marselkei/VS/intra
[ ] 2. git status   (expect clean tracked tree)
[ ] 3. git checkout rc-1.5-curated && git rev-parse HEAD
       Expect: a hash on rc-1.5-curated branch (current HEAD = 090076a or newer)
[ ] 4. docker ps --format 'table {{.Names}}\t{{.Status}}'
       Expect: intra-api-1 healthy, intra-redis-1 healthy, trading_platform_db_paper healthy
[ ] 5. curl -s http://localhost:8000/health
       Expect: {"status":"ok",...}
[ ] 6. ls artifacts/deploy_preflight_rc_1_5_curated/organism_brain_backup_pre_rc_1_5_curated_*
       Expect: directory present (brain backup taken Saturday)
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
[ ] 9. docker-compose down api
[ ] 10. docker-compose up -d --build api
        Wait ~60–90s for build + start.
[ ] 11. curl -s http://localhost:8000/health
        Expect: {"status":"ok","version":"1.0.0",...}
[ ] 12. docker ps --format 'table {{.Names}}\t{{.Status}}'
        Expect: intra-api-1 Up, healthy, restart count = 0
```

## Post-deploy verification (8:50–9:00 ET, before market open)

```
[ ] 13. tail -100 logs/application.log | grep -iE 'governance|drawdown|halt|frozen|alert'
        Expect to see:
          - "Governance state restored from brain"
          - "drawdown_kill_pct=0.2000 ..." (canonical resolver firing)
          - "alert wiring registered" (or graceful skip if URLs absent)

[ ] 14. ./venv/bin/python scripts/runtime/write_runtime_snapshot.py
        Then: cat artifacts/resolved_config_snapshot.json | head -20
        Expect: ORGANISM_DRAWDOWN_KILL_PCT=0.20, MAX_POSITIONS=8, ALPHA_TOP_N=5

[ ] 15. cat organism_brain/manifest.json
        Expect: gen, total_trades, cumulative_pnl unchanged from sticky-note in step 7
        (deploy must NOT wipe brain — F1–F4 guards protect this)

[ ] 16. Diff verification:
        diff <(jq -S . artifacts/deploy_preflight_rc_1_5_curated/manifest.json 2>/dev/null || \
                jq -S . artifacts/deploy_preflight_rc_1_5_curated/organism_brain_backup_pre_rc_1_5_curated_*/manifest.json) \
             <(jq -S . organism_brain/manifest.json)
        Expect: only 'saved_at' (and possibly 'total_runs') differ.
        Critical fields (generation, total_trades, cumulative_pnl, best_sharpe,
        ml_is_trained, feature_count) must be IDENTICAL.

[ ] 17. Confirm RC-1.5 changes are in container:
        docker exec intra-api-1 python -c "import sys; sys.path.insert(0,'/app'); \
            from backend.organism.regime import RegimeDetector; \
            d = RegimeDetector(is_intraday=True, bars_per_day=390, intraday_trend_sensitivity=0.50); \
            print(f'shadow detector accepts kwarg, threshold={d._trend_threshold:.5f}')"
        Expect: prints non-zero threshold value.
```

## First-tick observation (9:00–9:30 ET, market open)

```
[ ] 18. Watch logs/application.log live for first 5 minutes:
        tail -f logs/application.log
        Look for:
          - tick_count incrementing
          - regime detection running
          - alpha_scanner / breakout_scanner producing scores
          - "RC-1.5 shadow:" log lines (regime/composite disagreement events)
          - any ERROR / CRITICAL = STOP, investigate

[ ] 19. After ~5 min of trading, verify a trade has fired or non-fire decisions logged:
        grep -E 'order|fill|entry|exit|skipped' logs/application.log | tail -20

[ ] 20. After 30 min, run a quick health check:
        - container.RestartCount still 0
        - logs free of unexpected ERROR
        - manifest.json saved_at is recent
        - account state at Alpaca: positions populated as expected
```

## Synthetic verification of new capabilities (during the day, low priority)

```
[ ] 21. Notional-cap reject path (synthetic test) — verify rejection in logs.
[ ] 22. Daily max-loss kill path (replay-only synthetic test) — verify halt event.
[ ] 23. Alert wiring delivery — verify Slack/webhook receives test event.
[ ] 24. Drawdown-kill canonical resolver — verify log line at step 13.
[ ] 25. **NEW for RC-1.5:** confirm shadow-disagreement log lines appear in
       logs/application.log with format "RC-1.5 shadow: regime disagreement"
       and "RC-1.5 shadow: composite gate disagreement". These accumulate
       across the session — should see at least a few per hour on real bars.
```

## Post-close (16:00 ET)

```
[ ] 26. Capture post-deploy session metrics:
        ./venv/bin/python scripts/runtime/write_runtime_snapshot.py
        cat organism_brain/manifest.json
        cat organism_brain/learning_state.json
        Note: trades_today, pnl_today, halt_events, exit_reason mix.

[ ] 27. **NEW for RC-1.5:** count shadow disagreements:
        grep -c "RC-1.5 shadow: regime disagreement" logs/application.log
        grep -c "RC-1.5 shadow: composite gate disagreement" logs/application.log
        These two counts feed RC-2 evidence base.

[ ] 28. **CRITICAL POST-DEPLOY METRIC**:
        # how many trades fired this session?
        N=$(awk -F, '$22 ~ /^2026-04-27/' organism_brain/trade_history.csv | wc -l)
        # how many were pyramid_cut?
        P=$(awk -F, '$22 ~ /^2026-04-27/ && $9 ~ /pyramid_cut/' \
            organism_brain/trade_history.csv | wc -l)
        echo "trades=$N pyramid_cut=$P pct=$(echo "scale=2; 100*$P/$N" | bc)%"
        # Pre-deploy 12-session baseline: pyramid_cut = 31% of exits.
        # RC-1.5 expectation: pyramid_cut <= 8% of exits (composite gate
        # should filter 81% of would-be pyramid_cuts).
        # If pyramid_cut% > 20%, the gate fix isn't doing what we expect.

[ ] 29. Write a one-paragraph note in artifacts/deploy_preflight_rc_1_5_curated/
        DAY_1_POST_DEPLOY_NOTE.md.

[ ] 30. Commit the day-1 note locally. Do NOT push without confirmation.
```

---

## Rollback path (if any check fails)

If at any point a check fails:

```
1. Stop trading immediately (governance halt API or compose down):
   docker-compose down api

2. Restore brain from backup:
   cp -r artifacts/deploy_preflight_rc_1_5_curated/organism_brain_backup_pre_rc_1_5_curated_*/* organism_brain/

3. Choose rollback target:
   # Option A: revert to bare eb90fa3 (less risk than RC-1.5):
   git checkout main   # main is at eb90fa3 + audit docs
   # Option B: revert all the way to ce06d41 (fully back to current live):
   git checkout ce06d41

4. Rebuild:
   docker-compose up -d --build api

5. Verify health:
   curl http://localhost:8000/health
   docker inspect intra-api-1 --format '{{.RestartCount}}'

6. Note what failed in artifacts/deploy_preflight_rc_1_5_curated/ROLLBACK_NOTE.md
```

---

## Why ship RC-1.5 curated instead of bare eb90fa3?

The composite-gate fix has the strongest live-data evidence of any change in the platform: counterfactually, it would have avoided 98% of the 12-session loss. Track 1 forensic analysis. RC-1.5 also adds shadow-mode telemetry that turns RC-2 (regime + ML weight) into a data-driven decision a week from now.

Trade-off: marginally more risk surface (one new gate variable, two new logging code paths) vs. fixing the known-broken gate. Worth it.

If you'd rather ship bare eb90fa3 (no composite gate change), use `MONDAY_DEPLOY_eb90fa3.md` instead. RC-1.5 curated is strictly additive — same eb90fa3 code plus the gate fix and shadow telemetry.

---

## What this deploy resolves (one shot)

- 5 P0 real-money blockers (RM-1 to RM-5, RM-7) — from eb90fa3 base
- 3 P1 mechanical drag fixes (G1, G2, G3) — from eb90fa3 base
- 1 strategy experiment (Exp 4) — from eb90fa3 base
- 1 P1 governance fix (H5 settings API) — from eb90fa3 base
- 1 P1 config alignment (compose drawdown-kill) — from eb90fa3 base
- **NEW: composite-gate fix** — Track 1 finding, +$106 counterfactual

Bundle composition: 9 commits ahead of `main`, RC-1.5 fixes plus all weekend research artifacts.

Reference: `docs/engineering/reviews/pr-deploy-eb90fa3-eb90fa3/` (eb90fa3 review bundle still applies for the base layer).
