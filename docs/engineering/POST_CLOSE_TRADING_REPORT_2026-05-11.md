# Post-Close Trading Report - 2026-05-11

Generated: 2026-05-11 20:10 PT / 2026-05-12 03:10 UTC

## Executive Summary

The platform was operationally healthy, deployed on the expected code, and
flat after the session. The main paper book did not place any live orders
today: `orders_today=0`, `realized_trades_today=0`, `realized_pnl_today=0`.
This means today's live PnL was flat, not profitable or unprofitable.

The new evidence layer did its first real job: it captured first-class Phase 9
shadow strategy events during the session. We recorded `202` first-class
strategy-evidence rows today, including `59` Phase 9 shadow strategy events.
After fetching matching Alpaca 1-minute bars, `348` Phase 9 outcome rows joined
successfully.

Strategy conclusion: do not promote anything. `orb_sip_v2` and
`eod_reversal_shadow` had encouraging one-session shadow results, but they are
single-day, concentrated, and rejected by Phase 9D portfolio controls.
`residual_mean_reversion` was negative today. The current live `alpha_baseline`
strategy remains historically unprofitable.

## Runtime And Platform State

- Host HEAD: `12fdd95b8a4dd5da5aa9f1cefdba2812722bc1cd`.
- Container `GIT_SHA`: `12fdd95b8a4dd5da5aa9f1cefdba2812722bc1cd`.
- Container `IMAGE_SHA`: `12fdd95b8a4dd5da5aa9f1cefdba2812722bc1cd`.
- Build time: `2026-05-11T05:52:31Z`.
- `/healthz`: `200`.
- Migration head: `20260503_000003`.
- Phase 9 shadow engines: enabled.
- Strategy evidence telemetry: enabled.
- Candidate filter shadow telemetry: enabled.
- Exploration: disabled.
- Positions after close: `0`.
- Live-open orders after close: `0`.
- Outbox rows after close: `0`.

Operational warnings seen in logs:

- `PREFLIGHT: 17/18 checks passed (0 critical failures, 1 warnings)`.
- `USE_MOCK_DATA=True` appears in `backend.api.routes.signals` requests. This
  appears tied to the API signals route, but should be explicitly checked
  against live-engine market-data wiring before relying on API signal screens.
- Brain load reports a small PnL reconciliation drift:
  `state=-626.93`, `csv_sum=-624.78`, drift `$2.15`.
- Production promotion remains blocked because total PnL and Sharpe are below
  floor. This is correct.

## Main Book Performance

Database results for 2026-05-11 UTC:

| Metric | Value |
| --- | ---: |
| Orders created today | `0` |
| Filled orders today | `0` |
| Realized lot rows today | `0` |
| Realized PnL today | `$0.00` |
| Max open positions | `0` |

Tick telemetry:

| Metric | Value |
| --- | ---: |
| Tick rows today | `272` |
| First tick | `2026-05-11 13:28:59.995227+00` |
| Last tick | `2026-05-11 20:00:08.920002+00` |
| Orders submitted | `0` |
| Regime counts | `chop=252`, `high_vol=13`, `trending_up=7` |
| Entry block reasons | blank `246`, `opening_block=18`, `stale_data=8` |

Why no live trades?

- Top-candidate max score was only `0.344`.
- Main confidence threshold is normally `0.40` baseline or `0.45` defensive.
- Top candidates were mostly direction `0`; only `16 / 1255` top-candidate rows
  had nonzero direction.
- This looks like the live engine correctly declined weak candidates rather
  than failing to submit orders.
- However, telemetry should be improved: tick telemetry did not clearly label
  these as confidence-threshold misses even though that is the inferred reason.

## Current Strategy Health

Live strategy health endpoint:

| Metric | Value |
| --- | ---: |
| Strategy trades | `551` |
| Total PnL | `-$763.1831` |
| Win rate | `0.3321` |
| Sharpe per trade | `-1.3366` |
| Max drawdown | `-$985.93` |
| Last 25 mean PnL | `$1.3008` |
| Last 25 win rate | `0.28` |
| Last 50 mean PnL | `$0.3144` |
| Last 50 win rate | `0.36` |

Attribution remains clear: the live strategy is still `alpha_baseline`.
Historical full-scope expectancy is not good enough to scale. The recent
rolling slices are less bad, but the sample is too small and the win rate is
still weak.

Key attribution observations:

- `alpha_baseline`: `551` trades, `-$763.1831`.
- Entry-source historical slices:
  - blank legacy rows: `149` trades, `-$970.08`.
  - `alpha`: `220` trades, `+$178.02`.
  - `alpha+breakout`: `162` trades, `+$15.20`.
  - `breakout`: `20` trades, `+$13.68`.
- Regimes:
  - `chop`: `360` trades, `+$29.36`.
  - `trending_up`: `21` trades, `+$94.06`.
  - `high_vol`: `14` trades, `+$93.31`.
  - blank legacy rows dominate historical loss.
- Confidence inversion is still flagged: the highest-confidence bucket
  underperforms the mid-confidence bucket.

## Phase 8 Evidence Warehouse

`scripts/ci/run_phase8_postclose_evidence.py --include-db --require-db` passed.

| Metric | Value |
| --- | ---: |
| Total evidence events | `766` |
| Strategy events | `397` |
| Candidate-filter events | `369` |
| Outcomes | `581` |
| Joined outcomes | `579` |
| Trade-history rows | `559` |
| DB orders | `1535` |
| DB realized rows | `1082` |
| Count reconciliation | `ok` |
| Promotion authorized | `false` |

