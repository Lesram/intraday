# Deep Research & Audit of Intra Organism Trading Engine

## Scope, sources, and what is now verifiably true

This audit targets the **Organism** intraday engine (“Intra”) as an autonomous/semi-autonomous 1-minute US equities trader (30-symbol universe) running on entity["company","Alpaca Markets","broker api provider"] paper trading, with ML-driven scanning, breakout detection, adaptive ATR exits, Kelly-based sizing, and (optionally) self-evolution. fileciteturn66file10

Evidence base used for this report:

- The unified decision-tree map: `docs/architecture/mapss.md` (“mapss.md”). fileciteturn66file10  
- The March 2–3 trading day report describing the pre/post-reset behavior and today’s failure patterns (`trading_report_2026.md`). fileciteturn45file0  
- The prior audit (“improve3”) that diagnosed the system as **return-horizon mismatched, entry-starved, learning-starved, and attribution-blind** (`improve3.md`). fileciteturn45file1  
- The tick scheduler that controls tick cadence (`backend/organism/scheduler.py`). fileciteturn66file3  

### Confirmed status of the March 3 “plumbing” fixes
Based on the March 3 report and the updated platform map, the prior audit’s “information plumbing” fixes were implemented (confidence propagation, exit attribution, gate telemetry, multi-bar horizon, and data sufficiency defenses). The **data quality** of post-reset trades is now materially better than pre-reset (no more constant fake confidence and fake exit reasons), which is why you can now see the system’s true decision behavior. fileciteturn45file0turn45file1turn66file10

That also means: **the remaining underperformance is now primarily strategy/decision-logic and parameter design**, not just missing metadata.

## Reconstructed cognitive decision process and why the engine behaves this way now

### The tick loop “brain” in plain English
Each tick is the single integrated loop below (exits always run; entries can be blocked). Tick cadence is configurable (code default 60s; production `.env` commonly 10s). fileciteturn66file10turn66file3

1. **Governance / warmup**  
   Entries are blocked for the first 5 ticks (warmup), and can later be blocked by manual halt, drawdown kill-switch, market-open block (9:30–10:00 ET), a “sit-out when everything is bearish” filter in high_vol/stress, and the **entries/hour throttle**. fileciteturn66file10  

2. **Data + features**  
   For each symbol, the engine computes ~79+ features (plus MTF features, depending on config), with a minimum-bar gate (intraday auto-adjusts MIN_BARS down to ~50). If too few symbols have usable features, entries block, but exit safety nets still run. fileciteturn66file10  

3. **Regime detection**  
   A single market regime is detected using a 3-tier priority: cross-asset (sector ETFs), SPY-based, then market aggregate. This regime is then used broadly for: exit parameter tables, alpha thresholding, and position sizing multipliers. fileciteturn66file10  

4. **Exit engine runs first**  
   For each open position, the adaptive exit engine checks (in priority order): max-loss safety net, hard stop, then (after a minimum hold gate) profit lock, partial TP, full TP, trailing stop, failure-to-follow, time-based exits, loser time stop, and stress tightening. fileciteturn66file10  

5. **Entry scanning and candidate formation**  
   - Breakout scanner produces breakout candidates.  
   - ML runs batch predictions and provides direction/confidence/predicted_return.  
   - Alpha scanner combines 7 factors and returns top-N candidates (typical N=3).  
   - Candidates pass multiple gates (already in position, cooldowns, sector cap, fitness, liquidity, etc.).  
   fileciteturn66file10  

6. **Confidence calculation (entry “conviction”)**  
   For alpha candidates that pass gates, blended confidence is additive:  
   `confidence = 0.50×ML_conf + 0.30×breakout_score + 0.20×tension` (bounded in [0,1]). fileciteturn66file10turn45file0  

7. **Sizing**  
   KellySizer applies a multi-step pipeline: direction/return sanity checks, half-Kelly, edge-over-cost gate, floors, drawdown scaling, vol targeting, regime scaling, confidence scaling, breakout bonus, then hard caps/minimums. fileciteturn66file10  

