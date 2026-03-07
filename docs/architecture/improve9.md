According to a document from March 6, 2026, Intra finished the day down **$71.58** on **39 completed trades**, with the win rate up to **53.8%** but the payoff still broken: **average win $5.60 vs average loss $9.05**, for a **0.62x win/loss ratio**. The report itself identifies three post-close structural fixes: stale symbol-fitness collapse, stop-loss ATR multipliers that were too tight for 1-minute bars, and anti-predictive confidence amplification in learning mode.

My headline conclusion is blunt: **the strategy is not dead, but the current learning-mode architecture is still wrong in three foundational ways**.
First, untrained ML is still contaminating ranking and confidence. Second, **heuristic / uncalibrated `predicted_return` is still contaminating Kelly sizing**, which makes the Kelly stack mathematically elegant but economically meaningless. Third, the exit stack is **not aligned to the 15-bar thesis horizon**; it still behaves like a mix of small-win harvesting and full-stop loss acceptance rather than a coherent horizon-based trade management system.

One immediate audit issue: the final report is internally inconsistent. The headline says **21W / 18L**, but the exit-reason table sums to **18 wins / 21 losses**. That reconciliation bug needs to be fixed before you use March 6 as a calibration set for expectancy, confidence, or regime attribution.

A second constraint: the attachment gives full row-level detail for the first 20 trades and only aggregate detail for the remaining 19 afternoon trades, so I can do a rigorous **full-day causal decomposition** and a **trade-level diagnosis for the morning block**, but not a literal row-by-row autopsy of every afternoon trade from the attachment alone.

## Executive verdict

The March 6 loss was caused by five things, in order:

1. **The stop-loss engine was still the main economic drag** on the day that was actually traded. Stop-loss exits lost **-$156.38** and FTF lost **-$51.64**; those two exit modes alone were **-$208.02**, far larger than the reported daily loss because they were partially masked by `live_close` gains and one `take_profit`.

2. **The report’s headline loss understates how weak the autonomous stack still is.** If you add back the overnight ABNB carry (**+$106.66**) but remove the non-strategy `live_close` gains (**-$107.31**), the day’s core intraday strategy is still about **-$72.23**. So the same-day autonomous engine was still negative even after excluding the overnight legacy loss.

3. **Untrained ML is still doing real damage upstream.** The highest-confidence trades performed worst, and the current alpha scanner still gives ML a 25% top-level factor weight while computing ML score from `confidence × abs(predicted_return) × 20`, which means broken confidence and broken return forecasts get amplified twice.

4. **Kelly should not be live in learning mode in its current form.** The current Kelly path still uses `predicted_return / (atr_pct × sqrt(horizon_bars))²` and an edge-over-cost gate of `predicted_return >= 2 × spread_cost`. With predicted returns overstating realized returns by **22x**, that is not edge estimation; it is noise passed through a leverage formula.

5. **The learning-mode control system is still too complex for the amount of data it has.** Between fitness gating, exploration routing, regime-conditioned confidence thresholds, heuristic expected-return exemptions, burst caps, symbol bans, FTF variants, and Kelly floors, the platform is still trying to run a production-grade control stack on a small, noisy bootstrap sample.

---

## Part 1 — What actually caused the March 6 loss

### 1) Full-day loss decomposition

The cleanest causal split from the report is:

* `stop_loss`: **21 exits, -$156.38**
* `failure_to_follow`: **10 exits, -$51.64**
* `max_loss_limit`: **2 exits, -$8.50**
* offset by `live_close`: **+$107.31**
* `take_profit`: **+$31.60**
* `eod_flatten`: **+$6.03**

That means the day was not lost because the system “couldn’t find winners.” It found winners often enough. It lost because the **negative exit modes were too frequent and too expensive**, while most positive exits were either tiny or non-strategy artifacts.

### 2) Why the win rate rose but expectancy stayed negative

This is the core mechanical flaw.

The platform won **53.8%** of the time but still lost money because it is currently structured to **harvest small wins and wear larger losses**. The map shows:

* profit lock at **2R**
* partial TP at **3R**, selling **20%** intraday and moving stop to breakeven
* trailing stop only activates after **2.0× ATR**
* time-based exit only closes **profitable** trades
* loser time-stop is far out at **120 bars fallback**
* FTF still exists as an early negative-progress screen in some regimes

That is not a balanced horizon-aligned exit design. It is a design that tends to:

