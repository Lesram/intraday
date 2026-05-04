# Experiment 3 Prep — Confidence inversion / ML contamination instrumentation

**Commit**: `ce06d41`
**Parent**: `d79cae0` (Exp2)
**Status**: COMMITTED, NOT deployed. Read-only instrumentation, no trade impact.

## What this adds

Non-invasive side-by-side confidence logging at the alpha candidate evaluation point in `live_engine.py`. For every alpha candidate (every tick, when market is open):

| Field | Source | Purpose |
|---|---|---|
| `confidence_live` | `0.50*ml + 0.30*breakout + 0.20*tension` | What the system actually uses |
| `confidence_bt_only` | `0.65*breakout + 0.35*tension` | What learning-mode would produce |
| `confidence_ml_component` | `c.ml_signal.confidence` | The raw ML value being weighted |
| `gate_pass_live` | `confidence >= _MIN_MAIN_CONF` | Would the candidate pass? |
| `gate_pass_bt_only` | `conf_bt_only >= _MIN_MAIN_CONF` | Would it pass WITHOUT ML? |

- Logged at **DEBUG** level (won't appear unless log level is lowered)
- Also added as fields on `cand_dicts` entries for candidates that pass the gate — available in the decision telemetry pipeline for post-session analysis
- **Does NOT change any gating decision, threshold, or trade eligibility**

## What evidence this will produce

After deployment and 1+ sessions of data, we can answer:

1. **How often does ML boost a weak candidate past the gate?** (gate_pass_live=True, gate_pass_bt_only=False → ML-boosted entries)
2. **How often does ML suppress a strong candidate below the gate?** (gate_pass_live=False, gate_pass_bt_only=True → ML-suppressed entries)
3. **Do ML-boosted entries win or lose?** Cross-reference with trade outcomes
4. **Is the confidence inversion regime-specific?** Compare in chop vs other regimes
5. **Does reverting to learning-mode weights in chop improve expected edge?**

## What it does NOT do

- Does not change the confidence formula
- Does not change thresholds
- Does not change ML model weights or training
- Does not add/remove any entry gate
- Does not affect exit logic or persistence

## Tests — 115/115 passed

- 8 new tests (production-mode formula, learning-mode formula, missing ML, NaN ML, learning-mode ML=0, gate equivalence, ML drag-down, candidate dict fields)
- 107 organism regression — PASS

## When to deploy

Deploy stacked with Exp2 after Exp1A observation, OR independently if ML investigation becomes the priority. The instrumentation is read-only so deploying it adds zero risk and maximum observability.

## Rollback

```bash
git revert ce06d41
```
