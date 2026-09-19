# Phase 3 Alternative-Timeframe Scout Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase3_timeframe_scout.py`

## Verdict

Do not promote `5Min`.

The full cached-universe scout replayed the current decision stack against the
same trailing cached bars at `1Min` and resampled `5Min`. The `5Min` variant
produced more trades than the `1Min` baseline but still lost money, and the
expectancy improvement was only `$0.25/trade`, below the predeclared
`$0.50/trade` scout gate.

This result is useful as a negative screen, not as proof that `1Min` is
optimal. It says the current code and cached bars do not justify switching the
paper engine to `5Min`.

## Evidence Command

```bash
./venv/bin/python scripts/phase3_timeframe_scout.py \
  --symbols AAPL,AMD,AMZN,AVGO,CAT,COST,CRM,GOOGL,IWM,LLY,META,MSFT,NVDA,PSQ,QQQ,SH,SPY,TSLA,WMT,XLE,XLK,XOM \
  --bar-limit 900 \
  --max-ticks 80 \
  --lookback 90
```

Outputs:

- `artifacts/phase3_timeframe_scout/summary_timeframe_scout.json`
- `artifacts/phase3_timeframe_scout/timeframe_scout_results.csv`

## Results

| Timeframe | Symbols | Ticks | Trades | Orders | PnL | Expectancy | Delta vs 1Min | Max DD | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `1Min` | `22` | `80` | `2` | `9` | `-$12.33` | `-$6.17` | `$0.00` | `0.022%` | Baseline sample too thin. |
| `5Min` | `22` | `80` | `8` | `23` | `-$47.32` | `-$5.92` | `+$0.25` | `0.065%` | Do not promote. |

The replay also emitted the existing walk-forward promotion blocker:

```text
Full production promotion blocked: total_pnl -787.99 < floor 0.00; last_50_mean_pnl -0.3538 < floor 0.0000; sharpe_ratio_per_trade -1.3985 < floor 0.0000
```

## Recommendation

Keep paper trading on the current `1Min` runtime timeframe. If timeframe
research continues later, use a larger fresh bar capture and compare `1Min`,
`3Min`, `5Min`, and `15Min` with enough trades per variant to clear the sample
floor. This scout does not justify a runtime config change.
