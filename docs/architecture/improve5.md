# Deep Research & Audit of the Intra Intraday Trading Platform Decision System

## Executive diagnosis of what is truly going wrong

Your platform is not “failing because it needs more indicators.” It is failing because the **timebase and incentive structure of the decision tree are internally inconsistent**, and the system is **structurally designed to (a) enter rarely, (b) size tiny, and (c) exit quickly for the same “failure_to_follow” reason**, which prevents both profitability and learning.

Across the repo’s “organism” path, the platform repeatedly uses the word **“bars”** to mean *different things in different modules*. In practice, your live loop is operating on **10‑second ticks**, while the trading logic is intended for **1‑minute bars with a 15‑bar prediction horizon** (≈15 minutes). Multiple subsystems still treat “bars held,” retrain cadence, progress checks, and min-hold gates as if one tick = one bar. This produces exactly the syndrome you’re seeing:

- **Exits arrive ~3 minutes after entry** due to the exit engine’s minimum-hold being implemented as “18 bars” where a “bar” is effectively a 10‑second tick, not a 1‑minute bar.
- **Failure-to-follow becomes a dominant exit reason** because it is the first non-stop-profit exit condition to regularly become eligible, and it is evaluated on a timebase that is too fast for your stated horizon.
- **New entries are choked** by a hard cap of **3 entries per hour** plus other gates (opening block, ML hold penalty cascade, long-only blocks), which prevents the model from collecting sufficient trade outcomes to calibrate confidence, expected edge, or regime-conditioned Kelly stats.
- **Sizing stays tiny** because your “KellySizer” pipeline stacks multiple conservative multipliers (vol targeting + regime scaling + confidence capping when ML is untrained + no breakout bonus when ML is untrained), leaving final weights around sub‑1% notional even in a $112K account.
- The platform appears “sophisticated,” but that sophistication is not currently compounding into edge; it is compounding into **more ways to silence itself**.

Separately, the “1000%+ returns” target is not a realistic acceptance criterion for production intraday systems. A real institutional bar is **stable positive expectancy net costs**, then **controlled risk scaling**. The platform must first become **time-consistent, attribution-consistent, and cost-consistent**. High returns cannot be engineered by “turning knobs up” until these fundamentals are correct—doing so usually just increases blow-up risk.

## Critical bugs that are definitely wrong

Severity key: **P0** = blocks correct operation / dominates P&L behavior; **P1** = major degradation; **P2** = meaningful inefficiency; **P3** = hygiene/observability.

### P0 — Exit engine counts 10‑second ticks as “bars,” causing premature exit eligibility

**File:** `backend/organism/adaptive_exits.py`  
**Where:** `AdaptiveExitEngine.check_exit()` increments `levels.bars_held += 1` **on every call**. The engine is called from the live tick loop (10‑second cadence), so `bars_held` advances 6× faster than 1‑minute bars. This means your “bars” are actually “ticks,” and *all time-based logic is incorrect relative to H=15 (15 minutes).*  

**Why it’s catastrophic:**
- `MIN_HOLD_BARS_PROFIT = 18` is described as “18 bars × 10s = 3 min.” That is already a red flag: your platform trades **1‑minute bars**, and the prediction horizon is **15 bars** (~15 minutes). A “min hold” of 3 minutes makes no sense for a 15‑minute predictive horizon.
- Because the minimum-hold gate suppresses profit exits up to that point, the *first time the engine is allowed to take profit exits*, it immediately checks **failure_to_follow** (priority 4b) and frequently triggers it if the trade hasn’t moved fast enough.

**Observed symptom match:** All trades exiting for `"failure_to_follow"` at ~3 minutes is the exact expected outcome of this implementation and the current thresholds.

**What should happen instead:**  
- `bars_held` must mean **completed 1‑minute bars since entry**, not 10‑second ticks.
- Exits that are sensitive to intrabar movement (hard stop, max-loss safety net, trailing stop breach) can be checked each tick, but **the “time-like” counters must advance only when a new bar closes**.

### P0 — Strategy horizon and exit timing are structurally mismatched

**Files:**  
- `backend/organism/ml_signal.py` (prediction horizon)  
- `backend/organism/adaptive_exits.py` (min hold + failure-to-follow)  

