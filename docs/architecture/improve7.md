# Forensic Deep Audit of the Intra Organism Trading Engine — March 4, 2026 Session

## Executive summary

- **FTF is still structurally harming expectancy**: even after the mid‑day redesign and disabling it in `high_vol`, `failure_to_follow` remains **58% of all exits (31/53)** and is **net −$80.92**, making it the largest avoidable drag. fileciteturn73file1turn73file0  
- **Your edge today was “patience + trend capture,” not “fast follow-through”**: the day’s P&L is dominated by **max_holding_period (+$364.21)** and **trailing_stop (+$65.69)** exits; these are the only exit modes that reliably monetized moves. fileciteturn73file1turn73file0  
- **Entry selection is still too permissive in chop**: overall win rate is **37.7% (20/53)**. That can be fine if the system consistently produces a few large winners—but right now it also produces many “low-quality” churn trades that FTF exits at a loss. fileciteturn73file1  
- **Sizing is behaving like “near-constant notional,” not conviction sizing**: your position notionals today cluster tightly (most trades are around the same ~$5k entry notional), implying the **learning-mode risk-budget floor and caps are dominating**, reducing differentiation between strong vs weak signals. That defeats the purpose of the sophisticated Kelly stack. fileciteturn73file0turn73file1  
- **A major forensic blocker remains**: you still do not persist enough per-trade metadata to answer the questions you asked (entry source alpha vs breakout, regime at entry vs exit, MFE/MAE). The map describes the lifecycle and telemetry but today’s day report cannot support true forensic causality on a per-trade basis—this is now a P0 observability gap. fileciteturn73file0turn73file1  

## Trade-by-trade forensics

### What can be proven from the 53 trades

- **Total realized P&L**: +$154.66 on 53 completed trades. fileciteturn73file1  
- **Two phases** (because of two intra-day hotfixes): Phase 1 (26 trades, +$97.28), Phase 2 (27 trades, +$57.38). fileciteturn73file1  
- **Exit distribution changed materially after the hotfix** (first appearance of trailing and take-profit exits; lower average loss), confirming the fixes were directionally correct. fileciteturn73file1turn73file0  

### What you cannot currently prove (and must start recording)

Your prompt requested, for every trade:
- entry source (alpha/breakout/both),
- regime at entry and at exit,
- max favorable excursion (MFE) vs realized exit,
- whether a “hold longer” counterfactual would have helped.

**Those fields are not present in the March 4 day report**, and the platform map does not specify that these are persisted into `TradeRecord` and then into daily reporting. As a result, any “held longer” conclusion per trade would be guesswork. This is a structural gap, not an analyst gap. fileciteturn73file1turn73file0  

### Full trade ledger and forensic verdict tags

Below is the complete list of the 53 completed trades (from the day report). I’m adding an evidence-based “forensic tag” that is strictly grounded in **exit reason + confidence + repetition patterns** (not in unobserved MFE). fileciteturn73file1  

**Legend for forensic tags**
- **FTF-churn**: FTF exit in chop conditions; strongest candidate for redesign (not necessarily “wrong exit,” but empirically value-destroying at scale today).
- **Stop-loss sound, entry suspect**: stop-loss is doing its job; the upstream entry signal quality/timing is suspect.
- **Winner-patience**: winner produced by “patience exits” (max_hold / trailing / TP); preserve.
- **Overtrade risk**: same symbol repeatedly traded with mixed/negative outcome; needs per-symbol throttles.
- **Manual close leakage**: `live_close` = process/automation weakness; should not exist for an intraday organism.