### What the March 3 post-reset day shows about current behavior
Post-reset (March 3), the engine placed **3 entries early**, then became effectively inert because of the **3/hour throttle**, with tiny position sizes, low confidence, and uniform exits. fileciteturn45file0turn66file10

Those 3 trades were winners but extremely small:
- entity["company","Salesforce","crm software company"]: 3 shares, +$0.19  
- entity["company","Palantir Technologies","enterprise software company"]: 3 shares, +$0.80  
- entity["company","Walmart","us retail company"]: 10 shares, +$0.90  
All three exited with the same reason: `failure_to_follow`. fileciteturn45file0  

The report also shows why confidence was low: ML contribution to alpha was near-zero, so breakout/momentum drove selection, producing blended confidence values around 0.09–0.14. fileciteturn45file0turn66file10

## Critical findings blocking “normal operation” and scalable profitability

### The engine is still structurally time-mismatched between ML horizon and exit timing
You run **1-minute bars** (LIVE_TIMEFRAME = 1Min in production), but the tick loop is often configured at **10 seconds**. The exit engine’s key time mechanics (including the profit-exit suppression gate `MIN_HOLD_BARS_PROFIT = 18`) are explicitly described as “~3 min @10s ticks,” meaning the engine is **counting tick-calls, not 1-minute bars, as its ‘bars held’.** fileciteturn66file10

At the same time, the ML “prediction horizon” used operationally is described as **H=15 bars ahead for 1Min** (i.e., ~15 minutes). Exiting systematically after ~3 minutes is therefore **functionally inconsistent** with the horizon you’re asking the ML model to predict. This is visible in the March 3 behavior: entries at ticks ~37–41 and exits ~18–19 ticks later (~3 minutes), far shorter than a 15-minute forecast horizon. fileciteturn45file0turn66file10

**Why it matters**: even if ML and alpha were perfect, you are cutting trades before the modeled edge horizon can express. This will force the strategy into a “micro-scalp” behavior with tiny expectancy, dominated by spread/slippage/noise.

### “Failure_to_follow” is acting as a deterministic, first-profit-exit trigger
The map makes it explicit: after profit exits are allowed (post MIN_HOLD), `failure_to_follow` checks whether a position has achieved **0.5R** by a progress checkpoint; if not, it exits. fileciteturn66file10

On March 3:
- All 3 trades were winners but small.
- All exited via `failure_to_follow`.
- Holding time was ~3 minutes (first moment profit exits are allowed).  
fileciteturn45file0turn66file10

This pattern indicates `failure_to_follow` is currently functioning less as a nuanced “stall detection” rule and more as a **tight latency requirement**: “If you didn’t immediately move enough, we exit.” That is often incompatible with:
- choppy/high_vol regimes (where follow-through is slower), and
- any forecast horizon > a few minutes. fileciteturn45file0turn66file10

### Entry starvation is now dominated by the throttle gate, not by “missing opportunities”
The platform map describes an explicit throttle: **3 entries per rolling hour**. Once you place 3 orders, entries remain blocked until one falls out of the 3600s window. fileciteturn66file10

Your March 3 run matches this exactly: the system fired 3 entries early, then was effectively “done” for the hour. fileciteturn45file0

This is appropriate as a safety device once a profitable strategy exists. It is **counterproductive when you are still trying to learn, calibrate, validate ML, or collect enough post-fix outcomes**.

### Kelly sizing is currently structurally conservative in the exact scenario you’re in
In the current design, your position sizing is suppressed by multiple multiplicative factors, several of which are particularly harsh during a cold start / low-confidence regime:

