# Platform Deep-Audit — V5 Plan

**Date:** 2026-05-02
**Branch:** rc-1.5-curated @ `d43dbec` (post wave 16 — H-1, H-2, Z-R-3, Z-R-4 closed)
**Predecessors:** V1 (Tracks A-G, 30 findings), V2 (re-audit + 8), V3 (Tracks H-M, 58), V4 (N/O/P/Q/R/Z, 52). Waves 8-16 closed ~145 findings; 0 deferred-open.

## Goal

Verify the wave 12-16 sweep held cleanly AND extend coverage to the three
new-surface tracks the V4 synthesis proposed: Stress/Failure-Mode (S),
Numerical/Floating-Point (T), Replay-Live Divergence (U).

## Tracks

| Track | Surface | New / Refined |
|---|---|---|
| **Z2** | Closure regression for waves 12-16 (50+ recently-closed findings) | REFINED |
| **S** | Stress & Failure-Mode (network partition, broker burst, DB drop, OOM, clock skew, disk-full, Redis outage, outbox backpressure) | NEW |
| **T** | Numerical / Floating-Point (Decimal vs float P&L, cumulative-counter drift, ATR / Sharpe / Kelly numerical stability, calibration math, bar-timestamp arithmetic) | NEW |
| **U** | Replay-Live Divergence (deterministic trace through identical bars, diff every intermediate state, surface bypass sites of `self._now_fn()` and other live-only state) | NEW |

## Out of scope

- V1-V4 closures already verified via Track Z (V4) — Z2 only covers waves 12-16.
- V5 refinements of existing A/G/R/P tracks: subsumed by Z2 since waves 12-16 touched
  all of those surfaces.
- Live broker integration tests — only synthetic / replay / probe.

## Output structure

```
artifacts/audit/prompts/v5/
  V5_PLAN.md
  track_s_stress.md
  track_t_numerical.md
  track_u_replay_live_divergence.md
  track_z2_closure_regression_waves12_16.md

artifacts/audit/v5_reports/
  track_s_stress.md
  track_t_numerical.md
  track_u_replay_live_divergence.md
  track_z2_closure_regression.md

artifacts/audit/MASTER_AUDIT_SYNTHESIS_v5.md
```

## Constraints (all tracks)

- Read-only on production. Synthetic tests via `./venv/bin/python` ok.
- `curl` against running container; do NOT mutate state.
- No docker rebuild. No git push. No production changes.
- Each track must self-document: file paths, line numbers, repro commands.

## Quality bar

V4 found 52 issues across 6 surfaces. V5 has 4 tracks; expect at least 15 findings.
Track U has the highest discovery bar — every place `_now_fn()` is bypassed is a
divergence point; expect 3-7 from a careful audit.

## Synthesis

After all 4 tracks complete, generate `MASTER_AUDIT_SYNTHESIS_v5.md` with:
- Cross-track patterns (V3 found 3, V4 found 5)
- Total findings, severity breakdown
- Wave 17+ proposed fix sequence
- Update `FINDINGS_LEDGER.md` with V5 findings
