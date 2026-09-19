# Release Candidate Deploy Plan

**RC**: `eb90fa3` | **From (live)**: `ce06d41` | **Platform**: paper Alpaca
**Deploy status**: PLAN ONLY — no deploy has occurred in this sprint.

---

## 0. Deploy gates (must all be TRUE before starting)

```
[ ] Worktree clean at eb90fa3                    (verified by sprint)
[ ] All 8 RC commits present in main            (verified by sprint — git log)
[ ] Focused test suites green                    (10/10 governance tests pass)
[ ] ORGANISM_MAX_NOTIONAL set in .env (>0)       (deploy-time)
[ ] ORGANISM_MAX_DAILY_LOSS set in .env (>0)     (deploy-time)
[ ] SLACK_WEBHOOK_URL set in .env                (deploy-time)
[ ] ORGANISM_DRAWDOWN_KILL_PCT reviewed          (current .env=0.20 is 4x default)
[ ] Off-hours deploy window                      (post-close, pre-open)
[ ] Rollback image available                     (ce06d41 image retained)
```

No deploy-time code changes needed.

---

## 1. Deploy sequence (exact)

### Step 1 — Pre-deploy (offline)

```bash
# Verify repo state
git rev-parse HEAD                               # expect eb90fa3
git status --short                               # expect clean
./venv/bin/python -m pytest \
    tests/test_governance_drawdown_canonical.py \
    tests/test_h5_settings_governance.py \
    tests/test_g1_g2_g3_mechanical_fixes.py \
    tests/test_experiment_4_trailing_giveback.py \
    tests/test_h1_h2_real_money_hardening.py \
    tests/test_real_money_risk_limits.py \
    --timeout=15 -q
# expect: all pass
```

### Step 2 — Set the env prerequisites

Edit `.env` to add/verify:
```
ORGANISM_MAX_NOTIONAL=2500
ORGANISM_MAX_DAILY_LOSS=500
SLACK_WEBHOOK_URL=<paste real webhook>
ORGANISM_DRAWDOWN_KILL_PCT=0.20   # or tighten to 0.10 for Stage-1-adjacent safety
```

Test the Slack webhook with a manual curl before proceeding:
```bash
curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"RC eb90fa3 deploy gate test"}' \
    "$SLACK_WEBHOOK_URL"
```
Expect Slack message received. If not, stop.

### Step 3 — Build image from HEAD

```bash
docker compose -f docker-compose.paper.yml build api
docker image inspect intra-api --format='{{.Created}}'
# expect: a fresh timestamp (not 2026-04-16)
```

Optional but recommended: write the commit SHA into the image via a build step so `/health` can report it. (Deferred to a future hardening pass unless operator requires it now.)

### Step 4 — Rolling restart

```bash
docker compose -f docker-compose.paper.yml up -d --no-deps api
docker logs --tail 100 intra-api-1 | grep -i "governance\|drawdown\|startup"
```

**Expect in startup logs**:
```
Governance drawdown_kill_pct=0.2000 source=env code_default=0.0500 cooldown_s=300
WARNING ... drawdown_kill_pct=0.2000 is 4.00x the code default 0.0500 — verify this is intentional
```

If `source=code_default` appears, the env file was not loaded — stop and investigate.

### Step 5 — Post-deploy verification

```bash
# Container healthy
curl -f http://localhost:8000/healthz                    # 200
curl -f http://localhost:8000/health                     # 200

# Governance state sane
curl -s http://localhost:8000/organism/status | jq '.governance'
# expect: frozen=false, trading_halted=false

# Brain state intact
jq '.total_trades, .generation, .cumulative_pnl' organism_brain/manifest.json
# expect: ≥ 370 trades, ≥ 115 gen, roughly -619.75 pnl
```

### Step 6 — First-tick smoke test

Let the live loop run for one tick cycle (`ORGANISM_TICK_INTERVAL_SECONDS=10`). Watch for:
- No NEW tracebacks in logs
- `exit_levels_restored` lines (G1 guard)
- No `bypass` or `fallback` warnings from the new drift/guard code

### Step 7 — Observation window (5–10 sessions)

