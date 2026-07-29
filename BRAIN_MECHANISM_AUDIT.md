# Brain Mechanism Audit (S15)

**Question:** Is the platform smart enough? What does "the brain" actually do?
**Answer:** It is **disciplined, not smart.** The brain is a rule-based trading system with a learning component grafted on. The rules dominate; the learning is small-magnitude and partial.

---

## What "the brain" actually comprises

| Component | File | LOC | Role |
|---|---|---|---|
| `MLSignalGenerator` | `ml_signal.py` | 862 | XGBoost classifier (direction) + regressor (magnitude) |
| `ContinuousLearner` | `continuous_learner.py` | 529 | Retrain triggers, acceptance gate, drift detection |
| `EvolutionEngine` | `self_evolution.py` | 1247 | Evolves params (thresholds, scales) + per-symbol fitness |
| `RegimeDetector` | `regime.py` | 480+ | Market regime classification + per-regime parameter selection |
| `GovernanceController` | `governance.py` | 304 | Frozen / halted / drawdown-kill / circuit breakers |
| `BrainPersistenceManager` | `brain_persistence.py` | 1869 | Save/restore with F1-F4 hardening |

Combined: ~5,300 LOC of "brain" — about 25-30% of the platform's strategy code.

---

## What actually LEARNS (changes over time from data)

| Variable | Where it changes | How fast | Track-1 finding |
|---|---|---|---|
| **ML classifier + regressor** | `continuous_learner.retrain()`, every 60 bars or on drift | Fast (every retrain = full refit) | corr(pred, actual) = 0.056 → essentially noise |
| **Symbol fitness** | `EvolutionEngine._evolve_symbol_fitness`, post-300 trades | Slow EMA (alpha=0.30, max_shift=0.20) | Modest impact (0.84-1.18× multiplier) |
| **Direction thresholds** | `EvolutionEngine._evolve_direction_thresholds`, post-300 | Slow EMA | Currently buy=0.5555, sell=0.4484 (small drift from neutral 0.55/0.45) |
| **Stop ATR scale** | `EvolutionEngine._evolve_stop_atr_scale`, post-300 | Slow EMA, range [0.5, 1.8] | Currently 0.985 (essentially unchanged) |
| **Trailing distance scale** | `EvolutionEngine._evolve_trailing` | Slow EMA | Currently 0.892 |
| **Regime size scales** | `EvolutionEngine._evolve_regime_size_scales` | Slow EMA | Currently chop=0.5, trending_up=1.2 — these are the static defaults, evolution barely moved them |
| **Confidence calibration** | `MLSignalGenerator` calibration tracking | Per-prediction | Active but ML predictions are uncalibrated noise |

### The honest accounting

In `learning_state.json`:
- generation = 124 (number of retrains)
- total_trades = 396
- best_sharpe = 3.4363 (from generation 26 — over 100 generations ago)
- drift_events = 0 (drift detection never fired in 124 retrains)

**Nine generations ago (gen 115), evolution_engine had moved most params less than 5% from their defaults.** The "learning" is mathematical EMA updates with strict bounds and slow alpha. By design, params can't swing wildly. The flip side: they can't learn much either.

---

## What's STATIC (rules, not learning)

| Rule | Where it lives | Magnitude of impact |
|---|---|---|
| Composite formula weights (0.50/0.30/0.20) | `live_engine.py` | LARGE — drives all gating |
| Regime classifier thresholds | `regime.py` | LARGE — determines which param set is used |
| Pyramid triggers (+1.5R, +3.0R, -1.0R, -0.7R) | `pyramider.py` | LARGE — determines sizing trajectory |
| Universe (22 symbols) | startup config | LARGE |
| Time-of-day rules (EOD 15:45 / 15:58) | `live_engine.py` | LARGE |
| Drawdown-kill (20%) | `governance.py` | LARGE — single-shot circuit breaker |
| 79 features | `ml_features.py` | LARGE — defines the input space |
| Risk budget percentages | `kelly_sizer.py` | LARGE |
| Bar timeframe (1-min) | startup config | LARGE |
| Bar boundary entry only | `live_engine.py` | LARGE |
| Tick interval (10s) | `scheduler.py` | LARGE |

These are MORE consequential than anything that "learns." The learning only operates within the channels that the static rules define.

---

## Coordination: do the components actually work together?

Yes. The brain saves periodically through `BrainPersistenceManager` (F1-F4 hardened). On startup, all components restore from the same brain state:

```
Container startup
  ↓
BrainPersistenceManager.load()
  ↓
  ├─ MLSignalGenerator: clf, reg, calibration
  ├─ ContinuousLearner: state (gen, retrain_count, drift)
  ├─ EvolutionEngine: evolved_params (fitness, thresholds, scales)
  ├─ GovernanceController: frozen/halted state, drawdown_triggered_at
  └─ RegimeDetector: history, smoothed_probs
```

