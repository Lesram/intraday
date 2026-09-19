# Intra 2.0 — Final Build-Out Plan (Phase 3: Live Integration + Definitive Verdict)

**Audience:** Claude Code (repo + per-line access).
**Purpose:** Finish the platform completely — route all strategies through the engine, make the selection real, and stand up the definitive forward verdict — so the system can render a *trustworthy* answer on whether edge exists. No deferrals left dangling; every remaining piece is scheduled here with its own acceptance gate.
**This is a contract + acceptance-criteria document.** Code owns implementation; this defines what must be true when done, in what order, and why.

---

## 0. Read this first — two hard realities that gate everything

**Reality A — nothing from Phase 1/2 is actually deployed.** The running paper container is built from `main`. The entire Phase-1/Phase-2 body of work lives on `intra-2.0-phase1` and is **not live**. This means: (1) the strategies you modularized are not what's trading; (2) the freeze in `param_freeze.json` references the new code (`5988bcb`) while the *running* system is old `main` — so the forward corpus currently accumulating is measuring the wrong code. Until the branch is deployed and `running == frozen`, no forward number is valid. This is Task 1 and it blocks everything downstream.

**Reality B — the data feed is now IEX, which compromises verdict validity.** IEX carries ~2.5% of consolidated volume. The liquidity gate was dropped 20× ($1M → $50k) to compensate; hedge legs (SH/PSQ) are bar-starved (10–13 bars/hr vs 61); volume and relative-volume features — core inputs to breakout/momentum — are now computed on a thin, noisy slice. Price signals on liquid names and paper fills are fine, so IEX is workable for *execution testing*. But the definitive forward verdict would be measuring a **degraded system**, and a FAIL on IEX answers "no edge visible on 2.5% of the tape," not "no edge in the strategy." This is Task 0: decide the data question before the definitive test, don't discover it after.

If a conflict ever arises between "make the platform look finished" and these two realities, the realities win. A beautiful selection engine fed by unvalidated data trading on undeployed code is not "done" — it's a demo.

---

## The correct execution order (and why it's this order)

The instinct is "just wire the strategies into the engine." That's wrong as a starting point, for three reasons the sequence below encodes:

1. **You can't measure forward until `running == frozen`** — so deploy the branch first (Task 1).
2. **You can't do fair cross-strategy selection until the comparability metric is sound** — and today's confidence composite is *anti-predictive* (corr = −0.112 with correct direction). Ranking strategies by a broken axis picks the wrong winner. So confidence redesign (5b) comes **before** meaningful selection (5c), not after. This is the key sequencing insight.
3. **Every change to the decision surface resets the forward clock** — so you freeze **once**, at the end, after everything is stable. Freezing mid-build throws away accumulation repeatedly.

Order: **Task 0 (data decision) → Task 1 (deploy branch) → Task 2 (5b confidence) → Task 3 (5c routing) → Task 4 (regime selection + attribution) → Task 5 (freeze once) → Task 6 (definitive forward test).**

---

## Task 0 — Resolve the data-validity question (precondition, do not skip)

- **Goal:** the definitive forward test runs on data good enough to trust its verdict.
- **Decide:** either (a) **re-subscribe to the SIP feed** (`ALPACA_DATA_FEED=sip`, ~$99/mo) for the forward-test window — the recommended path, trivial cost against the effort and capital at stake; or (b) **explicitly accept an IEX-limited verdict**, recorded in writing, understanding it will likely FAIL and possibly for data reasons.
- **If IEX is kept**, the plan must additionally: resolve the hedge-leg problem (SH/PSQ are bar-starved on IEX — either replace them with liquid inverse exposure, special-case their gate/indicator handling, or drop hedging from the tested universe), validate the recalibrated `$50k` liquidity floor against a full live session's gate-rejection telemetry, and confirm the in-play universe isn't starved by the IEX volume thresholds.
- **Acceptance:** the data decision is documented in the freeze artifact (Task 5) as a first-class fact — which feed the verdict was produced on — so the verdict can never be read out of its data context. "IEX-limited" is a valid, recorded state; a clean SIP verdict is the stronger one.

