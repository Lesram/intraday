According to a document from March 5, 2026, the platform’s loss day was not a random bad session. It was a compound failure of bursty post-hotfix entry behavior, weak learning-mode entry quality, repeated symbol re-entry, and oversized sizing in the wrong regime. The documented loss was -$351.45 with a 25.7% win rate, and the report explicitly says losses were concentrated in `trending_up` entries that reversed into `high_vol` / `trending_down` after the engine resumed trading aggressively following earlier blocking bugs.

I reviewed the latest March 5 loss-day report against the latest platform map and treated the March 5 recommendations as hypotheses to validate, not gospel. My conclusion: most of the recommendations are directionally right, but several are too narrow. The real fix is not “tune one threshold.” It is to tighten main-book learning-mode entry quality, hard-cap learning-mode risk, stop treating heuristic `predicted_return` as real statistical edge, and prevent repeated symbol churn. The exact implementation plan for Claude Code is below. The strongest evidence is that the biggest losses came from (1) `trending_up` entries that reversed, (2) repeated WMT re-entries, (3) CAT and XLE as poor names with outsized damage, and (4) late-day long entries in `trending_down`.

## Executive verdict

The March 5 deep-research recommendations are **mostly valid**, but they need to be reframed into an implementation sequence that fixes the right layer first:

* Keep: regime-scale freeze enforcement, symbol repeat-loss controls, XLE sizing investigation, `trending_down` entry restrictions, stale-data provenance, orphan-state cleanup, and richer causal telemetry.
* Modify: confidence-gate raising, entry-throttle tuning, and partial-exit investigation. Those are secondary unless you first separate main-book trades from exploration trades and fix learning-mode sizing/risk discipline.
* Do **not** spend the next cycle retuning FTF. The March 5 report says the improve7 FTF redesign appears to be working and reduced FTF relative to March 4. That is not where the next dollar of engineering should go.

The largest blind spot still in the architecture is this: the system is mixing **ranking logic** and **sizing logic** too tightly. The alpha scanner ranks names with a 7-factor composite, but the downstream sizer still treats `predicted_return` as if it were a reliable edge estimate, while the live engine can assign synthetic floors to `predicted_return` for breakout/no-ML cases. That is dangerous because ranking signals are not the same thing as a calibrated expected return for position sizing.

## Validation of the March 5 recommendations

### 1. “Investigate trending_up regime scale”

**Validated, but stronger than the report says.**

This should be treated as a **P0 enforcement issue**, not just an investigation. The March 5 report shows `trending_up` regime scale at 1.164 and explicitly says losses were amplified there. The latest map says evolved regime scales are supposed to stay frozen until there are at least 200 total trades and 30 trades in the specific regime; otherwise static fallback scales should be used. With only 93 trades total on March 5, any boosted evolved regime sizing should not have been live. If it was live, either the code is wrong or the doc is stale. Either way, Claude Code must enforce the freeze in code and expose the source of the regime scale in telemetry.

### 2. “WMT repeat-entry problem”

**Validated, but current circuit breaker is too weak for learning mode.**

The report shows WMT entered three times, all losses, with average P&L about -$40/trade, while still sitting above the relaxed learning-mode fitness gate of 0.30. The latest map confirms the learning-mode symbol fitness gate is 0.30, production 0.45, and the symbol circuit breaker only bans after 2 consecutive losers or -$15 daily P&L. That logic is too permissive for a LONG_ONLY learning engine. Cooldown should not “reset the moral memory” of a bad symbol for the day.

### 3. “XLE 92-share position sizing”

**Validated, but the right fix is broader than XLE.**

The order log shows XLE jumped to a 92-share main-book position at tick 411 and exited four ticks later via the circuit breaker for -$144.44. This is not just an XLE anomaly. It indicates the learning-mode sizing stack can still produce oversized exposures. The latest map shows that in learning mode the pre-Kelly risk-budget floor is still `0.25% equity / (atr × 1.5)` and is applied after Kelly combine, with confidence scaling, then clamped only by an 8% intraday position cap. That is too loose for a still-learning book. The fix is to lower the learning floor, add an explicit dollar-risk cap per trade, and lower the learning-mode position cap.