| # | Symbol | Exit reason | P&L | Confidence | Verdict tag |
|---:|---|---|---:|---:|---|
| 1 | CRM | failure_to_follow | +0.19 | 0.14 | FTF-churn (win, but tiny; not scalable) |
| 2 | PLTR | failure_to_follow | +0.80 | 0.12 | FTF-churn (win, but tiny; overtrade risk later) |
| 3 | WMT | failure_to_follow | +0.90 | 0.09 | FTF-churn (win, but tiny) |
| 4 | PLTR | live_close | -3.76 | 0.33 | Manual close leakage + overtrade risk |
| 5 | NFLX | failure_to_follow | -33.35 | 0.66 | FTF-churn + **signal selection failure** (high conf, big loss) |
| 6 | AVGO | failure_to_follow | +7.38 | 0.64 | FTF-churn winner (but later erased by stops) |
| 7 | AMD | failure_to_follow | -21.28 | 0.60 | FTF-churn loser (high conf, wrong) |
| 8 | TSLA | failure_to_follow | +3.31 | 0.51 | FTF-churn (small win) |
| 9 | MU | failure_to_follow | +8.13 | 0.25 | FTF-churn (small win; MU volatility flagged later) |
| 10 | PLTR | failure_to_follow | +7.17 | 0.43 | FTF-churn + overtrade risk |
| 11 | INTC | failure_to_follow | 0.00 | 0.57 | FTF-churn (dead trade) |
| 12 | IWM | failure_to_follow | -7.11 | 0.35 | FTF-churn loser |
| 13 | AVGO | stop_loss | -26.48 | 0.29 | Stop-loss sound, entry suspect |
| 14 | QQQ | failure_to_follow | +12.80 | 0.63 | FTF-churn winner (good) |
| 15 | AAPL | failure_to_follow | -9.00 | 0.56 | FTF-churn loser |
| 16 | MU | stop_loss | -43.31 | 0.24 | Stop-loss sound, MU timing suspect |
| 17 | XOM | stop_loss | -11.88 | 0.43 | Stop-loss sound, **symbol structurally bad today** |
| 18 | CRM | failure_to_follow | -9.18 | 0.44 | FTF-churn loser |
| 19 | ABNB | failure_to_follow | -3.48 | 0.25 | FTF-churn loser |
| 20 | COIN | max_holding_period | +242.14 | 0.66 | **Winner-patience** (core edge) |
| 21 | AMZN | max_holding_period | +72.57 | 0.35 | **Winner-patience** |
| 22 | PLTR | live_close | -29.05 | 0.27 | Manual close leakage + overtrade risk |
| 23 | AMZN | stop_loss | -27.12 | 0.39 | Stop-loss sound, re-entry timing suspect |
| 24 | MU | stop_loss | -25.76 | 0.49 | Stop-loss sound, MU re-entry suspect |
| 25 | UBER | failure_to_follow | -2.15 | 0.34 | FTF-churn loser |
| 26 | TSLA | failure_to_follow | -5.20 | 0.41 | FTF-churn loser |
| 27 | ADBE | failure_to_follow | -5.23 | 0.61 | FTF-churn loser **(repeat pattern)** |
| 28 | AVGO | stop_loss | -15.04 | 0.60 | Stop-loss sound, AVGO direction unstable |
| 29 | NVDA | failure_to_follow | +2.31 | 0.46 | FTF-churn (small win) |
| 30 | SNOW | stop_loss | -7.75 | 0.90 | Stop-loss sound, but **ML/confidence misfire** |
| 31 | XLE | failure_to_follow | +0.48 | 0.32 | FTF-churn (tiny) |
| 32 | MSFT | stop_loss | -7.94 | 0.18 | Stop-loss sound, low-conf entry should be blocked |
| 33 | MU | failure_to_follow | -3.77 | 0.42 | FTF-churn loser |
| 34 | PLTR | max_holding_period | +49.50 | 0.50 | Winner-patience + overtrade risk |
| 35 | XOM | live_close | -10.50 | 0.22 | Manual close leakage + symbol bad today |
| 36 | SNOW | trailing_stop | +66.72 | 0.56 | Winner-patience (trail worked) |
| 37 | TSLA | stop_loss | +5.28 | 0.57 | Stop-loss winner (profit-lock behavior working) |
| 38 | MSFT | failure_to_follow | -18.55 | 0.59 | FTF-churn loser (high conf, wrong) |
| 39 | AMZN | failure_to_follow | +2.35 | 0.61 | FTF-churn (small win) |
| 40 | PLTR | failure_to_follow | -23.14 | 0.62 | FTF-churn loser + overtrade risk |
| 41 | COIN | failure_to_follow | -12.92 | 0.63 | FTF-churn loser **post-big-win re-entry** |
| 42 | META | failure_to_follow | -13.97 | 0.48 | FTF-churn loser |
| 43 | CRM | failure_to_follow | -4.03 | 0.42 | FTF-churn loser |
| 44 | PLTR | failure_to_follow | -2.55 | 0.56 | FTF-churn loser + overtrade risk |
| 45 | XLE | take_profit | +23.20 | 0.58 | Winner-patience (TP finally fired) |
| 46 | UBER | stop_loss | -6.65 | 0.52 | Stop-loss sound, symbol weak today |
| 47 | COIN | failure_to_follow | +2.28 | 0.57 | FTF-churn small win |
| 48 | ABNB | trailing_stop | -4.68 | 0.58 | Trail fired but still lost (market-order slip / reversal) |
| 49 | XLE | trailing_stop | +3.85 | 0.34 | Trail small win |
| 50 | XOM | stop_loss | -7.56 | 0.49 | Stop-loss sound, symbol bad today |
| 51 | MU | failure_to_follow | +51.87 | 0.42 | FTF-churn **but winner** (evidence FTF isn’t purely bad; it’s poorly targeted) |
| 52 | COST | trailing_stop | -0.20 | 0.67 | Trail near-flat (noise trade) |
| 53 | ADBE | failure_to_follow | -5.98 | 0.57 | FTF-churn loser **(repeat pattern)** |

