# Phase 7 Test Trust Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
Baseline HEAD while inspected: `b18478b26e14a046e14cf12bc82ded49ab0db4ca`

## Verdict

The current test suite is useful, but the audit-era wave tests still contain too
much source-shape proof. The critical/high marker-only gate passes, which is an
important improvement, but the broader wave-style corpus remains structurally
untrustworthy as a refactor safety net: 121 of 360 classified wave-style tests
are marker-only, and 162 of 360 are marker-only or mixed.

This does not mean the platform is unsafe today. It means green audit-wave tests
cannot be treated as strong evidence for behavior unless the specific touched
path has a behavioral test, replay, or live/runtime probe. For Phase 7, every
live-engine extraction should carry its own behavioral proof and should convert
nearby source-marker tests when they cover the same risk.

## Evidence Inputs

- `artifacts/phase7/test_trust_inventory.json`
- `scripts/ci/forbid_marker_only_critical_high.py`
- `scripts/ci/lint_ratchet.py`
- `tests/test_wave*_fixes.py`
- `tests/test_v12_w*.py`
- `tests/test_v13_w*.py`

## Baseline Counts

| Metric | Value |
|--------|-------|
| Wave-style files scanned | 54 |
| Wave-style tests classified | 360 |
| Behavioral | 197 |
| Marker-only | 121 |
| Mixed | 41 |
| Structural | 1 |
| Marker-only ratio | 33.61 percent |
| Marker-or-mixed ratio | 45.0 percent |
| Skip/xfail hits in full test source scan | 66 |

## Marker-Heavy Files

| File | Marker-only | Mixed | Behavioral | Notes |
|------|-------------|-------|------------|-------|
| `tests/test_wave41_fixes.py` | 11 | 0 | 7 | Error handling, alerting, and operational proof remain too source-shaped. |
| `tests/test_wave35_fixes.py` | 6 | 0 | 2 | Strategy-gate and timing checks need behavior probes. |
| `tests/test_wave40_fixes.py` | 6 | 0 | 0 | Stage-helper extraction proof is entirely source-shaped. |
| `tests/test_wave42_fixes.py` | 6 | 0 | 0 | Auth/logout/order cleanup checks need behavioral proof. |
| `tests/test_wave32_fixes.py` | 5 | 1 | 4 | Includes pending-exit max-loss and admin/HSTS marker checks. |
| `tests/test_v13_w91_plan_doc.py` | 5 | 0 | 2 | Mostly document-contract tests; lower risk. |
| `tests/test_wave52_fixes.py` | 5 | 0 | 0 | Alert/readiness checks are not behavior-proven. |
| `tests/test_wave56_fixes.py` | 5 | 0 | 0 | Brain backup/corrupt-head/tmp-sweep checks need filesystem behavior probes. |
| `tests/test_v13_w95_data_integrity.py` | 4 | 3 | 8 | Some observability/data-integrity checks still source-shaped. |
| `tests/test_v12_w82_dockerfile_env.py` | 3 | 2 | 4 | Deploy/config tests combine parsing with marker proof. |

## Highest-Risk Marker Examples

These are the first conversion candidates because they assert safety or runtime
behavior by source text rather than observable behavior:

| Priority | Test | Current weakness | Conversion target |
|----------|------|------------------|-------------------|
| P0 | `tests/test_v13_w100_live_tick_coverage.py::test_w100_equity_gates_drawdown_kill_invocation` | Source marker for drawdown-kill invocation. | Simulate equity drawdown in a lightweight engine fixture and assert entries block and alert hook/counter behavior. |
| P0 | `tests/test_v13_w100_live_tick_coverage.py::test_w100_pyramid_path_present_in_source` | Source marker for pyramid path. | Drive a fake position and feature frame through pyramid evaluation or a replay fixture and assert no order path bypass. |
| P0 | `tests/test_wave32_fixes.py::test_dd2_1_pending_exit_max_loss_safety_net_present` | Source marker for pending-exit max-loss safety net. | Create engine state with pending exit and adverse PnL; assert max-loss exit remains reachable. |
| P0 | `tests/test_wave35_fixes.py::test_dd2_8_pure_breakout_gates_on_direction` | Source marker for pure-breakout direction gate. | Feed pure-breakout candidates with mismatched direction and assert no execution intent. |
| P0 | `tests/test_wave52_fixes.py::test_yy_1_governance_drawdown_kill_dispatches_alert` | Source marker for alert dispatch. | Monkeypatch alert dispatcher, trip governance kill, assert alert call and blocked state. |
| P1 | `tests/test_wave56_fixes.py::test_ww_2_backup_naming_microsecond_resolution` | Source marker for backup naming. | Use temp brain dir, perform two fast saves, assert two distinct backup dirs. |
| P1 | `tests/test_wave56_fixes.py::test_pp2_3_save_sweeps_tmp_orphans` | Source marker for tmp sweep. | Create orphan `.tmp` files in temp brain dir, save, assert removal. |
| P1 | `tests/test_v13_w95_data_integrity.py::test_w95_outbox_prune_emits_metrics` | Source marker for metrics emission. | Run prune loop/repo path with temp DB or mocked repo, assert metric counters change. |
| P1 | `tests/test_wave68_fixes.py::test_aaa_f1_debug_endpoints_gated` | Source marker for route gating. | Start app/router test client and assert debug endpoint is absent in paper/prod config. |
| P2 | `tests/test_v13_w91_plan_doc.py::*` | Document-marker tests. | Keep or downgrade; documents can be checked by source markers if labeled as document-contract tests. |