---

## Task 1 — Deploy `intra-2.0-phase1` and prove `running == frozen`

- **Goal:** the code that's live is the code that's frozen, so forward measurement is valid.
- **Build:** rebuild/recreate the paper container from `intra-2.0-phase1` with `ORGANISM_FRAMEWORK_ROUTING=false` (flag-off = the parity-proven no-op). Deploy in a market-closed window.
- **Acceptance:** (1) the Phase-1 step-5 parity gate passes on the deployed image — live entries/exits/sizes bit-for-bit identical to the pre-deploy `main` behavior on a replay window that actually trades; (2) `strategies/` and `phase2_gate.py` are present *inside* the container; (3) the freeze source-hashes match the deployed source (if any drift, re-freeze — Task 5 — since `running` now differs from the old freeze); (4) container healthy, 0 restarts. Until this is green, treat all forward numbers as invalid.

---

## Task 2 — 5b: Confidence redesign (prerequisite for fair selection)

- **Goal:** a comparability metric the selector can actually rank strategies on — because the current one is anti-predictive and would systematically pick the wrong strategy.
- **Context:** live confidence today is the composite `0.39·readiness + 0.26·squeeze + 0.35·tension`, and `corr(confidence, correct_direction) = −0.112`. Sizing scales by it (Kelly 0.3–1.5×) and ranking uses it. Porting that composite into the framework would enshrine a known defect (the pyramiding mistake in a new costume).
- **Build:** treat "what should confidence be" as an open redesign, not a port. Baseline is **flat sizing / uniform confidence** — the thing any proposed model must beat. Candidate confidence models are evaluated through the Task-1 walk-forward holdout (already built, teeth-proven).
- **Acceptance:** a confidence model routes into live sizing/ranking **only if** it beats flat sizing on **costed, out-of-sample** expectancy at t≥2 on the test fold. If nothing beats flat, **flat sizing ships** — that is a valid, honest outcome and removes the anti-predictive composite from the decision path. Cross-strategy comparability is explicit: the confidence scale must mean the same thing across momentum/breakout/MR/ORB, or the selector's ranking is invalid.

---

## Task 3 — 5c: Route all strategies through the selector (the actual integration)

- **Goal:** one engine, one strategy path — all four strategies produce candidates through `StrategySelector`, everything downstream (gates → sizing → exits → record) is shared and identical, inline scanners retired.
- **Build:**
  - In `_live_tick_inner`, replace the scattered inline scanner calls (`alpha_scanner.scan` ~2973, `breakout_scanner.scan` ~3880, `mean_reversion_scanner.scan` ~2894, `orb_scanner.scan` ~2654/2818) with a single `selector.scan_all(features, regime)` path behind `FRAMEWORK_ROUTING_ENABLED`.
  - The selector aggregates candidates from all **enabled** strategies, applies the regime-eligibility policy (Task 4), ranks by the Task-2 confidence, and hands the engine one candidate list.
  - Retire the inline scanners once the routed path is proven (keep them briefly behind the flag for the parity diff, then delete).
  - EOD stays parked (excluded from the registry) unless explicitly revived with its own validation.
- **Acceptance (per-strategy parity — note this is NOT "behavior unchanged"):** because you *want* behavior to change (more strategies now trade), the gate is different from Phase 1's. Prove, per strategy, that each strategy's **live entries match what the backtester says that strategy would do** on the same bars (entered-symbol set, direction, size, exit reason) — the same trade-for-trade reconciliation used before, now applied to breakout, MR, and ORB individually. Plus: safety/governance/risk limits unchanged; the LOC/structural guards stay green; a tripwire logs any selector/engine divergence.

---

## Task 4 — Regime-adaptive selection + per-strategy attribution (the comparison capability)