**Pattern, stated bluntly:** a large share of your book is still “FTF-churn noise trades” that you either should not enter or should manage with *stop tightening*, not forced exits. The day’s edge came from a small subset of “let it mature” trades. fileciteturn73file1turn73file0  

## Exit system effectiveness

### Failure-to-follow (FTF)

**Evidence**
- Full day: FTF = **31/53 exits (58%)**, net **−$80.92**. fileciteturn73file1  
- Phase 2: FTF reduced from 65% → 52% after the redesign, and per-trade damage decreased, but it remains net-negative. fileciteturn73file1  
- Your mid-day fix added:  
  - wall-clock bar detection,  
  - momentum confirmation via prior-bar price storage,  
  - regime adjustments (FTF disabled in high_vol, thresholds lowered). fileciteturn73file1turn73file0  

**Root cause (structural)**
FTF is currently acting as a **primary exit mode in chop**, but your realized edge today in chop/high-vol conditions was not “fast follow-through”—it was “rare but meaningful intraday extensions” captured by time/trailing exits. That makes FTF fundamentally misaligned with your actual payoff distribution. fileciteturn73file1turn73file0  

**What to do (concrete change)**
In `backend/organism/adaptive_exits.py`, change FTF from “exit engine” → “risk management modifier” in chop:

- **Chop regime**:  
  - Keep the *signal* (“this isn’t following through”), but **do not flatten winners**.  
  - If PnL is ≤ 0 and momentum is negative for multiple bars → exit (FTF as loser killer).  
  - If PnL is > 0 but under-threshold → **tighten stop**, don’t exit (convert to `ftf_stop_tighten` event).

This directly targets the mechanism that is destroying value while preserving the protective benefit.

### Trailing stops

**Evidence**
- Phase 2 produced 4 trailing_stop exits (+$65.69 net), including the day’s third-largest win (SNOW +$66.72). fileciteturn73file1  
- The platform map shows trailing activates intraday at ~2×ATR excursion and then ratchets. fileciteturn73file0  

**Verdict**
Trailing is the correct direction. The reason you only saw 4 is not necessarily “activation too high”; it’s that many trades never survive long enough (FTF) or are never good enough (entry quality). Fix entry filtering and FTF targeting first; trailing frequency will rise naturally. fileciteturn73file1turn73file0  