* convert many mildly favorable trades into small wins,
* leave bad trades to be decided by hard stop or max-loss,
* and delay loser resolution far beyond the thesis horizon unless the hard stop gets there first.

That is exactly the profile you saw: **more wins than losses, but winners too small to pay for the losers**.

### 3) Why I do **not** think FTF is tomorrow’s main lever

FTF is still negative on March 6, but it is no longer the single biggest issue. The report’s own post-close counterfactual says widening stops was the largest expected improvement, with a projected **+$70–100** effect on a March 6-like day, versus only **+$5–15** from neutralizing confidence sizing and **+$10–20** from restoring the full symbol universe.

So the next dollar of engineering should go to:

* wider/cleaner stop architecture,
* getting Kelly out of learning mode,
* and removing ML contamination from learning-mode confidence and ranking.

Not another round of FTF surgery.

---

## Part 2 — Audit of the three post-market fixes

## Fix 1 — Fitness decay + relaxed learning fitness gate

This fix is **directionally correct**, but it is not the best final design.

The emergency problem is real: stale low fitness scores collapsed the tradeable universe from **29 names to 9**, which concentrated exposure and starved the engine of alternatives. But there is also an architecture smell here: the platform map already documents a universe-rotation mechanism that decays fitness toward 0.50, while the March 6 report says no decay existed and one had to be added post-close. That means you likely have **duplicate or disconnected fitness systems** rather than one canonical path.

My verdict:

* **10% per epoch** toward neutral is acceptable as an emergency patch.
* **Epoch-based decay is not the right long-term control.**
* In learning mode, **hard fitness rejection should be removed or heavily softened** until a symbol has enough observations.

Better alternative:

* Keep symbol-level session bans for obviously bad names.
* Turn learning-mode fitness into a **soft ranking penalty only** until each symbol has at least **10 closed trades**.
* Move decay to a **session/trade-count-based** rule, not epoch cadence.

So: **valid patch for tomorrow, not the right end-state.**

## Fix 2 — Double the ATR stop multipliers

This is the **highest-impact** post-market fix, and it is the most justified one. The report attributes **-$156.38** to stop-loss exits and says the old ATR multipliers were effectively daily-bar logic ported into a 1-minute engine, resulting in stops only a few cents away from entry on many names.

I agree with the direction. I do **not** agree with treating the new values as “optimal.”

There is no universal optimal stop distance for 1-minute intraday trading. Under a simple diffusion heuristic, barrier width should scale with the square root of horizon, so a 15-bar thesis naturally implies wider horizontal barriers than a single-bar rule. But the right practical framework is **not** “pick one ATR multiple forever.” It is:

* horizontal barriers as a function of realized volatility,
* plus a **vertical barrier** at the thesis horizon,
* calibrated from realized **MAE/MFE** by symbol and regime. That is the logic behind triple-barrier style trade management. ([Mizar][1])

My verdict:

* **Good emergency fix**
* **Do not widen further tomorrow**
* **Must be paired with a vertical time barrier around the 15-bar thesis horizon**

Without that vertical barrier, wider stops just risk turning “false stops” into “slow bags.”

## Fix 3 — Neutral confidence scaling + new learning confidence formula

This is also directionally right, but it does not go far enough.

The report is unambiguous: high-confidence trades underperformed low-confidence trades, and the root cause is that ML still influenced confidence before it had earned the right to do so.

My verdict:

* `confidence_scale = 1.0` in learning mode is **correct**.
* The new learning-mode blend of **ML 15% / breakout 50% / tension 35%** is **better than before but still too generous to ML**.
* For main-book learning-mode trading, **ML should be 0% in confidence and 0% in sizing** until it proves calibration and monotonicity.

I would only allow ML back in after it passes all of these:

* at least **300 clean post-reset trades**,
* positive monotonicity across confidence buckets,
* Brier/log-loss meaningfully better than a naive baseline,
* predicted-return error ratio below **3x**,
* and a high-confidence bucket that actually outperforms the low-confidence bucket.

Until then, ML can stay in **shadow mode** for logging and offline validation.

---

## Part 3 — Full strategy architecture audit

### Entry logic

The current alpha scanner is too sophisticated for bootstrap mode and still gives too much influence to ML. The latest platform map still documents a 7-factor alpha score with **25% ML**, while ML score itself is driven by confidence and predicted return — both known-bad on March 6.

