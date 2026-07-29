# Pyramid-Cut Bleed — Quantification (Task C, exit-experiment brief)

**Date:** 2026-06-20 · **Source:** `organism_brain/trade_history.csv` (567 clean live trades, Mar 30–Jun 18 2026, net −$792.22).

## Headline

`pyramid_cut*` is the single largest loss bucket in the live book.

| Metric | Value |
|---|---|
| Trades | **151** (26.6% of all trades) |
| Net P&L | **−$451.64** (≈ **57% of the −$792 total loss**) |
| Win / loss | **1 win / 150 losses** |
| Avg / worst | −$2.99 / −$41.52 |
| MFE given back | **$425.01** (sum_mfe $132.16, realized −$292.85 on the 96 positive-MFE cuts) |

This reproduces the Tier-1 estimate (~$425 recoverable). These exits are inline in
`live_engine.py` `_live_tick_inner` (decision in `pyramider.py`
`MomentumPyramider.check_pyramid`), so the exit-engine A/B (`AltExitEngine`) cannot
reach them — confirmed by Tier-2, where `pyramid_cut*` still appeared among the worst
trades in every arm.

## Where it concentrates: chop

| regime_at_entry | n | net |
|---|---|---|
| **chop** | **136** | **−$360.40** (80% of the bleed) |
| trending_up | 7 | −$47.82 |
| high_vol | 4 | −$22.01 |
| unknown | 1 | −$16.85 |
| trending_down | 3 | −$4.55 |

## Cut-threshold distribution (the `-N.NR` in the reason string)

Median cut −1.3R; mean −1.55R; range −0.7R … −6.5R.

| R bucket | n | net |
|---|---|---|
| (−1.0, 0.0] | 17 | −$18.94 |
| **(−1.5, −1.0]** | **72** | **−$180.19** |
| **(−2.0, −1.5]** | **36** | **−$142.58** |
| (−3.0, −2.0] | 18 | −$67.08 |
| (−4.0, −3.0] | 7 | −$37.51 |
| (−99, −4.0] | 1 | −$5.33 |

**The −1.0R…−2.0R band carries −$322.77** (108 of 151 trades) — i.e. the pyramider
cuts adds at shallow adverse excursion (prod thresholds: `CUT_PARTIAL=-0.7R`,
`CUT_FULL=-1.0R`), inside the chop noise band, locking in losses on positions that
frequently would have recovered (96 reached positive MFE).

## Lever designed (replay-only, offline)

`pyramid_soft` arm in `scripts/edge_experiments.py`: widens the anti-add cut
thresholds to `CUT_FULL=-3.0R`, `CUT_PARTIAL=-2.5R` via a runner-side monkeypatch of
`MomentumPyramider` class attrs in the replay subprocess (env
`ORGANISM_PYRAMID_CUT_FULL_R` / `ORGANISM_PYRAMID_CUT_PARTIAL_R`, default unset = prod
behavior). **No edit to `_live_tick_inner` or `pyramider.py`** (both guarded). This
lets chop adds breathe past the −1R…−2R noise band; the disaster stop + time cap still
bound the downside.

> Note: the inline Exp1A chop min-hold gate (`_should_suppress_chop_cut`, 10 bars) only
> *delays* a cut; it does not change the threshold. The threshold is the lever here.

## Result

See `report.json` from the broad-corpus run (Task A) for `pyramid_soft` vs `baseline`
after costs (net, expectancy, t-stat, PF, MFE-giveback, sub-period stability) and the
go/no-go on a live-shadow trial.
