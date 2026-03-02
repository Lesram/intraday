# Audit of the INTRA Platform Trading Decision Tree and Profitability Levers

## Scope and evidence

This audit reconstructs the platform’s “trading brain” from the current **mapss.md** architecture/decision-tree document you provided, with emphasis on the **OrganismScheduler / OrganismLiveEngine** tick lifecycle: governance → data/features → regime → exits → entries → sizing → orders → learning. fileciteturn8file0L27-L43 fileciteturn8file4L32-L56

I could not directly inspect the rest of the repository’s source code in this environment (only the uploaded file is available), so I cannot *prove* that implementations match the document everywhere. Where the doc references specific modules and parameter values, I treat those as “design intent” and flag any internal inconsistencies or design choices that typically break profitability in live trading. fileciteturn8file4L32-L56 fileciteturn3file2L13-L41

External research used here is narrowly targeted: (a) Kelly sizing properties and failure modes, (b) volatility targeting evidence, (c) machine-learning backtest overfitting and leakage controls, and (d) broker order-type mechanics (especially IOC/FOK). citeturn2search0 citeturn0search1 citeturn2search1 citeturn5view0

## Reconstructed trading cognitive process

The document describes a deterministic “tick brain” that runs roughly every ~10 seconds, serializes itself with an async lock, and expires cooldown state each tick; it also performs a periodic stream health check. fileciteturn8file0L27-L43

Within each tick, there is a consistent ordering: (1) governance gate, (2) data acquisition + feature engineering, (3) regime detection, (4) portfolio/equity/drawdown, (5) exit decisions, and *only then* (6) pyramids + entry scan + sizing + entry submissions when entries are allowed. fileciteturn8file4L39-L56 fileciteturn8file0L1-L17

A critical structural point: **exit logic is designed to run even when entries are blocked**, i.e., the system prefers “always able to de-risk” over “always able to enter.” That is explicitly called out as a design insight and is the right high-level principle. fileciteturn8file0L23-L43

### Governance and “can I trade?” determination

Governance can block entries for: manual halt, drawdown kill switch with adaptive cooldown, adaptation freeze, and change budget exhaustion. Importantly, the governance “halt” semantics are *entries_blocked* rather than “stop all trading,” and exits should still run. fileciteturn8file1L49-L67 fileciteturn2file3L18-L36

Drawdown kill is described as firing at **8%** drawdown (production setting shown), after which the system blocks entries and applies cooldown scaling based on how far beyond the limit the drawdown went. fileciteturn2file3L21-L26 fileciteturn2file4L24-L30

### Market data and feature generation

The live engine fetches **SPY first** (cross-asset features dependency), then fetches bars per symbol (streaming fast path, REST fallback), enforces a minimum bars threshold (50 intraday), computes “79 features,” and applies a global NaN/Inf-to-zero safety net. fileciteturn2file0L29-L47

If fewer than three symbols produce usable features, entries are blocked for that tick (while exits can still proceed via broker price fallback paths). fileciteturn2file0L51-L53

### Regime inference and its role in decisions

Regime detection is three-tiered: cross-asset (sector ETF set), then SPY-based, then market aggregate fallback. It converts signals → softmax probabilities → EMA smoothing (α=0.3) → argmax label. fileciteturn4file3L26-L43 fileciteturn2file4L1-L6

The regime labels include `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown`. fileciteturn2file4L3-L6

Regime then conditions (a) position sizing multipliers and (b) exit parameterization (stop ATR multiple, TP multiple, trailing ATR multiple, max holding bars, etc.). fileciteturn5file1L17-L22 fileciteturn4file1L41-L49

### Exit decision tree

Exits are evaluated per open position, with explicit fallback behavior when features are missing or exit levels are missing (safety net max loss). fileciteturn4file0L1-L16

When normal evaluation is possible, exit logic is hierarchical: max-loss safety net (8%), hard stop loss, “profit lock” at 2R, partial take-profit at 3R (sell 30% + stop to breakeven), full TP, ATR trailing stop activation (3× ATR move), a “failure to follow through” condition tied to max bars, time-based profit exit, loser time-stop, time-decay tightening, and one-time stress-regime tightening; there is also a partial exit on ML signal reversal under certain conditions. fileciteturn4file0L15-L53 fileciteturn4file1L20-L31