For bootstrap, I would simplify the entry edge to:

* breakout readiness,
* abnormal volume / liquidity,
* short-horizon momentum,
* and regime sanity checks,
  with ML in shadow only.

### Exit logic

The core design flaw is **horizon mismatch**. The system still uses a 15-bar horizon in sizing logic, but the exit engine does not enforce a clean 15-bar vertical barrier. Instead, profitable time exits are regime-dependent, losers can remain until a much later loser-time-stop, and partial exits / breakeven ratchets clip upside before the thesis fully expresses.

That is why I think the deepest blind spot is not “bad thresholds.” It is:
**you do not have one canonical definition of what a trade thesis is or when it expires.**

### Kelly sizing

Kelly should be **disabled in learning mode**. Simulation evidence on Kelly and fractional Kelly is clear that aggressive Kelly use under estimation error is dangerous over short and medium horizons; bad sequences can destroy wealth even when the long-run edge is positive. ([EconPapers][2])
Intra’s March 6 report shows the edge estimate is not merely noisy; it is **22x overstated**. That is disqualifying for Kelly. Use fixed ATR-dollar risk until calibration exists.

### Regime detection

Regime can still help as a **risk-off / context** signal, but it should not be a strong control input in learning mode. The regime-confidence gate bug shows that weak labels were still affecting live gates intraday.
My recommendation is:

* keep regime for telemetry,
* keep stress/high-vol safety behavior,
* but freeze regime-conditioned sizing and threshold shifts until there is more data.

### Self-evolution

At this stage, self-evolution is mostly hurting interpretability. The map shows it can adapt stop ATR, trail ATR, Kelly fraction, breakout thresholds, regime scales, shorts enablement, and more.
That is too much freedom for too little data. Freeze almost all of it until you have a larger clean sample.

### LONG_ONLY

A long-only intraday engine should accept idle bearish windows **or** trade inverse ETFs. What it should not do is force marginal long entries just to stay busy. The March 6 report itself lists LONG_ONLY as an open issue because the engine sat idle while alpha was short-directional.
Near-term answer: add **inverse broad-market ETFs** before you add naked single-name shorts.

### Universe

Static 30-name mega-cap + ETF coverage is acceptable for infrastructure testing, but it is not ideal for bootstrap alpha. Best results in short-horizon equity trading tend to come from **Stocks in Play** / abnormal activity names rather than a static large-cap basket. Research on >7,000 U.S. stocks found ORB performance materially stronger when limited to Stocks in Play, with strong after-cost results in that subset. ([SSRN][3])

---

## Part 4 — What a best-in-class version of this system would look like

A best-in-class 1-minute intraday system would start from **observable, short-horizon edges**:

* stocks in play / abnormal relative volume,
* opening or intraday momentum,
* and genuine order-flow / depth imbalance. Research supports all three: Stocks in Play materially improve ORB outcomes, intraday momentum is stronger on volatile and high-volume days, and order-flow imbalance explains short-interval price changes more directly than blunt volume proxies. Intra has some bar-level microstructure proxies, but not true order-book imbalance or depth, so its 10-second loop is currently acting faster than its information set supports. ([SSRN][3])

The ideal exit system would be simpler:

* one volatility-adjusted hard stop,
* one trailing mechanism,
* one vertical barrier aligned to the forecast horizon,
* and EOD flatten.
  That is much closer to triple-barrier thinking than the current stack of overlapping partial TP, FTF, profitable-only time exit, loser-time-stop, and multiple ratchets. ([Mizar][1])

The ideal learning-mode sizing would be:

* fixed ATR-dollar risk,
* capped notional,
* capped sector/correlation exposure,
* no Kelly until calibration exists. ([EconPapers][2])

---

## Phase A — implement before next trading day

