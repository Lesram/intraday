# Master Deploy Sequence

## Next live deployment: Deploy 2 — Hardening bundle

**When**: After current experiment observation window (target Thu Apr 23 post-close)
**Target commit**: `33d6138` (HEAD)
**What ships**:
| Commit | What | Category |
|---|---|---|
| 15cc0a4 | G1/G2/G3 mechanical | Hardening |
| b97f903 | Exp4 trailing-stop widen | Algorithm (bundled) |
| 679ffd2 | H1/H2 risk-budget + drift guard | Hardening |
| bb5cbb5 | Notional cap + daily max-loss | Risk (disabled by default) |
| c306074 | H5 settings governance | Governance |
| 33d6138 | Alert wiring | Observability |

**Config at deploy**: Add `SLACK_WEBHOOK_URL=<url>` to `.env`
**Disabled by default**: `ORGANISM_MAX_NOTIONAL=0`, `ORGANISM_MAX_DAILY_LOSS=0`

## What should NOT be deployed next

- Any structural persistence change (FROZEN)
- Any confidence formula change (Exp3 still inconclusive)
- Any new experiment beyond what's committed
- Nightly scheduler activation (dormant, not ready)

## What must remain disabled in paper

| Feature | Env var | Paper value |
|---|---|---|
| Notional cap | ORGANISM_MAX_NOTIONAL | 0 |
| Daily max-loss | ORGANISM_MAX_DAILY_LOSS | 0 |
| These activate for Stage 1 only ||

## Post-Deploy 2 monitoring checklist

- [ ] Container healthy, RestartCount=0
- [ ] All 9 signature checks pass
- [ ] Force-save succeeds
- [ ] Slack test alert fires (trigger via diagnostic endpoint if possible)
- [ ] Evolution params applied after trade 300 (check logs)
- [ ] No guard fires
- [ ] Expectancy stable vs pre-deploy

## Future deploys (not yet scheduled)

| Deploy | Content | When | Prerequisite |
|---|---|---|---|
| Risk activation | Set ORGANISM_MAX_NOTIONAL=2500, MAX_DAILY_LOSS=250 | Week of May 5 | 2 weeks positive expectancy |
| Stage 1 switch | Change Alpaca keys to live | Week of May 12 | All Stage 1 criteria met |
| Dead code cleanup | Remove exploration routing + runner.py | After Stage 1 | Low priority |
| Nightly scheduler | Enable ORGANISM_NIGHTLY_ENABLED=1 | After 500 trades | Evaluate first |
