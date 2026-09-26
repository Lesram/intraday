# Strategy research readiness — September 26 audit

The platform has useful historical evidence, but no demonstrated deployable edge. Operational acceptance and strategy profitability are separate gates. The last independently accepted paper release is PR30 source `87c1addb39321e4f3a628041d8fb68a6e848255d`, merged as `bf533a43d01a4c2e7428ea9589159d9c7d242319`, with active forward cutoff **2026-09-25T21:11:46.270521+00:00**. It was released after the session. Its initial immutable daily pack is `READY_FOR_REVIEW`, but contains **zero forward trades**, four `INSUFFICIENT` strategy gates, `NO_FORWARD_DECISIONS`, and incomplete reconciliation solely for `no_forward_evidence`. Natural-session acceptance remains pending. A valid empty pack verifies collection, not trading ability or profitability.

These facts come from the private PR30 `final-deployment-review.json` and the saved September 25 pack `3659ef14…/report.json`; this review read those reports, not models, credentials, broker endpoints or live ledgers. Their full paths and checksums are recorded in the companion source manifest.

## What historical evidence can support

| Evidence | Defensible use | What it cannot establish |
| --- | --- | --- |
| Historical broker fills and preserved ledgers | Reconstruct economic cash flows where exact entry/exit attribution, quantities and prices reconcile; retain unresolved records as unknown | Treat every inherited row/count or approximate bar-close PnL as clean strategy evidence; pool old trades into the new forward cohort |
| Immutable session logs and packs | Diagnose availability, discovery, gating and execution paths; reproduce collection and quality failures | Infer edge from successful ticks, scanner counts, no logged errors or no-trade sessions |
| Timestamped historical OHLCV | Rebuild controlled research datasets after checking source/feed/session coverage and chronology | Assume previously computed feature caches equal the corrected deployed strategy; the composite producer changed and this audit found SPY alignment defects |
| Old shadow event/outcome joins | Retain hypotheses, negative findings and explicitly bounded samples; re-audit event-time/bar joins, costs and dependence | Treat gross forward returns or many correlated repeated signals as independent executable trades |
| PR30 paired synthetic replay | Verify causal feature differences, real simulated admission/exits, accounting and deterministic repeats | Establish market edge or quantify September 24 missed profit; down-scenario results worsened and crash drawdown increased |

Specific exclusions matter. The May ORB report explicitly excludes May 1 stale-cache shadow logs as profitability evidence. Its separate cached-bar simulator found only 20 hypothetical trades and negative average R. The May 5 filter study found `alpha_breakout_chop` negative across 1/5/10 bars; `conf_45_55` had only 14 events. Those are useful reasons not to promote, not evidence that every old data file is worthless. The September 24 report documents good session capture but zero orders, a scanner/subscription mismatch and contaminated composite inputs. It is an operations dataset, not a strategy verdict. See `docs/engineering/PHASE3_ORB_SHADOW_OUTCOME_REPORT.md`, `PHASE5_SHADOW_EVIDENCE_LOOP_REPORT.md`, and `reports/session_review_2026-09-24/SESSION_REVIEW.md`.

The Phase 5b confidence study also did **not** establish a better ranking model: all four study lanes returned `FLAT_SHIPS`. Momentum's selected model had naive test t=2.58 but session-clustered t=0.93; breakout's was 0.34, MR negative, and ORB had only 44 test observations. This is the historical result of that study, not current-release proof. Its referenced `artifacts/broad_corpus_v2/bars.pkl` is absent from this audit worktree, so this review did not independently reproduce its inputs. See `artifacts/phase2/phase5b_confidence_verdict.txt`.

## Strategy inventory and current authority