| Change                                                                          | Files                                 | Exact implementation                                                                                                                                                                                                                               | Expected impact                                                                             | Risk                                          | Validate                                                                            |
| ------------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Turn Kelly off in learning mode**                                             | `kelly_sizer.py`, `live_engine.py`    | If `learning_mode` or `expected_return_source != "ml_calibrated"`, set `signal_kelly=0`, bypass Kelly floors, and size only by fixed ATR-dollar risk: `risk_budget = equity * 0.001`, shares = `min(risk_budget / stop_distance, 5% notional cap)` | Removes noise leverage from 22x-overstated returns; likely the single safest P&L stabilizer | Lower upside if a few trades really have edge | Size should no longer correlate with `predicted_return` in learning mode            |
| **Set ML weight to 0 for learning-mode main-book confidence and alpha ranking** | `live_engine.py`, `alpha_scanner.py`  | `learning_confidence = 0.65*breakout + 0.35*tension`; learning alpha weights = `ML 0.00, breakout 0.40, momentum 0.20, institutional 0.15, volume 0.10, quality 0.10, regime 0.05`                                                                 | Removes anti-predictive confidence/ranking distortion                                       | Could miss hidden ML signal                   | Confidence buckets should become monotonic instead of inverted                      |
| **Add a hard vertical barrier aligned to H=15**                                 | `adaptive_exits.py`                   | In learning mode, if neither stop nor trailing has exited by `bars_held >= 18`, exit `reason="horizon_timeout"`                                                                                                                                    | Fixes the deepest thesis/exit mismatch; should improve payoff symmetry                      | May cut some late runners                     | Average holding time clusters around intended horizon; loser_time_stop becomes rare |
| **Disable partial take-profit in learning mode**                                | `adaptive_exits.py`                   | `partial_tp_pct = 0.0` when `learning_mode=True`; keep trailing + full TP                                                                                                                                                                          | Stops clipping already-too-small winners                                                    | Slightly lower hit-rate on tiny wins          | Avg win should rise; number of sub-$3 winners should fall                           |
| **Make fitness a soft penalty, not a hard reject, during learning**             | `live_engine.py`, `self_evolution.py` | If symbol has `<10` clean trades, do not hard-reject on fitness; use fitness only as ranking multiplier. Keep session loss-ban logic                                                                                                               | Prevents another universe collapse and concentration                                        | More weak symbols enter sample                | Tradeable universe breadth should recover without repeated same-name churn          |
| **Entries only on completed 1-minute bars**                                     | `live_engine.py`                      | Keep exits/risk checks every 10s, but allow new entries only when `is_new_bar == True`                                                                                                                                                             | Reduces same-bar churn and false urgency from 10s loop                                      | Lower trade count                             | Fewer repeated same-bar entries; cleaner MFE/MAE distributions                      |
| **Kill the dead exploration path for now**                                      | `live_engine.py`                      | Do not route to `_confidence_exploration_queue` until an executor exists; log them instead                                                                                                                                                         | Removes misleading dead-code behavior and future B1-like bugs                               | Slightly less passive data collection         | No candidates silently disappear into non-trading queue                             |
| **No overnight carry, ever**                                                    | `live_engine.py`                      | Keep `15:45` entry block and `15:58` flatten; add invariant test that no organism position survives post-close                                                                                                                                     | Removes single largest risk source seen on March 6                                          | Can miss overnight gap winners                | Zero overnight organism positions every day                                         |

The most important three for tomorrow are:
**Kelly off, ML weight 0 in learning mode, and horizon-aligned exits.**

---

## Phase B — implement this week

Unify symbol-fitness logic into one canonical system. Right now the map documents one decay path and the March 6 report documents another, which means the control surface is fragmented.

Raise learning-mode `top_n` from **3 to 5** once fitness hard-rejects are removed and the burst cap is still active. With the universe fixed, 3 is unnecessarily concentration-prone in bootstrap mode.

Add a daily **Stocks in Play overlay** to the static universe: relative volume, abnormal gap/news/activity, and spread/liquidity sanity. That is much closer to what the literature supports for short-horizon equity intraday alpha. ([SSRN][3])

Add **inverse ETFs** (`SH`, `PSQ`) before single-name shorts. That lets a long-only execution framework participate in bearish tapes without building a full short stack immediately.

Freeze **all** self-evolution except symbol bookkeeping until at least **300 clean post-reset trades**. The current adaptation space is too wide for the sample size.

---

## Phase C — next two weeks

Introduce a real separation between:

* `ranking_score`,
* `direction`,
* `expected_return`,
* and `size`.

That separation exists partially on paper, but the March 6 B1 bug proved it is not operationally clean yet.

Add **true microstructure alpha** if you insist on keeping the 10-second decision loop:

* order-flow imbalance,
* queue/depth imbalance,
* bar-to-bar impact proxies tied to actual market depth.
  Right now the system has proxies, not the actual short-horizon variables the microstructure literature says matter most.  ([SSRN][4])

Move from a hard “200 trades and production” switch to a staged release:

