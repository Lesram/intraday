# Platform Deep-Audit — V9 Plan

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `db1a3fc` (post wave 32-40)
**Predecessor cumulative:** V1-V8 = ~315 audit items, ~250 closed, ~65 deferred entering V9.

## What's different about V9

V8 OO meta-audit identified the cycle's lens-availability lag as the real recurring-finding driver, not "easy-first sequencing." V9 ships the 3 missing lenses OO recommended (PP chaos, UU error-handling, TT performance) PLUS deeper passes on the V8-touched domains, PLUS verification that V8 wave-32-40 fixes actually close their root causes (not just pass tests).

## V9 design principles

1. **Verify recently-shipped fixes under load**, not just unit tests. (Z7 + W4 do this.)
2. **Apply V8-validated lenses (NN reachability, OO meta) at greater depth.**
3. **Ship NEW lenses for unaudited classes.** Chaos, error-handling, performance.
4. **Keep yield expectation modest:** 10-30 findings. Below 10 = cycle genuinely converging; above 30 = lens still finding new surfaces.
5. **Audit-only.** Wave 41+ ships fixes.

## Tracks (8 total)

| # | Track | Lens | Yield estimate | New vs V8 |
|---|---|---|---|---|
| 1 | **Z7** — closure regression on waves 32-40 + db1a3fc | continuity | 0-2 | continuation |
| 2 | **W4** — verify wave-32 CI rule fixes ACTUALLY close W3-G1/G2/G3 | process | 1-3 | continuation |
| 3 | **AA3** — security Phase 2: JWT lifecycle, session fixation, CSRF, smuggling, IDOR | depth | 2-5 | depth-pass |
| 4 | **BB3** — data integrity Phase 2: schema invariants, FK cascades, txn boundaries | depth | 2-4 | depth-pass |
| 5 | **DD3** — strategy logic Phase 3: position lifecycle, partial-fill state machine, pyramid vs new-entry | depth | 3-7 | depth-pass |
| 6 | **PP** — chaos / fault injection (DB kill mid-trade, network partition, broker timeout) | **NEW** | 3-7 | OO recommendation |
| 7 | **UU** — error handling: bare except, swallowed exceptions, fail-open paths | **NEW** | 2-5 | OO recommendation |
| 8 | **TT** — performance: tick p99, query plans, memory growth, allocation hot paths | **NEW** | 1-4 | OO recommendation |

Total expected: **14-37 findings**. Convergence below 14 = cycle stabilizing; above 37 = expansion still warranted.

## V9-specific verification targets

The cycle has been criticized in V7/V8 for "fix didn't fix." V9 must:
- **Z7**: confirm waves 32-40 markers all in place; behavioral tests still pass; no later commits dropped them.
- **W4**: synthetic bad-wave commits explicitly testing the W3-G1/G2/G3 wave-32 fixes (timeout, scope-widening, prompt-prefix).
- **PP**: synthetic chaos scenarios — kill DB during a tick, restart api mid-flight, drop brain file mid-save.
- **UU**: AST scan for `except Exception: pass`, `except: ...` (bare), and identify which are pure logging vs swallowing real errors.
- **TT**: profile a single tick with `cProfile` or `py-spy`; identify allocations / DB queries / network calls.

## Output structure

```
artifacts/audit/prompts/v9/
  V9_PLAN.md                                  (this file)
  track_z7_closure_regression_waves32_40.md
  track_w4_ci_rule_post_wave32.md
  track_aa3_security_phase2.md
  track_bb3_data_integrity_phase2.md
  track_dd3_strategy_logic_phase3.md
  track_pp_chaos_fault_injection.md
  track_uu_error_handling_consistency.md
  track_tt_performance_latency.md

artifacts/audit/v9_reports/
  track_z7_closure_regression.md
  track_w4_ci_rule_post_wave32.md
  track_aa3_security_phase2.md
  track_bb3_data_integrity_phase2.md
  track_dd3_strategy_logic_phase3.md
  track_pp_chaos_fault_injection.md
  track_uu_error_handling_consistency.md
  track_tt_performance_latency.md

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v9.md
```

## Constraints (all tracks)

- Read-only on production.  `curl`, `docker exec`, `pytest`, `psql` SELECTs ok.
- **Chaos track may use a SCRATCH container or local sandbox**, NEVER production.
- No mutations to live brain / DB.
- No git push.
- Do NOT write fixes during V9 — wave 41+ ships fixes.

## Quality bar

V9 must close the loop on:
- All 9 V8 wave fixes (32-40) independently verified to actually function under varied conditions.
- ≥3 V8 deferred items (DD2-6, BB2-F2, NN-HIGH-2, HH2-N-1, HH2-N-2) confirmed still-open OR newly-resolved.
- ≥1 finding from each NEW lens (PP/UU/TT) — proves the lens has yield.
- Closure regression clean (Z7 returns 0-2).

End-of-V9 success criteria:
- The audit cycle's "fix didn't fix" pattern is provably DEAD on the V8 fix surface.
- V9 surfaces fewer findings than V8 (37) — measurable convergence.
- 3 new lenses prove their value for V10 retention.