- **Vol targeting** uses annualization on intraday bars: `ann_vol = std(returns) × √(252×bars_per_day)` and then `vol_scale = 0.15 / ann_vol`. With 1-minute bars (bars_per_day≈390), this commonly yields vol_scale well below 1.0, shrinking size significantly. fileciteturn66file10  
- **Regime scaling** in chop/high_vol further shrinks size (typical 0.5–0.8). fileciteturn66file10  
- **Confidence scaling** begins at 0.3 and only rises meaningfully with higher confidence; your confidence was ~0.09–0.14. fileciteturn45file0turn66file10  
- The **edge-over-cost gate** requires predicted_return ≥ 2×spread_cost (3–50 bps). With a newly trained model and small predicted returns, many candidates will be rejected or floored into minimum notionals. fileciteturn66file10  

Result: the system can be “right” and still produce economically meaningless PnL, which is exactly what March 3 shows (+$1.89 total). fileciteturn45file0

### ML remains too weak (sample size + conditioning) to be used as a primary directional filter
The March 3 report states:
- ML trained during session with 79 features.
- Train window ~100 bars.
- ML contribution to alpha remained near-zero.
- Breakout and momentum dominated. fileciteturn45file0turn66file10

With data this limited, your ML direction filter can become a near-random gate:
- If it stays mostly HOLD (0), it suppresses alpha (map notes an ML-hold penalty in alpha scanning), starving entries. fileciteturn66file10  
- If it flips direction based on weak evidence, you risk taking trades with spurious direction + low confidence, pushing you into conservative sizes and fast `failure_to_follow` exits. fileciteturn45file0turn66file10  

## Moderate findings and key design tensions to resolve

### The system is mixing two incompatible “styles” without an explicit holding-period contract
Your strategy stack contains both:
- “Breakout / momentum” components (which can justify longer holds when trend is real), and
- a “must move immediately” exit rule (`failure_to_follow`) combined with short profit gating timing. fileciteturn66file10turn45file0  

Because there is no explicit “expected holding period” attached to a trade at entry, the exit engine can’t correctly choose whether to be patient (trend/trailing) or strict (scalp/fade).

### Single “market regime” applied to all 30 symbols is a blunt instrument
The engine computes one regime label used for sizing and exits across the whole universe. This is better than pure SPY-only, because the map documents cross-asset breadth conditioning, but it is still **one label for everything**. fileciteturn66file10  

In practice, a tech momentum breakout and an energy mean-reversion candidate can simultaneously be in different micro-regimes even when the market regime is “high_vol.”

### Telemetry retention is insufficient for serious post-mortems
Decision telemetry is stored in an **in-memory ring buffer** of ~360 ticks (~1 hour at 10s). That is not enough to audit a full trading day, correlate decisions with PnL, or build reliable supervision datasets. fileciteturn66file10

### WebSocket instability can silently corrupt decision quality even if the system “recovers”
The March 3 report documents repeated WebSocket disconnects and one tick that took **~710 seconds**, indicating either blocking I/O inside the tick or degraded asynchronous behavior. fileciteturn45file0  

Even if reconnect succeeds, a long-stalled tick can cause:
- stale features,
- mis-timed progress counters,
- delayed exits,
- and “phantom momentum” signals after reconnect.

## Prioritized recommendations with concrete code/config changes

The recommendations below are ordered by expected impact on (a) getting the engine to behave “normally,” then (b) enabling scalable profitability. None of these can guarantee extreme returns; they are required to stop self-sabotaging behaviors and to make the learning loop coherent.

### Align time units across ML, exits, and tick cadence
**What to change**
- If you trade on **1-minute bars**, set `ORGANISM_TICK_INTERVAL_SECONDS=60` for the OrganismScheduler. fileciteturn66file3turn66file10  
- If you insist on 10-second ticks for responsiveness, split the tick loop into:
  - **Bar-tick (1Min)**: feature refresh, ML predict/train, alpha scan, entry decisions, and **incrementing bars_held**.
  - **Risk-tick (10s)**: fast exit safety checks using quotes (stop/max-loss), *without* advancing “bars held.”