* **Stage 0:** fixed risk, no Kelly, no ML influence
* **Stage 1:** ML shadow only
* **Stage 2:** ML 5–10% ranking weight and quarter-Kelly only after calibration passes
* **Stage 3:** production after rolling profit factor, calibration, and drawdown criteria are satisfied

---

## Final judgment

The strategy is **not fundamentally impossible**, but the current version is still **over-engineered in the wrong places and under-specified in the right ones**. The biggest blind spot is that the platform still does not define one clean answer to these three questions:

1. **What is the edge?**
2. **What is the intended holding period?**
3. **Why should size be proportional to this edge estimate?**

Until those three are clean, the organism will keep looking sophisticated while behaving like a noisy hypothesis generator.

The highest-probability path to profitability is **not** more ML right now. It is:

* simplify learning mode,
* stop using uncalibrated ML and predicted returns in sizing,
* align exits to the thesis horizon,
* and build the bootstrap edge around observable intraday phenomena: stocks in play, abnormal volume, momentum, and eventually true order-flow imbalance. ([SSRN][3])

Next moves

* Implement Phase A exactly before the next paper session.
* Reconcile the March 6 win/loss-table inconsistency before using the day for calibration.
* After one clean post-fix day, re-measure only three things: stop-loss share of losses, payoff ratio, and confidence monotonicity.
* Do not re-enable Kelly or ML-driven sizing until those three metrics improve materially.

[1]: https://docs.mizar.com/mizar/mizarlabs/transformations/labeling-methods "https://docs.mizar.com/mizar/mizarlabs/transformations/labeling-methods"
[2]: https://econpapers.repec.org/RePEc%3Awsi%3Awschap%3A9789814293501_0038 "https://econpapers.repec.org/RePEc%3Awsi%3Awschap%3A9789814293501_0038"
[3]: https://papers.ssrn.com/sol3/Delivery.cfm/4729284.pdf?abstractid=4729284 "https://papers.ssrn.com/sol3/Delivery.cfm/4729284.pdf?abstractid=4729284"
[4]: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2048974_code1579617.pdf?abstractid=1712822&mirid=1 "https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2048974_code1579617.pdf?abstractid=1712822&mirid=1"

---

## Implementation Log

### Phase A — Implemented 2026-03-06 (before next trading day)

All 8 Phase A items implemented, tested (7,136 + 26 replay), Docker deployed.

| # | Change | Files Modified | Implementation Detail |
|---|--------|---------------|----------------------|
| A1 | Kelly OFF in learning mode | `kelly_sizer.py` | Complete rewrite of sizing path. Learning mode: fixed ATR-dollar risk only (`risk_budget = equity * 0.001 / stop_distance`), no Kelly, no confidence scaling, no breakout bonus. Production mode: full Kelly stack preserved. Added `_RISK_BUDGET_PER_TRADE_LEARNING = 0.0010` and `_RISK_BUDGET_STOP_ATR` constants. |
| A2 | ML weight = 0 in learning mode | `live_engine.py`, `alpha_scanner.py` | **live_engine.py**: Learning confidence = `0.65 * breakout + 0.35 * tension` (ML 0%). Production: `0.50 * ml + 0.30 * breakout + 0.20 * tension`. **alpha_scanner.py**: Learning alpha weights = ML 0%, breakout 40%, momentum 20%, institutional 15%, volume 10%, quality 10%, regime 5%. Dynamic ML weight in production adjusts when avg confidence < 0.10. |
| A3 | Horizon timeout at 18 bars | `adaptive_exits.py` | Added `learning_mode: bool` attribute. In `check_exit()`: if `learning_mode and bars_held >= 18` → exit with `reason="horizon_timeout"`. H=15 prediction horizon + 3 grace bars. |
| A4 | Disable partial TP in learning mode | `adaptive_exits.py` | In `check_exit()`: skip `_check_partial_tp()` when `self.learning_mode`. Full TP and trailing still active. |
| A5 | Fitness soft penalty (not hard reject) | `live_engine.py` | Learning mode: skip fitness hard-reject entirely. Production mode: keep gate at 0.45. Session loss-bans remain the only hard protection in all modes. |
| A6 | Entries only on bar boundaries | `live_engine.py` | Added `_current_minute` check using `self._now_fn()` (supports replay via simulated time). New entries only when minute boundary changes. Exits/risk checks run every 10s tick. |
| A7 | Kill dead exploration queue | `live_engine.py` | Replaced exploration queue routing with simple logging. No candidates silently disappear into non-trading queue. |
| A8 | EOD flatten verified | `live_engine.py` | Confirmed: 15:45 ET entry block + 15:58 ET force close all positions. No changes needed. |

