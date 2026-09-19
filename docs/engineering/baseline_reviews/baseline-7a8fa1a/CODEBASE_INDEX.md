# Codebase Index

Generated: 2026-03-09
SHA: `7a8fa1a`
Branch: `main`

## Scale

| Scope | Files | Lines |
|-------|-------|-------|
| backend/ (total) | 297 | 133,082 |
| backend/organism/ | 37 | 20,618 |
| backend/ (non-organism) | 260 | 112,464 |
| tests/ | 391 | 120,151 |
| **Total tracked** | **688+** | **253,000+** |

## Organism Module Map (37 modules, 20,618 lines)

| Category | Modules | Key Files (lines) |
|----------|---------|-------------------|
| Core engine | 5 | `live_engine.py` (4,080), `scheduler.py`, `runner.py`, `routes.py`, `governance.py` (250) |
| Signal generation | 6 | `ml_signal.py` (619), `alpha_scanner.py` (396), `breakout_scanner.py` (477), `composite_indicators.py` (534), `ml_features.py` (457), `multi_timeframe.py` (172) |
| Risk & sizing | 4 | `kelly_sizer.py` (601), `adaptive_exits.py` (706), `pyramider.py` (267), `sector_map.py` (96) |
| Learning & evolution | 6 | `self_evolution.py` (1,253), `continuous_learner.py` (401), `background_trainer.py` (412), `training.py`, `transfer_learning.py` (581), `walk_forward.py` (459) |
| Data & telemetry | 7 | `decision_telemetry.py` (464), `diagnostics.py`, `diagnostic_checks.py`, `streaming_data_provider.py` (336), `market_scanner.py` (475), `attribution.py` (421), `brain_persistence.py` (1,251) |
| Regime & ensemble | 2 | `regime.py` (666), `ensemble_models.py` |
| Infrastructure | 7 | `replay_simulator.py` (708), `promotion.py`, `nightly_scheduler.py`, `feature_store.py`, `universe_selector.py`, `replay_data_loader.py`, `replay_reporting.py` |

## Non-Organism Key Backend Files

| File | Lines | Role |
|------|-------|------|
| `services/order_service.py` | 1,714 | Order lifecycle management |
| `services/backtest_service.py` | 2,775 | Full backtesting engine |
| `risk/risk_manager.py` | 1,832 | Institutional risk manager |
| `config/base_settings.py` | 1,745 | Pydantic settings (all env vars) |
| `infra/schemas.py` | 1,444 | SQLAlchemy ORM models |
| `data/alpaca_client.py` | 925 | Alpaca REST data client |
| `integrations/alpaca_broker.py` | 881 | Order execution via Alpaca |
| `infra/security.py` | 859 | JWT auth, password hashing |
| `integrations/alpaca_stream.py` | 733 | Trade update WebSocket |
| `integrations/alpaca_market_data_stream.py` | 713 | Market data WebSocket |
| `infra/guardrails.py` | 545 | Pre-execution validation |

## Test Coverage

| Category | Files | Covers |
|----------|-------|--------|
| Organism core | 10 | Tick loop, scenarios, evolution, replay, invariants |
| Orders & positions | 7 | Lifecycle, fills, reconciliation, guardrails |
| Risk management | 5 | VaR, margin, limits, scenarios |
| ML / models | 4 | Pipeline, inference, prediction, ensemble |
| Strategies | 4 | Engine, service, comprehensive, basic |
| API & infrastructure | 7 | Routes, WebSocket, resilience, caching |
| Semantic invariants | 1 | 20 AST/import-based trading invariant checks |
| Unit comprehensive | 24 | Deep per-module coverage |
| Unit smoke | 199 | Import validation for all modules |
| Other | ~131 | Production, diagnostics, security, utilities |

## Architecture Docs

| Document | Lines | Scope |
|----------|-------|-------|
| `mapss.md` | 4,883 | Unified platform map (source of truth) |
| `improve9.md` | 359 | AIA deep research (Phase A+B) |
| `improve8.md` | 513 | Two-tier entry, session gating, learning risk caps |
| `improve7.md` | 381 | FTF chop redesign, confidence gating, circuit breaker |

## Control Plane

| File | Role |
|------|------|
| `AGENTS.md` | Agent operating contract |
| `.claude/settings.json` | Hooks: session start, pre-edit guard, post-edit verify, stop report |
| `.github/workflows/pr-verify.yml` | Path-based CI |
| `.github/workflows/paper-postclose-audit.yml` | Daily post-close KPI |
| `scripts/ci/check_spec_drift.py` | 3-way spec-vs-runtime drift |
| `scripts/runtime/write_runtime_snapshot.py` | 3-layer config snapshot generator |

## Bundle Contents

| File | Description |
|------|-------------|
| `CODEBASE_INDEX.md` | This file |
| `BASELINE_AUDIT_CONTEXT.md` | Module-by-module pipeline walkthrough |
| `strategy_surface_manifest.json` | Machine-readable 10-stage pipeline manifest |
| `core_backend_snapshot.tar.gz` | Source archive of 32 trading-critical modules |
| `resolved_config_snapshot.json` | Env-resolved config from live container |
| `live_process_runtime_snapshot.json` | Live process state from running API |