**What’s wrong:**
- The ML model trains using `prediction_horizon = H` (your H=15), and targets are defined as `(close[t+H] - close[t]) / close[t]`. That means predictions are for a **15‑bar ahead return**.
- The exit engine, as implemented, can forcefully exit for failure-to-follow after becoming eligible at ~3 minutes (due to tick/bars mismatch) and after a very small “progress check” window.

**Why it matters:** You’re training for a 15‑minute outcome but holding for ~3 minutes. That is not a “tuning issue”; it is a **category error**: the learning target and policy evaluation window differ, so:
- The ML model cannot be judged correctly (it never gets time to realize its horizon).
- The exit reason attribution becomes meaningless (everything becomes “failure_to_follow”).
- Continuous learning gets polluted (the same exit reason dominates, which biases evolution).

### P0 — Entry starvation is still structurally enforced

**File:** `docs/architecture/mapss.md` (platform map) + core tick loop behavior, plus your reported behavior  
**What’s wrong:** You still have a **hard throttle of 3 entries/hour**, which causes a 60‑minute lockout after three initial entries. That creates the exact “learning-starved” system that you already diagnosed.

**Why it’s catastrophic:**  
For a “living organism,” early generations need *data* more than they need restraint. A 3/hour throttle is appropriate for late-stage risk control, not for bootstrapping a model whose calibration and Kelly stats need trade outcomes. With only 3 trades/day, you cannot learn regime-conditioned expectancy, you cannot calibrate confidence bins, and you cannot meaningfully stabilize adaptive parameters.

### P1 — Alpha scanner punishes ML “hold” in a way that suppresses non-ML edges

**File:** `backend/organism/alpha_scanner.py`  
**What’s wrong:**  
- Direction comes only from ML (if `ml_sig.direction != 0`).  
- Then: `if direction == 0: composite *= 0.3` (constant, always).  

This means: if ML says “hold” (common early or under weak signal), your composite alpha is crushed by 70% even if breakout/momentum/inst-flow are strong.

**Why it matters:**  
You attempted to implement “dynamic ML weight” when ML confidence is low, but the hold penalty remains a **hard veto** in practice. That is internally inconsistent: you say “ML is dead weight when low confidence,” then you still let ML hold **gate the entire alpha rank**.

### P1 — KellySizer disables breakout bonus when ML is untrained, compounding conservative sizing

**File:** `backend/organism/kelly_sizer.py`  
**What’s wrong:**  
- Breakout bonus is defined to size up high breakout scores, but the code sets:

```python
breakout_bonus = self._breakout_bonus(breakout_score)
if not ml_is_trained:
    breakout_bonus = 1.0
```

So in the exact regime where you most need a non-ML engine to carry the system (cold start), the breakout amplifier is removed.

**Why it matters:**  
This strongly contributes to:
- tiny positions,
- low realized P&L even when the system is “right,”
- low learning signal (small outcomes are harder to distinguish from noise after costs).

### P2 — Telemetry reports a fitness gate of 0.35 when the real entry gate is 0.45

**File:** `backend/organism/decision_telemetry.py`  
**What’s wrong:** `SymbolAlphaDetail.fitness_gate` is set to `0.35`, and the map explicitly notes the actual entry gate is 0.45. This creates *operator confusion* and makes “fixes from the sidelines” more likely, because operators are diagnosing using misleading dashboards.

### P2 — Transaction-cost and impact assumptions can be off by an order of magnitude relative to holding time

If your typical holding time is only a few minutes, **bid–ask spread and slippage become a dominant tax**. Even for liquid U.S. equities, spreads measured in a few to tens of bps are normal depending on instrument and conditions. citeturn0search0  
And impact grows nonlinearly with size; square‑root style impact models are commonly used as approximations. citeturn0search1turn0search2  

A system that exits after ~3 minutes on “failure_to_follow” is implicitly a short-horizon scalp. For scalps, **cost modeling must be extremely accurate**, because gross edge per trade is small. If costs are underestimated, the system will look like it’s “working” in paper (or on tiny size) but fail on meaningful scale.

## Design flaws that work as coded but sabotage profitability