- **Goal:** the thing you actually asked for — the engine picks the right strategy for the conditions, and you can *see* which strategies win.
- **Build:**
  - A declarative regime→eligible-strategies policy (e.g. momentum/breakout in trend/high-vol, MR in chop *only if it ever clears the bar*, ORB in high-vol) in config, with a defined tie-break and an explicit **stand-down** when no strategy is eligible.
  - **Per-strategy, per-regime attribution logging**: every trade tagged with originating strategy + regime + realized P&L + costed net, streamed into the forward corpus so the verdict gate (Task 6) reports **each strategy separately**, not just an aggregate.
  - Rule A still holds: a strategy influences **live capital** only if it has passed the forward verdict for that regime. Until then it can trade in **shadow/attribution** mode (measured, not sized into live risk) — so you accumulate its comparison data without betting on it blind.
- **Acceptance:** the attribution report shows, per strategy per regime, n / net expectancy / t-stat on the forward corpus; the stand-down path is tested; no strategy routes to live capital without clearing its gate.

---

## Task 5 — Freeze ONCE, at the end

- **Goal:** start the definitive forward clock on a stable, complete system — and only once.
- **Build:** after Tasks 1–4 are green and the system is stable, re-run the freeze (`phase2_freeze.py`) over the full decision surface (entry direction, gates, exit engine, Kelly sizer, regime detector, strategy_config, exit env, **and the data feed**). Record the data-feed decision from Task 0 in the freeze artifact.
- **Acceptance:** `param_freeze.json` reflects the deployed, unified system; `running == frozen` (source hashes match the live container); the forward corpus is empty and begins filling from this cutoff. Any subsequent surface change resets the clock — so hold changes after this point.

---

## Task 6 — The definitive forward test

- **Goal:** one honest verdict per strategy per regime, on the complete system.
- **Build:** the Phase-2 gate (already built, null-sim FPR 0.044, optional-stopping-proof) runs against the post-freeze forward corpus, per strategy per regime, at the two pre-registered looks (n=60, n=120 trend-slice-equivalent), OBF spending, cluster-robust variance.
- **Acceptance:** `INSUFFICIENT` until n crosses the first look; `PASS`/`FAIL` only at the pre-registered looks; verdict reported per strategy, tagged with the data feed it was produced on. The deliverable of this phase is *a trustworthy instrument that currently says INSUFFICIENT* — the verdict itself lands ~1–2 quarters after Task 5's freeze.

---

## Honest timeline and expectation (hold this clearly)

- **Build (Tasks 0–5):** on the order of weeks, not days — 5b and 5c are real work with real parity gates.
- **Freeze → first verdict:** ~1–2 quarters of forward accumulation *after* the build stabilizes. So the definitive answer is **Q4 2026 / early 2027 at the earliest**, and only if the data (Task 0) is adequate.
- **The prior is unchanged:** the most likely verdict remains `FAIL` — no edge clearing costs on 1-minute mega-caps for a retail operator — and on IEX data that likelihood is higher and the answer muddier. Finishing the platform does **not** create edge; the strategies routed through a clean engine are the same strategies. What it creates is a *trustworthy verdict* — the ability to say "there is no edge here" as a proven fact rather than a suspicion, which is what earns the standing to either fund it or change ponds without second-guessing the tool.
- **What would change the answer is not this build — it's the pond.** This plan finishes the instrument. If and when the verdict lands `FAIL`, the real lever is a different universe/horizon where edge structurally exists for who you are, not more tuning of efficiently-priced intraday markets. That's the next conversation, and it reuses this entire framework (contract, selector, gate) with new strategy modules.

---

## What "done" means for this phase

Not "the strategies are wired in." Done is: **the branch is deployed and running == frozen; confidence is sound (or honestly flat); all strategies route through one selector with per-strategy parity proven; the engine selects by regime and logs attribution; the system is frozen once on adequate data; and the verdict gate is running per-strategy, currently reading INSUFFICIENT.** At that point the platform is genuinely finished and the only thing left is time — the corpus fills, and the instrument tells you the truth.