### 4. “Late-day trending_down entries”

**Validated, but should be a main-book block, not a global block.**

The report explicitly calls out XOM, GOOGL, and WMT long entries after tick 499 in `trending_down`, and all were stopped out. For a LONG_ONLY learning engine, new main-book longs in `trending_down` should be blocked after the opening stabilization window. But you should still allow **exploration** there at micro-size if you want data. A blanket global block would make the system even more learning-starved.

### 5. “Raise confidence gate to 0.40”

**Partially validated, but threshold-only is not the best fix.**

The report notes overconfident ML calibration: predicted 60%, actual 23% in the mid-confidence bucket. The latest map shows the current confidence gate is 0.30 baseline, 0.35 in chop, and those sub-threshold candidates can route to exploration rather than be thrown away. Raising the main-book gate is correct, but the better fix is:

* keep raw confidence for telemetry,
* use a shrunken or calibrated `effective_confidence` for gating and sizing,
* and route weak-but-interesting trades to exploration instead of just cutting them.

### 6. “Stale-data handling needs telemetry”

**Fully validated and should be expanded.**

The March 5 report says the stale-data gate was broken until a hotfix added `last_update_time` to the streaming provider, after which the stale-data block started working. The latest map says the stale-data threshold is 120s and exits should still run while entries are blocked. That is necessary but not sufficient. Claude Code should add per-symbol/per-tick `data_source=streaming|rest_fallback|stale`, `stream_age_seconds`, and `bar_timestamp_source`, and then require **fresh streaming provenance** for main-book entries.

### 7. “Throttle may be too aggressive”

**Modify, do not simply lower it.**

The latest map shows the learning-mode throttle is already 12/hour, not 3/hour. The March 5 report shows it was hit repeatedly after the hotfix burst. The problem is not the one-hour total. The problem is **burst concentration**: too many new names in too short a window after the engine recovered. The fix is a **burst cap** like 4 entries per 15 minutes plus max 2 new symbols per tick, not just a lower hourly ceiling.

### 8. “Verify partial exit sizing”

**Valid to instrument, not valid as an immediate trading fix.**

Partial exits did happen, but they are not the dominant driver of the March 5 loss day. The dominant drivers are entry quality, repeat-entry churn, and learning-mode oversizing. Instrument partials now; retune later.

### 9. “UBER orphaned position/state”

**Validated as a P0 state-consistency fix.**

The March 5 report calls out UBER stale `exit_levels` with no `entry_metadata` as an orphan-state problem. Claude Code should fix this before more trading sessions because state inconsistency corrupts both exits and post-trade learning.

### 10–12. “Track entry_source, time_in_trade_seconds, MFE/MAE”

**Validated and mandatory.**

The improve7 change list says those trade-causal fields were added pre-market on March 5. If the latest deep research report still needs to ask for them, the persistence or reporting path is incomplete. Claude Code needs to ensure they are not just stored, but surfaced in the daily report and in any replay/export path.

---

## Additional critical item the report underweights

### Separate `ranking_score` from `expected_return`

This is the biggest architectural correction I recommend.

The latest map shows:

* the alpha scanner ranks names with a 7-factor composite where ML still carries 25% weight and `ml_score = confidence × abs(predicted_return) × 20`, capped at 1.0,
* the Kelly sizer still uses an edge-over-cost gate requiring `predicted_return >= 2 × spread_cost`, and also uses `predicted_return` inside signal-based Kelly, floors, and conviction sorting,
* and the live engine injects synthetic return floors for non-ML or weak-ML breakout cases: ML floor 0.3%, no-ML range 0.5%–2.0%.

That means heuristic return assumptions are still being fed into both **ranking** and **sizing** as if they were true expected returns. This is the design flaw that can create trades like XLE 92 shares: a name can look “good enough” for ranking, get a synthetic expected return, then clear sizing logic that assumes the edge is statistically meaningful.