### The platform is trying to run a 15‑minute prediction policy with a 3‑minute patience policy

This is the single most important design flaw. You can either:
- trade a **3–5 minute** style (then ML horizon, exits, and entry gates must match that), or
- trade a **10–30 minute** style (then min-hold, failure checks, pyramiding, and take-profit logic must match that).

Right now, the system is split-brain.

### The decision tree has too many “reasonable” filters that multiply into near-zero throughput

You have many gates that each seem prudent:
- opening block,
- regime sit-out,
- long-only,
- entry throttle,
- alpha min threshold,
- ML hold penalty,
- symbol fitness gate,
- per-sector cap,
- liquidity checks,
- cost gate,
- min notional.

Individually, you can defend each gate. Collectively, they create a funnel that often yields **0 candidates** and therefore no learning. This is a classic silent killer in automated trading.

### “Kelly sizing” is mostly not Kelly yet

True Kelly sizing requires **a stable estimate of edge and payoff distribution**. Early in life (few clean trades), you do not have that. Your code tries to approximate Kelly using short-horizon return statistics, but such estimates are extremely unstable and can saturate or collapse, especially with small variance artifacts and limited samples. In practice, most professional teams either:
- use **fixed risk budgets per trade** (risk parity / stop-distance sizing) until enough post-cost outcomes accumulate, then
- transition to a Kelly-like adapter gradually (half-Kelly or less, with conservative priors and shrinkage), because naive Kelly can overbet when parameters are uncertain. citeturn0search5  

### The system’s “confidence” is not a decision asset yet; it is a decision bottleneck

Because blended confidence weights ML heavily, a cold-start model produces low confidence values (around 0.1–0.2), which then:
- reduces alpha scores indirectly (ML direction often 0 → penalty),
- reduces size (confidence scaling is capped when ML is untrained),
- reduces evolution signal (smaller trades → weaker gradient).

In a sane cold-start design, confidence should be **redefined**:
- either as “model confidence” (ML-only) *and not used to veto breakouts*, or
- as “policy confidence,” where non-ML signals can drive confidence when ML is weak.

## Subsystem communication failures where information is lost or misused

### ML direction is treated as the only legitimate direction signal in the alpha scanner

Breakout scanner produces directionality signals (pivot break direction, RS, tension dynamics), but alpha scanner’s `direction` remains 0 unless ML produces a buy/sell. That leads to the hold penalty that suppresses otherwise strong candidates.

**Impact:** makes the platform behave as “ML-or-nothing,” even though you built multiple non-ML signal engines.

### Exit reasons are structurally biased toward “failure_to_follow”

Because of:
- the min-hold gate,
- the fast timebase,
- the early progress check window,
- failure_to_follow checked before many longer-horizon mechanisms have time to matter,

the system is predisposed to attribute exits to failure-to-follow even when the true reason is “we didn’t give the trade time to realize the thesis.”

**Impact:** evolution and learning become biased (you will tune around a pathology, not around a real edge).

### Telemetry inconsistencies encourage wrong fixes

When dashboards show a 0.35 fitness gate while the engine enforces 0.45, operators “fix” behavior by editing the wrong thing. This directly matches your concern that fixes are coming from the sidelines and missing the root cause.

## Prioritized recommendations with concrete code-level changes

The ordering below is by expected improvement to platform correctness and P&L per unit risk.

### Make the timebase consistent across all modules

**What to change**
- In `backend/organism/live_engine.py`: compute `is_new_bar` per symbol using the timestamp of the latest **1‑minute bar** (not “tick time”).  
- In `backend/organism/adaptive_exits.py`:
  - change `check_exit()` signature to accept `is_new_bar: bool`,
  - increment `levels.bars_held` **only when `is_new_bar` is True**,
  - evaluate “time-like” exits (min-hold gate, failure_to_follow, max holding, loser time stop, time decay) **only on new bars**,
  - continue evaluating hard stop and max-loss on every tick; optionally evaluate trailing stop breach on every tick.

**Why it matters**
This single change will:
- stop premature “failure_to_follow” exits,
- align holding times with the ML horizon,
- make exit reasons meaningful again (so learning and evolution can work).