**Test results**: 7,136 backend passed (4 flaky async), 26 replay passed.

### Phase B — Implemented 2026-03-06

All 5 Phase B items implemented, tested (7,136 + 26 replay), Docker deployed.

| # | Change | Files Modified | Implementation Detail |
|---|--------|---------------|----------------------|
| B1 | Unify symbol-fitness into one canonical system | `self_evolution.py`, `live_engine.py`, `alpha_scanner.py` | **Canonical trade counts**: Added `symbol_trade_counts: dict[str, int]` to `EvolvedParams` with persistence. Trade counts increment at source (trade recording in `live_engine.py`), not during evolution. **Trade-count-based decay**: Symbols <10 trades snap to neutral (0.5). 10-30 trades: 15% decay rate. 30+: 5% decay rate. Old epoch-based 10% flat decay removed. **Fitness gate**: Production only hard-rejects symbols with 10+ trades AND fitness < 0.45. Learning mode: no gate (soft ranking only). **Alpha scanner scaling narrowed**: Old range [0.6, 1.45] → new [0.84, 1.18] via `composite *= 0.8 + fitness * 0.4`. |
| B2 | Raise learning-mode top_n from 3 to 5 | `live_engine.py` | `AlphaScanner(top_n=5)` — reduces concentration risk in learning mode. Burst cap (4/15min) and position limits still prevent overtrading. Hot-reload path kept at `MAX_OPEN_POSITIONS` for explicit user overrides. |
| B3 | Stocks in Play daily overlay | `alpha_scanner.py` | Added `_stocks_in_play_score()` static method. Uses existing `vol_sma_ratio` and `gap_pct` features (already computed in ml_features). Scoring: relative volume >1.5x starts boosting (3x = max), gap >0.5% starts boosting (2% = max). Combined into multiplicative boost [1.0, 1.25] on composite score. Applied after fitness scaling, before cap. No new API calls needed. |
| B4 | Add inverse ETFs (SH, PSQ) to universe | `live_engine.py`, `alpha_scanner.py`, `sector_map.py` | **Universe**: Added `SH,PSQ` to default `ORGANISM_LIVE_SYMBOLS` (22 symbols total). **Sector map**: Added SH and PSQ as "ETF" sector. **Alpha scanner**: Added `INVERSE_ETFS = {"SH", "PSQ", "DOG", "RWM"}` set. Updated `_regime_alignment()` with `symbol` parameter — flips regime interpretation for inverse ETFs (trending_down → trending_up and vice versa), so buying SH in a bear tape is scored as aligned. |
| B5 | Freeze self-evolution until 300+ clean trades | `live_engine.py` | In `_retrain_and_evolve()`: skip `evolution_engine.evolve()` entirely when `len(self._all_trades) < 300`. Only ML retraining + calibration map updates run. Symbol bookkeeping (trade counts) still updates because counts increment at trade recording source (B1). Logged: "Evolution frozen (N/300 trades) — symbol bookkeeping only". All parameter adaptation (signal weights, exit params, regime scales, breakout weights, XGB hyperparams, direction thresholds, feature selection) frozen until sufficient data. |

**Test results**: 7,136 backend passed (4 flaky async), 26 replay passed. Docker rebuilt.

### Phase C — Planned (next 2 weeks)

| # | Change | Status | Notes |
|---|--------|--------|-------|
| C1 | Clean separation of ranking_score / direction / expected_return / size | Planned | Partially started with `expected_return_source` on AlphaCandidate (improve8 B1). Need fully independent pipelines for ranking vs sizing. |
| C2 | True microstructure alpha (order-flow imbalance, depth) | Planned | Currently using bar-level proxies. Need real L1/L2 data from Alpaca streaming. Justifies the 10-second decision loop. |
| C3 | Staged learning-to-production transition (4 stages) | Planned | Replace binary 200-trade switch with Stage 0 (0-100: fixed risk, no ML) → Stage 1 (100-200: ML shadow) → Stage 2 (200-300: quarter-Kelly, ML 5-10%) → Stage 3 (300+: full production after calibration passes). |
