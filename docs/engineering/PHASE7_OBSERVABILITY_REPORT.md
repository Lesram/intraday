# Phase 7.6 Observability And Operator View Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`

## Executive Summary

P7.6 tightened the operator-facing checkpoint from a broad green light into a
more useful runtime console. The Phase 7 integration checkpoint now proves the
authenticated deploy-health and data-integrity endpoints are reachable, exposes
container build metadata, kill-switch envs, open-position state, order status
mix, outbox age, strategy health, and migration/runtime hashes in one report.

This slice also found two real observability bugs. First, the checkpoint queried
`outbox` even though the live table is `outbox_events`; the failure was captured
as raw command output but was not elevated into a check. Second, live logs showed
`GET /api/v1/organism/status` throwing `PydanticSerializationError` on a nested
`numpy.bool` value. Both are now fixed and covered by focused regression tests.

Trading behavior is unchanged. This is an operator/read-path hardening slice:
the system is easier to inspect, and endpoint serialization is less brittle, but
no candidate filter or strategy revision was promoted.

## Changes

| Surface | Change | Why it matters |
|---------|--------|----------------|
| `scripts/ci/phase7_integration_checkpoint.py` | Uses `outbox_events`, adds authenticated deploy/data-integrity probes, kill-switch visibility, position/order/outbox DB checks, and an operator snapshot section. | Prevents a bad table query from hiding in raw output and gives the operator one coherent runtime readout. |
| `backend/organism/routes.py` | Converts nested NumPy scalars/arrays, Decimals, datetimes, and non-finite floats into JSON-safe values for `/organism/status` and `/organism/runs`. | Fixes a live 500 on `/api/v1/organism/status` caused by `numpy.bool` in runtime state. |
| `tests/test_phase7_integration_checkpoint_redaction.py` | Adds checkpoint behavior tests for the real outbox table and operator snapshot text. | Keeps the checkpoint from regressing back to decorative evidence. |
| `tests/test_phase7_organism_status_serialization.py` | Adds endpoint serialization regressions with nested NumPy runtime state. | Reproduces the live failure mode without needing the container. |

## Live Evidence Before Commit

Authenticated integration checkpoint against the paper container:

```text
Phase 7 integration checkpoint: 18 pass, 1 warn, 0 fail
```

The single warning was expected before commit: the worktree was dirty from this
slice. Runtime evidence from the generated checkpoint:

| Signal | Value |
|--------|-------|
| Container SHA | `b0ce75edbe9d1934b835500295b1ea7f22b1521f` |
| Deploy endpoint SHA | `b0ce75edbe9d1934b835500295b1ea7f22b1521f` |
| Build time | `2026-05-06T15:09:30Z` |
| Migration head | `20260503_000003` |
| Runtime config hash | `9a5833dff070cf50` |
| Kill switches | `ORGANISM_DRAWDOWN_KILL_PCT=0.20`, `ORGANISM_MAX_DAILY_LOSS=5500`, `ORGANISM_MAX_NOTIONAL=2000` |
| Open positions | `0` |
| Orders by status | `cancelled:5,expired:1,failed:4,filled:1432` |
| Outbox events | `927`, from `2026-04-07 15:38:10+00` to `2026-05-06 15:12:12+00` |
| Data integrity endpoint | `accounting_status=warning`, `realized=936`, `brain=524` |
| Strategy health | `n_trades=517`, `total_pnl=-812.1659`, `win_rate=0.3327`, `sharpe=-1.4307`, `is_profitable=false` |
| Phase 6 evidence | `phase5_rows=66`, `phase6_rows=14`, `joined=186`, recommendation `insufficient_shadow_sample` |

## Live Bug Found

The paper container logged:

```text
Unhandled exception [...] in GET http://localhost:8000/api/v1/organism/status:
Unable to serialize unknown type: <class 'numpy.bool'>
```

Root cause: `/organism/status` returned nested scheduler/live-engine runtime
state under a `dict[str, Any]` response-model field. Pydantic v2 does not
implicitly serialize NumPy scalars in that nested structure. The route now
sanitizes nested runtime values before assigning `live_engine`, `governance`,
`policy_weights`, `promotion`, and `/organism/runs` state.

## Alert Reality Check

Code-present is not the same thing as production-proven.

| Claim | Current status | Evidence |
|-------|----------------|----------|
| Drawdown-kill alert dispatches | Code-present, not production-proven in this deploy window. | `backend/organism/governance.py` dispatches a critical alert when drawdown kill triggers. Logs from the current 24-hour container window show the main event loop was captured, but no drawdown-kill trigger. |
| Emergency-stop alert dispatches | Code-present, not production-proven in this deploy window. | `backend/services/risk_manager.py` dispatches an alert in `trigger_emergency_stop`; no emergency-stop trigger observed in current logs. |
| ML/feature-drift alert dispatches | Code-present, not production-proven in this deploy window. | `backend/organism/ml_signal.py` and `backend/organism/background_trainer.py` use the cross-thread dispatcher; no matching production alert event observed in current logs. |
| Tick watchdog alert dispatches | Code-present, not observed firing in this deploy window. | `backend/organism/live_engine.py` has TT-2 watchdog alert wiring; current logs show normal tick completion and no TT-2 fire. |
| Low-win-rate alert from brain save | Code-present. Production path now exists in `brain_persistence`; not enough live evidence here to claim operator delivery. | `backend/organism/brain_persistence.py` calls `maybe_dispatch_low_win_rate_alert` from the manifest save path. |

Recommendation: future Track A slices should distinguish three states in every
operator claim: `code_present`, `behaviorally_tested`, and `production_observed`.

## Tests

Focused tests run locally:

```bash
./venv/bin/python -m py_compile scripts/ci/phase7_integration_checkpoint.py
./venv/bin/python -m py_compile backend/organism/routes.py
./venv/bin/python -m pytest -q \
  tests/test_phase7_organism_status_serialization.py \
  tests/test_phase7_integration_checkpoint_redaction.py \
  --timeout=30
```

Result: `6 passed`.

## Phase Position

P7.6 can close after the required organism safety bundle, repo gates, artifact
pack, commit, push, rebuild, deploy parity, and live endpoint checks are green.
The platform is more inspectable than before this slice, but the negative
strategy-health and data-integrity warning remain Track A risk-register items.