**Risk**
Medium. You will change live behavior substantially; some bad trades will lose more before exiting. But that is the *correct* trade-off if you claim a 15‑minute horizon.

**Complexity**
Medium. This is a surgical refactor but touches core exit flow.

### Replace “failure_to_follow” with a regime- and horizon-consistent implementation

**What to change**
- In `backend/organism/adaptive_exits.py`:
  - redefine failure-to-follow check time: `check_after = max(int(0.5 * H), 5)` **bars**,
  - define threshold by regime:
    - trending_up / low_vol: disable failure_to_follow (or convert to partial trim only),
    - high_vol / chop: require `R_achieved < 0.25` at check_after (not 0.5) and confirm lack of momentum (e.g., last N bars not improving),
  - use **bar-based** R progression, not tick-based.

**Why it matters**
Your current version is effectively a scalp stop that forces you to win quickly. It is incompatible with a 15‑minute horizon and will systematically cut winners early in choppy conditions.

**Risk**
Medium. You will hold more and may see larger variance.

**Complexity**
Small to medium.

### Remove the ML “hold penalty” as a hard veto during cold start

**What to change**
- In `backend/organism/alpha_scanner.py`:
  - replace:

```python
if direction == 0:
    composite *= 0.3
```

  - with:
    - if ML is trained and confidence is high, keep penalty,
    - if ML is untrained or low-confidence, derive `direction` from non-ML signals (breakout direction, momentum sign, regime alignment), then **do not apply the hold penalty** (or apply a mild 0.85 multiplier).

A minimal implementable rule with low complexity:
- if `ml_sig` missing or `ml_sig.direction == 0`, set direction from `ret_20d` sign and/or breakout pivot direction, then keep composite intact.

**Why it matters**
This unlocks your non-ML edge engines so the system can trade and learn even when ML is weak.

**Risk**
Medium: you will take more non-ML trades. But that is required to build initial training outcomes.

**Complexity**
Small.

### Fix the sizing stack so cold-start breakouts can size above “toy” scale

**What to change**
- In `backend/organism/kelly_sizer.py`:
  - do **not** force `breakout_bonus = 1.0` when ML is untrained. Instead:
    - cap it at 1.5 when untrained (not 2.0), *or*
    - apply it only when breakout_score ≥ 0.85 and liquidity is high.
  - raise the untrained confidence scale cap (currently `min(confidence_scale, 0.6)`) to ~0.9, *or* decouple “policy confidence” from “ML confidence.”
  - implement a **pre-Kelly sizing mode** until you have enough clean trades:
    - risk-budget sizing: `risk_usd = equity * risk_per_trade` (e.g., 0.25%),
    - shares = `risk_usd / (entry_price - stop_loss)`.

**Why it matters**
Right now, you are stacking conservative multipliers that guarantee sub‑1% weights. That blocks meaningful P&L and slows learning. A systematic risk-budget baseline is how professional teams bootstrap before “true Kelly” becomes statistically justified. citeturn0search5  

**Risk**
High if you simply “increase sizes” without fixing the exit horizon issue first. Do **timebase fixes first**, then sizing.

**Complexity**
Medium.

### Replace the hard 3/hour entry throttle with a learning-mode throttle

**What to change**
- In the live engine entry gating, change throttle policy to:
  - learning mode (e.g., < 200 clean trades): 10–15 entries/hour,
  - mature mode: 3–6 entries/hour, scaled down when positions are already full.

Also: throttle should be **per-symbol and per-sector aware**, not global-only.

**Why it matters**
Your current throttle is mathematically incompatible with learning goals.

**Risk**
Medium: more trades = more variance, but that is the point in paper and early training.

**Complexity**
Small.

### Persist telemetry and fix telemetry truthfulness

**What to change**
- Fix `fitness_gate` value in `backend/organism/decision_telemetry.py` to match engine reality.
- Persist decision snapshots to DB at low frequency (e.g., every 6 ticks) so post-day analysis can be performed deterministically. A 360‑tick ring buffer is insufficient for a full session audit.

**Why it matters**
You cannot run a “self-evolving organism” without high-fidelity historical decision records.

**Risk**
Low.

**Complexity**
Small to medium (DB schema + write path).