**Better architecture:**

* `ranking_score` decides which names are interesting.
* `expected_return` decides whether main-book sizing is justified.
* If `expected_return_source == heuristic`, the trade may qualify for exploration, but not the main book.

That one separation will improve robustness more than another round of threshold fiddling.

---

## Exact implementation plan for Claude Code

Below is the sequence Claude Code should execute. Follow the order. Do not deviate.

### Phase A — P0 fixes (must land together)

#### A1. Enforce regime-scale freeze in code

**Files**

* `backend/organism/kelly_sizer.py`
* `backend/organism/decision_telemetry.py` or equivalent telemetry path

**What to change**
In the regime-scaling step, add a hard guard:

```python
use_evolved_regime_scale = (
    total_trades_across_all_regimes >= 200
    and trades_in_current_regime >= 30
)
if use_evolved_regime_scale:
    regime_scale = evolved_or_default_scale(current_regime)
    regime_scale_source = "evolved"
else:
    regime_scale = STATIC_REGIME_SCALES[current_regime]
    regime_scale_source = "static_frozen"
```

**Static scales to use while frozen**

* `trending_up: 1.20`
* `trending_down: 0.60`
* `chop: 0.50`
* `high_vol: 0.80`
* `low_vol: 1.00`
* `stress: 0.40`
* `unknown: 0.70`

**Additional requirement**
Emit telemetry fields:

* `regime_scale_used`
* `regime_scale_source`
* `total_trade_count`
* `regime_trade_count`

**Why**
The report shows `trending_up` scale at 1.164 with only 93 total trades and losses concentrated there.

---

#### A2. Tighten learning-mode main-book entry quality; route weak names to exploration

**Files**

* `backend/organism/live_engine.py`

**Replace current candidate classification with two tiers**
Current map:

* fitness gate: `0.30 learning / 0.45 production`
* confidence gate: `0.30` baseline, `0.35` in chop

**New rules**
Main book:

* `fitness >= 0.45` always
* `confidence >= 0.40` baseline
* `confidence >= 0.45` in `chop`, `high_vol`, or `trending_down`

Exploration:

* `fitness >= 0.30`
* `confidence >= 0.25`
* `missingness <= 0.25`
* `liquidity >= 10k avg vol/bar`

Behavior:

* Below main-book threshold but above exploration threshold → mark as exploration candidate.
* Below exploration threshold → reject outright.

**Why**
March 5 losers cluster in low-fitness names while higher-fitness names held up better.

---

#### A3. Replace current symbol breaker with session-aware loss gating

**Files**

* `backend/organism/live_engine.py`
* wherever symbol-level session state is stored/persisted

**Current rule**

* Ban if `2 consecutive losers OR daily P&L <= -$15`

**New rule**
For LONG_ONLY learning mode, ban symbol for the rest of the session if any of these hold:

1. `closed_trades_today >= 2 and wins_today == 0`
2. `realized_pnl_today <= -max(25.0, equity * 0.0010)`
3. `stop_loss_exits_today >= 2 within rolling 30 minutes`

**Important**
Cooldown expiration must **not** reset symbol session stats.

**Why**
WMT lost three times and still kept getting re-entered because cooldown and the current breaker logic were too weak.

---

#### A4. Reduce learning-mode risk floor and add explicit dollar-risk cap

**Files**

* `backend/organism/kelly_sizer.py`

**Current logic**

* pre-Kelly floor uses `0.25% equity / (atr × 1.5)` with confidence scaling
* 8% intraday max position cap

**New logic**
When `trade_count < 200`:

* base floor risk budget = `0.10% equity`, not `0.25%`
* max notional per position = `5% equity`
* max dollar risk per trade = `0.10% equity`

Add a post-share-calculation clamp:

```python
risk_per_share = abs(entry_price - stop_loss)
max_risk_dollars = equity * 0.0010
max_shares_by_risk = floor(max_risk_dollars / max(risk_per_share, 1e-6))
shares = min(shares, max_shares_by_risk)
```