### Take-profit

**Evidence**
Only 1 take_profit fired all day (XLE +$23.20). fileciteturn73file1  
The map shows regime-dependent TP multiples (higher in trending regimes, lower in chop/stress). fileciteturn73file0  

**Verdict**
Take-profit is not a critical lever right now. Your profitable exits are time/trailing; full TP rarely fires because (a) regimes are mostly chop/high_vol and (b) your system is exiting earlier for other reasons. Keep TP, but don’t chase it as the fix for today’s P&L. fileciteturn73file1turn73file0  

### Max holding period

**Evidence**
- Max holding period exits are only 3 trades but contribute **+$364.21** total. fileciteturn73file1  

**Verdict**
This is the strongest evidence on the entire page: **your organism’s edge is currently being realized only when it waits.** You should treat this not as a “crutch,” but as **the correct profit-capture mode** until proven otherwise—then evolve more sophisticated exits around it. fileciteturn73file1turn73file0  

### Time decay, loser time-stop, min-hold

The map describes these mechanisms (time-decay stop tightening, loser time-stop fallback, min-hold gating), but none of them show up distinctly in the day’s exit taxonomy, meaning they are not the primary drivers of today’s outcomes. fileciteturn73file0turn73file1  
You should not tune them yet; first fix the components that actually dominate outcomes (FTF and entry filters).

## Entry quality

### The win/loss geometry is “few big winners,” but the organism is still taking too many low-quality bets

**Evidence**
- Full day win rate is ~37.7% with payoff ratio reported ~2.27:1. fileciteturn73file1  
- Today’s P&L is concentrated: COIN +$242, AMZN +$73, SNOW +$67, MU +$52, PLTR +$50. fileciteturn73file1  

This is a viable style **only if you ensure losers stay contained AND you avoid bleeding on “noise trades.”** Right now, you are bleeding through FTF churn and repeated re-entries into the same symbols in chop.

### The single most actionable entry insight from the data you *do* have: blended confidence is already a quality separator

Your day report includes trade-level blended confidence. Even without entry-source tags, this field is forensic gold.

From the 53 trades:
- Trades with **confidence ≥ 0.50** are **net positive** (+$248.64), while trades with **confidence < 0.50** are **net negative** (−$93.98). fileciteturn73file1turn73file0  
- That means a simple confidence-based gate would have materially improved the day—even before smarter modeling. fileciteturn73file1turn73file0  

**Root cause (design)**
Your current pipeline uses confidence mainly for sizing; it still admits many medium/low-confidence trades in chop that do not express edge. fileciteturn73file0turn73file1  

**Fix**
In `backend/organism/live_engine.py` candidate filtering, add:

- **Main-book confidence gate**: require `blended_confidence >= 0.30` (or 0.35 in chop).  
- Below that: route to **exploration** (micro-size) rather than normal sizing, so you still learn but stop losing meaningful dollars on low-conviction trades. The map already contains an exploration bucket design specifically for this. fileciteturn73file0  

### Symbol-level pathology and overtrading

**Evidence**
Some symbols are clearly structurally bad *today*:
- XOM: 3 trades, **all losers**, net −$29.94. fileciteturn73file1  
- MSFT: 2 losers, net −$26.49. fileciteturn73file1  
- AVGO: net −$34.14 on 3 trades. fileciteturn73file1  
- PLTR: 7 trades, net ~−$1.03 (high churn). fileciteturn73file1  

**Fix**
Add an intraday **symbol circuit breaker** (in live_engine gating):
- If symbol’s intraday realized P&L ≤ −$15 OR ≥ 2 consecutive losing round-trips → **ban new entries in that symbol for the rest of the session**.
This is what a real systematic desk does to stop “death by a thousand cuts” in chop.

## Kelly sizing and risk analysis

### What position sizing looked like today