Exit regimes include parameters where `trending_up` and `low_vol` show **∞ max bars**, whereas other regimes are finite (20–40 bars). fileciteturn4file1L41-L49

### Entry scan and candidate formation

Entry scanning is composed of: breakout scan (top-8), ML predictions, alpha scan (top-5), then a 7-gate filter funnel. fileciteturn6file0L2-L26

After passing gates, the doc states blended confidence is **additive** (0.50×ML confidence + 0.30×breakout + 0.20×tension) and explicitly notes that ML confidence is treated as **0.0 when no signal**, versus an older approach that apparently used 0.5. fileciteturn6file0L28-L35

The alpha composite is a weighted combination of seven factors (ML score, breakout, institutional, momentum, momentum quality, volume, regime alignment) with additional modifiers including a strong penalty when ML direction is HOLD (direction==0), plus symbol-fitness scaling and a stress-regime minimum composite increase. fileciteturn5file4L3-L20

The document also describes **PURE breakout additions** (not in alpha candidates) that force direction long and apply a **predicted_return floor = max(ml_return, 0.01)**, which becomes important later because predicted_return is used for “edge-over-cost” gating in the Kelly sizer. fileciteturn6file0L37-L44

A broad market “SPY < SMA(50)” long-entry gate exists but is currently disabled by `_spy_filter_enabled = False` per the document. fileciteturn6file0L50-L53

### Kelly sizing and risk scaling

Sizing is a multiplicative stack: half-Kelly × drawdown scaling × volatility targeting × regime scaling × confidence scaling × breakout bonus. fileciteturn5file0L39-L46

The “edge-over-cost gate” is described as requiring **predicted_return ≥ 0.002** (20 bps) to clear a conservative “10 bps round trip” cost estimate; if cost not cleared and Kelly is small, the position is skipped. fileciteturn5file2L29-L33

Volatility targeting is explicitly “timeframe-aware” by annualizing per-bar volatility as `std × √(252 × bars_per_day)` for intraday bars, and the document includes a note that an earlier bug used `√252` only (material undershoot) and **over-sized positions by ~4×**. fileciteturn5file1L12-L16 fileciteturn5file3L38-L40

Sizing also has caps/filters: per-position cap 10% of equity, portfolio cap 95%, minimum weight 0.1%, and minimum notional **$2,000**, plus a seasonal downscale during the first and last 15 minutes of market hours. fileciteturn10file4L22-L35 fileciteturn7file1L8-L11

### Order submission and broker execution

Entry orders are submitted as **MARKET + IOC** with idempotency keys; exits are **MARKET + DAY** with explicit long-only safety checks against broker positions. fileciteturn10file3L15-L49

At the broker level, the platform integrates with entity["company","Alpaca Markets","broker api platform"] REST and WebSocket endpoints. fileciteturn8file2L4-L10

The document also describes an outbox dispatcher that defaults to `day` and checks market hours (9:30–4:00 ET), but other components reference slightly different windows (see below). fileciteturn11file1L55-L59

On IOC semantics specifically: Alpaca defines IOC as “execute all or part immediately; cancel the unfilled remainder,” which can yield partial fills and, in some cases, full cancellation depending on liquidity/market-maker inventory. citeturn5view0

## What the current mapss.md changes appear to improve

Because you requested an “another deep research” after changes, I focused on the *changes that are explicitly called out inside the document as fixes or deltas*, and whether those changes are directionally correct.

The shift to **additive blended confidence** with “ML=0.0 when no signal” is a real improvement in decision integrity because it prevents the system from silently treating “no information” as mildly bullish/bearish. In the doc, the older approach is explicitly contrasted (“not 0.5 like old multiplicative formula”), and the new blend keeps confidence in [0,1] without needing caps. fileciteturn6file0L28-L35

The volatility annualization fix in the Kelly sizer is also a material correctness improvement. The document states that previously annual volatility was under-computed for intraday bars by ignoring bars-per-day, causing volatility scaling to cap at 2× and “over-size positions by ~4×.” Fixing this removes a systematic risk blow-up pathway. fileciteturn5file3L38-L40 fileciteturn5file1L12-L16

This fix aligns with a broader principle: exposure scaling that reduces risk when volatility is high can improve risk-adjusted results in some settings, but only when the volatility estimate is correctly specified for the sampling horizon. citeturn0search1