**Where**
- Tick cadence: `backend/organism/scheduler.py` (`ORGANISM_TICK_INTERVAL_SECONDS`). fileciteturn66file3  
- “Bar vs tick semantics”: `backend/organism/live_engine.py` exit loop + exit levels bookkeeping. fileciteturn66file0turn66file10  

**Why it matters**
This fixes the foundational contradiction: predicting a 15-minute edge while exiting at the first 3-minute checkpoint. It will also stabilize retrain cadence (“ticks between retrains”) and any gate keyed to tick counts. fileciteturn45file0turn66file10

**Risk**
- Medium: reducing tick frequency could delay stop execution unless you keep a separate quote-based risk-tick.

**Complexity**
- Medium if you only set tick_interval=60.  
- Large if you implement a true two-loop architecture.

### Redesign `failure_to_follow` to be horizon-aware and regime-aware
**What to change**
Replace the current “0.5R by the early checkpoint” with a rule that depends on:
- the trade’s **expected holding horizon** (derived from ML horizon and/or breakout type),
- the current regime, and
- the trade’s expected move size (e.g., predicted_return in ATR units).

Concrete directional change options (choose one):

1) **Disable failure_to_follow until a minimum fraction of ML horizon has passed**  
   - Example: do not evaluate failure_to_follow until `bars_held >= max(0.5×H, 10)` *in 1-minute bars*.  
2) **Make target R smaller in chop/high_vol**  
   - Example: require only 0.25R in chop/high_vol, and 0.5R in trending_up/low_vol.  
3) **Only apply failure_to_follow when predicted edge is large enough**  
   - Example: if expected move < 1 ATR, do not require 0.5R follow-through.

**Where**
- Exit logic: `backend/organism/adaptive_exits.py` (failure-to-follow section and constants). fileciteturn66file10  
- Exit-level creation: if needed, store predicted_return on exit levels so the exit engine can use it later. (Current map shows predicted_return is used to create exits, but failure_to_follow is not conditioned on it.) fileciteturn66file10  

**Why it matters**
Right now, failure_to_follow is producing consistent “small win, fast exit” behavior and identical exit attribution, which strongly suggests it’s too aggressive for your environment and currently dominates all profit exits. fileciteturn45file0turn66file10

**Risk**
- Medium: loosening can increase drawdowns if stops are not robust.

**Complexity**
- Small to medium (parameter/rule change).  
- Medium if you add horizon/predicted_return conditioning properly.

### Replace entry throttle with a learning-mode throttle and a production-mode throttle
**What to change**
- Add a “learning mode” (paper / post-reset) throttle of **8–12 entries/hour**, plus portfolio exposure caps.  
- Keep production throttle lower, but make it *dynamic*:
  - throttle based on number of open positions, realized volatility, and recent drawdown rather than a hard count of “3/hour.”

**Where**
- Entry throttle is documented in the entry gates (map) and implemented in the engine gate logic. fileciteturn66file10turn66file0  

**Why it matters**
Your March 3 day demonstrates that the engine can “use up” its day in a burst of 3 entries, then spend the rest of the hour doing nothing. That is not a viable learning loop and will delay calibration for weeks. fileciteturn45file0turn66file10

**Risk**
- Medium: more trades can increase churn/costs; mitigate with strict notional caps and drawdown kill.

**Complexity**
- Small if it’s only config + conditional logic.

### Make ML a veto in cold-start, not the primary directional gate
**What to change**
In cold-start (low sample,low accuracy), do not let ML direction (BUY/SELL/HOLD) dominate whether the system can trade:

- Use breakout scanner direction / price action direction to set trade direction.
- Use ML only to **block** trades when it strongly disagrees with high confidence (veto), rather than to require ML direction to be non-zero.

**Where**
- Candidate formation: Alpha scanning + candidate gating in `backend/organism/live_engine.py` and `backend/organism/alpha_scanner.py`. fileciteturn66file0turn66file10  

**Why it matters**
Your March 3 report says ML contribution was near-zero, and trades were driven by breakout/momentum. This is fine—but it’s dangerous for ML to remain a gating dependency when it is not yet informative. fileciteturn45file0turn66file10

