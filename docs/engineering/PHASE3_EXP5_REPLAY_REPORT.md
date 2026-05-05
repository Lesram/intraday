# Phase 3 Exp 5 Replay Report

Generated: 2026-05-05
Branch: `codex/v13-phase2-expectancy`

## Question

Would widening the chop-regime initial stop from `2.5x ATR` to `3.0x` or
`3.5x` reduce whipsaw stop exits enough to justify shadow promotion?

## Verdict

Do not promote Exp 5 from replay. In the first usable bounded scout, all three
ATR variants produced identical outcomes. The stop-width hypothesis did not
change exits, PnL, win rate, drawdown, or exit mix in this window.

This is not full negative proof. It is enough to stop spending immediate Phase 3
time on chop stop width until replay throughput is improved or a broader
sample can be run cheaply.

## Evidence Runs

### Failed Full Attempt

Command:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0,3.5 --out-dir artifacts/backtest_exp5_phase3_full --summary-out artifacts/backtest_exp5_phase3_full/summary_exp5.json
```

Result: stopped manually after several minutes because the first variant had not
written `metrics_atr2_5.json` and the live-engine replay path emitted repeated
ORB stale-cache warnings. No live brain state was touched; only replay brain
copies under `artifacts/` were used.

### Zero-Trade Harness Sanity

Command:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0,3.5 --bar-limit 100 --out-dir artifacts/backtest_exp5_phase3_scout100 --summary-out artifacts/backtest_exp5_phase3_scout100/summary_exp5.json
```

Result: completed, but each variant had only 25 active ticks and 0 trades. This
validated the harness controls but is not strategy evidence.

### Usable Active-Symbol Scout

Command:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0,3.5 --symbols QQQ,NVDA,XLE,XLK,SPY,AMZN,XOM,TSLA --max-ticks 200 --out-dir artifacts/backtest_exp5_phase3_active8_200 --summary-out artifacts/backtest_exp5_phase3_active8_200/summary_exp5.json
```

Scope:

- Symbols: `QQQ,NVDA,XLE,XLK,SPY,AMZN,XOM,TSLA`
- Selection basis: top historical seed-brain activity by trade count
- Ticks: 200 per variant after replay warmup
- Seed brain: `artifacts/deploy_preflight_rc_1_5_curated/organism_brain_backup_pre_rc_1_5_curated_20260425_005638`
- Cached bars: `artifacts/backtest_rc_1_5/bars.pkl`

| Variant | Brain trades | Broker sells | Broker PnL | Expectancy / brain trade | Broker win rate | Max drawdown | Exit mix | Gate |
|----------|-------------:|-------------:|-----------:|-------------------------:|----------------:|-------------:|----------|------|
| `2.5x` | 3 | 6 | `-$5.33` | `-$1.78` | `16.7%` | `0.0089%` | 1 stop, 1 pyramid, 1 max-hold | fail |
| `3.0x` | 3 | 6 | `-$5.33` | `-$1.78` | `16.7%` | `0.0089%` | 1 stop, 1 pyramid, 1 max-hold | fail |
| `3.5x` | 3 | 6 | `-$5.33` | `-$1.78` | `16.7%` | `0.0089%` | 1 stop, 1 pyramid, 1 max-hold | fail |

Promotion criteria were not met:

- Required expectancy lift: at least `$0.50` per trade. Observed lift: `$0.00`.
- Required pyramid-cut constraint: no more than 25% relative increase. Observed:
  unchanged.
- Required drawdown constraint: no more than 0.5 percentage points absolute
  worsening. Observed: unchanged.

## Observations

The three variants being identical suggests this window's stop-loss exit was not
sensitive to the chop stop ATR multiplier. The one stop-loss trade probably
breached all three stop levels before the exit path had a chance to distinguish
them, or the effective stop source was not the `AdaptiveExitEngine.REGIME_STOP_ATR`
table for that specific position.

Replay throughput is now a real Phase 3 blocker. The active-symbol scout took
about 224 seconds per 200-tick variant, or roughly 0.9 ticks/second. At that
speed, a full 22-symbol replay across the cached window is not a practical
parameter-sweep loop.

The metrics intentionally report both brain trade rows and broker sell events.
The active-symbol scout had 3 brain trade rows but 6 broker sells, likely because
the simulated broker records partial or staged sell events separately. Promotion
math uses brain-history trade rows for expectancy because those rows carry exit
reason attribution.

## Recommendation

Do not change live stop ATR settings. Deprioritize Exp 5 until replay throughput
is improved.

Move the next Phase 3 slice to a lane with higher expected information value:
ORB shadow outcome simulation or confidence/entry-source attribution. In
parallel, add a replay-performance cleanup task so future hypotheses can be run
over larger windows without turning every idea into a half-day backtest.
