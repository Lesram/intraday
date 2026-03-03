# Intraday Trading Platform Audit Focused on Trading Logic and Decision Tree

## Situation summary and what the March 2 run is really telling you

Your current platform behavior is best described as **“entry-starved, learning-starved, and attribution-blind”** rather than “broken in one obvious place.” The system is *functioning* as coded, but the combined effect of (a) layered entry gating, (b) a return-horizon mismatch between ML predictions and cost/risk gates, and (c) missing/incorrect propagation of key decision metadata means you get **too few quality trades**, and the trades you do get are **poorly labeled for learning and debugging**. fileciteturn24file1 fileciteturn24file0

The biggest meta-signal in your “not much activity today” report is not “the market had no opportunities.” It’s that the platform’s decision tree can easily converge to **near-zero entries** while simultaneously producing **almost no actionable diagnostics explaining why**, which causes your team to patch symptoms (thresholds and toggles) instead of removing root causes. The code already contains strong scaffolding for telemetry and invariant checking, but several critical values that should drive learning and post-mortems are either not captured or are overwritten. fileciteturn24file2

## The platform’s cognitive loop as implemented today

At a high level, the organism live engine is a single “cognitive tick” that does: **governance → data/features → regime → exits → (if entries allowed) scanning + candidate assembly → sizing → order submission → reconciliation → retrain/evolve → persistence/telemetry**. fileciteturn24file2

A few specific properties of this loop matter hugely to profitability and “feel”:

The system is deliberately designed to *always* manage risk on open positions even when new entries are blocked (halt, drawdown kill, insufficient data, etc.). That part is correct and is an important stability improvement. fileciteturn24file2

However, several entry-side gates stack multiplicatively:

- **Opening block**: no entries 9:30–10:00 ET for intraday runs. fileciteturn24file2  
- **Regime sit-out**: in `high_vol` or `stress`, if ML batch signals are all bearish, the engine skips entries. fileciteturn24file2  
- **Entries-per-hour throttle**: hard cap at 3 entries/hour. fileciteturn24file2  
- **Fitness gate**: symbols below a fitness threshold are blocked. fileciteturn24file2  
- **Liquidity gate**: symbols whose average per-bar volume over the last 20 bars is below 10k are blocked. fileciteturn24file2  
- **Feature missingness gate**: blocks entries if the last-row NaN/Inf missingness exceeds 25%. fileciteturn24file2 fileciteturn40file0  
- **Sizer gates**: cost/edge gating and minimum-notional gating can eliminate candidates even after “good” signals. fileciteturn24file4

The mental model that’s important here: You have built something closer to a **risk-first “capital preservation organism”** than a **data-hungry “alpha discovery organism.”** That can be valid, but it creates a catch-22 if you expect the system to self-improve quickly while it is allowed to take very few trades.

## Root causes of low activity and weak profitability

### The return-horizon mismatch is a structural blocker, not a tuning problem

Your ML model predicts **next-bar** direction and return magnitude:

- Training labels (`y_dir`, `y_ret`) are computed using the **next bar** (close[t+1] vs close[t]). fileciteturn32file0  
- Feature returns labeled `ret_1d`, `ret_2d`, … are actually **1-bar, 2-bar** returns (`pct_change(1)`, `pct_change(2)`, …). The “_d” naming is misleading in intraday contexts. fileciteturn40file0  

But the Kelly sizing layer contains a hard **edge-over-cost** gate:

- It requires `predicted_return >= 2 × spread_cost_pct`. fileciteturn24file4  
- Spread cost is dynamically estimated from bid/ask with time-of-day and liquidity multipliers, clamped between 3 bps and 50 bps. fileciteturn24file4  

This is a fundamental mismatch because **a next-bar expected return is generally much smaller than a round-trip spread/slippage cost** for many liquid equities—especially at 1-minute horizons. In real markets, you rarely get “next minute expected return” that consistently exceeds a few basis points, and you’re comparing it to a cost threshold that is often several basis points even in calm conditions.

This mismatch has two bad outcomes:

- In many regimes, the cost gate will **silence ML-driven trades** (even if classification accuracy is decent) because predicted return magnitudes are tiny on the next-bar horizon. fileciteturn32file0 fileciteturn24file4  
- If you “fix” this by loosening thresholds, you often end up **letting through trades where predicted return is not meaningful**, which worsens expectancy rather than improving it.

This is why repeated parameter patches “from the sidelines” don’t make a dent: the system is comparing quantities that don’t belong on the same scale.

### Confidence and predicted-return metadata are not reliably propagated to orders and trade records

Several parts of the engine compute nuanced confidence, then lose it:

- Candidate confidence is computed as a blend of ML confidence, breakout score, and scanner tension. fileciteturn24file2  
- But the `PositionSize` object returned by the sizer does **not** carry the candidate’s confidence (the dataclass has no field for it). fileciteturn24file4  
- The live engine then submits orders using `confidence=getattr(sz, "confidence", 0.6)` which will default to 0.6 for essentially all entries. fileciteturn24file2  

