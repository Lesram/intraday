# Phase C-1 Design — Separation of Ranking / Direction / Expected Return / Size

**Status:** DESIGN — RC-3+ candidate, multi-day implementation, NOT a weekend item
**Branch:** `rc-1.5-curated` (design only; no code change)
**Author:** Saturday 2026-04-25 weekend sprint, S9
**Builds on:** Track 1 forensic findings, MEMORY.md Phase C planning

## Problem statement

The current candidate-selection-to-execution pipeline conflates four responsibilities:

| Responsibility | What it answers | Currently lives in |
|---|---|---|
| **Ranking** | "Which symbols are the most attractive trade candidates *right now*?" | `alpha_scanner.composite_score` |
| **Direction** | "Long or short?" | `alpha_scanner.direction` (driven by ML) |
| **Expected return** | "If we take this trade, what return should we expect?" | `ml_signal.predicted_return` |
| **Size** | "How many shares to put on?" | `kelly_sizer` (uses predicted_return as input) |

The conflation problem:

- ML `predicted_return` is the input to BOTH expected-return AND direction (sign of pred). If ML has a long bias (Track 1 found +0.4% bias), it injects into both.
- `composite_score` for ranking includes ML signal weight (0.5 in production). So ML's noise drives ranking too.
- A bad ML signal contaminates all four outputs.

Visible symptoms (from Track 1):
- Correlation(predicted_return, actual_return) = 0.056. ML signal is essentially noise.
- 76% of live trades have composite < 0.45. Composite is dominated by ML.
- Tail predictions (≥1% pred) anti-predict (25% wr vs 31% baseline).

## Vision

Each of the four responsibilities should be independently designable, testable, and replaceable:

```
                 Ranking (different model)
                  |
  Universe → ┌──────┐
             │ Rank │ → top-N candidates ────┐
             └──────┘                        │
                                             ↓
              Direction (different model)
              ┌──────────┐
              │ Predict  │ → long/short for each candidate
              └──────────┘
                                             ↓
              Expected return (different model)
              ┌──────────┐
              │ Forecast │ → magnitude for each candidate
              └──────────┘
                                             ↓
              Size (deterministic mechanics)
              ┌──────────┐
              │  Kelly   │ → shares
              └──────────┘
```

Each box can be a different model (or rule), trained on different data with a different target. A bad direction model can be swapped without touching ranking.

## Architectural changes required

### New: `RankingModel` interface

```python
class RankingModel(Protocol):
    def score(self, features_by_symbol: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Return a ranking score for each candidate symbol. Higher = more attractive.
        Does NOT specify direction. Does NOT specify magnitude."""
```

Initial implementation: weighted blend of breakout score + tension + volume / atr regime. NO ML in ranking.

### New: `DirectionModel` interface

```python
class DirectionModel(Protocol):
    def predict_direction(self, symbol: str, features: pd.DataFrame) -> tuple[float, float]:
        """Return (direction, confidence). direction in {-1, 0, +1}, confidence in [0,1]."""
```

Initial implementation: same XGBoost classifier we have today (`ml_signal._clf`), but isolated to this concern. Output is a direction probability, period — not a ranking input.

### New: `ExpectedReturnModel` interface

```python
class ExpectedReturnModel(Protocol):
    def predict_return(self, symbol: str, direction: float, features: pd.DataFrame) -> float:
        """Conditional expected return GIVEN a direction is taken."""
```

Initial implementation: regressor (`ml_signal._reg`) but only invoked AFTER direction is decided.

### `KellySizer` already separated

Current `kelly_sizer` already takes `predicted_return` as an argument. Its responsibility is clean. No change.

## Cleanup of `alpha_scanner.composite_score`

Currently `composite_score = 0.50*ml + 0.30*breakout + 0.20*tension`. After Phase C-1:

`composite_score = ranking_score (no ML)`

Direction comes from `DirectionModel`. Expected return comes from `ExpectedReturnModel`. Size from `KellySizer`. Ranking is its own thing.

## Migration plan (sketch — NOT for RC-1.5)

**Stage 1 (RC-3 candidate):**
- Define the three Protocol classes
- Wrap existing code paths to conform: `MLSignalGenerator` becomes both a `DirectionModel` and an `ExpectedReturnModel`
- Implement `RankingModel` as breakout+tension only (no ML)
- Test that behavior is unchanged when `RankingModel = breakout+tension` and direction/return-models = current ML
- Keep production gate using composite (RC-1.5 fix) — but composite now no longer drives ranking, only the gate

**Stage 2 (RC-4):**
- A/B test: compare ranking with breakout+tension vs ranking with ML included. If breakout+tension ranking outperforms, retire ML from ranking permanently.

**Stage 3 (RC-5+):**
- Train DIFFERENT models for direction vs return. The current single `MLSignalGenerator` does both with shared features. Splitting them lets each be optimized separately.

## Why not now (RC-1.5/RC-2)

This is a **multi-day refactor** with broad surface area:
- Touches `alpha_scanner.py`, `ml_signal.py`, `kelly_sizer.py`, `live_engine.py`, all the tests
- Behavior must be exactly preserved during transition
- Real engineering risk if we ship without thorough testing

The composite-gate fix in RC-1.5 already addresses the IMMEDIATE harm (ML signal admitting weak entries). Phase C-1 is about making FUTURE improvements easier, not fixing today's bug.

## When to actually do it

After:
- RC-1.5 deployed, 10+ sessions of stable observation
- RC-2 (regime + ML weight) shipped
- We have data on whether RC-2's ML-weight drop helps or hurts
- A second engineer / model-trainer collaborator joins (this is too big for solo without review)

Realistic timing: 6-12 weeks from RC-1.5 deploy.

## Acceptance criteria for the eventual implementation

1. All existing tests pass
2. Live behavior bit-identical when ranking/direction/return models are exact wrappers of current code
3. New unit tests for each Protocol implementation
4. Replay-validated A/B between breakout-only ranking and ML-included ranking
5. Documentation in `docs/architecture/` for each model interface
