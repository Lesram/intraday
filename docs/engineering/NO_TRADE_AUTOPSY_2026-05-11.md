# No-Trade Autopsy - 2026-05-11

Generated: 2026-05-11 PT / 2026-05-12 UTC

## Verdict

Zero trades on 2026-05-11 should not be treated as normal. The platform was
operationally alive, but the live decision path failed to turn a moving market
into valid orders. This was not a broker failure: the database has zero order
records for the day, so the engine never reached order creation.

The market did move. From fetched 1-minute Alpaca bars, approximate regular
session close-to-close returns included `TSLA +503 bps`, `NVDA +196 bps`,
`XOM +207 bps`, `LLY +178 bps`, `XLE +119 bps`, `XLK +86 bps`, `SPY +31 bps`,
and `QQQ +28 bps`. The problem was not "no market opportunity"; it was a
strategy/gating/telemetry failure inside the current live path.

## What Happened

Runtime/order facts:

- `orders_today=0`.
- `filled_today=0`.
- `open_like_today=0`.
- Tick telemetry rows during the session: `272`.
- Orders submitted from tick telemetry: `0`.
- Entry block reasons: blank `246`, `opening_block=18`, `stale_data=8`.

Candidate facts from `tick_telemetry.top_candidates`:

- Top-candidate slots inspected: `1260`.
- Nonzero-direction top candidates: `16`.
- Max top-candidate score: `0.344`.
- Max score among nonzero-direction top candidates: `0.3012`.

Candidate-filter telemetry gives the clearer picture:

- `143` alpha-baseline candidate-filter telemetry rows were recorded.
- `120` were blocked by `alpha_breakout_chop_blocked_by_evidence`.
- `23` were marked `live_pipeline_candidate=true`.
- All `23 / 23` live-pipeline candidates had `direction=0.0`.

That means the live pipeline produced candidates that passed enough upstream
filters to be considered, but had no actionable direction. The Kelly sizer then
silently dropped them because it refuses `direction == 0`. This rejection is
currently not counted in `tick_telemetry.gate_rejections`, so the day looked
like "no candidates strong enough" instead of "all live candidates were
directionless."

## Root Cause

There were two interacting causes:

1. Directional `alpha+breakout` in `chop` was intentionally blocked.

   The defensive filter blocked `120` alpha+breakout candidates in `chop`,
   including `68` with `direction=1.0`. This was not random: historical evidence
   had flagged alpha+breakout in chop as a bad slice.

2. The remaining live alpha candidates were neutral-direction.

   The current alpha path can remove ML from the gate/confidence decision while
   still relying on ML to provide direction outside strict learning mode. When
   ML says hold/neutral, a candidate can still carry confidence from
   breakout/tension but retain `direction=0.0`. That candidate cannot become a
   trade.

This is a design inconsistency: if ML is excluded from the live gate, then live
direction must also come from a strategy-specific non-ML rule, or the candidate
must be rejected explicitly with a clear reason before sizing.

## Did The Blocked Trades Deserve To Trade?

Not obviously. The blocked directional `alpha+breakout` candidates had mixed
forward outcomes after joining to Alpaca 1-minute bars:

| Slice | Horizon | Events | Mean Directional bps | Win Rate | Median bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Blocked directional alpha+breakout | 5 bars | 68 | `-0.007` | `45.6%` | `0.000` |
| Blocked directional alpha+breakout | 15 bars | 68 | `+1.846` | `39.7%` | `-1.493` |
| Blocked directional alpha+breakout | 30 bars | 68 | `+1.063` | `39.7%` | `-1.445` |
| Blocked directional alpha+breakout | 60 bars | 68 | `+1.364` | `44.1%` | `-3.171` |

There were some attractive individual misses, including TSLA, LLY, AMD, MSFT,
and XOM-related movement elsewhere in the shadow layer. But as a slice, the
blocked alpha+breakout candidates were not strong enough to simply re-enable.
Mean returns were small, medians were negative at the longer horizons, and
spread/slippage would erase much of the average edge.

## Why The Existing Report Was Too Soft

Calling the day "operationally safe" was narrowly correct but incomplete.
The stronger verdict is:

- The broker/container/database stack worked.
- The live decision layer did not produce tradable signals.
- Telemetry failed to make the reason obvious.
- The fixed universe did not represent "the whole market."
- The current alpha-baseline strategy is not an adequate professional trading
  strategy in its present form.

## Required Fixes

1. Add explicit no-trade diagnostics.

   Tick telemetry must record counts for:
   - live candidates before sizing,
   - `direction_zero`,
   - below confidence threshold,
   - defensive-filtered candidates,
   - sizer invalid-value rejects,
   - final `no_order_reason`.

2. Align direction with the strategy source.

   If a candidate is `alpha+breakout`, direction must come from a documented
   breakout/momentum rule or the candidate must be explicitly rejected before
   it is recorded as live-pipeline eligible. It should not pass upstream gates
   with `direction=0.0`.

3. Keep the chop alpha+breakout block for now, but study exceptions.

   Do not blindly re-enable the whole slice. Instead, test whether a stricter
   exception set exists, for example high RVOL, sector-confirmed trend,
   VWAP-confirmed continuation, or top-of-day stocks-in-play.

4. Stop pretending the fixed live universe is the whole market.

   The live universe was the configured organism list, not all tradable U.S.
   equities. A professional system needs a real stocks-in-play/universe
   expansion layer before judging whether "nothing was worth trading."

5. Treat Phase 9 strategy engines as the path forward.

   Today's shadow evidence was more useful than the live alpha baseline.
   `orb_sip_v2` and `eod_reversal_shadow` deserve more forward evidence.
   `residual_mean_reversion` was weak today. `etf_intraday_momentum` emitted no
   events and needs a specific diagnostic.

## Bottom Line

The zero-trade day exposed a real weakness. It was not a catastrophic runtime
failure, but it was not acceptable for the trading ambition of the platform.
The platform needs a code fix for silent direction-zero candidates, a telemetry
fix for no-trade explainability, and a strategy fix that moves live decisions
away from the current over-bundled alpha baseline.

## Remediation Applied

The first mechanical remediation was implemented after this autopsy:

- `AlphaScanner.scan(..., derive_direction_from_observables=True)` now derives
  candidate direction from breakout/momentum features when ML is deliberately
  excluded from the live gate.
- `OrganismLiveEngine` passes that flag when `ORGANISM_DROP_ML_FROM_GATE=true`.
- Live-path candidates with `direction=0` are rejected before sizing and
  recorded with `defensive_filter_reason=direction_zero`.
- `KellySizer` records invalid direction/signal rejects instead of dropping
  them silently.
- Decision telemetry now carries `live_candidates_pre_sizing`,
  `direction_zero`, `below_main_conf`, `below_expl_conf`, `defensive_filter`,
  `sizer_invalid`, and `no_order_reason`.
- Focused regression coverage was added in `tests/test_no_trade_diagnostics.py`.

This does not make the strategy profitable by itself and does not promote any
shadow strategy. It closes the unacceptable silent-failure mode so tomorrow's
paper run can explain exactly why it traded or why it sat out.