**Risk**
- Medium: can increase false positives. Mitigate with tighter breakout-quality gates and risk controls.

**Complexity**
- Medium.

### Fix the sizing philosophy: stop using noisy “last-60-bar unconditional returns” as the primary Kelly fallback
**What to change**
The current fallback Kelly (`mean(dir_returns)/var(dir_returns)`) over a short recent window is a poor proxy for edge. Replace with one of:

1) **Signal-based Kelly approximation**  
   - `kelly ≈ μ / σ²`, where μ is predicted_return and σ estimated from ATR/realized vol.  
2) **Bayesian win-rate Kelly with priors**  
   - Use Beta priors for win rate and conservative payoff priors, stratified by signal type/regime, so early trades don’t collapse sizing to near-zero or explode to caps.

Also: remove the “breakout bonus disabled when ML untrained” behavior in learning mode—this is exactly when breakout signals should be allowed to size up *modestly* (still under caps). fileciteturn66file10  

**Where**
- `backend/organism/kelly_sizer.py` (Kelly fallback + scaling interactions). fileciteturn66file10  

**Why it matters**
Your current system can be right but still make no money because the multiplicative shrink factors reduce notional to the minimums. For learning, you need consistent, interpretable bet sizing so you can evaluate exits and entries meaningfully. fileciteturn45file0turn66file10

**Risk**
- Medium to high: sizing changes can materially increase drawdowns if edge is not real.

**Complexity**
- Medium to large, depending on the approach.

### Add an explicit “holding period contract” to each trade and condition exits on it
**What to change**
When a trade is entered, attach an “expected hold type”:
- `scalp` (minutes), `intraday_trend` (tens of minutes), `swing` (hours), etc.

Then condition:
- `MIN_HOLD_BARS_PROFIT`
- trailing activation
- failure_to_follow thresholds
- time-stop behavior

based on that hold type.

**Where**
- Entry metadata structure and exit-level creation in `backend/organism/live_engine.py` + `adaptive_exits.py`. fileciteturn66file0turn66file10  

**Why it matters**
Without this, you will continue mixing “trend-style entries” with “scalp-style exits,” producing persistent early exits and low expectancy even if direction is correct.

**Risk**
- Medium: requires calibration and can increase overnight risk if misused (but you can still enforce day-only exits).

**Complexity**
- Medium.

### Persist decision telemetry and rejection reasons to the database
**What to change**
Write these to DB tables (or append-only files) per tick:
- Filtering summaries (gate reject counts),
- top-K candidate diagnostics (confidence, breakout_score, predicted_return, edge-over-cost pass/fail),
- exit decisions and reasons.

**Where**
- `backend/organism/decision_telemetry.py` and its API endpoints. fileciteturn66file10  

**Why it matters**
A 1-hour in-memory ring buffer makes it impossible to build reliable post-mortems and supervised learning datasets. You currently cannot answer “what gate dominated entry starvation for 6 hours” without running live observation. fileciteturn66file10

**Risk**
- Low to medium (storage and performance; mitigate with sampling/top-K-only persistence).

**Complexity**
- Medium.

### Treat WebSocket stalls as a first-class trading risk, not just an infra hiccup
**What to change**
- Add per-call timeouts at the lowest level for market data reads (not just at scheduler wait_for).  
- Detect and mark ticks as **stale** when data age crosses a threshold, and suppress entry logic on stale ticks (but still allow reduce-only exits).

**Where**
- The system already uses scheduler-level timeouts and has streaming stale detection; expand to cover blocking REST calls and any synchronous calls in the tick loop. fileciteturn66file3turn66file10turn45file0  

**Why it matters**
A tick that lasts hundreds of seconds can invalidate every “bars held” and “progress” metric and can cause incorrect follow-through exits or delayed stops. fileciteturn45file0

**Risk**
- Low to medium.

**Complexity**
- Medium.

