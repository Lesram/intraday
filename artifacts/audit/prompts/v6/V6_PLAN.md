# Platform Deep-Audit — V6 Plan

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `3f660f4` (post wave-19; all V5 findings closed)
**Predecessors:** V1 (30), V2 (8 new), V3 (58), V4 (52), V5 (21). 169 cumulative audit items, all closed.

## Goal

V5's headline finding was that **three previously-shipped "fixes" did not deliver the
behavior they promised** (S-J3-1 alert delivery, U-RF4 replay clock, S-WS-GAP-1
gap-fill). The pattern is now load-bearing for the audit cycle: the audit catches
its own holes. V6 directly attacks this pattern by verifying that recent fixes
*actually fire at runtime* (telemetry coverage), not just that the code is present.

Plus the standard closure regression for waves 17-19, plus the property-based
numerical and backtesting-reliability surfaces V5 synthesis proposed.

## Tracks

| Track | Surface | New / Refined |
|---|---|---|
| **Z3** | Closure regression for waves 17-19 (21 recently-closed findings) | REFINED |
| **V** | Telemetry coverage — ORGANISM_* metrics, alert paths, log levels: are they actually emitting? | NEW |
| **W** | Wave-cycle audit — for every shipped fix, verify (a) marker present, (b) same-bug-class scan clean, (c) CI test exists | NEW |
| **T2** | Property-based numerical — round-trip cumulative_pnl, Sharpe(empty)→None, Kelly(0var)→None, etc. | REFINED |
| **X** | Backtesting reliability — with V5 clock-injection fixes, run a deterministic replay; assert reproducibility + live-vs-replay invariants | NEW |

## Out of scope

- V1-V5 closures already verified by their respective Z tracks.
- Live broker integration tests — synthetic / replay only.
- Re-auditing API security (V3 Track I) or DB layer (V4 Track N) — covered.

## Output structure

```
artifacts/audit/prompts/v6/
  V6_PLAN.md
  track_z3_closure_regression_waves17_19.md
  track_v_telemetry_coverage.md
  track_w_wave_cycle_audit.md
  track_t2_numerical_property_tests.md
  track_x_backtesting_reliability.md

artifacts/audit/v6_reports/
  track_z3_closure_regression.md
  track_v_telemetry_coverage.md
  track_w_wave_cycle_audit.md
  track_t2_numerical_property_tests.md
  track_x_backtesting_reliability.md

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v6.md
```

## Constraints (all tracks)

- Read-only on production. Synthetic tests via `./venv/bin/python` ok.
- `curl` against running container; do NOT mutate state.
- No docker rebuild. No git push. No production changes.
- Each track must self-document: file paths, line numbers, repro commands.

## Quality bar

V5 found 21 issues across 4 surfaces. V6 has 5 tracks; expect 10-25 findings.
Track V (telemetry) and Track W (wave-cycle) are the centerpieces — they directly
operationalize the V5 Pattern 1 finding. Each should surface at least one
"declared-but-not-actually-firing" instance.

## Synthesis

After all 5 tracks complete, generate `MASTER_AUDIT_SYNTHESIS_v6.md` with:
- Cross-track patterns (V3 found 3, V4 found 5, V5 found 5)
- Total findings, severity breakdown
- Wave 20+ proposed fix sequence
- Update `FINDINGS_LEDGER.md` with V6 findings