Verified in current state: manifest.json + learning_state.json + governance_state.json + regime_state.json + evolved_params.json all coherent at gen=124, total_trades=396.

**This part of the brain is sound.** The state tracking and persistence is the most-developed and battle-tested piece (F1-F4 fixes addressed real corruption issues earlier). It's not the limitation.

---

## What's missing for the platform to be actually "smart"

| Capability | Current state | Gap |
|---|---|---|
| **Adapts strategy itself** (not just params) | NO — rule structure is fixed | Real intelligence would explore different gate variables, different exit policies, different feature subsets and pick what works. We don't. |
| **Notices when strategy stops working** | PARTIAL — `recent_accuracy < 0.40` triggers retrain (line 286 of continuous_learner) | But `correct_direction = pnl > 0` is degenerate (Track 1 finding). The metric is broken. |
| **Explores alternatives during exploitation** | NO — exploration was removed entirely | This is intentional (improve9 H1 hardening removed exploration). But it means we never test "what if we did X differently?" |
| **Meta-learning** (learning to learn better) | NO | Not even a backlog item. |
| **Causal reasoning** (why did this trade work?) | NO — attribution is correlation only | `attribution.py` exists; not deeply used |
| **Long-term planning** (multi-day, multi-week strategies) | NO — every decision is per-tick | Bar-boundary entries with per-tick decisions only |
| **Cross-strategy ensemble** | NO — single strategy | One model, one ranking, one direction logic |
| **External information** (news, earnings, options flow, dark pools) | NO — bars + scanner only | Phase C-2 microstructure scoping |

---

## So is the platform smart enough?

**For Stage-1 paper trading: YES.** It's stable, observable, persistence-hardened, has risk controls, retrains its model, evolves its parameters within bounds. That's enough operational sophistication to run unattended for weeks.

**For Stage-1 tiny capital live: YES, with caveats.** The infrastructure (drawdown-kill, notional cap, daily max-loss in eb90fa3, alert wiring, brain persistence) is real. The platform won't blow up. It just won't make money either, given the underlying ML is uncalibrated noise.

**For real edge / scale to meaningful capital: NO.** Not yet. The "smart" pieces (ML, evolution) are doing modest work; the dominant behavior comes from static rules that haven't been re-examined in months. Becoming actually smart is a research project, not a weekend sprint.

---

## What "smart" upgrades would actually move the needle

Ranked by expected impact / effort:

### Tier 1 — Direct wins (RC-3 to RC-6)

1. **Fix the broken `correct_direction = pnl > 0` metric in `continuous_learner.recent_accuracy`.** It's currently triggering retrains based on win rate, not direction prediction quality. They're confounded. **Should be: `recent_directional_accuracy = sum(sign(predicted) == sign(actual_return))`. ~10 LOC change.**
2. **Same-holdout new-vs-old gate** (already documented in S6 Data Leakage Audit). RC-3 candidate.
3. **Predict longer horizon return** (5-10 bars instead of 1) per ML retrain redesign doc S11. RC-4.
4. **Train ML on candidate-bars-only** (filtered to inference distribution) per S11. RC-5.

### Tier 2 — Structural (RC-7 to RC-10+)

5. **Regime-conditional ensemble**: separate model per regime (after RC-2 regime fix proves out).
6. **Strategy variant exploration**: a second strategy running in parallel as shadow telemetry. E.g., reverse-momentum strategy logged but not executed. After 100+ trades, compare. Discover whether reverse-momentum works better on this universe. **This is the closest the platform could come to "exploring alternatives."**
7. **Add a meta-rule selector**: trained on which regime+symbol+time-of-day combinations produce profitable trades. Use as a top-level filter ("don't trade NVDA in chop after 14:00 ET"). Simple decision tree, very interpretable.

### Tier 3 — Infrastructure for real intelligence (multi-month)

8. **Microstructure data feed** (Phase C-2) — gives the ML a chance at real edge.
9. **News / sentiment integration** — event-conditional alpha.
10. **Causal attribution framework** — beyond correlation. Useful for understanding which decisions actually contributed to outcomes.

---

## Recommendation

**Don't add "smarter" components before fixing the obvious mechanical issues.** The brain isn't dumb because it lacks intelligence — it's dumb because:
- The composite gate was bypassed (RC-1.5 fix)
- The regime classifier was wedged in chop (RC-2 fix, shadowed in RC-1.5)
- The ML signal is uncalibrated noise (RC-2 weight drop, RC-3+ retrain redesign)
- The "directional accuracy" metric is degenerate (RC-3 candidate, ~10 LOC)

Each of these is a small fix attacking a specific problem. None of them require AI breakthroughs. After they all ship and stabilize, *then* you have a clean substrate to add genuinely smart components on top. Adding "smart" features to a broken substrate is how technical debt accumulates.

The honest verdict: **the platform isn't smart, but it's becoming honest about not being smart.** That's prerequisite to becoming smarter later.
