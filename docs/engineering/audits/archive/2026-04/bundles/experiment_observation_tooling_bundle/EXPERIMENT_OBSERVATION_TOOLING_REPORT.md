# Experiment Observation Tooling Report

**Commit**: see git log
**Status**: COMMITTED, ready for Monday post-close use

## Script
`scripts/generate_experiment_observation_report.py`

### Daily usage (post market close)
```bash
# From inside the repo root:
./venv/bin/python scripts/generate_experiment_observation_report.py \
    --date 2026-04-13 \
    --log <(docker exec intra-api-1 cat /app/logs/application.log) \
    --out EXP1A_OBSERVATION_APR13.md
```

### Cumulative window (end of observation)
```bash
./venv/bin/python scripts/generate_experiment_observation_report.py \
    --from 2026-04-13 --to 2026-04-18 \
    --log <(docker exec intra-api-1 cat /app/logs/application.log) \
    --out EXP1A_CUMULATIVE_WINDOW.md
```

## Outputs
- Exp1A gate suppression count + per-event detail
- Core metrics vs Apr 7-10 baseline with delta indicators
- Success/failure criteria (win rate >25%, expectancy >-$0.50, suppressions >10, max loss <-$25)
- PnL by exit reason, symbol, regime
- Exp2 readiness (PSQ/SH trade count, PnL, win rate, chop-specific)
- Exp3 readiness (confidence buckets <0.35 / 0.35-0.45 / >=0.45 with PnL and win rate)
- Brain state snapshot
