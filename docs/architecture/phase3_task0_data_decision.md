# Phase 3 — Task 0: Data-validity decision record

**Status: OPEN until Task 5 (freeze). Current operating state: IEX (free plan).**

## Current state (2026-07-07)
- `ALPACA_DATA_FEED=iex` since 2026-07-06 — the Algo Trader Plus (SIP) subscription was
  cancelled and the user chose to stay on the free plan.
- `ORGANISM_MIN_AVG_DOLLAR_VOLUME=50000` — liquidity-gate floor recalibrated from the $1M
  code default, calibrated against measured IEX minute bars (IEX carries ~2.5% of
  consolidated dollar-volume; $50k IEX-observed ≈ $1M consolidated). With the $1M floor on
  IEX bars, only NVDA passed.
- Measured IEX dollar-vol/min (2026-07-06, quiet afternoon hour): NVDA $1.29M, AAPL $513k,
  V $377k, WMT $228k, JNJ $195k, COST $151k, SH $54k, PSQ $41k.

## Known IEX degradations (from the buildout plan, Reality B)
- SH/PSQ hedge legs bar-starved: 10–13 bars/hr vs 61; hover at the $50k floor.
- COST ~30/61 bars/hr.
- Volume / relative-volume features computed on a thin, noisy slice.
- Quotes are IEX-only (not NBBO) → spread-cost estimates noisier.
- Price signals on liquid names and paper fills unaffected.

## The decision (binds at Task 5, not before)
The data feed only becomes load-bearing when the forward clock starts (Task 5 freeze).
Switching the feed before the freeze costs nothing; switching after resets the clock.
Therefore:

- **(a) Re-subscribe to SIP (~$99/mo) for the forward-test window** — recommended by the
  plan; produces the stronger, cleaner verdict.
- **(b) Accept an IEX-limited verdict** — valid but weaker: a FAIL answers "no edge visible
  on ~2.5% of the tape," and requires first resolving the hedge-leg problem (replace/
  special-case/drop SH+PSQ), validating the $50k floor against a full live session's
  gate-rejection telemetry, and confirming the in-play universe isn't starved.

**The user must confirm (a) or (b) before Task 5 executes.** Whichever is chosen is recorded
as a first-class fact in `param_freeze.json` so the verdict is never read out of its data
context. Build work (Tasks 1–4) proceeds identically under either choice.