**Evidence**
The report shows wide variation in shares, but **position notionals are surprisingly clustered** (many entries are ~$5k notional), with occasional larger (~$9k) positions on the biggest winner. fileciteturn73file1turn73file0  
The map explains why: when in learning mode (<200 trades), you apply a **risk-budget floor** after Kelly, plus regime scales, confidence scaling, caps, and min notional gates. fileciteturn73file0  

### Critical sizing flaw: the risk-budget floor is likely dominating Kelly differentiation

If most trades converge to a similar notional, that implies:
- Kelly edge estimates are not differentiating candidates enough, **or**
- even when Kelly would size smaller, the **risk-budget floor overrides** and pushes size up to a common baseline, and caps then limit the upside.

This produces a “sophisticated pipeline” that in practice behaves like **fixed-fraction sizing**.

**Why that matters**
- You lose the very thing you need to become a high-return system: **conviction sizing**.
- You also mislead yourself: the platform looks like it’s reacting to ML/breakout nuance, but P&L behavior reflects a simpler sizing regime.

**Fix (specific logic change in `backend/organism/kelly_sizer.py`)**
Change the learning-mode floor from:

- `target_weight = max(kelly_target, risk_budget_weight * dd_scale)` fileciteturn73file0  

to:

- `target_weight = max(kelly_target, risk_budget_weight * dd_scale * confidence_floor_scale)`

where `confidence_floor_scale` is something like:
- `0.5 + 0.8 * blended_confidence`, capped to `[0.5, 1.1]`.

This keeps the floor’s purpose (avoid microscopic trades) but stops it from forcing near-constant sizing on mediocre setups.

### Regime scales may currently be suppressing too much in the regimes you actually trade

**Evidence**
The map and the day report show that regimes were predominantly chop/high_vol, and your evolved regime size scales are already reduced (chop ~0.485, high_vol ~0.70, stress ~0.30). fileciteturn73file1turn73file0  

With only 53 trades total in a fresh learning run, “evolved” regime scales are not statistically stable. This can easily drift you into under-sizing or mis-sizing.

**Fix**
Freeze regime scale evolution until you have at least:
- 200+ clean trades overall, and
- 30+ trades in each of the major regimes you actually see.

## Regime detection and regime response

### Dominant regime behavior

**Evidence**
March 4 was mostly chop/high_vol; no meaningful trending_up/low_vol periods were detected, which is why the “FTF disabled in trending_up/low_vol” logic had limited effect. fileciteturn73file1turn73file0  

### The uncomfortable possibility: your regime classifier may be under-detecting “trend” intraday

Your biggest winners (especially COIN and the strong SNOW trail) look like trend extensions, yet the day regime headline is “chop/high_vol.” That can be true (trend extensions happen inside volatile chop), but it also may indicate the “trend slope” thresholds are not calibrated to 1‑minute structure. The map shows intraday threshold scaling is applied to some signals; if slope thresholds are effectively too strict, trending regimes will rarely trigger, leaving you stuck in chop logic. fileciteturn73file0turn73file1  

**Fix**
In `backend/organism/regime.py`, audit which regime signals are scaled for intraday and which are not, and bring the trend-detection thresholds onto comparable units with 1‑minute bars (the map already documents the intended scaling approach). fileciteturn73file0  

Practical effect: more accurate trending regime detection would (a) change exit parameters and (b) stop chop-mode logic (including FTF) from being applied during micro-trends.

## Structural and architectural issues

### Timing is much better post hotfix, but one subtle risk remains

**Evidence**
Phase 1 bar detection was delayed because it used the broker’s bar timestamps; Phase 2 switched to **wall-clock UTC minute boundaries**, restoring 1 bar/min consistency. fileciteturn73file1turn73file0  

**Residual risk**
If market data becomes stale (stream disruptions), wall-clock “new bar” events can advance bar-counters even when the underlying bar stream hasn’t truly updated. The map notes a stale-data entry block at 2 minutes and a streaming health system—but you should ensure the *exit bar logic* is also guarded from acting on stale inputs. fileciteturn73file0turn73file1  

