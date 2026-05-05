# Phase 3 Trade Attribution Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase3_trade_attribution.py`

## Verdict

This slice does not promote a live trading change. It gives us a cleaner map
of where expectancy is being created or destroyed so the next replay can test
one focused hypothesis at a time.

The old broad "confidence inversion" story is now too blunt. On the full
strategy-only history, the worst confidence bucket is `[0.55,0.65)` with
`140` trades and `-$487.51` PnL. But confidence `>=0.65` is only `-$48.42`
all-time, and the last 100 trades show confidence `>=0.65` at `+$53.56`.
So the next candidate is not "invert high confidence." It is: investigate
mid-high confidence and `alpha+breakout|chop` interactions.

## Evidence Command

```bash
./venv/bin/python scripts/phase3_trade_attribution.py --out-dir artifacts/phase3_trade_attribution
```

Outputs:

- `artifacts/phase3_trade_attribution/summary_trade_attribution.json`
- `artifacts/phase3_trade_attribution/segments_trade_attribution.csv`
- `artifacts/phase3_trade_attribution/candidates_trade_attribution.csv`

## Strategy Scope

The analyzer uses the same reconciliation-artifact exclusion rules as
`/api/v1/health/strategy`:

- Total CSV rows: `508`
- Strategy rows: `501`
- Excluded reconciliation artifacts: `7`
- Invalid PnL rows: `0`

Overall strategy-only state:

| Metric | Value |
| --- | ---: |
| Trades | `501` |
| Total PnL | `-$778.90` |
| Mean PnL | `-$1.55` |
| Win rate | `32.9%` |
| Correct-direction rate | `32.9%` |
| Profit factor | `0.6923` |
| Best / worst trade | `+$174.00 / -$273.90` |

## All-Time Attribution

The all-time drag is polluted by legacy rows from before attribution fields
were populated. Those rows are diagnostically useful but should not directly
drive a live disable.

| Segment | Trades | PnL | Mean | Win rate | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| `legacy_blank` entry source | `149` | `-$970.08` | `-$6.51` | `40.3%` | Historical attribution gap, not a current gate target. |
| `legacy_blank|legacy_blank` | `142` | `-$944.75` | `-$6.65` | `40.1%` | Same legacy problem. |
| `[0.55,0.65)` confidence | `140` | `-$487.51` | `-$3.48` | `32.9%` | Real candidate for replay. |
| `[0.00,0.35)` confidence | `156` | `-$294.56` | `-$1.89` | `35.3%` | Also weak, but mixed with legacy rows. |
| `AVGO` | `24` | `-$201.39` | `-$8.39` | `25.0%` | Symbol-specific drag worth isolating in replay. |
| `alpha+breakout|chop` | `107` | `-$52.28` | `-$0.49` | `29.9%` | Current-code candidate, not just legacy. |

Entry-source totals are more nuanced:

| Entry source | Trades | PnL | Mean | Win rate |
| --- | ---: | ---: | ---: | ---: |
| `legacy_blank` | `149` | `-$970.08` | `-$6.51` | `40.3%` |
| `alpha+breakout` | `112` | `-$0.52` | `-$0.00` | `30.4%` |
| `breakout` | `20` | `+$13.68` | `+$0.68` | `40.0%` |
| `alpha` | `220` | `+$178.02` | `+$0.81` | `28.6%` |

## Recent Attribution

The recent windows are more important than the legacy-heavy all-time rows.

Last 100 strategy trades:

- Total PnL: `+$18.09`, mean `+$0.18`, win rate `32.0%`.
- `alpha+breakout|chop`: `64` trades, `-$35.12`, mean `-$0.55`, win rate
  `28.1%`.
- `chop` overall: `86` trades, `-$30.11`, mean `-$0.35`, win rate `30.2%`.
- `[0.45,0.55)` confidence: `23` trades, `-$20.73`, win rate `21.7%`.
- `[0.65,0.75)` confidence: `13` trades, `+$70.87`, win rate `53.9%`.

Last 50 strategy trades:

- Total PnL: `+$34.03`, mean `+$0.68`, win rate `32.0%`.
- `alpha+breakout|chop`: `22` trades, `-$12.45`, mean `-$0.57`, win rate
  `22.7%`.
- `[0.45,0.55)` confidence: `11` trades, `-$21.06`, win rate `9.1%`.
- `[0.65,0.75)` confidence: `9` trades, `+$73.74`, win rate `66.7%`.

Last 25 strategy trades:

- Total PnL: `+$63.07`, mean `+$2.52`, win rate `36.0%`.
- `alpha+breakout|chop`: `6` trades, `-$3.29`, still weak but too small for
  an action gate.
- `breakout|chop`: `10` trades, `+$3.93`.
- `breakout|trending_up`: `5` trades, `+$16.05`.
- A single `alpha+breakout|high_vol` winner contributed `+$51.45`, so the
  last-25 headline is not yet stable.

## Exit-Family Diagnostics

Exit families diagnose symptoms rather than direct entry disables:

| Exit family | All-time PnL | Last 100 PnL | Last 50 PnL |
| --- | ---: | ---: | ---: |
| `stop_loss` | `-$567.50` | `-$37.83` | `-$17.08` |
| `pyramid_cut` | `-$404.32` | `-$61.93` | `-$37.00` |
| `failure_to_follow` | `-$306.93` | `-$8.59` | `-$3.33` |
| `trailing_stop` | `-$183.93` | `-$20.06` | `-$18.23` |
| `max_holding_period` | not top all-time drag | `+$123.43` | `+$108.90` |

This argues against loosening stops blindly. Recent winners are surviving to
`max_holding_period`; recent losers are still being cut by pyramid/stop/trailing
logic. The next replay should ask whether current chop entries are structurally
bad before changing exits.

## Promotion Decision

Do not promote any live behavior from this slice.

Candidates for replay or shadow-only evaluation:

1. Suppress or down-rank `alpha+breakout` only in `chop`.
2. Test a warning-only or shadow gate for confidence `[0.45,0.55)` and
   `[0.55,0.65)` separately; do not invert all high confidence.
3. Isolate `AVGO` drag with symbol-level replay before considering symbol
   restrictions.
4. Compare `breakout|trending_up` and `breakout|chop` as potential protected
   strengths, but require more samples.

The next Phase 3 coding step should be a replay harness that can apply these
candidate filters to historical decisions and report opportunity cost, PnL
delta, drawdown delta, exit mix, and trade-count reduction.
