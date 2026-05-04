# Platform Deep-Audit — V7 Plan (Super-Comprehensive)

**Date:** 2026-05-03
**Branch:** rc-1.5-curated @ `d44eace` (post wave-22; all V6 actionable findings closed)
**Predecessors cumulative:** V1-V6 = ~187 audit items, ~186 closed (V-T-8 deferred).

## Why this round is different

V1-V6 leaned heavily on **infrastructure correctness**:
- Time / clock handling (4 rounds touched it)
- Order lifecycle, persistence, concurrency
- Numerical precision, replay determinism
- Telemetry coverage, alert delivery

V7 deliberately covers **eight surfaces V1-V6 left untouched or only grazed**:

| Surface | V1-V6 coverage | V7 plan |
|---|---|---|
| Security & trust (auth, secrets, CSRF, SQL injection, supply chain) | grazed in V3 Track I (3 findings) | comprehensive Track AA |
| Data integrity & invariants (DB constraints, state machines, audit trail) | reconciliation only (V1 G, V4 N) | comprehensive Track BB |
| Test quality & coverage (line/branch coverage, mutation, flaky detection) | wave-counts only | comprehensive Track CC |
| **Strategy logic correctness** (alpha factors, regime, exits, risk math) | **never audited** | comprehensive Track DD |
| Operational readiness / SRE (runbooks, DR, graceful shutdown, SLOs) | observability only (V4 P) | comprehensive Track EE |
| Edge cases & adversarial inputs (malformed bars, NaN, extreme prices, fuzz) | not done | comprehensive Track FF |
| Documentation truthfulness (AGENTS.md, mapss.md, docstrings, README) | not done | comprehensive Track GG |
| Architecture / code organization (coupling, god classes, circular deps) | not done | comprehensive Track HH |

Plus the standard per-round closures:

| Track | Surface | Continuity |
|---|---|---|
| **Z4** | Closure regression for waves 20-22 (~24 findings) | REFINED |
| **W2** | CI rule verification (did Track W's proposals actually ship?) | NEW (V6 W follow-up) |

## Tracks (10 total)

1. **Z4** — Closure regression for waves 20-22
2. **W2** — CI rule verification (V6 W's "every wave PR must..." proposal: did it ship into PR template / CI workflow?)
3. **AA** — Security & Trust
4. **BB** — Data Integrity & Invariants
5. **CC** — Test Quality & Coverage
6. **DD** — Strategy Logic Correctness ← **first-ever audit of trading logic itself**
7. **EE** — Operational Readiness / SRE
8. **FF** — Edge Cases & Adversarial Inputs
9. **GG** — Documentation Truthfulness
10. **HH** — Architecture / Code Organization

## Out of scope

- Any V1-V6 surface that already had a closure-regression track (Z, Z2, Z3).
- Live broker integration tests — synthetic / replay / probe only.
- Refactoring proposals (HH surfaces them; doesn't fix them).

## Output structure

```
artifacts/audit/prompts/v7/
  V7_PLAN.md
  track_z4_closure_regression_waves20_22.md
  track_w2_ci_rule_verification.md
  track_aa_security_trust.md
  track_bb_data_integrity.md
  track_cc_test_quality.md
  track_dd_strategy_logic.md
  track_ee_operational_readiness.md
  track_ff_edge_cases_adversarial.md
  track_gg_docs_truthfulness.md
  track_hh_architecture.md

artifacts/audit/v7_reports/
  track_z4_closure_regression.md
  track_w2_ci_rule_verification.md
  track_aa_security_trust.md
  track_bb_data_integrity.md
  track_cc_test_quality.md
  track_dd_strategy_logic.md
  track_ee_operational_readiness.md
  track_ff_edge_cases_adversarial.md
  track_gg_docs_truthfulness.md
  track_hh_architecture.md

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v7.md
```

## Constraints (all tracks)

- Read-only on production. Synthetic tests via `./venv/bin/python` ok.
- `curl` against running container; do NOT mutate state.
- No docker rebuild. No git push. No production changes.
- DD may run synthetic backtests via `replay_simulator.py` — read-only.
- AA may probe `/api/...` with `curl` (no state mutation, no auth bypass attempts beyond reading public surface).

## Quality bar

This is the largest round so far (10 tracks). Per-track yield will vary:

- Z4: 0-2 regressions expected (continuity).
- W2: 0-3 (process-level).
- AA: **8-15** (first deep security audit; expect significant findings).
- BB: 5-10 (first deep invariant audit).
- CC: not bug-counted (deliverable is coverage report + flaky list).
- DD: **5-12** (first strategy-logic audit; high yield expected).
- EE: 4-8.
- FF: 4-10 (fuzz / property-based on adversarial inputs).
- GG: 3-8 (doc accuracy).
- HH: 5-10 (structural).

Total expected: **30-80 findings**. Even at the low end this is the largest yield round in the cycle.

## Synthesis

After all 10 tracks complete, generate `MASTER_AUDIT_SYNTHESIS_v7.md` with:
- Cross-track patterns (V3 found 3, V4 found 5, V5 found 5, V6 found 5)
- Total findings, severity breakdown
- Wave 23+ proposed fix sequence (will likely span 4-6 waves)
- Update `FINDINGS_LEDGER.md` with V7 findings.

## A note on audit fatigue

V1-V6 closed 186 items across 6 rounds. The marginal yield per track has been
declining — V6 was 18 actionable findings vs. V1's 30. V7 deliberately
opens 8 new surfaces simultaneously to combat this; if any track returns
< 3 findings, that's strong-signal that the surface is genuinely clean
rather than that the audit was lazy.

If V7 finds 50+ items, expect a 4-week wave campaign (23-26). If it finds
< 20, the cycle is converging and V8 should be a smaller, focused round.
