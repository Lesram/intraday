# Platform Deep-Audit — V8 Plan (post-recommendations)

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `79b38fb` (post wave 28-31; the 4 post-V7 recommendations all shipped)
**Predecessors cumulative:** V1-V7 = ~278 audit items, ~220 closed, ~58 open going into V8.

## What's different about V8

The post-V7 discussion identified four root causes of recurring findings:

1. **Audit scope expansion** — first-look findings on new surfaces.
2. **Process enforcement lag** — same-class scans inconsistent → fix-didn't-fix pattern.
3. **Structural debt** — god-classes guarantee per-round findings.
4. **Easy-first sequencing** — strategy / security / data integrity came late.

Waves 28-31 shipped the four recommendations:
- **Wave 28:** CI rules tightened from warn → required (kills #2).
- **Wave 30:** BB-8 LotTracker + BB-10 audit_logs wired (kills "dead code with live-looking telemetry" subset of #3).
- **Wave 31:** Reachability tests added (new lens for #3).
- **Wave 29:** HH R-1 partial pipeline-split (chips at #3 god-class debt; full split tracked in `docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md`).

V8 is the FIRST audit round with these tools available. It should:
- Verify the tools actually catch what they claim to catch (W3 + reachability re-audit).
- Re-run V7's deferred items with reachability lens.
- Penetration-test wave-23/24 security fixes from outside.
- Re-audit DD strategy logic looking for subtler bugs (V7 found 11; V8 should find fewer if waves 24+30 closed the easy ones).
- Run the closure regression on waves 23-31.

## Tracks (8 total)

| # | Track | What's new vs. V7 | Yield estimate |
|---|---|---|---|
| 1 | **Z6** — closure regression (waves 23-31, 33 fixes) | Standard pattern; uses wave-31 reachability tests as a new closure verification lens | 0-2 |
| 2 | **W3** — verify wave-28 CI rules ACTUALLY block bad PRs | Construct a synthetic bad-wave commit; assert the script rejects it | 1-3 |
| 3 | **AA2** — security re-audit + external probing | Curl-probe wave-23/24 fixes from outside the container; same-class scan for new auth gaps | 2-5 |
| 4 | **BB2** — data integrity re-audit with reachability lens | Verify LotTracker + audit_logs actually populate under live load (use wave-31 reachability + DB row counts) | 2-4 |
| 5 | **DD2** — strategy logic deeper pass | V7 DD found 11 in 1 round; expect diminishing returns. Drill into Kelly edge cases, regime hysteresis, exit precedence under partial fills | 3-7 |
| 6 | **HH2** — architecture coupling under R-1 partial | Verify Stage 0a doesn't introduce regression; identify next-easiest stages to extract | 1-3 |
| 7 | **NN** — **NEW: Reachability audit** | Use wave-31 lens systematically across the codebase. For every test, is the code path actually reached in production? Mutation testing + import-graph analysis | **5-10** |
| 8 | **OO** — **NEW: Audit-cycle meta-audit** | After 7 rounds, what patterns has the cycle missed? Audit the AUDITS for blind spots. | 3-6 |

Total expected: **15-40 findings**. Dramatically lower than V7 (~91) because the easy / first-look surfaces are mostly covered. If V8 finds <15, the cycle is genuinely converging.

## Specifically what V8 must verify

### Verify the recommendations actually work

- **Wave-28 CI rules:** synthetic bad-wave PR (no grep, count > 0 grep, no test on Critical) — does check_wave_markers.py reject it?
- **Wave-30 BB-8 wiring:** under live load, does `position_lots` actually populate? Check DB row count delta.
- **Wave-30 BB-10 wiring:** under live load, does `audit_logs` actually populate? Already verified login_failed; verify drawdown-kill / daily-loss too.
- **Wave-31 reachability tests:** do they actually fire when wiring is broken? Synthetic regression test.
- **Wave-29 HH R-1 partial:** does extracting stage 0a not change tick behavior? Replay-vs-live diff.

### What V8 should NOT do

- Don't re-run identical V1-V7 tracks; closure regression covers continuity.
- Don't expand to brand-new surfaces V7 didn't touch (8 + 4 recommendations is enough).
- Don't write fixes during the audit — V8 is read-only; wave-32+ ships fixes.

## Output structure

```
artifacts/audit/prompts/v8/
  V8_PLAN.md
  track_z6_closure_regression_waves23_31.md
  track_w3_ci_rule_actual_enforcement.md
  track_aa2_security_re_audit.md
  track_bb2_data_integrity_re_audit.md
  track_dd2_strategy_logic_deeper.md
  track_hh2_architecture_under_r1_partial.md
  track_nn_reachability_audit.md
  track_oo_audit_cycle_meta_audit.md

artifacts/audit/v8_reports/
  track_z6_closure_regression.md
  track_w3_ci_rule_actual_enforcement.md
  track_aa2_security_re_audit.md
  track_bb2_data_integrity_re_audit.md
  track_dd2_strategy_logic_deeper.md
  track_hh2_architecture_under_r1_partial.md
  track_nn_reachability_audit.md
  track_oo_audit_cycle_meta_audit.md

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v8.md
```

## Constraints (all tracks)

- Read-only on production. `curl`, `docker exec`, `pytest`, `psql` SELECTs ok.
- No mutations.
- No git push.
- Do NOT write fixes (V8 is audit-only; wave 32+ fixes).

## Quality bar

Per V7's lesson: the audit-cycle is good at finding things and weak at
*verifying its own recommendations work*. V8 must close that loop.

End-of-V8 success criteria:
- All 4 recommendations independently verified to actually function.
- ≥3 V7 deferred items confirmed still-open (or reflagged with new context).
- ≥1 finding the audit cycle "should have caught earlier" (proves OO meta-audit value).
- Closure regression clean (Z6 returns 0-2).
