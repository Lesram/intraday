# Pre-300 Evolution Readiness Audit

**Current trades**: 293. **Freeze exit at**: 300. **Trades remaining**: 7 (~1 session).

## What activates at trade 300

When `total_trades >= 300`, `apply_evolved_params()` fires at three code sites:
1. **Background trainer completion** (`live_engine.py:677`): after async retrain, evolved params applied to scanners/kelly/exits
2. **Engine initialization** (`live_engine.py:931`): on boot, evolved params applied to all components
3. **Retrain/evolve cycle** (`live_engine.py:4300`): periodic re-evolution of parameters

### Exact parameter values that will activate

**Alpha scanner weights** (from `evolved_params.json`):
| Weight | Evolved | Current hardcoded |
|---|---:|---:|
| ML | 0.3558 | 0.25 (default) |
| Volume | 0.1949 | 0.10 |
| Momentum | 0.1529 | 0.15 |
| Breakout | 0.1461 | 0.20 |
| Regime | 0.1000 | 0.05 |

**ML weight increases from 25% to 36%.** This gives ML more influence on candidate ranking. Given the confidence inversion concern (ML contamination), this could amplify the problem — OR it could be neutral if the ML models have improved with 300 trades of calibration.

**Direction thresholds** (ML signal generation):
| Threshold | Evolved | Current |
|---|---:|---:|
| Buy | 0.5555 | 0.52 |
| Sell | 0.4484 | 0.48 |

Buy threshold **increases** (harder to trigger buys). Sell threshold **decreases** (easier to trigger sells). Net effect: slightly more conservative on entries, slightly more aggressive on shorts/sells.

**Exit/sizing scales**:
| Scale | Evolved | Effect |
|---|---:|---|
| stop_atr_scale | 0.985 | Stops 1.5% tighter (negligible) |
| trailing_distance_scale | 0.8916 | Trailing stop ~11% tighter |
| partial_tp_pct | 0.20 | Partial TP at 20% (was 30%) |
| regime_size chop | 0.50 | Chop positions 50% of base (conservative) |
| regime_size stress | 0.30 | Stress positions 30% of base (very conservative) |

**Trailing distance scale 0.8916** is concerning — it TIGHTENS the trailing stop by ~11%. Given that trailing-stop giveback is already a known leak, tightening it further would make the problem worse. However, Exp4 widens the chop trailing to 5.0× ATR, which may offset this scale (5.0 × 0.89 ≈ 4.45× ATR, still wider than the current 3.0× ATR).

## Risk assessment

### LOW risk parameters (safe to activate):
- stop_atr_scale 0.985 → negligible 1.5% tightening
- partial_tp_pct 0.20 → takes profit at 20% instead of 30% (less aggressive, more conservative)
- regime_size chop 0.50 → half-size positions in chop (reduces IWM-class outlier risk)
- regime_size stress 0.30 → tiny positions in stress (good)
- direction_threshold_buy 0.5555 → harder to buy (slightly more selective)

### MEDIUM risk parameters (acceptable but monitor):
- alpha_weight_ml 0.3558 → ML gets 36% instead of 25% of alpha score. If ML calibration is good, this helps. If ML is anti-predictive, this amplifies the problem.
- trailing_distance_scale 0.8916 → tightens trailing. Partially offset by Exp4's chop widening.

### NO HIGH risk parameters found.

## Recommendation

### **Allow evolution at 300: CONDITIONAL YES**

Allow activation BUT:

1. **Monitor the first 2 sessions after trade 300 for behavioral changes** — specifically watch:
   - Entry count change (direction thresholds might reduce entries)
   - Position size change in chop (should halve with regime_size 0.50)
   - Trailing-stop behavior (tighter scale vs Exp4 widening)
   - Alpha candidate quality (ML weight increase)

2. **The chop regime_size 0.50 is actually helpful** — it would have prevented the IWM -$41.52 outlier by halving the position. This is the single most valuable evolved parameter.

3. **If ML contamination is confirmed by Exp3 data**, consider manually overriding `alpha_weight_ml` back to 0.25 in `evolved_params.json` before the next session. This is a 1-line JSON edit, not a code change.

## Exact recommended action before trade 300

1. **No code changes needed** — evolution activation is the designed behavior.
2. **Log the moment it activates** — the "apply_evolved_params" log entry will show in the post-close report.
3. **Compare pre-300 vs post-300 metrics** in the next observation report:
   - Entry count per session
   - Average position size
   - Pyramid_cut frequency (should decrease if trailing tightens)
   - Win rate
   - Expectancy
4. **Have the manual override ready**: if metrics degrade significantly, edit `organism_brain/evolved_params.json` to restore conservative defaults and restart.
