# Deep Research Strategy Review And Action Plan

Date: 2026-05-09
Branch: `codex/v13-phase2-expectancy`
Research input: `/Users/marselkei/Downloads/deep-research-report (9).md`
Local baseline: `docs/engineering/STRATEGY_AUTOPSY_2026-05-09.md`

## Executive Verdict

The deep research report is directionally correct. It agrees with the local strategy autopsy on the core point: the platform is technically much cleaner now, but the trading edge is not yet durable enough to scale. The original untagged strategy was structurally losing, while the newer tagged slice is materially better but still too concentrated, too short-lived, and too weakly benchmarked to call a production-grade strategy.

The most important recommendation to accept is this: stop treating the blended composite score as the strategy. The current book mixes continuation, breakout, volume, regime, ML, inverse ETF behavior, and pyramiding into one candidate path, then labels the trade after the fact. That is not sufficient strategy governance. Each engine needs a first-class `strategy_id` before ranking, sizing, order creation, telemetry, replay, and promotion.

The biggest correction is ORB. The report calls stocks-in-play ORB the best near-term promotion candidate. I agree it is one of the best near-term research lanes, but I do not agree it is promotion-ready. Our own Phase 3 ORB shadow simulator found 20 hypothetical trades, gross PnL/share `-$27.88`, avg R `-0.416`, win rate `35%`, and explicitly recommended keeping `ORGANISM_ORB_LIVE_ENABLED=false`. ORB should be redesigned and shadowed with better stocks-in-play selection, not enabled live from current evidence.

## Evidence Checked

Local evidence:

- `docs/engineering/STRATEGY_AUTOPSY_2026-05-09.md` says the legacy untagged slice lost `-$970.08` with profit factor `0.498`, while the newer tagged slice made `+$206.90` with profit factor `1.295`.
- `backend/organism/strategy_attribution.py` segments by `exit_reason`, `entry_source`, `regime_at_entry`, and `confidence_bucket`, but not yet by first-class `strategy_id`.
- `docs/engineering/PHASE3_ORB_SHADOW_OUTCOME_REPORT.md` rejects live ORB promotion from current evidence.
- `docs/engineering/PHASE8_EVIDENCE_WAREHOUSE_V2_REPORT.md` shows the evidence warehouse exists, but current filter and symbol summaries are still first-pass and do not yet implement the full benchmark/null stack.
- `backend/organism/orb_scanner.py`, `backend/organism/eod_scanner.py`, and `backend/organism/mean_reversion_scanner.py` exist as separate shadow/live-flagged scanners, but their live adoption still flows into the shared candidate pipeline rather than a full strategy-family governance layer.

External checks:

- ORB/stocks-in-play is plausible research, but mostly working-paper level evidence: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284>
- Intraday momentum and intraday periodicity are real enough to justify an ETF/index engine research lane, especially with time-of-day controls: <https://www.sciencedirect.com/science/article/pii/S0304405X18301351>
- Backtest overfitting controls are not optional in a platform doing repeated model search: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253>
- Inverse ETFs have daily objectives and can diverge from intuitive inverse exposure over longer periods, so they should be intraday hedges or overlays, not generic alpha engines: <https://www.sec.gov/investor/pubs/leveragedetfs-alert.htm>
- Residual/stat-arb research is a credible hedge-fund-style direction, but it is a materially harder business than the current long-only composite: <https://math.nyu.edu/~avellane/AvellanedaLeeStatArb20090616.pdf>

## Recommendation Acceptance Matrix

| Research recommendation | Verdict | Local interpretation |
| --- | --- | --- |
| Break the blended composite into first-class strategies | Accept | Highest-priority structural fix. Add `strategy_id` before ranking/sizing and report every metric by strategy. |
| Treat current composite as baseline research engine | Accept | Keep it conservative and defensive. Do not tune it as the main future strategy. |
| Promote ORB as strongest near-term candidate | Modify | ORB is a strong research lane, not a promotion candidate yet. Current ORB evidence is negative. |
| Build stocks-in-play universe selection | Accept | This is likely more important than another score-weight tweak. Start with gap, RVOL, liquidity, sector shock, and earnings/news proxies. |
| Build ETF/index intraday momentum engine | Accept | Good near-term research lane for SPY/QQQ/IWM plus sector ETFs. Must be separate from single-name alpha. |
| Build EOD momentum | Modify | Plausible only as ETF/index or catalyst-driven EOD continuation. Current generic single-name EOD rule needs stricter evidence. |
| Build mean reversion | Modify | Plausible only as liquidity/residualized reversion with separate risk, not generic dip-buying. Current MR scanner is a starting point, not a finished engine. |
| Build residual stat-arb | Accept as medium-term | Worth incubating, but requires beta/sector residuals, hedging, execution measurement, and probably short/paired exposure support. |
| Use inverse ETFs | Modify | Use as intraday hedge overlay only. Flatten by close unless evidence explicitly supports otherwise. |
| Keep ML out of primary direction/ranking/sizing | Accept | Current ML confidence is not calibrated enough. Use ML as meta-filter only after monotonic OOS bucket evidence. |
| Require benchmark/null models | Accept | This is mandatory before any strategy promotion. |
| Use White/PBO/Deflated Sharpe style validation | Accept in phases | Start with practical walk-forward, null, delay, benchmark, concentration, and cost tests; add advanced adjusted statistics after the evidence dataset is large enough. |

