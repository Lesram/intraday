# Master Roadmap: Current State → Stage 1 Tiny Live Capital

## Current state (2026-04-19, weekend)

**LIVE**: ce06d41 (Exp1A + Exp2 + Exp3 prep on Full Patch F)
**FROZEN**: Structural persistence (Full Patch F, zero guard fires, 9+ days stable)
**OFFLINE READY**: 6 commits (G1/G2/G3 + Exp4 + H1/H2 + CAP/HALT + H5 + alerts)
**BRAIN**: gen=84, trades=293, 7 trades from evolution freeze exit (300)

## What stays frozen

- Full Patch F structural stack — observation only, no changes
- Exp1A — KEEP, no modifications
- Exp2 — KEEP, continue observing

## Phase 1: Continue current observation (Mon Apr 20 – Wed Apr 22)

**Action**: Run post-close observation reports daily. No deploys.
**Watch for**:
- Exp2 PSQ/SH suppression continuing (should be zero inverse-ETF trades in chop)
- Evolution freeze exit at trade 300 (~7 trades, likely Mon or Tue)
- Exp3 confidence data accumulation
- Overall expectancy trend

**Decision by Wed Apr 22**: Is the system stable enough to deploy the hardening bundle?

## Phase 2: Deploy hardening bundle (Thu Apr 23 or next post-close window)

**Target**: HEAD (`33d6138`) — includes everything:
```
33d6138  Alert wiring
c306074  H5 governance
bb5cbb5  CAP + HALT (disabled by default)
679ffd2  H1 + H2
b97f903  Exp4 trailing-stop widen
15cc0a4  G1/G2/G3
```

**Preflight**: market closed, positions flat, brain synced, account active
**Post-deploy**: signature checks, force-save, boot log verification
**Config at deploy time**: set `SLACK_WEBHOOK_URL` in .env (paper mode, no CAP/HALT activation yet)
**Risk limits remain disabled**: `ORGANISM_MAX_NOTIONAL=0`, `ORGANISM_MAX_DAILY_LOSS=0`

## Phase 3: Observe hardened platform (Fri Apr 24 – Fri May 1)

**Duration**: ~5 sessions
**Watch for**:
- G1/G2/G3 correctness (exit-level restore, cooldown behavior, NaN guard)
- Exp4 trailing-stop behavior in chop (wider trail reducing giveback?)
- H1 risk-budget cap activating in production sizing
- H2 feature drift guard (should be silent unless SPY drops)
- Alert wiring (Slack notifications working if webhook configured)
- Evolution params actively applied (post trade 300)
- Overall expectancy trajectory

**Success criteria**:
- No new mechanical issues
- Expectancy trend neutral or positive
- Zero guard fires
- Alerts working (test with diagnostic triggers)

## Phase 4: Enable risk limits for Stage 1 prep (week of May 5)

**IF expectancy is neutral/positive over 2 weeks**:
1. Set `ORGANISM_MAX_NOTIONAL=2500` in .env (cap per-trade at $2,500)
2. Set `ORGANISM_MAX_DAILY_LOSS=250` in .env (halt at -$250/day)
3. Observe 1 week with limits active (paper)
4. Verify limits fire correctly (may need to test with a manual trigger)

**IF expectancy is still negative**:
- Do NOT proceed to Stage 1
- Evaluate Exp3B (confidence formula change)
- Consider wider pyramid_cut thresholds (Exp1B)
- Reassess at end of May

## Phase 5: Stage 1 — Tiny live capital (earliest: week of May 12)

**Entry criteria (ALL must be true)**:
1. ≥2 weeks of neutral/positive expectancy on paper
2. G1/G2/G3/H1/H2/H5/CAP/HALT all deployed and verified
3. Risk limits tested (notional cap + daily max-loss)
4. Slack alerts working
5. Container stable ≥7 days without restart
6. Zero guard fires
7. Win rate ≥25% sustained

**Stage 1 parameters**:
- Capital: $5,000
- Max notional per trade: $2,500 (50%)
- Max daily loss: $250 (5%)
- Max open positions: 4
- Paper parallel: continue paper on separate account
- Duration: 2-4 weeks minimum

**Exit criteria for Stage 2**:
- Positive expectancy sustained 2+ weeks on live fills
- Max intraday drawdown < 5%
- No mechanical incidents

## Timeline summary

| Week | Phase | Key action |
|---|---|---|
| Apr 20-22 | Observe | Continue Exp1A+Exp2, watch for trade 300 |
| Apr 23-25 | Deploy 2 | Hardening bundle, configure alerts |
| Apr 28-May 2 | Observe | Hardened platform, evolution active |
| May 5-9 | Prep | Enable risk limits, test on paper |
| May 12+ | Stage 1 | Tiny live capital IF criteria met |
