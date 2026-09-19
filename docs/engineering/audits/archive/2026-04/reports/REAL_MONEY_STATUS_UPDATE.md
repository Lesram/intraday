# Real-Money Status Update — Apr 19, 2026

## Current stage: Stage 0 (paper only)

## Readiness by category

| Category | Current | Target | Gap |
|---|---|---|---|
| Structural stability | ✅ Full Patch F, 9 days stable, 0 guard fires | Same | CLOSED |
| Expectancy | -$0.50/trade (improving) | >+$0.50 sustained 3 weeks | MEDIUM |
| Risk control | ATR stops + EOD flatten | + daily max-loss + position-size cap | MEDIUM |
| Inverse ETF | ✅ Exp2 blocking in chop (0 trades) | Same | CLOSED |
| Confidence/ML | Inconclusive (Exp3 instrumenting) | Proven direction | SMALL |
| Kill switches | POST /halt + POST /save | + auto drawdown halt | SMALL |
| Monitoring | GET endpoints only | + Slack/email alerts | MEDIUM |
| Rollback | Per-commit revert | Same | CLOSED |

## Earliest realistic Stage 1 date

**Week of May 4** — IF:
1. Expectancy turns sustainably positive over the next 2 weeks
2. G1/G2/G3 deployed (mechanical hardening)
3. Daily max-loss auto-halt implemented
4. Position-sizing cap addresses IWM-class outliers

## What must happen first
1. 2+ consecutive weeks of positive or near-zero expectancy
2. Deploy G1/G2/G3
3. Add daily max-loss circuit breaker (-$500 → halt trading for the day)
4. Add per-trade notional cap ($5K max per entry)