Then enforce:

```python
notional_cap_learning = equity * 0.05
shares = min(shares, floor(notional_cap_learning / entry_price))
```

**Why**
The XLE 92-share trade should have been impossible in learning mode.

---

#### A5. Block LONG_ONLY main-book entries in `trending_down`; add regime-transition cooldown

**Files**

* `backend/organism/live_engine.py`

**Add rules**
Main-book entries:

* if `LONG_ONLY and regime == "trending_down" and now >= 10:00 ET`: block new main-book entries
* exploration may still proceed

Regime transition guard:

* if regime changes from `trending_up` to `high_vol` or `trending_down`, block new main-book entries for 120 seconds

**Why**
March 5 report explicitly calls out late-day `trending_down` longs as a loss source.

---

#### A6. Fix orphan-state cleanup

**Files**

* `backend/organism/live_engine.py`

**Add startup and every-tick cleanup**

* If `exit_levels[symbol]` exists and `entry_metadata[symbol]` does not, and broker has no position: purge all local state for symbol and log `orphan_state_purged`
* If broker has a position but local entry state is missing: either reconstruct full state immediately or flatten that broker position if reconstruction fails safely

**Why**
The March 5 report calls out UBER orphaned state explicitly.

---

### Phase B — P1 structural fixes

#### B1. Separate `ranking_score` from `expected_return`

**Files**

* `backend/organism/alpha_scanner.py`
* `backend/organism/live_engine.py`
* `backend/organism/kelly_sizer.py`
* candidate dataclasses / typed objects

**Add fields**

* `ranking_score`
* `expected_return`
* `expected_return_source` in `{ml, calibrated_breakout, heuristic}`

**Immediate rule**

* If `expected_return_source == "heuristic"`, do not allow main-book sizing.
* Those candidates may go to exploration only.

**Interim implementation**
For pure breakout additions:

* keep the current breakout ranking
* set `expected_return_source = "heuristic"`
* prevent the Kelly main-book path from using it as true edge

**Why**
Current architecture still lets synthetic return floors influence sizing and cost-gating as if they were real expected edge.

---

#### B2. Use `effective_confidence` for gating and sizing

**Files**

* `backend/organism/ml_signal.py`
* `backend/organism/live_engine.py`
* `backend/organism/alpha_scanner.py`
* `backend/organism/kelly_sizer.py`

**Add**

* `raw_confidence`
* `effective_confidence`

**Learning-mode rule**
If bucket calibration exists:

```python
effective_confidence = min(raw_confidence, empirical_precision_for_bucket)
```

If not:

```python
effective_confidence = raw_confidence * 0.75
```

Use `effective_confidence` for:

* Gate 11
* alpha `ml_score`
* Kelly confidence scaling
* ML floor eligibility

Keep `raw_confidence` in telemetry for calibration analysis.

**Why**
March 5 explicitly shows overconfidence: predicted 60%, actual 23%.

---

#### B3. Add data-source provenance and require fresh stream for main-book entries

**Files**

* `backend/organism/live_engine.py`
* streaming provider module
* telemetry structures

**Per symbol/tick fields**

* `data_source = streaming | rest_fallback | stale`
* `stream_age_seconds`
* `bar_timestamp_source = stream | rest | wallclock_only`

**Entry rule**
Main-book entries require:

* `data_source == "streaming"`
* `stream_age_seconds <= 20`

Exploration can optionally still use `rest_fallback`, with explicit telemetry.

**Why**
The stale-data gate bug was real on March 5, and you still need provenance, not just a binary stale/fresh flag.

---

### Phase C — P2 instrumentation and controlled tuning

#### C1. Do not retune FTF yet

Keep the improve7 FTF design:

* chop delay 12 bars
* others 7 bars
* `trending_up/low_vol/high_vol` disabled
* chop losers-only, winners tighten stop

Only add report breakdowns:

