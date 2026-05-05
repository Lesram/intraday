# Phase 3 Strategy Research Plan

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`

## Operating Rule

Phase 3 is a replay-first profitability phase. No live trading behavior changes
from this phase may ship unless all of the following are true:

- The change has a written hypothesis and falsifiable promotion criteria.
- Replay reports relative deltas against the same bars and same brain seed.
- Risk metrics do not degrade beyond the predeclared limits.
- The first live step is shadow telemetry unless the change is observability-only.
- Runtime config snapshots and replay artifacts are attached to the PR.

## Current Starting Point

The paper brain is mechanically stable but not yet profitable on strategy-only
truth:

- Strategy trades: 501
- Strategy PnL: approximately `-$778.90`
- Strategy Sharpe per trade: approximately `-1.37`
- Full production state: `production_guarded`
- ML influence: disabled
- Kelly sizing: disabled in favor of fixed ATR-dollar risk

The strongest drag buckets are stop-loss, pyramid-cut, failure-to-follow,
legacy attribution rows, and current `alpha+breakout|chop` entries. Phase 3
should attack these with controlled research, not by loosening live gates.

## First Slice: Exp 5 Replay Harness

Hypothesis: widening the chop initial stop from `2.5x ATR` to `3.0x` or `3.5x`
may reduce whipsaw stop-loss exits. It is not accepted unless replay shows:

- Expectancy improvement of at least `$0.50` per trade versus the `2.5x` baseline.
- Pyramid-cut share does not increase by more than 25% relative.
- Max drawdown does not worsen by more than 0.5 percentage points absolute.

Implementation status:

- `scripts/backtest_exp5_stop_atr.py` is the Phase 3 replay harness.
- The script copies a seed brain into `artifacts/backtest_exp5/` for each run.
- The first variant is treated as baseline.
- Output includes per-variant metrics and `summary_exp5.json`.
- Recommendation values are `do_not_promote_from_replay` or `shadow_candidate`.
- Scout controls are available via `--symbols`, `--bar-limit`, and
  `--max-ticks`; these are explicitly not promotion-grade evidence.
- Replay logs are quiet by default so repeated live-engine warnings do not
  turn research runs into terminal I/O benchmarks. Use `--verbose` when
  debugging the replay/live-engine path itself.
- Current evidence report: `docs/engineering/PHASE3_EXP5_REPLAY_REPORT.md`.
- Current result: do not promote from replay; all measured ATR variants were
  identical in the active-symbol scout.

Example smoke run:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0 --max-ticks 50
```

Bounded scout run:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0,3.5 --bar-limit 500
```

Full run:

```bash
./venv/bin/python scripts/backtest_exp5_stop_atr.py --variants 2.5,3.0,3.5
```

## Next Research Lanes

Phase 3's planned evidence lanes are now complete. The next roadmap step is
Phase 4: shadow-only model/strategy advancement using the Phase 3 evidence
pack, not live promotion.

## Completed Research Slices

- Exp 5 chop stop ATR replay: do not promote. See
  `docs/engineering/PHASE3_EXP5_REPLAY_REPORT.md`.
- ORB shadow outcome simulation: keep ORB shadow-only; default and sensitivity
  runs were small-sample negative. See
  `docs/engineering/PHASE3_ORB_SHADOW_OUTCOME_REPORT.md`.
- Trade attribution and confidence cleanup: no live promotion. The broad
  confidence-inversion story is too blunt; recent drag clusters around
  `alpha+breakout|chop` and mid-confidence buckets. See
  `docs/engineering/PHASE3_TRADE_ATTRIBUTION_REPORT.md`.
- Candidate-filter counterfactual replay: no live promotion. Confidence
  `[0.45,0.55)` is the cleanest recent shadow candidate; `alpha+breakout|chop`
  is plausible but removes too much of the last-100 stream without further
  refinement. See
  `docs/engineering/PHASE3_CANDIDATE_FILTER_REPLAY_REPORT.md`.
- Candidate-filter fill-path replay: no live promotion. The current cached bars
  match only `106 / 352` fill-valid rows and `0` trades in the last-100,
  last-50, and last-25 windows, so candidate filters need fresh shadow telemetry
  before any gate can be considered. See
  `docs/engineering/PHASE3_CANDIDATE_FILTER_FILL_REPLAY_REPORT.md`.
- Alternative-timeframe scout: no live promotion. `5Min` improved expectancy
  by only `$0.25/trade` versus the thin `1Min` baseline and still lost money.
  See `docs/engineering/PHASE3_TIMEFRAME_SCOUT_REPORT.md`.
- ML target redesign comparison: no live promotion. The current one-bar target
  is very noisy; `close_return_h5` is a shadow-training candidate only. See
  `docs/engineering/PHASE3_ML_TARGET_REDESIGN_REPORT.md`.
- Candidate-filter shadow telemetry: available but disabled by default. It can
  capture `confidence [0.45,0.55)` and `alpha+breakout|chop` candidates during
  paper sessions without affecting ranking, sizing, or orders. See
  `docs/engineering/PHASE3_CANDIDATE_SHADOW_TELEMETRY_REPORT.md`.

## Non-Goals

- Do not promote ORB, stop widening, confidence gating, or ML reweighting live
  from one replay result.
- Do not optimize parameters directly against the same short replay window and
  call it edge.
- Do not increase trade count as a goal; only improve risk-adjusted expectancy.
