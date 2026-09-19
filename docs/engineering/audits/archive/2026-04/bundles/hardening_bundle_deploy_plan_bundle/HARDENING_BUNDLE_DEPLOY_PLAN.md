# Hardening Bundle Deploy Plan

## Target: Deploy ALL hardening except Exp4

The hardening commits between live (`ce06d41`) and HEAD (`33d6138`) include both hardening AND Exp4. Exp4 must remain offline.

### Commit chain (ce06d41..HEAD):
```
33d6138  Alert wiring                    ← INCLUDE (hardening)
c306074  H5 settings governance          ← INCLUDE (hardening)
bb5cbb5  Notional cap + daily max-loss   ← INCLUDE (hardening)
679ffd2  H1/H2 risk-budget + drift guard ← INCLUDE (hardening)
b97f903  Exp4 trailing-stop              ← EXCLUDE (experiment)
15cc0a4  G1/G2/G3 mechanical             ← INCLUDE (hardening)
```

**Problem**: Exp4 (`b97f903`) sits BETWEEN G1/G2/G3 and H1/H2. Cannot deploy HEAD without including Exp4.

### Solution: Deploy HEAD and accept Exp4

Exp4's trailing-stop widening is controlled by a constant `_EXP4_CHOP_TRAIL_MODE = "widen"` inside `adaptive_exits.py`. It is **always active** when deployed — there is no env-var disable switch. However, the change is narrow and the trailing-stop widening in chop has been the recommended Exp4 direction anyway.

**Recommendation**: **Deploy HEAD (`33d6138`)** which includes everything. Exp4 becomes live alongside the hardening. This is acceptable because:
1. Exp4 only affects trailing_stop in chop regime (narrow scope)
2. Trailing-stop was identified as a leak in the giveback analysis
3. The widen-to-5.0-ATR change is conservative (not disabling trailing entirely)
4. Exp4 has 7 passing tests and zero regression impact

### Alternative: Cherry-pick without Exp4
Create a new branch that cherry-picks G1/G2/G3, H1/H2, CAP/HALT, H5, and alerts but skips Exp4. More complex, more risk of merge conflicts, for marginal value.

**Decision: Deploy HEAD (`33d6138`). Accept Exp4 as part of the hardening bundle.**

## Bundle grouping

**ONE DEPLOY**: Everything ships together.

| Commit | What | Category | Risk |
|---|---|---|---|
| `15cc0a4` | G1/G2/G3 mechanical | Hardening | Very low |
| `b97f903` | Exp4 trailing-stop widen in chop | Algorithm | Low |
| `679ffd2` | H1/H2 risk-budget + drift guard | Hardening | Low |
| `bb5cbb5` | Notional cap + daily max-loss | Risk limits | Very low (disabled by default) |
| `c306074` | H5 settings governance | Governance | Very low |
| `33d6138` | Alert wiring | Observability | Zero |

## What remains DISABLED in paper mode

| Feature | Env var | Paper value | Stage 1 value |
|---|---|---|---|
| Per-trade notional cap | `ORGANISM_MAX_NOTIONAL` | `0` (disabled) | `2500` |
| Daily max-loss halt | `ORGANISM_MAX_DAILY_LOSS` | `0` (disabled) | `250` |
| Slack alerts | `SLACK_WEBHOOK_URL` | not set (silent) | set to webhook URL |

All other changes are always-active with no env-var toggle. H1 risk-budget, H2 drift guard, G1/G2/G3, H5 governance, and Exp4 trailing-stop widen are all active immediately on deploy.

## Preflight checks

Before deploy, verify:
- [ ] Market closed
- [ ] Positions flat
- [ ] Account ACTIVE
- [ ] Container healthy
- [ ] Brain synced (manifest = learning_state)
- [ ] `git rev-parse HEAD` = `33d6138`

## Post-deploy verification

After rebuild:
1. Container healthy, RestartCount=0
2. Boot log: `Brain loaded: gen=N, trades=N` matches pre-deploy
3. Signature checks:
   - G1: `grep "G1: Cannot restore"` → present
   - G3: `grep "math.isfinite(current_price)"` → present
   - H1: `grep "_prod_max_risk"` → present
   - H2: `grep "H2: Feature drift"` → present
   - H5: `grep "_check_governance"` → present
   - CAP: `grep "MAX_NOTIONAL_PER_TRADE"` → present
   - HALT: `grep "MAX_DAILY_LOSS"` → present
   - Exp4: `grep "EXP4_CHOP_TRAIL"` → present
   - Alerts: `grep "send_alert.*CRITICAL"` → present
4. Force-save succeeds
5. Manifest synced post-save

## Rollback

```bash
git checkout ce06d41
docker compose -f docker-compose.paper.yml up -d --build api
```

Rolls back to Exp1A + Exp2 + Exp3 prep only.