The practical result:

- Your stored order attributes “confidence” becomes **nearly constant**, destroying the usefulness of confidence calibration and weakening post-trade analysis. fileciteturn24file2 fileciteturn32file0  
- Downstream, the system’s confidence calibration (`record_prediction_outcome`, binning, calibration map) becomes distorted because it’s learning from a fake constant rather than the real confidence distribution. fileciteturn32file0  

This is a real “brain wiring” defect: the cognitive system computes the signal strength, then forgets it at the point where it should be most valuable.

### Trade reconciliation is not using true fills and is losing exit reasons

Your reconciliation logic records a `TradeRecord` when a tracked symbol disappears from broker positions, but it:

- Uses last bar close or quote midpoint as an “exit price” proxy when the position disappears (not the actual fill price). fileciteturn24file2  
- Hard-codes `exit_reason="live_close"` for reconciled trades, rather than using the actual exit reasons already being attached to exit orders. fileciteturn24file2  

You *do* have a more accurate DB-based trade reconstruction path that pairs entry/exit filled orders and reads exit attributes, but it’s only used on startup when brain trade records are missing. fileciteturn24file2  

If trade outcomes (price and reason) are noisy or wrong, then:

- Regime-stratified Kelly statistics are polluted. fileciteturn24file4 fileciteturn24file2  
- Continuous learning evaluation (“is this model better?”) becomes less meaningful because the “ground truth” PnL and return are approximations. fileciteturn24file2 fileciteturn32file8  
- You end up debugging ghost behavior (what the system *thinks* happened vs what the broker actually executed).

This alone can explain “we keep fixing things but results are still bad”: you are feeding the learning and reporting loop with partially synthetic trade outcomes.

### Your system can easily become “entry-starved” by design gates

Even ignoring model/attribution issues, your live engine entry-rate is constrained by decisions that may be overly conservative for a platform that still needs data:

- `AlphaScanner(top_n=3)` explicitly reduces candidate breadth. fileciteturn24file2  
- Entries-per-hour throttle is set to 3. fileciteturn24file2  
- Fitness gate is set at 0.45 in the entry loop, and sector diversification gates can block additional candidates within the same tick. fileciteturn24file2  
- Missingness gate and liquidity gate can remove candidates before sizing. fileciteturn24file2 fileciteturn40file0  
- The sizer has a minimum-notional requirement (intraday uses $500 min in `live_engine`, daily uses $2,000), so even viable signals can be dropped if the computed weight is too small. fileciteturn24file2 fileciteturn24file4  

The important observation: these gates and constraints do not just reduce trade frequency—they also reduce the platform’s ability to **discover** and **validate** whether it has an edge.

## Audit of mapss.md versus code changes and what is still missing

The repo now contains an extensively revised `docs/architecture/mapss.md` plus a dedicated trading-day report for 2026-03-02, indicating that a broad audit pass was indeed performed and merged into documentation. fileciteturn24file1 fileciteturn24file0

Based on direct code inspection, several of the “audit fixes” are clearly present in the live system:

- Liquidity gate is set to **10k per-bar average volume** (not 500k) in the live engine. fileciteturn24file2  
- Exit orders and entry orders are now submitted with `tif="day"` in the organism path. fileciteturn24file2  
- Exit processing is explicitly designed to continue even when entries are blocked. fileciteturn24file2  
- Dynamic cost model exists in the Kelly sizer and is used by the live engine via a quote provider when available. fileciteturn24file4 fileciteturn24file2  
- Feature engine computes and exposes `_nan_missingness`, and the live engine gates on it. fileciteturn40file0 fileciteturn24file2  

However, there are still “map-level” gaps that are not just documentation issues—they are real cognitive-system defects:

- **Confidence propagation is broken** (confidence defaults to 0.6 at order time because it is not carried through sizer outputs). fileciteturn24file2 fileciteturn24file4  
- **Exit reason attribution is broken** (`TradeRecord.exit_reason` becomes “live_close” for reconciled trades). fileciteturn24file2  
- **Telemetry inconsistencies exist** (example: the decision snapshot uses a different `fitness_gate` value than the entry filter uses, which can mislead dashboards and post-mortems). fileciteturn24file2  
- **The ML prediction horizon is not aligned** with sizing and cost gates, and this cannot be corrected by documentation changes. fileciteturn32file0 fileciteturn24file4  

If your team’s goal is to stop “random patches,” the priority is to repair these structural information flows and scale mismatches first.

## High-impact recommendations that are likely to improve efficiency, effectiveness, and profitability

### Redesign the model target to match the execution and exit horizon

Right now, the model predicts **next-bar** return, but your platform behaves like it wants to hold positions across multiple bars and exits based on ATR multiples and timeouts. fileciteturn32file0 fileciteturn24file2

A practical fix that preserves your existing architecture:

