# Post-Exp1A Deployment Plan

## Target commit

**`ce06d41e207faebd8d2cbecec7e4ec5fb73fda26`**

This includes:
- ✅ Full Patch F structural stack (A-F4) — already live
- ✅ Exp1A: chop 10-bar min-hold gate — already live, KEEP
- ✅ Observation tooling script (`6754223`)
- ✅ **Exp2: suppress PSQ/SH entries in chop** (`d79cae0`) — NEW
- ✅ **Exp3 prep: confidence inversion side-by-side logging** (`ce06d41`) — NEW

This excludes:
- ❌ G1/G2/G3 mechanical hardening (`15cc0a4`) — deferred, not urgent for paper
- ❌ Exp4: trailing-stop giveback control (`b97f903`) — queued behind Exp2

## Rationale

### Why Exp2 now
- PSQ/SH in chop: 0% win rate across 8 trades over 6 sessions (Apr 7-15)
- Today (Apr 15): PSQ -$3.00, SH -$1.09, both losers in chop
- Cumulative PSQ/SH chop loss: ~$37 across the full observation period
- Highest-confidence fix: simple regime gate, zero risk to non-inverse symbols
- Orthogonal to Exp1A (entry filter vs exit timing) — both can coexist

### Why stack Exp3 prep
- **Confirmed read-only**: +33 lines of logging in `live_engine.py`, all at DEBUG level. No gate changes, no threshold changes, no entry/exit behavior changes. Verified by diff: zero lines matching `continue`, `return`, `should_exit`, `block`, `suppress`, or `skip`.
- **Zero trade impact**: adds `confidence_bt_only`, `confidence_ml_component`, and `gate_pass_bt_only` fields to candidate dicts for passed candidates. These fields are only read by analysis tooling, never by trading logic.
- **High diagnostic value**: enables side-by-side confidence analysis to determine whether ML is helping or hurting. Day 3 data showed the 0.35-0.45 confidence bucket turned positive (+$16.50), weakening the ML contamination hypothesis. More data needed — Exp3 instrumentation provides it.
- **Stacking saves a deploy cycle**: deploying Exp3 separately would require another container rebuild for zero behavioral change.

### Why NOT Exp4
- Trailing-stop leapfrog criteria not met: only 2 trailing-stop givebacks >$5 across 3 sessions (need 3+)
- Exp4 changes exit behavior (widens trailing stop in chop) — needs its own observation window
- Deploying Exp2 + Exp4 together would conflate entry and exit changes, making it harder to attribute improvement

### Why NOT G1/G2/G3
- These are real-money preparation fixes, not paper-trading improvements
- G1 (exit-level restore at WARNING) and G2 (cooldown on success only) change runtime behavior
- Deploying them alongside a new experiment would contaminate the Exp2 observation
- Schedule for deployment after the Exp2 observation window or before real-money staging

## Deploy prerequisites

- [ ] Market closed (verify via Alpaca clock `is_open=false`)
- [ ] Positions flat (verify via Alpaca positions `[]`)
- [ ] Container healthy, RestartCount=0
- [ ] Brain manifest synced with learning_state
- [ ] `git rev-parse HEAD` shows `ce06d41` OR checkout `ce06d41` explicitly
- [ ] Run focused tests: `pytest tests/test_experiment_2_inverse_chop_suppression.py tests/test_experiment_3_confidence_inversion.py -v`
- [ ] Source clean in `backend/organism/`

## Deploy sequence

```bash
# 1. Verify state
git checkout ce06d41   # if HEAD is ahead (at b97f903)
git rev-parse HEAD     # must be ce06d41

# 2. Rebuild
docker compose -f docker-compose.paper.yml up -d --build api

# 3. Verify healthy (poll)
docker inspect intra-api-1 --format '{{.State.Health.Status}}'

# 4. Verify signatures in container
docker exec intra-api-1 grep -c "CHOP_MIN_HOLD_BARS = 10" /app/backend/organism/live_engine.py     # Exp1A: 1
docker exec intra-api-1 grep -c "inverse_etf_suppressed_chop" /app/backend/organism/live_engine.py  # Exp2: >0
docker exec intra-api-1 grep -c "confidence_bt_only" /app/backend/organism/live_engine.py            # Exp3: >0
docker exec intra-api-1 grep -c "EXP4_CHOP_TRAIL" /app/backend/organism/adaptive_exits.py           # Exp4: 0
docker exec intra-api-1 grep -c "G1: Cannot restore" /app/backend/organism/live_engine.py            # G1: 0

# 5. Verify boot log
docker exec intra-api-1 sh -c "tail -200 /app/logs/application.log | grep -E 'Brain loaded|PREFLIGHT|Trading phase|scheduler loop'"

# 6. Force-save to confirm brain pipeline
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin@example.com","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST "http://localhost:8000/api/v1/organism/save?force=true" -H "Authorization: Bearer $TOKEN"
```

## Rollback plan

```bash
# Revert to Exp1A-only state:
git checkout ab54b2f
docker compose -f docker-compose.paper.yml up -d --build api
```

If only Exp2 is problematic but Exp3 is fine, revert Exp2 specifically:
```bash
git revert d79cae0
docker compose -f docker-compose.paper.yml up -d --build api
```

## Post-deploy observation plan (3-5 sessions)

### Exp2 metrics to track

| Metric | Baseline (with Exp1A) | Target |
|---|---|---|
| PSQ/SH trade count in chop | ~1-2/session | **0** |
| PSQ/SH PnL | ~-$2 to -$4/session | **$0** (no trades) |
| `Exp2: inverse ETF entry suppressed` log count | 0 | >0 (confirms gate fires) |
| Non-inverse trade quality | unchanged | unchanged |
| Net PnL | variable | ≥ cumulative Exp1A level |
| Win rate | 25% cumulative | ≥25% |

### Exp3 instrumentation metrics

| Field | What to check |
|---|---|
| `confidence_bt_only` in candidate dicts | present for every passed candidate |
| `confidence_ml_component` | tracks the raw ML contribution |
| `gate_pass_bt_only` | would the candidate have passed without ML? |
| Side-by-side comparison | do ML-boosted candidates win or lose? |

### Decision criteria after 3 sessions

- **Exp2 success**: PSQ/SH trades = 0 in chop, overall PnL not degraded → KEEP
- **Exp2 failure**: non-inverse trades degraded (unexpected interaction) → REVERT Exp2
- **Exp3 data ready**: if 20+ candidates have side-by-side data, scope Exp3B (confidence weight change)

## What stays unchanged

| Item | Status |
|---|---|
| Exp1A (10-bar min-hold) | KEEP live |
| Full Patch F stack | KEEP live |
| Exp4 (trailing-stop) | QUEUED (not deployed) |
| G1/G2/G3 (mechanical) | QUEUED (not deployed) |
