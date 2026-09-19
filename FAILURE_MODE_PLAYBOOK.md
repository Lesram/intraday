# Failure-Mode / Stress-Test Playbook (S19)

**Purpose:** when something goes wrong, you don't want to figure out the response on the fly. This documents likely failure modes, their detection signatures, and the operator response for each.

**Audience:** the operator (you) at the desk, possibly under stress, possibly half-awake.

---

## How to use this playbook

1. Match the symptom to a failure mode below
2. Execute the response steps in order
3. If a step doesn't resolve, escalate to the next one
4. Always: take a brain backup before any irreversible step
5. Always: log what you did in `artifacts/incident_log_<date>.md`

If the symptom doesn't match anything here: **halt trading first, investigate second.**

```sh
# Universal halt — works in any situation:
docker-compose down api
# Or via API if you can reach it:
curl -X POST http://localhost:8000/api/v1/governance/halt -H "Authorization: ..."
```

---

## A. Data-feed failures

### A1. Alpaca data feed dies mid-session (no bars arriving)

**Detection signatures:**
- `logs/application.log` shows `ConnectTimeout`, `ConnectError`, `SSLError` from `backend.integrations.alpaca_data`
- Tick log shows `signals=0 orders=0 exits=0` for many consecutive ticks
- Brain manifest `saved_at` timestamp doesn't update for >2 minutes during market hours
- Live engine logs `Entries blocked (insufficient data)` repeatedly