| Implemented lane | Source-level status | Evidence status established here |
| --- | --- | --- |
| Registry momentum | `live_routing=true`, guarded baseline | Explicitly unproven; new forward n=0 |
| Registry breakout | `live_routing=true`, separate pure-breakout generator | Explicitly unproven; new forward n=0 |
| Registry mean reversion | `live_routing=false`, benchmark/shadow | Historical costed evidence negative; no current promotion |
| Registry ORB | Implemented module, `live_routing=false` | Historical small/negative or insufficient samples; no current promotion |
| ETF intraday momentum, ORB SIP v2, residual mean reversion, EOD reversal | Four implemented Phase 9 engines, signals `shadow_only=true`, tier 0; creation/capture controlled by telemetry flags | No current source-bound promotion verdict or verified outcome sample located |
| Gamma/volatility proxy and policy IDs for pairs, inverse hedge, catalyst continuation | Proxy/authorization vocabulary exists | A policy ID is not an implemented, tested strategy or a passed gate |

Registry/config authority is `backend/organism/strategies/{registry,strategy_config}.py`; Phase 9 construction is `live_engine.py:862` and `engines/`. The separate strategy governor enables capital only for the inherited `alpha_baseline` policy; research strategies remain live-disabled. Registry names, governor IDs and telemetry IDs must not be counted as separate validated strategies. EOD is absent from the four-strategy registry, although separate shadow engines exist. Some older module prose still says momentum is the only live registry lane or ORB is unbuilt; executable config/module inventory takes precedence.

## Objective acceptance gates

**Working paper platform:** exact approved source/image/config/freeze identity; complete session coverage with explicit gaps; genuine streaming subscription/bar freshness and recorded admission; no duplicate orders; protective/EOD management; fills reconciled into exactly-once whole-position accounting; visible unresolved states; valid restart/restore evidence; and immutable daily packs with entry and close provenance. A zero-trade day can pass collection while leaving natural fills, partial exits and EOD flatten unobserved. This audit's reproduced recovery/alignment defects prevent an unconditional “all working” certification.

**A supported trading edge:** pre-register a fixed hypothesis, entry/exit and cost model, universe, holdout split and evaluation schedule; qualify the source-bound cohort before calculating significance; measure net expectancy with session dependence and concentration accounted for; compare against relevant hold/random/delayed-entry baselines; then require replay, independent review and explicit promotion. No strategy is promoted merely because the infrastructure is green.

The implemented forward gate uses fixed prefixes at **60 and 120** trades, session-cluster-robust CR1 statistics, boundaries **2.646 and 1.871** respectively; momentum is restricted to `trending_up`/`high_vol`. The daily evidence wrapper explicitly uses **6 bps round-trip** cost, while the standalone gate defaults to the runtime model (**3 bps**). Below the first look there is no statistic; an uncleared first look remains insufficient until the final prefix. The separate **300 clean-trade evolution condition is not the profitability gate**. Research lock independently disables automatic promotion. Sources: `backend/organism/phase2_gate.py`, `scripts/ops/paper_daily_evidence.py:277`, `backend/organism/research_policy.py`.

The shadow league's `replay_eligible` label is only permission for further research. Portfolio allocation requires stronger evidence: at least 100 samples, PF≥1.20, positive average R and benchmark/null alpha, concentration limits, at least two validated strategies/families, bounded correlation and beta; even then the module does not authorize live promotion. Historical Phase 9D documentation reported no eligible strategies; its generated verdict artifact is absent here, so that dated claim is not a current verified count.

## Remaining unknowns and immediate research sequence

Current per-strategy shadow sample counts, feature versions, live telemetry enablement and complete outcome joins have not been verified in this read-only review. Several older reports' referenced raw corpora/generated artifacts are absent from the worktree; they may exist elsewhere, but availability, integrity and comparability are unproven. Five preserved historical local order outcomes remain unknown under a narrow deployment exception and cannot be relabeled as resolved research trades.

First repair and verify the approved pipeline/accounting boundaries; preserve every prior cohort and defect label. Next create an inventory of immutable raw bars/events and rebuild versioned features/outcomes offline, with explicit timestamp, execution and cost qualification. Select one pre-registered shadow hypothesis and assess it on untouched sessions, without optimizing on the verdict window. Collect a clean current-release forward cohort and apply its existing gates. Do not discard useful history, backfill old results into the new clock, relax safety to create trades, or claim an edge from synthetic mechanics.
