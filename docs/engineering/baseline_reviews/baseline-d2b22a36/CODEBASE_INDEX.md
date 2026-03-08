# Codebase Index

Generated: 2026-03-08
SHA: `d2b22a36`
Branch: `control-plane-operationalize`

## Scale

| Scope | Files | Lines |
|-------|-------|-------|
| backend/ (total) | 297 | 133,082 |
| backend/organism/ | 37 | 20,618 |
| backend/ (non-organism) | 260 | 112,464 |
| tests/ | 391 | 120,151 |
| docs/architecture/ | 17 | 11,840 |
| Config & deployment | 31 | 5,719 |
| **Total** | **736** | **271,792** |

## Backend Module Map

### Organism (37 modules, 20,618 lines)

The living trading organism — the autonomous trading brain.

| Category | Modules | Key Files |
|----------|---------|-----------|
| Core engine | 5 | `live_engine.py` (4,080), `scheduler.py`, `runner.py`, `routes.py`, `governance.py` |
| Signal generation | 6 | `ml_signal.py`, `alpha_scanner.py`, `breakout_scanner.py`, `composite_indicators.py`, `ml_features.py`, `multi_timeframe.py` |
| Risk & sizing | 4 | `kelly_sizer.py` (601), `adaptive_exits.py`, `pyramider.py`, `sector_map.py` |
| Learning & evolution | 6 | `self_evolution.py` (1,253), `continuous_learner.py`, `background_trainer.py`, `training.py`, `transfer_learning.py`, `walk_forward.py` |
| Data & telemetry | 7 | `decision_telemetry.py`, `diagnostics.py`, `diagnostic_checks.py`, `streaming_data_provider.py`, `market_scanner.py`, `attribution.py`, `brain_persistence.py` |
| Regime & ensemble | 2 | `regime.py`, `ensemble_models.py` |
| Infrastructure | 7 | `replay_simulator.py`, `promotion.py`, `nightly_scheduler.py`, `feature_store.py`, `universe_selector.py`, `replay_data_loader.py`, `replay_reporting.py` |

### Non-Organism Backend (260 files, 112,464 lines)

| Category | Files | Lines | Key Files |
|----------|-------|-------|-----------|
| API routes | 26 | ~10,500 | `orders.py`, `models.py`, `scanner.py`, `auth.py` |
| API core + middleware | 17 | ~4,200 | `factory.py`, `lifespan.py`, `websocket_manager.py` |
| Services | 27 | ~14,500 | `order_service.py` (1,714), `backtest_service.py` (2,775) |
| Infrastructure | 33 | ~13,500 | `schemas.py` (1,444), `security.py`, `guardrails.py` |
| ML / MLOps | 29 | ~17,100 | `model_manager.py` (1,996), `prediction_service.py`, `governance.py` |
| Risk | 13 | ~6,300 | `risk_manager.py` (1,832), `advanced_risk.py` |
| Integrations | 7 | ~3,500 | `alpaca_broker.py` (881), `alpaca_stream.py` (733) |
| Strategies | 9 | ~4,900 | `engine.py`, `advanced_strategies.py` |
| Config | 7 | ~3,300 | `base_settings.py` (1,745) |
| Database | 12 | ~3,400 | `connection.py`, `optimization.py` |
| Data | 5 | ~2,600 | `alpaca_client.py` (925) |
| Monitoring | 8 | ~3,400 | `enhanced_slo_manager.py`, `memory_monitor.py` |
| Other | 67 | ~25,000 | models, migrations, analytics, features, utils, research, optimization, security, observability |

## Test Coverage Map

| Category | Files | Tests | Covers |
|----------|-------|-------|--------|
| Organism core | 10 | 239 | Tick loop, scenarios, evolution, replay, invariants |
| Orders & positions | 7 | 229 | Lifecycle, fills, reconciliation, guardrails |
| Risk management | 5 | 221 | VaR, margin, limits, scenarios |
| ML / models | 4 | 207 | Pipeline, inference, prediction, ensemble |
| Strategies | 4 | 151 | Engine, service, comprehensive, basic |
| API & infrastructure | 7 | 203 | Routes, WebSocket, resilience, caching |
| Unit comprehensive | 24 | ~1,400 | Deep per-module coverage |
| Unit smoke (generated) | 199 | ~200 | Import validation for all modules |
| Other root tests | ~131 | ~1,000+ | Production, diagnostics, security, utilities |

## Architecture Documentation

| Document | Lines | Scope |
|----------|-------|-------|
| `mapss.md` | 4,883 | Complete unified platform map (source of truth) |
| `improve9.md` | 359 | Latest AIA deep research (Phase A+B) |
| `improve8.md` | 513 | Two-tier entry, session gating, learning risk caps |
| `improve7.md` | 381 | FTF chop redesign, confidence gating, circuit breaker |
| `TRADING_ALGORITHMS.md` | 635 | Core algo documentation |
| `IMPLEMENTATION_PLAN.md` | 1,461 | Frontend roadmap |

## Artifacts in This Bundle

| File | Description |
|------|-------------|
| `CODEBASE_INDEX.md` | This file |
| `strategy_surface_manifest.json` | 10-stage trading pipeline with every participating module |
| `core_backend_snapshot.tar.gz` | Source archive of trading-critical modules |
| `BASELINE_AUDIT_CONTEXT.md` | Module-by-module role descriptions for auditors |