### End-of-day exposure is contradicting “intraday-only”

**Evidence**
The day ended with 3 open positions carrying unrealized losses, which is why ending equity trailed the opening despite positive realized P&L. fileciteturn73file1  

**Fix**
Implement a hard “flatten into close” policy for the organism if the mandate is autonomous intraday trading:
- block new entries after ~3:30–3:45 ET,
- force close all open positions by ~3:58–3:59 ET,
- record reason `eod_flatten` so it doesn’t pollute “live_close.”

### You still lack per-trade causal provenance

Even with TickTelemetry, the day report cannot answer entry-source and MFE/MAE. The map describes rich telemetry structures and DB persistence every ~minute, but you are not promoting the most important forensic fields into the final trade records / day reports. fileciteturn73file0turn73file1  

This is why you keep “finding new issues” each audit: you’re rebuilding causality from partial traces.

## Specific recommendations

### Critical issues to fix before next session

**FTF mis-targeting and overuse**
- **Problem (evidence)**: FTF is still the top exit type and net-negative (31 exits, −$80.92). fileciteturn73file1  
- **Root cause**: FTF is being used as a generic exit in chop, but today’s winners require patience; FTF is not conditioned on entry source or expected holding style. fileciteturn73file0turn73file1  
- **Fix**:  
  - In chop: convert FTF to “tighten stop if green, exit if red + momentum negative over multiple bars.”  
  - Increase FTF delay in chop to closer to the prediction horizon (don’t judge a 15-bar thesis at 7 bars). fileciteturn73file0turn73file1  
- **Expected impact**: materially reduces churn losses and increases the probability that a subset of trades reach trailing/time exits (the only consistently profitable exits today). fileciteturn73file1  

**Confidence-based gating for main-book trades**
- **Problem (evidence)**: low-confidence trades (below ~0.5) are structurally negative today. fileciteturn73file1turn73file0  
- **Root cause**: confidence affects size but does not block low-quality entries. fileciteturn73file0  
- **Fix**: add `MIN_MAIN_CONF` gate (0.30–0.40 depending on regime), route below-threshold candidates to exploration micro-trades instead of full sizing. fileciteturn73file0  
- **Expected impact**: fewer negative-expectancy trades without starving learning (exploration bucket still collects data). fileciteturn73file0turn73file1  

**Intraday symbol circuit breaker**
- **Problem (evidence)**: repeated losses in specific names (XOM, AVGO, MSFT, repeated PLTR churn). fileciteturn73file1  
- **Fix**: per-symbol daily ban after 2 consecutive losers or −$15 intraday.  
- **Expected impact**: removes a large portion of “avoidable noise trades” that accumulate to meaningful drag.

**Hard end-of-day flatten**
- **Problem (evidence)**: 3 open positions at close reduced ending equity. fileciteturn73file1  
- **Fix**: enforce `eod_flatten` logic path in live_engine.  
- **Expected impact**: prevents overnight exposure and aligns realized P&L with equity curve.

### High priority improvements to implement this week

**Fix sizing domination by the learning-mode floor**
- **Problem**: sizing appears to converge toward a narrow band; Kelly differentiation is not expressing strongly. fileciteturn73file0turn73file1  
- **Fix**: scale the risk-budget floor by confidence and/or predicted edge instead of letting it override Kelly universally. fileciteturn73file0  
- **Expected impact**: restores conviction sizing; improves asymmetry (bigger wins on best trades).

**Add trade causal fields to TradeRecord and reporting**
- Add: `entry_source`, `regime_at_entry`, `regime_at_exit`, `MFE`, `MAE`, `bars_held_at_exit`, `time_in_trade_seconds`.  
- These already exist partially in state (exit levels track favorable excursion; tick telemetry exists), but are not summarized per trade in the day report. fileciteturn73file0turn73file1  

**Regime classifier calibration audit**
- Validate that intraday trend detection thresholds produce reasonable time spent in trending regimes; otherwise you are effectively always in chop logic. fileciteturn73file0turn73file1  