The warehouse still exports one replay candidate from cumulative historical
evidence: `symbol:AMD`. This is not a strategy promotion. It means AMD remains
a replay/research candidate because forward and realized symbol evidence have
aligned positively in the older warehouse data.

## Phase 9 Shadow Evidence

Today's Phase 9 capture:

| Strategy | Events |
| --- | ---: |
| `residual_mean_reversion` | `36` |
| `eod_reversal_shadow` | `12` |
| `orb_sip_v2` | `11` |
| `etf_intraday_momentum` | `0` |

Matching bars were fetched for:

`AMD`, `AMZN`, `COST`, `GOOGL`, `IWM`, `META`, `MSFT`, `NVDA`, `QQQ`, `SPY`,
`TSLA`, `WMT`, `XLE`, `XLK`, `XOM`.

Outcome join:

| Metric | Value |
| --- | ---: |
| Phase 9 events | `59` |
| Outcome rows | `354` |
| Joined rows | `348` |
| Insufficient future bars | `6` |
| Replay candidates | `0` |
| Promotion authorized | `false` |

Strategy league from today's joined shadow outcomes:

| Strategy | Outcome | Net Avg bps | PF | Win Rate | Main Reason Not Promoted |
| --- | ---: | ---: | ---: | ---: | --- |
| `orb_sip_v2` | encouraging | `+15.016` | `6.0207` | `0.6212` | only one symbol/session; sample below portfolio minimum |
| `eod_reversal_shadow` | mildly positive | `+3.793` | `1.6036` | `0.6119` | sample below minimum; concentrated; delay alpha weak |
| `residual_mean_reversion` | negative | `-5.253` | `0.6950` | `0.4279` | poor expectancy and benchmark alpha |

Important interpretation:

- `orb_sip_v2` today was entirely `XOM` in the joined outcome rows. It cannot
  be promoted from a single-symbol/single-session win.
- `eod_reversal_shadow` was concentrated in `WMT` and `AMD`.
- `residual_mean_reversion` should remain shadow-only and likely needs redesign
  or tighter regime gating.
- `etf_intraday_momentum` produced no events, so we have no evidence for or
  against it from today.

## Phase 9D Portfolio Construction

Phase 9D correctly refused allocation:

- `portfolio_authorized=false`.
- `promotion_authorized=false`.
- Allocations: `0`.
- Eligible strategies: `0`.
- Eligible families: `0`.
- Blockers:
  - `not_enough_validated_strategies`.
  - `not_enough_independent_strategy_families`.

This is correct behavior. The platform observed strategy candidates but did
not confuse one-session shadow evidence with promotion-grade edge.

## Implementation Review Notes

The new implementation did work:

1. First-class strategy telemetry arrived with `signal_id`, `strategy_id`,
   `engine_version`, `created_at`, `git_sha`, and `runtime_config_hash`.
2. Phase 9 shadow engines remained shadow-only.
3. Phase 9D did not change live ranking, sizing, gates, orders, or promotions.
4. The platform truth observer now reports first-class Phase 9 events and no
   blockers.

Issues revealed today:

1. The post-close Phase 9 analysis must automatically fetch bars before running
   `phase9_shadow_evidence.py`. The first default run produced
   `no_bar_at_or_after_event` for all events until the explicit bar fetch.
2. The same-symbol-hold benchmark is currently tautological for long signals
   over the exact same entry/exit window. Net alpha over same-symbol hold is
   exactly `-cost_bps` for long-only rows. This should not be used as a hard
   rejection reason without redesigning that benchmark.
3. Main-book no-trade diagnostics need clearer labels. We can infer threshold
   misses from top-candidate scores, but tick telemetry should explicitly
   report the active threshold and below-threshold counts.
4. `etf_intraday_momentum` generated no events today. This may be valid due to
   regime/window filters, but it needs a daily "why no MIM events" diagnostic.
5. `USE_MOCK_DATA=True` appears in API signals logs. Confirm it is not feeding
   live-engine decisions.

## Recommendations

1. Keep all Phase 9 strategies shadow-only tomorrow.
2. Add a single post-close runner that performs the full sequence:
   fetch Phase 9 event bars -> join outcomes -> build Phase 9D portfolio report
   -> write daily post-close markdown.
3. Fix the same-symbol benchmark design before using it as a promotion blocker.
4. Add explicit no-trade diagnostics to tick telemetry:
   active threshold, max score, nonzero-direction candidates, threshold-miss
   count, and final no-order reason.
5. Treat `orb_sip_v2` and `eod_reversal_shadow` as promising research lanes,
   not live candidates.
6. Treat `residual_mean_reversion` as weak from today's data.
7. Investigate why `etf_intraday_momentum` emitted zero signals.
8. Do not increase notional or enable micro-paper from today's evidence alone.

## Verdict

The platform performed well operationally: it stayed deployed, captured
evidence, ended flat, and did not promote unproven strategies.

Trading performance from the live book was neutral because it did not trade.
This is disappointing if the goal was to participate in the day, but technically
it is preferable to forcing low-confidence trades. The useful result is that the
new research layer finally produced analyzable forward shadow evidence.

Bottom line: **system good, main strategy still unproven/weak, Phase 9 evidence
loop alive, no strategy promotion yet.**