### Tighten cost modeling to match a realistic holding period

Your system’s profitability is extremely sensitive to bid‑ask spread, slippage, and impact, especially at short holding periods. Spreads for U.S. equities can be on the order of single‑digit to tens of bps depending on instrument and conditions. citeturn0search0  
Impact models commonly scale like σ×√(Q/V) in simplified forms, and more formal frameworks treat temporary and permanent impact separately. citeturn0search1turn0search2  

**What to change**
- If you keep holding periods short (<10 minutes), shift order entry to:
  - limit-at-mid or limit-within-spread when possible,
  - or “marketable limit” with strict slippage caps.
- Ensure predicted_return and cost gate compare returns and costs on the same horizon and unit.

**Risk**
Medium (missed fills), but crucial for scalability.

**Complexity**
Medium.

### Recommended parameter changes table

| Parameter / behavior | Current | Recommended | Rationale | Complexity |
|---|---:|---:|---|---|
| Exit timebase for `bars_held` | increments per tick | increments per **1‑minute bar** | Removes 6× premature exits; aligns to horizon | Medium |
| `MIN_HOLD_BARS_PROFIT` | 18 “bars” (~3 minutes at 10s) | `max(3, H//3)` **true bars** (for H=15 → 5 minutes) | Matches predictive horizon and reduces forced early exits | Small |
| Failure-to-follow check time | progress_ref//4 with floor 5 (tick-based effect) | `check_after = max(int(0.5H), 5)` bars | Stops “3 minute thesis test” problem | Small |
| Failure-to-follow threshold | `R < 0.5` | chop/high_vol: `R < 0.25`; trending: disable or partial trim only | Makes it regime-consistent and less scalp-like | Medium |
| Alpha “hold penalty” | composite × 0.3 when direction==0 | conditional; or derive direction non-ML when ML weak | Prevents ML from vetoing non-ML edge | Small |
| Entry throttle | 3/hour | learning: 10–15/hour; mature: 3–6/hour | Fixes learning starvation | Small |
| Breakout bonus when ML untrained | forced 1.0 | allow ≤1.5 cap | Lets breakout engine carry cold-start | Small |
| Confidence scale cap when ML untrained | ≤0.6 | ≤0.9 (or policy-confidence separation) | Prevents systematic under-sizing | Small |

## Corrected decision tree for a time-consistent intraday organism

The goal is not “more branches.” The goal is **correct branching at the correct time resolution**.

```mermaid
flowchart TD
  A[Tick @ 10s] --> B[Housekeeping + Stream Health]
  B --> C{Governance Halt?}
  C -->|Yes| D[Entries blocked; exits still allowed]
  C -->|No| E[Proceed]

  D --> F[Risk/Exit Loop @ 10s]
  E --> F[Risk/Exit Loop @ 10s]

  F --> G{New 1-min bar closed?}
  G -->|No| H[Only: stop_loss / max_loss / trail-breach checks]
  G -->|Yes| I[Advance bar counters; evaluate time-like exits]
  I --> J{Exit triggered?}
  J -->|Yes| K[Submit reduce-only exit order + record reason]
  J -->|No| L[Entry pipeline allowed?]

  L --> M{Entry gates}
  M -->|Blocked| N[Skip entries this bar]
  M -->|Allowed| O[Compute Features + Regime + ML Predictions]

  O --> P[Alpha scan + breakout scan]
  P --> Q[Candidate gating + direction resolution]
  Q --> R[Compute policy-confidence (ML-aware)]
  R --> S[Pre-Kelly risk-budget sizing (if low trade count)]
  S --> T[Kelly sizing (only after sufficient clean outcomes)]
  T --> U[Submit entry orders]
  U --> V[Reconcile fills + write telemetry]
  V --> W[Continuous learning + evolution (if not frozen)]
  W --> X[Persist brain + snapshots]
```

This diagram contains two critical structural changes versus your current behavioral outcome:
1. **Exit evaluation becomes split into tick-sensitive risk checks and bar-sensitive time/behavior checks**, preventing bars_held distortion.
2. **Sizing becomes phase-dependent**, starting with deterministic risk sizing until enough clean data exists for Kelly-style adaptation.

---