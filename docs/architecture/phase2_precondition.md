# Phase 2 PRECONDITION — the honest OOS measuring instrument (work order)

**Status:** Task 0 ✅ (clock FROZEN_AT 2026-06-27T02:33Z) · Task 1 ✅ (real holdout
+ teeth-test) · Tasks 2/3 pending (forward corpus + verdict gate — accumulation-
gated). **Branch:** `phase2-precondition` off `intra-2.0-phase1`.
**Gate:** this is the PRECONDITION for Phase 2, not a Phase-2 step. Do NOT run any
config sweep or flip any `live_routing` until every acceptance gate below is green.
**Why first:** step 5b's whole purpose is to test whether a redesigned confidence
model beats flat sizing on costed OOS expectancy. You cannot run that test on an
instrument that can't measure OOS. The instrument is upstream of every verdict it
will ever produce — build it before the thing it measures.

## The trap this work order exists to close
`scripts/strategy_backtester.py` today has `holdout_frac`, which **only restricts
the evaluation window**. It looks like a holdout, is labeled like a holdout, and
is still in-sample if the strategy params overlap the "test" window. Shipping that
as "the OOS harness" is the half-fix that makes the whole project's discipline
fail silently — the harness would happily report flattering in-sample t-stats and
nobody would see the leak. The acceptance bar here is therefore NOT "the harness
has a holdout"; it is "prove the test trades were taken by params that never saw
the test data."

## PROVENANCE FINDING (settled — drives the corpus decision; record it permanently)
The live momentum thresholds (`_observable_direction`: 0.005 / 0.010 / 0.60 / 0.50)
have **no reconstructable fit-date**. `git log -S` traces them across `improve4/5`,
`improve9` (AIA deep research), and Task D — set and re-adjusted *iteratively
across the entire Mar–Jun 2026 live period* using observations from that period.

State this as the finding, not as a failed search. **The conclusion is not "we
couldn't find a tuning date so we'll go forward-only." It is "we established these
params have NO reconstructable fit-date; therefore ALL pre-cutoff data is
contaminated BY CONSTRUCTION."** That distinction is load-bearing: six months out,
someone will ask "we have all this history, why wait on forward data?" — and the
answer must be a written, settled fact, not a re-litigable judgment call. So the
no-provenance finding is recorded **permanently in `param_freeze.json` itself**,
next to the cutoff, as the reason the clock starts at zero (Task 0).

Therefore:
- A historical corpus disjoint from the tuning period is **impossible**, not just
  unavailable — you cannot carve a "test" window out of data that all, at some
  point, informed the params. Any such split is in-sample in a holdout costume —
  the same trap as `holdout_frac`, one level up.
- **FORWARD-ONLY is the only honest option** (not a fallback): validate only on
  trades taken AFTER a frozen cutoff, params frozen at that cutoff. The one corpus
  you can *prove* the params never saw.
- Cost of honesty: the real verdict lands ~1–2 quarters out (see prior). That is
  the price of a trustworthy answer; the prior is why it's worth paying.

## Tasks (each: Goal / Build / Acceptance)

### Task 0 — Freeze the params, start the forward clock
- **Goal:** a provable cutoff after which the live params are immutable.
- **Build:** snapshot into a committed `artifacts/phase2/param_freeze.json`:
  `FROZEN_AT` (UTC), git sha, config hash, `n_target` (Task 3), the
  `provenance: "no reconstructable fit-date; all pre-cutoff data contaminated by
  construction"` finding verbatim, AND the params themselves.