## Conversion Policy

Use this rule for Phase 7:

| Surface | Accept marker-only? | Required proof |
|---------|---------------------|----------------|
| Auth, RBAC, JWT, debug endpoints | No | HTTP/client behavior or direct security helper behavior. |
| Order submission, cancel, outbox, broker dispatch | No | Service/repo behavior with fake broker or DB fixture. |
| Safety gates, kill switches, EOD block/flatten | No | Engine fixture, replay, or explicit decision object behavior. |
| Brain persistence, backups, telemetry preservation | No | Temp directory filesystem behavior. |
| Docker/config/runtime parity | Marker-only only as secondary | Parsed config, built image, or one-command runtime gate. |
| Docs/process plans | Yes, if labeled low-risk | Document-contract marker checks are acceptable but must not count as behavior proof. |

## Phase 7 Test Cleanup Batches

### P7.3-A: Live Tick And Safety Gate Markers

Convert marker-only tests that assert safety in `_live_tick_inner`, especially
W100, wave32, wave35, wave40, wave42, and wave52. This should run before or
alongside P7.2 extraction.

Acceptance:

- Candidate telemetry extraction has behavioral tests.
- Drawdown-kill, pending-exit max-loss, pure-breakout gate, and EOD paths are
  covered by behavior or explicitly deferred with owner and reason.

### P7.3-B: Persistence And Data Integrity Markers

Convert wave56 and V13 W95 marker tests that claim brain backup, tmp sweep,
outbox prune, and telemetry preservation behavior.

Acceptance:

- Brain-save backup and tmp-sweep tests use temp dirs.
- Outbox prune metrics test observes a metric or repository effect.
- Telemetry preservation is tested by save/load behavior, not source strings.

### P7.3-C: Runtime And Deploy Markers

Convert or relabel V12 W82 and V13 W98 deploy/frontend marker tests. Keep only
low-risk document or static contract markers.

Acceptance:

- Docker/runtime proof comes from parsed config, image env, or runtime gate.
- Any source-marker-only deploy checks are labeled as structural, not behavior.

### P7.3-D: Document-Contract Markers

Keep document-marker tests where the artifact itself is the subject, but exclude
them from behavioral trust metrics used to justify live-trading changes.

Acceptance:

- Plan-doc tests do not inflate behavior coverage.
- Reports distinguish "document exists" from "runtime behavior works."

## Ratchet Targets

| Milestone | Marker-only ratio target | Marker-or-mixed target | Notes |
|-----------|--------------------------|------------------------|-------|
| Current baseline | 33.61 percent | 45.0 percent | 121 marker-only, 41 mixed. |
| End of P7.3-A | Below 30 percent | Below 42 percent | Focus on live tick/safety first. |
| End of Phase 7 | Below 25 percent | Below 35 percent | High-risk marker tests converted or formally deferred. |
| Before live trading readiness | Below 15 percent | Below 25 percent | Remaining markers are mostly document/static checks. |

## Required Gate Interpretation

Current gates mean:

- `forbid_marker_only_critical_high.py` passing means no known critical/high
  finding is closed only by marker proof.
- It does not mean all audit-wave fixes are behavior-proven.
- `lint_ratchet.py` passing means the selected ruff ratchet did not regress.
- It does not mean full static analysis is clean.
- A green artifact pack means the configured suites passed for the current
  scope.
- It does not prove profitability or strategy promotion readiness.

## Immediate Recommendation

Before the first P7.2 extraction, add behavioral tests around the candidate
evidence fanout contract. After extraction, rerun:

```bash
./venv/bin/python -m pytest -q tests/test_organism_live_engine.py --timeout=30
./venv/bin/python -m pytest -q tests/test_multi_tick_state.py --timeout=30
./venv/bin/python -m pytest -q tests/test_safety_invariants.py --timeout=30
./venv/bin/python -m pytest -q tests/test_replay_simulator.py --timeout=30
./venv/bin/python scripts/ci/phase7_integration_checkpoint.py
./venv/bin/python scripts/ci/forbid_marker_only_critical_high.py
```

The reason is simple: Phase 7 is allowed to make architecture cleaner, but it is
not allowed to make the platform less honest.