* FTF frequency by regime
* FTF frequency by `entry_source`
* FTF MFE after tighten-stop vs hard exit

The March 5 report already says it appears improved.

---

#### C2. Add burst cap instead of changing hourly throttle

**Files**

* `backend/organism/live_engine.py`

**Keep**

* `12/hr` learning mode throttle

**Add**

* max 4 new entries per rolling 15 minutes
* max 2 new symbols per tick
* re-entry cooldown after stop loss: 30 minutes
* re-entry cooldown after FTF loss: 10 minutes
* keep profit-exit cooldown at current shorter value

**Why**
The March 5 issue was concentrated burst entry after resumption, not just hourly totals.

---

#### C3. Surface trade-causal fields in reports, not just storage

**Files**

* `backend/organism/continuous_learner.py`
* report generator / exporter

Make sure daily reports include:

* `entry_source`
* `regime_at_entry`
* `regime_at_exit`
* `mfe`
* `mae`
* `bars_held`
* `time_in_trade_seconds`
* `is_exploration`

**Why**
Improve7 says these fields were added, but the March 5 analysis still asks for them as data-collection needs, which means the reporting surface is incomplete.

---

## Parameters Claude Code should set after implementation

Use these values exactly for the next learning-mode iteration:

| Parameter                          |                      Current |                                                                                 New |
| ---------------------------------- | ---------------------------: | ----------------------------------------------------------------------------------: |
| Main-book fitness min              |    0.30 learning / 0.45 prod |                                                                     **0.45 always** |
| Exploration fitness min            |                     implicit |                                                                            **0.30** |
| Main-book confidence min           |          0.30 / 0.35 in chop |                              **0.40 baseline, 0.45 in chop/high_vol/trending_down** |
| Learning risk-budget floor         |                 0.25% equity |                                                                    **0.10% equity** |
| Learning max position cap          |                  8% intraday |                                                                     **5% intraday** |
| Learning max dollar risk / trade   |                none explicit |                                                                    **0.10% equity** |
| Symbol day-ban                     | 2 consecutive losers OR -$15 | **2 closed losses and 0 wins, OR -max($25, 0.10% equity), OR 2 stop-losses in 30m** |
| Main-book longs in `trending_down` |                      allowed |                                                          **blocked after 10:00 ET** |
| Regime transition cooldown         |                         none |                                                     **120s after up→high_vol/down** |
| Burst cap                          |                         none |                                           **4 entries / 15m, 2 new symbols / tick** |
| Stop-loss re-entry cooldown        |                ~100s generic |                                                                      **30 minutes** |
| FTF-loss re-entry cooldown         |                ~100s generic |                                                                      **10 minutes** |

Grounding for current values: learning fitness gate, confidence gate, 12/hr throttle, 8% cap, and current FTF behavior are all documented in the latest map.

---

## What Claude Code must **not** change right now

Do not do these in the next patch set:

* Do **not** reset the brain again.
* Do **not** globally disable FTF.
* Do **not** retune partial exits before adding telemetry.
* Do **not** lower the learning hourly throttle unless you first add burst control.
* Do **not** keep heuristic breakout `predicted_return` eligible for main-book sizing.
* Do **not** leave the learning-mode main-book fitness gate at 0.30.

---

## One direct answer to your main concern

Yes — there is still something fundamental you were not seeing.

The main blind spot is that the platform still behaves as if a ranked opportunity is the same thing as a calibrated edge. It is not. The alpha scanner is useful for **ranking** names, but the sizer should only size a trade when expected return is grounded in a real edge estimate, not a fallback heuristic or synthetic floor. Until you separate those two concepts, you will keep getting polished-looking decision trees that still produce weak trades and occasional outsized mistakes.

Next moves

* Have Claude Code implement Phase A exactly first, in one branch.
* After that, implement B1 and B2 before another live learning day.
* Export one post-fix replay report showing symbol bans, regime-scale source, and per-trade causal fields.
* Do not promote any new evolution/regime-scale changes until the March 5 contaminated session is excluded from scale updates.