- **GAP-2 — freeze the FULL decision surface, not just the four thresholds.** The
  forward corpus is only "params never saw this data" if *every* param that
  affects WHICH trades happen and HOW they resolve is frozen — not just entry
  direction. Snapshot and clock-protect: (a) entry-direction thresholds
  (`_observable_direction`), (b) the exit engine (regime stop/trail/TP/max-bars
  dicts + the `ORGANISM_EXIT_*` env multipliers), (c) the regime detector config,
  (d) the entry gates (liquidity, fitness, confidence thresholds), (e) the Kelly
  sizer params. A change to ANY of them shifts the forward trades and **MUST reset
  the clock** — otherwise an exit tweak in week 6 silently contaminates the corpus
  with a moving target while everyone assumes "we only froze the momentum
  thresholds." (If a future maintainer wants to scope the verdict to the
  entry-direction signal ONLY, that is allowed — but it must be stated, and changes
  to exits/regime/gates/sizing STILL reset the clock for the resolved-P&L verdict.)
- **Acceptance:** a test asserts the **entire frozen surface** (a–e above) equals
  the snapshot — drift ANYWHERE ⇒ fail ⇒ clock resets — not just the
  `_observable_direction` literals. The freeze file carries date, git sha,
  `n_target`, and the recorded no-provenance finding.

### Task 1 — REAL holdout (tune-on-train / report-on-test), not window restriction
- **SCOPE (sequencing — important):** Task 1 is for FUTURE Phase-2 **sweeps**
  (tuning *new* params without overfitting). Validating the CURRENT frozen
  momentum is forward-accumulation-only — you just compute t on post-cutoff trades
  (Tasks 0/2/3). So **the current-momentum-edge verdict is gated on Tasks 0/2/3,
  NOT Task 1.** Task 1 only blocks the day you start sweeping for *better* params.
  It can be built in parallel but does not hold up the first honest verdict.
- **Goal:** make leakage structurally impossible, not just labeled-against.
- **Build:** the harness must (a) split a corpus into train/test **by time**;
  (b) any parameter selection (Phase-2 sweeps) reads ONLY train-fold metrics;
  (c) reported metrics come ONLY from the test fold; (d) `holdout_frac`'s
  window-restriction-only behavior is removed or renamed so it can't be mistaken
  for OOS. Walk-forward with purge/embargo between folds.
- **Acceptance (the teeth):** a test that *deliberately overfits* a param to the
  train fold and shows **train t-stat ≫ test t-stat** — proving the test fold is
  untouched by selection. A harness that merely restricts the window FAILS this
  test (the overfit param would still flatter the "test" window).
  **The teeth are only real if the planted overfit is genuinely predictive ON the
  train fold and genuinely useless out of it** — a spurious signal fit to train
  noise that ACTUALLY CLEARS the bar on train (high train t-stat), then collapses
  on test. A param that's degenerate everywhere (low train t too) passes the test
  vacuously — it proves nothing. So the acceptance criterion is the *pair*:
  `train_t >= 2` (the overfit really worked in-sample) AND `test_t` near 0 (the
  holdout caught it). If you can't make train_t high, the test isn't testing the
  holdout — it's testing nothing.

### Task 2 — Forward-only corpus + accumulation pipeline
- **Goal:** a growing, provably-disjoint test corpus.
- **Build:** a pipeline that collects post-`FROZEN_AT` live/paper trades — the
  ACTUAL fills, the book accumulates them for free — into
  `artifacts/phase2/forward_trades.parquet`, tagged by strategy + regime, costed.
- **GAP-3 — n-amplification must NOT reopen the replay-vs-live gap.** Re-deriving
  "what the strategy would have done" on post-cutoff bars is a SECOND surface, and
  it's the rosier one (we were burned: +$276 replay vs −$792 live). So re-derived
  forward signals are either (a) reconciled trade-for-trade against the actual
  forward fills, with the match rate reported, OR (b) kept as a SEPARATE,
  explicitly-labeled OPTIMISTIC estimate that **NEVER feeds the Task-3 verdict
  gate**. The verdict is computed on ACTUAL fills only. Re-derived n is
  supplementary color, never the corpus of record.
