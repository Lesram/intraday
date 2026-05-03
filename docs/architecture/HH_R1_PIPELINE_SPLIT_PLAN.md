# HH R-1 — `_live_tick_inner` Pipeline-Split Plan

**Created:** 2026-05-03 (post-V7 / wave-29)
**Status:** Wave-29 shipped Stage 0a (`_stage_expire_cooldowns`).
The remaining 12+ stages are multi-day work; this doc tracks the plan
so future waves don't have to rediscover the structure.

## Why this refactor

V7 Track HH found:
- `live_engine.py` is 6,401 LOC.
- `OrganismLiveEngine._live_tick_inner` is **2,510 lines in a single
  method**, with 13 commented step boundaries already in place.
- 374-line `__init__`, 104 attributes, 17 collaborator references.
- CC track found 21% line coverage on `live_engine.py` — the largest
  testing blind spot.

Per-round audits keep finding new issues inside `_live_tick_inner`
because no single audit can cover 2,510 lines comprehensively. R-1
is the highest-ROI structural refactor in the codebase.

## The 13 stages (from comment markers in source)

| # | Stage | Approx LOC | Extraction risk |
|---|---|---|---|
| 0a | Expire cooldowns + pending-entry maps + terminal-id early-clear | ~40 | **LOW (shipped wave-29)** |
| 0b | Stream health check + recovery | ~25 | LOW |
| 0.5 | Stale-data gate (entries-blocked) | ~25 | LOW |
| 1 | Governance halt check | ~15 | LOW |
| 1.1 | Warmup gate | ~15 | LOW |
| 1.2 | Stale-data entries gate | ~10 | LOW |
| 1.3 | EOD entry block + flatten | ~30 | MEDIUM |
| 1.5 | Market scanner pass | ~40 | MEDIUM (state writes to `_universe`) |
| 2 | Fetch latest data + features | ~60 | MEDIUM |
| 3 | Detect regime | ~80 | MEDIUM |
| 4 | Daily session roll + max-loss + drawdown-kill | ~250 | **HIGH** (many state mutations + alerting + audit logging) |
| 5 | Exit checks (per-symbol) | ~600 | **HIGH** (largest single block; pyramid logic + ATR stops + FTF + horizon + safety net) |
| 6 | Pre-entry gates | ~100 | MEDIUM |
| 7 | Scan + ML + alpha + breakout + ORB + EOD + MR build | ~500 | **HIGH** |
| 8 | Kelly sizing | ~60 | MEDIUM |
| 9 | Submit entries | ~150 | MEDIUM |
| 10 | Reconcile fills (record + brain save) | ~100 | MEDIUM |
| 11 | Periodic retrain + evolve | ~150 | MEDIUM |
| 12 | Brain save + telemetry export | ~100 | MEDIUM |

Total: ~2,300 LOC distributed across 18 stages. The remaining ~210
LOC is shared setup/teardown.

## Extraction strategy

**Constraint:** preserve EXACT behavior. The tick-loop runs ~once per
5 seconds in production; any subtle scope change in extracted helpers
would corrupt the platform's mental model of state.

**Approach:**
1. Extract one stage per wave commit. Test in isolation. Deploy.
2. Stage helpers take/return state via `self`, not via parameters
   (preserves the existing single-state-bag pattern).
3. Each helper has a behavioral test covering the reverted-behavior
   case (V6 W rule #3 / V8 wave-28 enforcement).
4. The extracted helper is named `_stage_<num>_<purpose>`, e.g.
   `_stage_3_detect_regime`, `_stage_5_check_exits`.

**Per-stage acceptance criteria:**
- [ ] Helper extracted; original site replaced with `self._stage_X_...()` call
- [ ] All `self._...` reads / writes inside helper match the original
- [ ] Behavioral test in `tests/test_live_tick_stages_v8.py`
- [ ] Container deploy verified (RestartCount=0, brain coherent)
- [ ] Wave commit cites HH-R1, includes same-class grep + count: 0

## Wave sequence (proposed)

| Wave | Stages | Effort | Risk |
|---|---|---|---|
| 29 (shipped) | Stage 0a | 30 min | LOW |
| 32 | Stages 0b + 0.5 + 1 + 1.1 + 1.2 (low-risk gates) | 1-2 hr | LOW |
| 33 | Stage 1.3 (EOD) + 1.5 (scanner) | 1 hr | MEDIUM |
| 34 | Stage 2 (data fetch) + Stage 3 (regime) | 1 hr | MEDIUM |
| 35 | **Stage 4 (daily-roll + max-loss + drawdown-kill)** | 2-3 hr | **HIGH** |
| 36 | **Stage 5 (exits — the largest block)** | 4-6 hr | **HIGH** |
| 37 | Stages 6-9 (gates + scan + Kelly + submit) | 3-4 hr | MEDIUM |
| 38 | Stages 10-12 (reconcile + retrain + brain save) | 2 hr | MEDIUM |

Total: ~15-22 hours of focused refactoring across 7 waves.

## Risks + mitigations

**Risk 1: behavior drift on extraction.**
Mitigation: behavioral test BEFORE extraction. Run replay with the
existing method, capture state snapshot. Run with the extracted
helper, assert identical state.

**Risk 2: shared mutable state between stages.**
Mitigation: stages share `self`. Document each stage's reads and
writes in the helper docstring. Avoid passing extracted state
back-and-forth; trust `self` as the single state bag.

**Risk 3: implicit ordering between stages.**
Mitigation: name stages `_stage_<num>_...` so call-site ordering
visibly matches the documented pipeline order. CI lint can verify
the call sequence in `_live_tick_inner` is monotonic.

**Risk 4: a stage extraction lands during market hours and breaks
production.**
Mitigation: extract during weekend / pre-market only. Add a
deploy-window check to AGENTS.md.

## Acceptance criteria for "R-1 complete"

- [ ] `_live_tick_inner` is < 200 LOC (currently 2,510).
- [ ] Each stage helper is < 250 LOC.
- [ ] Each stage has ≥ 1 behavioral test.
- [ ] Replay-vs-live trace diff (V8 Track U2 if revisited) shows
      zero state divergence pre-/post-refactor.
- [ ] Container brain coherent across all wave deploys.
- [ ] `live_engine.py` total LOC reduces by ≥ 1,500 (the extracted
      helpers are smaller than the inline blocks).

## Tracking

This doc is the source of truth. Each wave that ships an R-1 stage
must update the table above (mark stage shipped, note any deviations).
V8 Track HH should re-audit when 4+ stages are shipped to verify the
refactor is preserving behavior.