### Medium priority optimizations

- Refine cooldowns to be exit-reason dependent (longer cooldown after stop_loss/FTF losses; shorter after profitable exits). fileciteturn73file0  
- Review order-entry slippage cap logic versus observed fill quality; add metrics for “submitted but not filled” counts for marketable limits. fileciteturn73file0turn73file1  

### Parameter recommendations table

All “current” values are from the platform map and the March 4 report; recommended values are tuned specifically to reduce today’s demonstrated failure modes. fileciteturn73file0turn73file1  

| Parameter / rule | Current | Recommended | Why |
|---|---:|---:|---|
| FTF enabled regimes | disabled in trending_up/low_vol/high_vol | keep | Phase 2 proved disabling in high_vol allowed trailing winners to emerge. fileciteturn73file1turn73file0 |
| FTF in chop | exit if below ~0.15R + momentum check | **do not exit winners**; exit only if PnL ≤ 0 and multi-bar momentum negative; otherwise tighten stop | Removes value destruction while retaining protection against stagnating losers. fileciteturn73file1turn73file0 |
| FTF delay (H=15) | ~7 bars | **chop: 12–15 bars** | Don’t judge a 15-bar thesis at 7 bars in chop; today’s edge needed time. fileciteturn73file0turn73file1 |
| Main-book confidence minimum | none | **0.30 (baseline), 0.35–0.40 in chop** | Today’s low-confidence trades were net-negative. fileciteturn73file1 |
| Exploration bucket | off | on (for sub-threshold confidence trades) | Keep learning without paying full-size losses on weak setups. fileciteturn73file0 |
| Risk-budget floor | hard max override | scale by confidence | Prevent near-constant notional sizing; restore differentiation. fileciteturn73file0turn73file1 |
| Confidence scaling cap (untrained) | 0.9 cap | keep | This is good; cold-start under-sizing was a prior failure mode. fileciteturn73file0turn73file1 |
| End-of-day policy | open positions can remain | force flatten by close (`eod_flatten`) | Aligns intraday mandate; avoids equity drift from unrealized EOD losses. fileciteturn73file1 |
| Per-symbol intraday ban | none | ban after 2 consecutive losses or −$15 | Stops repeated symbol-level bleeding seen in XOM/AVGO/MSFT. fileciteturn73file1 |

### Corrected decision tree adjustment

This is the minimal decision-tree change that fixes the demonstrated failure mode (FTF churn) without removing safety nets.

```mermaid
flowchart TD
  A[Open position] --> B{New 1-min bar?}
  B -->|No| C[Risk-only checks: max_loss, stop_loss]
  B -->|Yes| D[Run profit/time suite]

  D --> E{Min-hold met?}
  E -->|No| C
  E -->|Yes| F[Profit lock / partial TP / TP / trailing update]

  F --> G{Trailing active?}
  G -->|Yes| H[Skip FTF; trailing governs]
  G -->|No| I{FTF eligible? bars_held >= delay}

  I -->|No| J[Continue holding]
  I -->|Yes| K{Regime == chop?}

  K -->|No| L[Existing FTF logic (regime threshold + momentum)]
  K -->|Yes| M{PnL <= 0 AND multi-bar momentum negative?}

  M -->|Yes| N[Exit: failure_to_follow]
  M -->|No| O[Tighten stop (ftf_stop_tighten), do not exit]
  H --> P[Time-based profit exits / loser time-stop / time decay]
  J --> P
  L --> P
  N --> P
  O --> P
```

---

**One final blunt conclusion:** March 4 proves the organism is no longer “broken”—it is now **diagnosable** and occasionally captures real intraday extensions. But profitability is still too dependent on a few large winners, while FTF churn and symbol overtrading actively leak edge. Fixing FTF targeting, adding confidence gating + exploration routing, and enforcing symbol/day discipline are the fastest routes to turning this into a “normal, well-operating autonomous intraday system” that can then be scaled. fileciteturn73file1turn73file0