## Actionable Backlog

### P0 - No-Regret Controls To Preserve

1. Keep `ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED=true`.
2. Keep `ORGANISM_DROP_ML_FROM_GATE=true`.
3. Keep `ORGANISM_ORB_LIVE_ENABLED=false`, `ORGANISM_EOD_LIVE_ENABLED=false`, and `ORGANISM_MEAN_REVERSION_LIVE_ENABLED=false` unless replay and shadow evidence explicitly promotes them.
4. Do not increase max notional or position count to chase index returns until engine-level alpha is proven.
5. Continue post-close evidence generation and do not authorize promotion from raw PnL alone.

### P1 - Strategy Attribution Hardening

Goal: every live trade, shadow candidate, replay row, and report answers: which strategy caused this?

Implementation items:

1. Add `strategy_id` to candidate dictionaries before ranking/sizing.
2. Add `strategy_id` to `PositionSize` or the sizing result object that carries entry metadata.
3. Persist `strategy_id` into live engine `_entry_metadata`.
4. Add `strategy_id` to `TradeRecord`, brain persistence, `trade_history.csv`, and manifest summaries.
5. Keep `entry_source` as a backward-compatible display label, but stop using it as the promotion key.
6. Add `strategy_id` segmentation to `backend/organism/strategy_attribution.py`.
7. Add tests for alpha, pure breakout, alpha+breakout, ORB, EOD, MR, and reconciliation/orphan fallback paths.

Acceptance bar:

- No live ranking/sizing behavior changes.
- Existing trade history loads without `strategy_id`.
- New trades persist `strategy_id` through order creation, close, CSV save, brain reload, and health/report APIs.

### P1 - Benchmark And Null Model Stack

Goal: stop confusing "made money" with "had edge."

Implementation items:

1. Extend the Phase 8 evidence warehouse with same-symbol trade-window passive hold.
2. Add SPY/QQQ/IWM and sector ETF benchmark returns over the same trade window.
3. Add time-of-day matched random-entry nulls by symbol, session, and hold duration.
4. Add 1/5/10-bar delay nulls for every candidate event.
5. Add a simpler-rule benchmark per strategy family.
6. Add after-cost and slippage assumptions to every benchmark table.
7. Store variant count: how many thresholds, universes, clocks, and filters were tried.

Acceptance bar:

- Every promoted or replay-eligible strategy reports `pnl`, `alpha_over_symbol_hold`, `alpha_over_market`, `alpha_over_sector`, `alpha_over_random`, `alpha_over_delay_1/5/10`, and concentration by symbol/session/regime.
- Promotion remains unauthorized if benchmark alpha is missing.

### P1 - Shadow Strategy League Table

Goal: decide which engines deserve capital.

Implementation items:

1. Generate a daily table by `strategy_id` for live trades and shadow candidates.
2. Include 1/5/10/20-bar forward outcomes and realized trade outcomes when available.
3. Include profit factor, win rate, avg bps, avg R, max adverse excursion, max favorable excursion, drawdown, turnover, slippage estimate, and sample size.
4. Add verdicts: `reject`, `collect_more`, `replay_eligible`, `paper_micro_eligible`, `paper_normal_eligible`.
5. Require sample-size and concentration gates before any promotion verdict can improve.

Acceptance bar:

- Daily report tells us what to do tomorrow without relying on narrative memory.
- A single symbol like AMD can be flagged for replay, but cannot be treated as a "strategy."

### P2 - Stocks-In-Play ORB Redesign

Goal: rebuild ORB around information intensity instead of generic opening breakouts.

Implementation items:

1. Add stocks-in-play score using opening gap, first 5/15-minute RVOL, dollar volume, spread/liquidity, sector shock, and news/earnings proxy if available.
2. Separate ORB into `strategy_id=orb_sip_long`, `orb_sip_short_or_inverse`, and possibly `orb_index`.
3. Require distinct holding and stop logic for ORB rather than the shared composite path.
4. Shadow forward for at least 5-10 sessions before replay eligibility.
5. Compare against same-symbol open-to-close drift, next-bar breakout continuation, and delayed-entry nulls.

Acceptance bar:

