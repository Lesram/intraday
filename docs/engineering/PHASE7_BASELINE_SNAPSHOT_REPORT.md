# Phase 7.0 Baseline Snapshot Report

Generated: 2026-05-06T04:10:31.503744+00:00
Branch: `codex/v13-phase2-expectancy`
HEAD: `9e620be1d6ee0727fb914646dd49f5f88a5623cd`
Container SHA: `9e620be1d6ee0727fb914646dd49f5f88a5623cd`

## Executive Verdict

P7.0 baseline capture is ready for Phase 7 hardening work. Integration checks are 13 pass, 1 warn, 0 fail. No trading behavior was changed.

The platform is mechanically coherent enough to start inventory-led cleanup: the running container matches HEAD, hot-path file parity passes, runtime snapshot generation passes, and the migration tree is single-headed.

The strategy itself is still not profit-ready. The baseline preserves the Phase 6 verdict: current main candidate flow should not be promoted, and Phase 6 telemetry should keep collecting evidence while Track A cleanup runs.

## Runtime Truth

- Repo clean at capture: `False`
- Healthz status: `200`
- Strategy health status: `200`
- Audit chain endpoint status: `200`
- Phase 5 telemetry enabled: `true`
- Phase 6 telemetry enabled: `true`
- Hot-path parity mismatches: `0`

## Strategy And Brain

- Strategy trades: `513`
- Strategy total PnL: `-810.5359`
- Strategy win rate: `0.3314`
- Strategy Sharpe per trade: `-1.4279`
- Strategy profitable: `False`
- Brain generation: `182`
- Brain manifest total trades: `520`
- Brain trade history rows: `520`
- Phase 5 candidate telemetry rows: `62`
- Phase 6 strategy evidence rows: `0`

## Phase 6 Evidence Policy

| Filter | Action | Events | Outcomes | 5-bar mean bps | Win rate |
|--------|--------|--------|----------|----------------|----------|
| all_candidates | reject_or_redesign | 62 | 62 | -2.5527 | 0.3548 |
| alpha_breakout_chop | reject_or_redesign | 56 | 56 | -3.481 | 0.3393 |
| conf_45_55 | collect_more_shadow_sample | 14 | 14 | 7.0155 | 0.5 |

## Architecture Inventory

- Backend Python files: `283`
- Backend functions/methods: `3702`
- Functions over 150 LOC: `50`
- Files over 1000 LOC: `20`
- `_live_tick_inner` LOC: `2802`

Top large methods:

| LOC | Function | File | Line |
|-----|----------|------|------|
| 2802 | `OrganismLiveEngine._live_tick_inner` | `backend/organism/live_engine.py` | 1954 |
| 573 | `calculate_indicator` | `backend/api/routes/indicators.py` | 159 |
| 549 | `OrganismLiveEngine._reconcile_fills` | `backend/organism/live_engine.py` | 5631 |
| 508 | `OrganismLiveEngine.initialize` | `backend/organism/live_engine.py` | 1073 |
| 504 | `run_backtest_panel_detailed` | `backend/research/optuna_meta_research_engine.py` | 248 |
| 478 | `validate_order_pre_trade` | `backend/api/routes/orders.py` | 386 |
| 454 | `KellySizer.size_positions` | `backend/organism/kelly_sizer.py` | 175 |
| 408 | `startup` | `backend/api/lifespan.py` | 15 |
| 399 | `OrganismLiveEngine.__init__` | `backend/organism/live_engine.py` | 428 |
| 373 | `BacktestService.run_backtest` | `backend/services/backtest_service.py` | 202 |

Top large files:

| LOC | File | Functions > threshold |
|-----|------|-----------------------|
| 7267 | `backend/organism/live_engine.py` | 7 |
| 2775 | `backend/services/backtest_service.py` | 7 |
| 2429 | `backend/organism/brain_persistence.py` | 2 |
| 1989 | `backend/ml/model_manager.py` | 1 |
| 1884 | `backend/services/order_service.py` | 2 |
| 1846 | `backend/models/ensemble_model.py` | 1 |
| 1832 | `backend/risk/risk_manager.py` | 0 |
| 1786 | `backend/api/routes/models.py` | 1 |
| 1745 | `backend/config/base_settings.py` | 0 |
| 1640 | `backend/api/routes/orders.py` | 2 |

## Test Trust Inventory

- Wave-style files scanned: `54`
- Wave-style tests classified: `360`
- Marker-only tests: `121`
- Mixed tests: `41`
- Marker-only ratio: `33.61%`
- Marker-or-mixed ratio: `45.0%`
- All-test source-grep pattern hits: `511`
- Skip/xfail hits: `66`

## P7.0 Risks To Carry Forward

- Strategy health remains negative; Phase 7 must not promote strategy behavior.
- `_live_tick_inner` remains above the historical 2510 LOC baseline.
- Some wave-style tests are still marker-only and need P7.3 review.
- Phase 6 strategy-evidence file has no new rows yet; next session should populate it.

## Recommended Next Step

Proceed to P7.1 architecture map and P7.3 test-trust review before the first live-engine extraction. The likely first extraction target remains telemetry fanout from `_live_tick_inner`, because it is recent, observable, and can be tested without changing order behavior.

## Raw Artifacts

- `artifacts/phase7/baseline_snapshot.json`
- `artifacts/phase7/god_method_inventory.json`
- `artifacts/phase7/test_trust_inventory.json`