Finally, the document’s emphasis that “exits ALWAYS run” even when governance halts entries is a strong risk-management design choice that many retail algos get wrong (they halt *everything*, then get trapped). Here, the tick lifecycle and the exit section both reinforce that exits are intended to remain active under entry blocks. fileciteturn8file0L23-L43 fileciteturn4file2L35-L40

## Structural issues likely driving inefficiency and weak profitability

This section focuses on *high-confidence*, “mechanism-level” issues that can plausibly explain poor live results even if the strategy has some signal. Where possible, I tie each issue to a specific branch/parameter in the decision tree.

### A time-stop and follow-through bug in trending regimes can strand capital

In the exit engine, `trending_up` and `low_vol` regimes have **∞ max bars**, while “failure to follow through” triggers only *after 25% of max_bars* and loser time-stop uses `loser_max = max_bars × 1.5`. fileciteturn4file1L41-L49 fileciteturn4file0L42-L53

If `max_bars = ∞`, then “25% of max_bars” and the loser time-stop threshold are effectively unreachable, which means *two separate cleanup mechanisms can be disabled exactly in the regime where your system is most likely to hold positions for a long time*. That creates a classic “bag-holding by regime misclassification” failure mode: one wrong `trending_up` label early in a trade can prevent time-based exits and follow-through culling from ever activating, leaving only the hard stop/max-loss as an escape hatch. fileciteturn4file1L41-L49 fileciteturn4file0L47-L53

This is not a “style preference” issue; it is a correctness/robustness issue because the decision tree explicitly relies on max_bars for multiple branches. fileciteturn4file0L42-L53

### A PnL-triggered circuit breaker may unintentionally block exits

The platform describes a Redis-backed **OrderService circuit breaker** that trips not only on technical failures but also when **daily PnL loss ≥ 5%**. fileciteturn9file0L41-L68

The inter-module dependency map shows that **LiveEngine orders flow through OrderService.submit_symbol_order()**, and the *first step* is “Check CircuitBreaker (Redis-backed, 5% PnL kill).” fileciteturn12file2L21-L27

If exit orders are routed through the same OrderService method (and the document suggests they are), then a daily-loss trip could block *risk-reducing* exit orders at the exact moment you most need to de-risk. That directly contradicts the “exits always run” safety intent at the organism layer. fileciteturn8file0L23-L43 fileciteturn12file2L21-L27

There are also multiple overlapping “circuit breaker” constructs (infra/resilience vs OrderService) plus an organism drawdown kill switch and a platform RiskManager with emergency-stop. This increases the probability of contradictory states unless you define an explicit precedence order and “exit bypass” policy. fileciteturn9file0L7-L18 fileciteturn9file4L13-L20

From an operational-risk standpoint, strong pre-trade risk controls are standard in automated trading systems (even beyond your broker), and regulators have explicitly focused on automated market-access risks. citeturn1search7 citeturn1search3

### IOC market entries plus a thin “20 bps edge” gate is a cost/drag trap

Your entry fills are described as **MARKET + IOC**. fileciteturn10file3L28-L33

IOC behavior at Alpaca is explicitly “fill immediately (all or part) and cancel the remainder,” which tends to push you toward paying the spread and adds partial-fill complexity. citeturn5view0

At the same time, the Kelly sizer’s edge-over-cost gate is described as `predicted_return >= 0.002` (20 bps) based on a conservative “10 bps round trip” estimate. fileciteturn5file2L29-L33

In real intraday trading, effective costs (spread + adverse selection + slippage + queue position + micro-volatility during execution) are often not stable and are frequently *state-dependent* (time of day, volatility, liquidity). Treating costs as a constant 10 bps while using market orders is a common reason “paper profitable” becomes “live unprofitable,” and modern backtesting guidance emphasizes explicitly incorporating transaction costs, order mechanics, and data frequency choices into evaluation. citeturn1search2 citeturn1search10

This issue becomes more acute because the platform also uses a “predicted_return floor” of **0.01** (1%) for pure breakout additions. That floor can cause the edge-over-cost gate to pass even when ML is neutral and the strategy is effectively saying “I don’t actually know the expected return, but assume 1% anyway.” fileciteturn6file0L37-L44 fileciteturn5file2L29-L33

### Prediction-unit ambiguity: predicted_return range vs gates suggests a label/horizon mismatch

The ML regressor output is described as `predicted_return ∈ [-0.5, 0.5]`. fileciteturn6file1L32-L34