## Corrected decision tree diagram and how to validate the fixes

### Corrected high-level decision tree
The main structural correction is to separate **bar-based cognition** from **tick-based risk checks**, and to condition exits on a holding-period contract.

```text
                           ┌───────────────────────────────┐
                           │   Scheduler tick (every 10s)   │
                           └───────────────┬───────────────┘
                                           │
                                   ┌───────▼────────┐
                                   │ Risk Tick Loop  │
                                   │ (quote-based)   │
                                   └───────┬────────┘
                                           │
                   ┌───────────────────────┴────────────────────────┐
                   │ Always: max-loss, hard stop, broker safety net  │
                   │ (NO "bars_held" increment here)                 │
                   └───────────────────────┬────────────────────────┘
                                           │
                         if new 1-min bar closes (bar boundary)
                                           │
                           ┌───────────────▼───────────────┐
                           │       Bar Tick Loop (1m)       │
                           └───────────────┬───────────────┘
                                           │
       ┌───────────────────────────────────┼───────────────────────────────────┐
       │                                   │                                   │
┌──────▼──────┐                    ┌───────▼────────┐                  ┌──────▼──────┐
│ Features +   │                    │ Regime (market │                  │ Governance   │
│ ML predict    │                    │ + sector/per-  │                  │ gates +      │
│ /train (1m)   │                    │ symbol)        │                  │ throttle(LM) │
└──────┬──────┘                    └───────┬────────┘                  └──────┬──────┘
       │                                   │                                   │
       └───────────────┬───────────────────┴───────────────┬───────────────────┘
                       │                                   │
               ┌───────▼────────┐                  ┌───────▼────────┐
               │ Exit Engine     │                  │ Entry Engine    │
               │ (increment      │                  │ Alpha/Breakout  │
               │ bars_held by 1) │                  │ + ML veto        │
               └───────┬────────┘                  └───────┬────────┘
                       │                                   │
        ┌──────────────▼──────────────┐        ┌───────────▼──────────────────┐
        │ Exits conditioned on hold    │        │ Size conditioned on signal   │
        │ contract + regime + horizon  │        │ type + risk model (not raw   │
        │ (failure_to_follow revised)  │        │ unconditional returns)        │
        └──────────────┬──────────────┘        └───────────┬──────────────────┘
                       │                                   │
                   ┌───▼────┐                         ┌────▼─────┐
                   │ Submit   │                         │ Submit    │
                   │ reduce-  │                         │ entries   │
                   │ only exits│                        │ (learning)│
                   └──────────┘                         └───────────┘
```

### Validation plan that directly answers “what do we do next”
To ensure the above fixes actually increase profitability *and* eliminate current self-sabotage patterns, validate in this order:

1) **Time coherence tests**  
   - Prove that “bars_held” equals *1-minute bars held* (not 10s ticks) when LIVE_TIMEFRAME=1Min.  
   - Prove ML horizon H=15 implies expected hold staging (not triggering failure_to_follow at 3 minutes). fileciteturn66file10turn45file0  

2) **Exit attribution distribution**  
   - A healthy system does not produce 100% of exits from a single reason on a normal day unless explicitly in a “scalp-only mode.” Your current distribution is dominated by `failure_to_follow`. That should change after the redesign. fileciteturn45file0turn66file10  

3) **Entry activity without losing safety**  
   - In learning mode, increase entries/hour and confirm you collect enough post-fix trade outcomes to calibrate ML and exits within days, not weeks. fileciteturn45file0turn66file10  

4) **Sizing sanity checks**  
   - For a fixed confidence and breakout_score bucket, position sizes should cluster and be explainable (not erratic due to noisy Kelly fallback). fileciteturn66file10  

If you implement only one “next” change: **fix the time-unit mismatch first**. Until timing is coherent, every other tweak (confidence weights, thresholds, Kelly tuning) will remain ambiguous because the system is not actually operating on the horizon it models. fileciteturn45file0turn66file10