- Introduce a configurable prediction horizon `H` (bars) by timeframe (example: `H=15` for 1Min, `H=6` for 5Min).  
- In `MLSignalGenerator._build_training_data`, label `y_dir` and `y_ret` using `close[t+H]` instead of `close[t+1]`. fileciteturn32file0  
- Now `predicted_return` becomes “expected return over the holding horizon,” which is the only version that makes sense to compare against round-trip cost and to size based on. fileciteturn24file4  

This change directly addresses the core mismatch that currently suppresses ML-based trades or forces you to rely on arbitrary `predicted_return` floors.

### Make confidence a first-class value carried from signal → sizing → order → trade record

This is a concrete wiring repair:

- Add `confidence`, `predicted_return_used`, and `breakout_score` fields to the sizer’s `PositionSize` output (or an attached metadata struct). fileciteturn24file4  
- In the live engine, submit orders using the real confidence from the sized candidate, not a default. fileciteturn24file2  
- Store this confidence in `_entry_metadata`, and record it into `TradeRecord.confidence` on reconciliation. fileciteturn24file2 fileciteturn32file8  

You already have confidence calibration machinery; it simply cannot work correctly while confidence is effectively constant at the final action layer. fileciteturn32file0

### Fix trade attribution to use real fills and real exit reasons

To make learning and debugging meaningful:

- Replace (or complement) the current “position disappeared” reconciliation with a DB/filled-order based approach similar to `_reconstruct_trades_from_db`, which already pairs entry and exit orders and reads exit attributes/reasons. fileciteturn24file2  
- At minimum, store “last submitted exit reason” per symbol at the moment you generate an exit order, and use it when you create the `TradeRecord`. fileciteturn24file2  

Without accurate fill prices and exit reasons, you are effectively training and evaluating with noisy labels, which will stall improvement even if the strategy has edge. fileciteturn24file2 fileciteturn32file8

### Convert the entry pipeline from “hard gates” to “budgeted exploration” until the system has data

If the organism is still early in its learning lifecycle, hard-gating entries can prevent the system from ever collecting enough representative trades (and can skew learning to only a handful of symbols and regimes). fileciteturn24file2 fileciteturn24file0

A hedge-fund style solution is not “disable risk,” but “separate capital allocation into buckets”:

- Keep your existing strict gates for the main capital bucket. fileciteturn24file2  
- Add a small “exploration” bucket (for paper trading or micro-size live) that can take trades that *fail cost/edge gates*, but at tiny notional size and with tighter kill switches. The goal is to learn distributions and failure modes quickly without risking meaningful capital. fileciteturn24file4 fileciteturn24file2  

This directly breaks the “entry-starved → learning-starved → still entry-starved” loop.

### Make the platform self-explaining via gate-level telemetry that answers “why no trades” in one view

You already have a `DecisionTelemetryStore`, `DecisionSnapshot`, “filtering funnel” fields, and Activity events. Expand it so a single tick/day report can answer:

- How many symbols had MIN_BARS features? fileciteturn24file2  
- How many candidates passed alpha threshold? fileciteturn24file2  
- How many failed *each* gate (fitness, liquidity, missingness, cost, min_notional, throttle, opening block, regime sit-out)? fileciteturn24file2 fileciteturn24file4  
- Which exact threshold values were applied (and from where—env vs defaults)? fileciteturn24file2 fileciteturn24file1  

This turns your debugging from “patch-and-pray” into a deterministic process: you can see the dominant bottleneck at a glance.

## What to change next to get to a “normal, well operating” autonomous trading platform

Your next phase should prioritize **stability + truthful measurement + decision transparency** before chasing large returns. “1000%+ returns” is not a settings problem; it is a long sequence of (1) finding durable edge, (2) executing with costs under control, and (3) scaling only after robustness is proven. This audit focuses on the technical work that removes the current blockers to that path. fileciteturn24file1 fileciteturn24file0

The highest leverage work items, in the order most likely to change outcomes:

First, fix the “information plumbing” defects that prevent learning and proper post-mortems (confidence propagation, exit reason attribution, true fill pricing). fileciteturn24file2 fileciteturn24file4

Second, realign the prediction target horizon with costs and exits so “predicted_return” becomes a meaningful quantity for gating and sizing. fileciteturn32file0 fileciteturn24file4

Third, restructure gating into (a) main capital bucket with strict gates and (b) tiny exploration bucket to prevent data starvation and allow faster iteration. fileciteturn24file2 fileciteturn24file4

Finally, elevate the decision telemetry from “nice to have” to “operational requirement,” so every no-trade day produces a precise explanation of which gate(s) dominated and whether that was intentional. fileciteturn24file2

If you implement those four items, you will stop spending cycles on scattered fixes and instead move toward an architecture where (a) the system trades when it should, (b) it can explain itself, and (c) it can actually learn from what occurred—three prerequisites for improving profitability. fileciteturn24file1