But the system also uses fixed thresholds like `predicted_return >= 0.002` for cost gating and `predicted_return floor = 0.01` for breakout-only additions. fileciteturn5file2L29-L33 fileciteturn6file0L37-L44

Those numbers only make coherent sense if predicted_return is (a) in **fractional return units** and (b) on a well-defined horizon (next bar? next N bars? until exit?). If the regressor is trained on one horizon but the gating and execution assume another, then it will look like the system has “AI confidence,” but it will be systematically mis-calibrated. This is a major failure mode highlighted in financial ML practice: wrong labeling / horizon mismatch and leakage can make models look good in-sample and fail out-of-sample. citeturn2search1

### Small-sample, high-feature-count ML training conditions are a backtest-overfitting risk

The system describes training on 79 features with minimum ~50 total samples across symbols and per-symbol minimums, with a time-based split (80/20). fileciteturn6file1L66-L72

Even with walk-forward checks and acceptance criteria, financial ML is notoriously vulnerable to backtest overfitting and leakage, and the **probability of backtest overfitting** rises materially as you explore many model/parameter variations. citeturn2search2

Modern techniques specifically recommend purging/embargoing and careful validation design to avoid time overlap leakage when labels depend on future windows; entity["people","Marcos López de Prado","financial ml researcher"] emphasizes these points and offers combinatorial purged CV as an evaluation discipline for financial ML. citeturn2search1

Separately, research reviewing CV techniques in the ML era finds that cross-validation choice matters materially for backtest overfitting mitigation. citeturn0search2

### Missing-data handling can silently create regime/prediction artifacts

In the live data pipeline, NaN/Inf is globally replaced with **0.0**. fileciteturn2file0L42-L47

That fails “quietly” in a dangerous way: 0.0 is not a neutral value for many technical indicators (distance-from-SMA, percentile ranks, vol-anomaly measures, etc.). While the doc also mentions a future “feature store” with QA gates, the tick-path described still includes the hard NaN→0 safety net, which can produce spurious regime classifications and ML predictions exactly when the data is degraded (API gaps, partial history, reconnects). fileciteturn2file0L42-L47 fileciteturn11file4L64-L70

### Market-hours definitions disagree across layers, creating avoidable rejects and noisy state

Market-hours enforcement appears in multiple places:

- OrganismScheduler checks market hours approximately **9:28–4:01 ET**. fileciteturn3file0L51-L59  
- Order guardrails require within **9:30–16:00 ET**. fileciteturn10file0L46-L53  
- Outbox dispatcher checks **9:30–4:00 ET**. fileciteturn11file1L55-L58  
- Alpaca’s own docs emphasize that DAY orders are generally valid in regular hours by default and have special behavior if submitted after the close. citeturn5view0  

Even if this “works,” it causes predictable friction: ticks and scans occurring in time windows where orders will later be rejected by guardrails or broker constraints, which amplifies churn in logs, state machines, and (worst case) ML training labels if your “intent” gets recorded but execution fails. fileciteturn10file0L46-L53 fileciteturn3file0L51-L59

### Fill reconciliation can corrupt learning when exit prices are missing

Fill reconciliation records trades by detecting symbols present in internal metadata but absent at the broker, then computing PnL; however, the doc notes “Get exit price (features fallback to entry price).” fileciteturn7file1L58-L73

If exit price is missing and you substitute entry price, you create “phantom flat trades” (0 PnL) that can materially distort: win rate, payoff ratio, regime-stratified Kelly stats, and confidence calibration. That directly impacts the system’s cognitive updates (continuous learner + Kelly regime stats + ML calibration). fileciteturn7file1L70-L77

## High-impact recommendations for improving the trading brain

The recommendations below are written as “audit actions”: each is a change you can implement and then objectively validate via your existing shadow/dry_run mechanisms and walk-forward gates.

### Make exits un-blockable: introduce a “reduce-only path” that bypasses PnL circuit breakers

You need a single invariant: **a risk-reducing exit must not be blocked by a loss-threshold circuit breaker**.

Concretely: mark exit intents as `reduce_only=True` (or equivalent) at the request level, and have OrderService’s PnL circuit breaker allow reduce-only orders even when tripped. Keep technical-failure breakers (e.g., broker down) in place, but do not block “flatten” logic when the reason is “you’re losing money.” fileciteturn9file0L41-L68 fileciteturn12file2L21-L27

