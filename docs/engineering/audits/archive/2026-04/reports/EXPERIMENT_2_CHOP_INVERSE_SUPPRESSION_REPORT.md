# Experiment 2 — Suppress inverse ETF entries in chop regime

**Commit**: `d79cae0`
**Parent**: `6754223` (observation tooling, on top of Exp1A `ab54b2f`)
**Status**: COMMITTED, NOT deployed. Ready for deployment after Exp1A observation.

## Hypothesis

PSQ and SH (inverse ETFs) are designed for trending_down hedging (improve9), but in chop regime they produce 0% win rate: 6 trades, -$28.54, 4/6 never went green. Suppressing their entries in chop eliminates the second-largest identified leak after pyramid_cut exits.

## Exact change

In `backend/organism/live_engine.py`, inside the entry loop (~line 2389), before the existing position check:

```python
_INVERSE_ETFS_CHOP_SUPPRESSED = frozenset({"PSQ", "SH"})

if sz.symbol in _INVERSE_ETFS_CHOP_SUPPRESSED and regime == "chop":
    logger.info("Exp2: inverse ETF entry suppressed in chop: ...")
    continue
```

**What is NOT changed**:
- Non-chop regime behavior for PSQ/SH — fully preserved
- All non-inverse symbols — completely unaffected
- Exit logic, sizing, ML, persistence, walk-forward — untouched
- Experiment 1A gate — untouched (both experiments can coexist)

## Files changed

| File | +/- |
|---|---|
| `backend/organism/live_engine.py` | +26 |
| `tests/test_experiment_2_inverse_chop_suppression.py` | +119 (new) |

## Tests — 114/114 passed

- 7 new Exp2 tests (PSQ blocked chop, SH blocked chop, PSQ allowed non-chop, SH allowed non-chop, non-inverse unchanged, log format, set boundary)
- 107 organism regression subset — PASS

## Expected measurable effect

Based on Apr 7-10 baseline (32 real trades):
- 6 PSQ/SH trades in chop would be eliminated → +$28.54 improvement
- 0 capital allocated to systematically losing inverse-ETF positions
- Freed-up position slots available for non-inverse entries
- **Expected: +$25-30 per 4-session window**

## When to deploy

| Scenario | Action |
|---|---|
| Exp1A succeeds (3-5 session observation) | Deploy Exp2 as the next layered experiment |
| Exp1A fails | Deploy Exp2 independently (it's orthogonal to exit logic) |
| Exp1A inconclusive | Deploy Exp2 to add a second independent signal |

Exp2 is orthogonal to Exp1A — one changes exit timing, the other changes entry filtering. They can coexist without interference.

## Rollback

```bash
git revert d79cae0
```

## Deployment

When ready: `docker compose -f docker-compose.paper.yml up -d --build api` (container will pick up both Exp1A + Exp2 since Exp2 sits on top of Exp1A's commit).