- **Acceptance:** (1) a **disjointness test** — every verdict-corpus trade
  timestamp is strictly after `FROZEN_AT`; any pre-cutoff row is rejected;
  (2) re-derived signals are tagged distinctly and a test proves they cannot enter
  the verdict gate's input. Empty-until-enough is a valid state (don't fabricate a
  verdict from 3 trades).

### Task 3 — The verdict gate (optional-stopping-proof)
- **Goal:** one honest pass/fail per strategy, immune to repeated looks.
- **Build:** report costed net expectancy + t-stat on the forward corpus, with n.
  Gate = net exp > 0 AND t_stat ≥ 2 AND n ≥ `n_target`.
- **GAP-1 — NO PEEKING (the big one).** `n_min` stops lucky-tiny-n; it does NOTHING
  about optional stopping. If you evaluate repeatedly as n grows and declare
  victory the first time t crosses 2, you inflate the false-positive rate
  enormously — a t hovering near 1 WILL touch 2 by chance if you keep looking
  (same family as the t=1.87 favorable-window we caught). So pre-commit, in code:
  - **Default: pre-registered single look.** Evaluate ONCE at a fixed, pre-declared
    `n_target`; before n_target the gate returns INSUFFICIENT and refuses a t-stat
    verdict. The `n_target` is written into `param_freeze.json` at freeze time.
  - **If monitoring is wanted:** the gate must EITHER apply alpha-spending (raise
    the threshold for repeated looks) OR require t ≥ 2 to HOLD across a sustained
    window (e.g. every look over the last K trades), never a single tag.
- **GAP-1b — pin `n_target` to the prior, don't leave it free.** Prior is t≈1.0 at
  n≈18 ⇒ ~50–70 trades to clear ⇒ **`n_target` ∈ [50, 70]**, derived from the
  effect size, NOT chosen for convenience (n_target=20 lets a lucky run pass on
  noise).
- **GAP-1c — momentum verdict is REGIME-CONDITIONAL.** Compute momentum's t on the
  **trend slice only** (its eligible regimes — where the prior lives and the only
  candidate edge is). Including chop forward trades dilutes it. n_target counts
  trend-slice trades, not all forward trades.
- **Acceptance:** (1) below `n_target` the gate returns INSUFFICIENT and emits no
  t verdict; (2) a test simulates a true-null stream (t drifting near 1) evaluated
  at every n and proves the gate does NOT fire before n_target / does NOT fire on
  a single threshold-touch under the monitoring mode; (3) verdict only on the
  forward corpus's ACTUAL fills, never synthetic/pre-cutoff/re-derived;
  (4) momentum's t is computed regime-conditionally.

## The prior (so the timeline isn't a surprise)
Honest forward estimator from live trend trades: **t≈1.0 at n≈18**. Clearing
t≥2 needs roughly **50–70 more OOS trend trades** — ~1–2 quarters at the current
rate, *if the effect is real and stable*. Odds it clears on 22 mega-caps at 1-min:
**low** (most efficiently-priced arena retail can touch), not zero. The value of
this work is NOT likely vindication — it is converting "we suspect no edge here"
into "we proved it on an instrument we trust," which earns the standing to **change
the pond** (longer horizon / different universe) without second-guessing the tool.

## Run in parallel, costs nothing
Keep the live book accumulating forward trend trades the entire time — that is the
corpus that ends up mattering most. The harness build and the accumulation run
concurrently; the verdict lands when n crosses n_min.

## What "done" means for this phase (hold this clearly)
The harness is buildable in **days**; the first moment it can return anything
other than INSUFFICIENT is gated by **trade accumulation, not engineering**. You
freeze params today and the forward corpus starts filling from zero. So the
deliverable of this phase is **"a trustworthy instrument that currently says
INSUFFICIENT"** — NOT an answer. The actual verdict arrives a quarter or two later
as forward trades land. "The harness is built" must not get mentally rounded up to
"we have an answer." We won't, yet. We'll have the thing that can finally produce
one.

## Hold 5b until this exists
No confidence/sizing redesign verdict is meaningful until Tasks 0–3 are green.