**Likelihood:** medium (we've seen single ConnectTimeout events on 2026-04-22, 2026-04-23 in production; usually self-resolves within seconds)

**Impact:**
- LOW if positions are flat: engine just doesn't enter
- MEDIUM if positions open: stops/exits don't update, position drifts at last-known regime

**Response:**
```
1. Check Alpaca status page: https://status.alpaca.markets/
2. If Alpaca is degraded:
   - Note positions that need manual oversight
   - Optional: place broker-side stop orders for open positions via Alpaca web UI
   - Wait for feed to recover (typically <5 min)
3. If feed dies for >10 min and we have open positions:
   - Manually close positions via Alpaca web UI or the platform's emergency-close admin route
   - Set governance.halt = true
4. After feed recovers:
   - Verify next 5 ticks fire normally
   - Check brain coherence: cat organism_brain/manifest.json
   - Resume trading by clearing the halt flag
```

### A2. Bad bar (missing data, invalid OHLC)

**Detection:**
- Feature compute warnings in logs
- Diagnostic check fails on `last_row_nans` count

**Response:**
- Wait one tick — usually self-resolves
- If persistent: investigate which symbol; consider removing from universe via `ORGANISM_UNIVERSE_OVERRIDE` env var

---

## B. Brain / state corruption

### B1. Brain manifest unexpectedly reset (gen=0, total_trades=0)

**Detection:**
- `organism_brain/manifest.json` shows critical fields zeroed
- "Brain saved: generation 0" appears in logs after we were at gen >0

**Likelihood:** LOW (F1-F4 hardening makes this hard to trigger)

**Impact:** CRITICAL — our trained ML and evolved params are gone

**Response:**
```
1. STOP trading immediately:
   docker-compose down api

2. Take a snapshot of the corrupted state for investigation:
   cp -r organism_brain organism_brain_corrupted_$(date +%s)

3. Restore from most recent good backup:
   ls organism_brain_archive/   # find newest dated dir
   rm -rf organism_brain
   cp -r organism_brain_archive/<newest-date> organism_brain

4. Verify restored manifest:
   cat organism_brain/manifest.json   # gen, total_trades should be normal

5. Restart container:
   docker-compose up -d --build api

6. Watch first 5 ticks: confirm gen+total_trades load correctly

7. File incident report — F1-F4 guards should have prevented this.
   Investigate which guard failed, re-test, possibly file a P0 fix.
```

### B2. Manifest exists but learning_state.json diverges

**Detection:**
- Diagnostic checks log warning about state divergence
- Manifest gen != learning_state gen

**Response:**
- This is a known pre-F-track edge case. F1-F4 guards prevent NEW occurrences
- Investigate which file is correct (typically the more-recent saved_at wins)
- If unsure, restore from backup as in B1

### B3. ML model file (joblib) corrupt

**Detection:**
- `MLSignalGenerator` raises during predict on every tick
- Log: "Direction model inference failed for X — defaulting to neutral"

**Response:**
- The platform has a built-in fallback (defaults to neutral). Trading continues but ML signal is zeroed.
- Take backup, restore ML files specifically:
  ```
  cp organism_brain_archive/<date>/ml_classifier.joblib organism_brain/
  cp organism_brain_archive/<date>/ml_regressor.joblib organism_brain/
  ```
- Restart container
- Force a retrain via admin route to regenerate fresh files

---

## C. Container / runtime failures

### C1. Container OOM-killed mid-session

**Detection:**
- `docker ps` shows container missing or restart count incremented
- `docker inspect intra-api-1 --format '{{.State.OOMKilled}}'` returns true

**Likelihood:** LOW unless universe expanded or feature memory grows

**Impact:**
- HIGH if positions open: no exits/stops are processed during downtime
- MEDIUM if flat: engine restarts normally, brain reloads

**Response:**
```
1. Check open positions in Alpaca paper/live web UI
2. If positions exist — manually monitor via Alpaca until container restarts
3. Run brain backup BEFORE restart (in case startup corrupts state):
   ./venv/bin/python scripts/runtime/rotate_brain_backup.py
4. docker-compose up -d --build api (auto-restart should already trigger)
5. Verify health: curl localhost:8000/health
6. Verify positions reconciled via broker sync
7. Log: how much memory was being used? Check container `docker stats`.
8. If recurring: increase Docker memory limit OR investigate memory leak.
```

### C2. Disk full

**Detection:**
- `df -h` shows /Users full or >95%
- Logs error: "No space left on device"
- Brain saves failing silently or with errors

**Response:**
- Free space: clear `logs/application.log.*` rotated logs (keep current)
- Clear `organism_brain_archive/` older than 30 days
- Clear Docker images / containers: `docker system prune -a` (CAREFUL)
- If must continue trading: temporarily disable brain saves via env var (NOT RECOMMENDED)

### C3. Bad RC ships (deploy introduces a bug)

**Detection:**
- Tests pass before deploy, behavior wrong after
- Logs show new exceptions
- Trade pattern differs unexpectedly

**Response:** rollback per `MONDAY_DEPLOY_RC_1_5_CURATED.md` rollback section.
```
docker-compose down api
git checkout <previous-good-commit>   # e.g., main / eb90fa3 or ce06d41
docker-compose up -d --build api
```

---

## D. Risk-control firings

### D1. Drawdown-kill fires (governance.frozen=true)

**Detection:**
- `governance_state.json` shows `frozen=true, drawdown_triggered_at=<timestamp>`
- Tick log: `Entries blocked (halt/drawdown/insufficient data)`
- Slack/webhook alert (if wired)

**This is NORMAL, expected behavior under sustained loss.**

**Response:**
```
1. Don't panic. Drawdown-kill IS the safety net working.
2. Check: how much was lost?
   cat organism_brain/extra_counters.json | jq '.peak_equity'
   curl https://api.alpaca.markets/v2/account | jq '.equity'
3. Investigate WHY the drawdown happened:
   - Look at last 20 trades: bad regime? bad symbol? cluster of stops?
   - Cross-reference with the day's market behavior (e.g., FOMC, earnings)
4. If diagnosis is clean ("market hit bad day, stops behaved correctly"):
   - Wait until next session
   - Reset the halt: curl -X POST .../api/v1/governance/unhalt
   - Resume trading next day
5. If diagnosis is concerning ("our stops failed", "ML went haywire"):
   - Don't unhalt yet
   - Investigate the specific failure
   - Consider rollback to previous RC
```

### D2. Daily max-loss kill fires

**Detection:**
- Halt event mid-session with reason "daily_max_loss"
- Today's cumulative P&L crossed threshold

**Response:**
- Halt is intentional. Trading stops for the day.
- Reset is automatic at next session start (next day's market open)
- No manual intervention needed unless the threshold itself is wrong

### D3. Notional cap rejects an order

**Detection:**
- Log: "Order rejected — notional_cap_exceeded"
- The trade simply doesn't fire

**Response:**
- This is the cap doing its job. No action needed unless rejections cluster.
- If many rejections: review whether the cap is correctly calibrated for current capital.

---

## E. Network / external

### E1. Slack/webhook alert delivery failure

**Detection:**
- Alert send retry logs in `application.log`
- You don't receive expected alerts

**Impact:** LOW for trading; HIGH for monitoring

**Response:**
- Verify Slack webhook URL valid (curl test)
- Check Slack/webhook service status
- Failover: monitor logs directly until restored

### E2. Database connection drops

**Detection:**
- Logs: "Database session error, rolling back"
- API endpoints returning 500 on writes

**Response:**
- Trading engine doesn't depend on DB for live ticks (uses brain files)
- API endpoints (status, admin) may be temporarily unavailable
- Restart DB container: `docker-compose restart db`
- If recurring: check disk, network, Postgres logs

### E3. Alpaca account flagged (PDT, restricted)

**Detection:**
- `/v2/account` returns `account_blocked=true` or `pattern_day_trader=true` (live capital)

**Likelihood:** MEDIUM if live capital < $25K (PDT rules apply for cash accounts)

**Response:**
- HALT trading immediately (we cannot trade through a blocked account)
- Resolve with Alpaca support
- For PDT: wait out the restriction OR stop day-trading until account >$25K

---

## F. Strategic / behavioral failures

### F1. Position-count violation (>2 simultaneous in Stage-1)

**Detection:**
- `curl /v2/positions` returns >2 positions
- Or our internal MAX_POSITIONS gate didn't fire

**Likelihood:** LOW (the gate is well-tested) but worth flagging

**Response:**
- Take brain backup
- HALT immediately
- Investigate: did our gate misfire? Was there a broker desync (our positions vs Alpaca's)?
- Manually close excess positions via Alpaca UI
- Don't unhalt until root cause identified

### F2. Pyramid_cut share spikes (>20% post RC-1.5)

**Detection:**
- Post-close metric: pyramid_cut > 20% of exits
- Expected post-RC-1.5: <= 8%

**This is a KEY POST-DEPLOY VALIDATION metric.**

**Response:**
- Note in DAY_1_POST_DEPLOY_NOTE.md
- If 2 consecutive days >20%: the gate fix isn't doing what we expect → consider rollback to bare eb90fa3
- Investigate: are entries firing at low composite? Are pyramid triggers misbehaving?

### F3. ML retrain rejected for 5+ consecutive cycles

**Detection:**
- `evaluation_event_history.json` shows "rejected" for many recent generations

**Response:**
- Acceptance gate is working — protecting against bad models
- But persistent rejection means the data has shifted to where any new model fails
- Investigate: regime change? Distribution shift? Bug in trainer?
- Don't intervene unless platform ALSO is performing poorly

### F4. Trade pattern changes drastically post-deploy

**Detection:**
- Trade rate doubles or halves vs baseline
- Symbol mix shifts dramatically

**Response:**
- Cross-reference with deploy: did we change something that should have caused this? Yes → expected, monitor.
- No → unexpected, investigate.

---

## G. Operator-side failures

### G1. You miss a session check

**Likelihood:** medium (you're human)

**Response:**
- The platform doesn't care; it runs autonomously
- Catch up at the next available time
- The Stage-1 monitoring template (in STAGE_1_CAPITAL_PLAN.md) is daily not hourly — missing one is fine

### G2. You fat-finger a config change

**Detection:** unexpected behavior post-restart

**Response:**
- Roll back the env var or config file change
- Restart container
- Don't push panicked fixes — sleep on it

### G3. You feel stressed and want to pull capital

**Detection:** emotional rather than technical

**Response:**
- That's a valid signal. Halt trading. Withdraw capital.
- The platform isn't going anywhere. You can come back later.
- Stage-1 specifically is designed to be SMALL so that this is OK.

---

## Severity matrix

| Severity | Examples | Response time |
|---|---|---|
| **CRITICAL** | brain corruption, account blocked, position-count violation | Immediate halt + investigate |
| **HIGH** | container OOM, deploy regression, sustained data feed outage | Halt during market hours; investigate before next session |
| **MEDIUM** | drawdown-kill (intentional), persistent ML rejection | Note, observe, decide next session |
| **LOW** | single ConnectTimeout, alert delivery delay, single bad bar | Log, continue |

---

## Pre-incident discipline (the best response is preparation)

```
[ ] Brain backup rotation active (verified via launchd)
[ ] At least 7 days of brain backups retained
[ ] Container memory limits set in docker-compose.yml
[ ] Alpaca status page bookmarked
[ ] Slack/webhook alert URLs in .env and tested
[ ] Rollback paths documented for current and previous RC
[ ] Operator phone alerts enabled
[ ] Operator emergency procedures reviewed (this file)
[ ] Stage-1 capital is small enough that worst-case loss is acceptable
```

If all 9 are checked, you're prepared for any of the failure modes in this playbook.

---

## What's deliberately NOT in this playbook

Things that aren't documented because they're truly unexpected:
- Cosmic-ray bit flips (build error correction into tooling, not playbook)
- Alpaca going out of business (account is segregated, would just mean withdrawing)
- Black-swan market events (no playbook can cover these — Stage-1's small size is itself the response)
- Multi-component cascading failures (rare; investigate root cause)

For these: the universal response is "halt trading, investigate, don't make hasty decisions."

---

## Living document

This playbook should be updated each time we encounter a real failure that isn't covered here. After every incident:
1. Add a new section with the symptom + response
2. Update severity matrix if needed
3. Commit with `docs(ops): playbook update — <symptom>`

The playbook gets better as the platform gets older.