- Daily post-close report every session
- Watch chop trailing-stop giveback delta (Exp4 success metric)
- Watch `SYSTEM_ERROR,WARNING` alerts (H2 drift neutralization rate)
- Watch `RISK_VIOLATION,CRITICAL` alerts (daily-loss halts)
- Watch G1 WARNING counts (exit-level restore failures)

**Decision point at end of observation window**: continue iterating (Phase C, exp3B decision, position-loss auto-close) OR evaluate Stage-1 readiness.

---

## 2. Rollback plan

### Tier A — Env-level rollback (fastest, no downtime)
- Unset `ORGANISM_MAX_NOTIONAL=0` → cap disabled
- Unset `ORGANISM_MAX_DAILY_LOSS=0` → circuit breaker disabled
- Unset `SLACK_WEBHOOK_URL` → alerts silent
- Restart container: `docker compose restart api`

This deactivates the new risk controls without reverting code.

### Tier B — Exp4 mode flip (single-file edit)
- In `backend/organism/adaptive_exits.py`, change `_EXP4_CHOP_TRAIL_MODE = "widen"` → `"disable"` OR revert the block
- Rebuild + restart
- Exp4 widen is reverted; mechanical hardening and alerting remain

### Tier C — Full rollback to live `ce06d41`
- `docker pull intra-api:ce06d41` (or rebuild from the commit)
- `docker compose -f docker-compose.paper.yml up -d --no-deps api`
- Brain state survives (Full Patch F persistence is unchanged by the rollback)

---

## 3. Failure modes and responses

| Failure | Detection | Response |
|---|---|---|
| Startup log missing `Governance drawdown_kill_pct=...` | No log line after restart | Image build failed or wrong entry point. Rebuild and retry. |
| Startup log says `source=code_default` when env is set | Log shows 0.05 / code_default | `.env` not loaded by compose. Verify `env_file:` block in `docker-compose.paper.yml`. |
| Slack webhook silent on staged test | No Slack message from Step 2 curl | Wrong URL / permissions / Slack workspace. Fix before deploying. |
| First-tick crash | Container unhealthy after restart | Tier C rollback. Capture logs. |
| Tracebacks on H1/H2 code path | `kelly_sizer` / `ml_signal` errors | Tier B or Tier C rollback. |
| Exp4 producing runaway trails | Trailing-stop logs show unreasonable distances | Tier B: mode flip. |
| Unexpected daily-loss halt on small PnL | Circuit breaker triggers on sub-threshold loss | Check `ORGANISM_MAX_DAILY_LOSS` value. Tier A rollback. |

---

## 4. Non-goals (explicit)

The following are **not** part of this deploy:
- Phase C rank/direction/size split
- Exp3B confidence inversion
- Position-loss auto-close (−$200/pos)
- Sector-notional cap (≤40%)
- Weekly max-drawdown halt (−$1,500/week)
- Calibration persistence across retrains
- Exploration dead-code removal
- Confidence-authority centralization

These are documented in `MASTER_PLATFORM_STRATEGY_SUMMIT.md §9` and are deferred.

---

## 5. Post-deploy follow-ups

Within 48 hours of deploy:
- [ ] Record the deploy in `docs/engineering/reviews/` with commit SHA + image ID
- [ ] First-session post-close report
- [ ] Verify expected startup log line is captured in log rotation
- [ ] Trigger one intentional test alert (e.g., via `/organism/save?force=true` in a staging harness) to confirm Slack path

Within 2 weeks:
- [ ] Aggregate giveback measurement for Exp4 evaluation
- [ ] Evaluate whether CAP/HALT caps triggered on any session (they shouldn't, if sizing is reasonable)
- [ ] Evaluate alerts rate — target < 5/day. If higher, tighten thresholds.

---

## 6. Ownership

| Step | Owner | Blocker |
|---|---|---|
| Env set | operator | needs decision on ORGANISM_DRAWDOWN_KILL_PCT |
| Image build | operator | trivial |
| Rolling restart | operator | off-hours window |
| Post-deploy verification | operator | docker + curl access |
| Observation window | operator + engineer | daily post-close reports |

No external dependencies. No external approvals needed.

— End of Release Candidate Deploy Plan —