This reconciles the organism guarantee (“exits always run”) with platform-level circuit-breaking. fileciteturn8file0L23-L43

At the policy level, document this precedence and connect it to your emergency-stop workflow so the platform behaves deterministically under stress. fileciteturn9file4L33-L39

### Fix trending-regime time logic: replace ∞ max_bars with a two-dimensional “opportunity cost” model

Right now, the exit-tree uses `max_bars` as a dependency for (a) failure-to-follow-through and (b) loser time-stop; with ∞ max bars, those branches effectively never run. fileciteturn4file0L42-L53 fileciteturn4file1L41-L49

A robust replacement is to decouple “let winners run” from “don’t strand capital” by introducing two limits:

- `max_bars_in_profit` (can be very large in trending regimes)
- `max_bars_not_making_progress` (finite across all regimes)

Progress should be defined by *MFE/MAE and R-multiples*, not only raw pnl. You already compute “R-achieved” in the failure-to-follow branch; reuse that idea but make it independent of `max_bars`. fileciteturn4file0L42-L46

In practice, this is one of the most direct ways to improve capital efficiency: you stop financing “dead money” positions that neither trigger a stop nor generate trend continuation.

### Remove the “predicted_return = 1% floor” hack and replace with an expected-return surrogate that is honest

The doc’s pure-breakout additions set `predicted_return floor = max(ml_return, 0.01)` while forcing direction long. fileciteturn6file0L37-L44

Because predicted_return is used for cost gating in the Kelly sizer, this design can unintentionally turn many breakout-only candidates into “edge-cleared” candidates even when ML has no signal, simply because their predicted_return was synthetically lifted. fileciteturn5file2L29-L33

Replace this floor with a computed proxy, for example:

- “expected move to first resistance” proxy (range width, ATR, breakout strength)
- or a historical conditional expectancy table: `E[return | breakout_score bin, regime, time_of_day]`

This aligns with the principle in financial ML that you must label and size using quantities that map to the true horizon and payoff distribution, or you will systemically mis-calibrate. citeturn2search1

### Upgrade cost modeling: move from a constant 10 bps to a state-dependent cost estimate and stop using market IOC by default

With MARKET+IOC entries, you are structurally choosing immediacy over price; Alpaca’s IOC definition explicitly allows partial fills and cancellation of remaining size. fileciteturn10file3L28-L33 citeturn5view0

If you keep MARKET entries, then **your edge gate must use a live cost estimate**, not a constant. The “10 bps round-trip estimate” is a placeholder; treat it as a default fallback rather than a constant. fileciteturn5file2L29-L33

At minimum, introduce a per-symbol, per-time-of-day effective spread proxy and incorporate it into:
- `edge_clears_cost` (use `predicted_return_net = predicted_return - cost_estimate`)
- position sizing (apply an extra downscale in high spread / low liquidity states)

Backtesting guidance repeatedly stresses that realism requires explicit transaction cost modeling and that ignoring these frictions is a common source of live underperformance. citeturn1search2 citeturn1search10

Also consider switching default entries to **limit orders** at or near mid/near-touch with timeouts (and selective reprice), using IOC only for the highest-conviction signals. Your system has fast outbox dispatch and idempotency infrastructure that supports this evolution safely. fileciteturn10file2L35-L49 fileciteturn11file1L73-L86

### Replace “NaN → 0.0” with “imputation + missingness flags” and block trading under data degradation

The current live-path global NaN/Inf→0.0 approach hides upstream data quality failures and can create non-neutral artifacts in features and regimes. fileciteturn2file0L42-L47

A better pattern is:
- impute using rolling medians/last-good values where appropriate
- add boolean missingness indicators for any imputed feature family
- hard-block entries when missingness exceeds a threshold, while allowing exits (consistent with your exit-first principle)

This also aligns with your stated future feature-store “Data QA gates” concept; the key is to enforce it in the live tick path rather than as a future-only abstraction. fileciteturn11file4L64-L71

### Enforce a single market-hours definition across scheduler, guardrails, and dispatcher

Currently, market-hours checks differ (9:28–4:01 vs 9:30–4:00 vs 9:30–16:00). fileciteturn3file0L51-L59 fileciteturn10file0L46-L53 fileciteturn11file1L55-L58