- Do not promote from the existing Phase 3 ORB evidence.
- Replay eligibility requires positive after-cost alpha versus same-symbol and delay nulls, not just positive raw PnL.

### P2 - ETF/Index Intraday Momentum Engine

Goal: test whether SPY/QQQ/IWM/sector ETF intraday momentum is cleaner than the single-name composite.

Implementation items:

1. Add a shadow-only ETF/index engine with `strategy_id=etf_intraday_momentum`.
2. Candidate universe starts with SPY, QQQ, IWM, XLK, XLE, and any sector ETFs already used for exposure diagnostics.
3. Signal variants: first-30-minute return, morning return to midday, high-volume/high-volatility filter, and EOD continuation.
4. Hold variants must be predeclared: to midday, to EOD flatten, and fixed 30/60/120-minute windows.
5. Benchmark against passive ETF same-window hold and delayed-entry nulls.

Acceptance bar:

- Only one or two predeclared variants can become replay-eligible at a time.
- Positive evidence must be broad across sessions, not one strong index day.

### P2 - Catalyst Continuation Universe Builder

Goal: make "what to trade today" a first-class decision.

Implementation items:

1. Start with bar-derived proxies: gap %, RVOL, dollar volume, open range expansion, sector ETF shock, and unusual volatility.
2. Add earnings/news flags only when the data source is reliable and auditable.
3. Persist universe-selection reason into telemetry and trade metadata.
4. Report PnL and forward outcomes by universe-selection reason.

Acceptance bar:

- The scanner must prove that selected "stocks in play" beat the static liquidity universe after costs and null comparisons.

### P2 - Residualized Mean Reversion Research

Goal: turn mean reversion from generic dip-buying into a hedged/residual hypothesis.

Implementation items:

1. Compute market beta and sector residual for each candidate using SPY/QQQ/IWM and relevant sector ETF proxies.
2. Define dislocation in residual terms, not raw price distance only.
3. Simulate paired hedge or beta hedge PnL net of slippage.
4. Keep the current long-only MR scanner as shadow baseline, but require residual MR to beat it.
5. Add regime gate: MR should be tested mostly in liquidity/chop states, not strong directional trend states.

Acceptance bar:

- No live MR promotion until residualized returns beat raw mean reversion and benchmarks after costs.

### P3 - Inverse ETF Hedge Overlay

Goal: hedge book-level beta intraday without pretending inverse ETFs are standalone alpha.

Implementation items:

1. Add hedge overlay simulator for SH/PSQ only in shadow/replay.
2. Measure hedge effectiveness against SPY/QQQ beta drift, tracking error, slippage, and opportunity cost.
3. Force EOD flatten by design.
4. Report overlay effect separately from underlying strategy alpha.

Acceptance bar:

- Overlay promotes only if it reduces drawdown or beta exposure without destroying expectancy.

### P3 - ML Meta-Filter Only

Goal: let ML earn back trust empirically.

Implementation items:

1. Build OOS calibration report by score bucket.
2. Require monotonic or at least directionally useful expectancy by bucket.
3. Compare ML-filtered candidates against non-ML baseline candidates.
4. Allow ML only as veto/meta-filter until it proves incremental value.
5. Keep ML out of sizing and primary direction until after a full promotion review.

Acceptance bar:

- ML cannot increase live risk unless it improves after-cost benchmark alpha out of sample.

## Proposed Execution Sequence

### Phase 9A - Evidence Foundation

Build `strategy_id` propagation, benchmark/null reports, and the daily shadow league table. This is the immediate next step because every later strategy decision depends on trustworthy attribution and baselines.

### Phase 9B - Parallel Shadow Engines

Run ORB stocks-in-play, ETF/index momentum, catalyst continuation, and residual MR as separate shadow strategies. Keep live behavior unchanged. The goal is not to trade more; it is to learn which hypotheses have legs.

### Phase 9C - Replay And Micro-Paper Promotion

Only strategies that beat benchmarks/nulls with enough sample size get replay plans. Only replay survivors get micro-paper eligibility. Micro-paper uses tiny capped notional and separate risk budgets.

### Phase 9D - Portfolio Construction

Only after multiple engines have evidence, build a portfolio layer with risk budgets, correlation cuts, beta control, hedge overlays, and exposure scaling.

## Immediate Next Slice

Start with Phase 9A:

1. Implement first-class `strategy_id` plumbing.
2. Extend the evidence warehouse with same-symbol, benchmark, random, and delay nulls.
3. Generate a post-close strategy league report.
4. Run focused tests plus required organism/replay safety tests because this touches trade metadata and evidence paths.
5. Keep runtime behavior unchanged and do not enable any new live strategy flag.

This is the cleanest bridge from "we cleaned the platform" to "we can now improve the trading machine honestly." It does not make a profitability claim; it gives us the instrumentation to stop fooling ourselves and promote only real edge.