Define one canonical function (e.g., “regular trading hours with X-minute buffer”) and use it everywhere: tick gating, order guardrails, and order routing. This reduces avoidable rejects and prevents edge cases where the strategy can enter state transitions that can’t be executed. fileciteturn10file0L46-L53

Use broker semantics as the final constraint: Alpaca’s documentation explains day-order validity and special handling after the close; align your engine to those behaviors. citeturn5view0

### Rebuild evaluation discipline: purged/embargoed CV, deflated metrics, and fewer degrees of freedom

You already have several “safety gates” (continuous learner acceptance criteria, walk-forward gate for brain persistence), which is good. fileciteturn6file2L25-L30 fileciteturn6file1L4-L8

But financial ML needs stronger evaluation discipline than generic ML because of (a) non-stationarity and (b) extremely low signal-to-noise. entity["people","David H. Bailey","mathematician backtest pbo"] and coauthors formalize the probability of backtest overfitting and show how easily selection bias can produce “great backtests” that fail out-of-sample. citeturn2search2

Concrete changes:
- Implement purged + embargoed CV for model selection (and, if feasible, combinatorial purged CV). citeturn2search1  
- Track and report “research degrees of freedom” (how many parameter/model variants were tried) and adjust performance reporting accordingly. citeturn2search2  
- Reduce model complexity degrees-of-freedom at the same time you increase evaluation rigor: 79 features with small samples is intrinsically high variance. fileciteturn6file1L66-L72  

This is not academic nitpicking; it’s a primary reason many ML-driven trading efforts fail. citeturn2search1

### Replace pure Kelly sizing with “fractional Kelly + estimation-error shrinkage” and make volatility targeting explicit at the portfolio level

Kelly is extremely sensitive to input error; its “bad properties” include high drawdowns when probabilities/edges are misestimated, and many practitioners use **fractional Kelly** for robustness. citeturn2search0

You already use half-Kelly and add multiple safety scalers; that’s directionally good. fileciteturn5file0L39-L46

But two improvements are high impact:
- shrink Kelly inputs (win rate, payoff ratio) with Bayesian priors / empirical Bayes so early samples don’t dominate  
- move from per-position “vol targeting” to an explicit *portfolio volatility budget* (especially because you cap portfolio weights at 95%, which can still create concentrated risk if correlations spike during stress) fileciteturn5file1L12-L16 fileciteturn5file1L36-L39  

Separately, evidence exists that volatility-managed exposure rules can raise Sharpe/utility in certain broad portfolio contexts, reinforcing the value of correctly specified volatility scaling (which your recent fix supports). citeturn0search1

## Validation framework for proving the improvements worked

Your platform already includes execution modes that are ideal for disciplined iteration: **shadow** (intent-only) and **dry_run** (simulated fills). Use them as the primary mechanism for isolating signal quality from execution cost and for testing decision-tree modifications without capital risk. fileciteturn12file0L10-L25

A robust, hedge-fund-grade validation loop in this architecture looks like:

- **Shadow (intent) first**: measure signal quality without execution friction, but record *the full decision trace* (features summary, regime, candidate scores, reason codes). fileciteturn12file0L15-L18  
- **Paper execute next**: measure slippage/partial fills versus intent; your promotion controller already anticipates rollback triggers like max slippage and turnover ratios, which can be reused to gate changes. fileciteturn12file4L34-L63  
- **Walk-forward only acceptance**: require that any change (especially to exits and sizing) improves net metrics over multiple rolling windows, not just immediately recent trades. The probability-of-overfitting literature provides strong justification for this discipline. citeturn2search2  
- **Net-of-cost reporting**: always include transaction costs/slippage assumptions explicitly; backtesting references emphasize that cost modeling is a first-order determinant of realism. citeturn1search2 citeturn1search10  

Finally, treat “profitability” as a *diagnostic decomposition* rather than a single number: (1) hit rate, (2) average win/loss, (3) tail losses, (4) turnover and cost drag, (5) capital utilization, (6) regime-conditional performance, and (7) failure modes (“blocked exits,” “stuck trending positions,” “rejections near market open/close”). The current decision tree already provides the hooks to compute most of these—what’s missing is enforcing the invariants and removing the few design choices that can silently sabotage edge (∞ holding dependencies, synthetic predicted_return floors, and cost under-modeling). fileciteturn4file1L41-L49 fileciteturn6file0L37-L44 fileciteturn5file2L29-L33