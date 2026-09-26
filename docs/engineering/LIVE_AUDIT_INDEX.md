# Live Audit Index

Generated: 2026-09-26T23:03:58Z
PR: n/a
SHA: `8ebbb1c126`
Branch: `codex/platform-audit-20260926`
Scope: **backend_logic**
Change scope: `base` (`bf533a43d01a4c2e7428ea9589159d9c7d242319...HEAD`)

## Changed files

Total distinct changed files: **45**

Category counts below partition that total. File previews show at most ten paths per category; the full list follows.

| Category | Count | Files (preview) |
|----------|-------|-----------------|
| Backend | 5 | `backend/api/lifespan.py`, `backend/api/portfolio.py`, `backend/api/socketio_server.py`, `backend/integrations/alpaca_stream.py`, `backend/services/portfolio_service.py` |
| Scripts | 1 | `scripts/ci/nightly_test_contract.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 12 | `tests/test_adversarial_inputs_v7.py`, `tests/test_fill_accounting_integrity.py`, `tests/test_fill_accounting_postgres.py`, `tests/test_monday_ci_workflows.py`, `tests/test_nightly_test_contract.py`, `tests/test_portfolio_availability_contract.py`, `tests/test_portfolio_service_comprehensive.py`, `tests/test_socketio_topic_authorization.py`, `tests/test_wave43_fixes.py`, `tests/test_wave52_fixes.py` |
| Docs | 1 | `docs/engineering/MONDAY_CI_READINESS.md` |
| Artifacts/evidence | 0 | none |
| Reports | 4 | `reports/PLATFORM_AUDIT_FROZEN_REPAIR_SCOPE_2026-09-26.md`, `reports/platform_audit_20260926/PLATFORM_REVIEW.md`, `reports/platform_audit_20260926/research_readiness.md`, `reports/platform_audit_20260926/research_readiness_sources.json` |
| Configuration | 0 | none |
| Other | 21 | `frontend/src/components/layout/GlobalStatusBar.test.tsx`, `frontend/src/components/layout/GlobalStatusBar.tsx`, `frontend/src/features/dashboard/Dashboard.test.tsx`, `frontend/src/features/dashboard/Dashboard.tsx`, `frontend/src/features/organism/OrganismDashboard.tsx`, `frontend/src/features/organism/__tests__/OrganismDashboard.test.tsx`, `frontend/src/features/portfolio/PortfolioPage.test.tsx`, `frontend/src/features/portfolio/PortfolioPage.tsx`, `frontend/src/hooks/useData.ts`, `frontend/src/hooks/usePortfolio.test.tsx` |

Organism subset of Backend: **0** file(s).

### Full changed-file list

- `.github/workflows/paper-readiness.yml`
- `backend/api/lifespan.py`
- `backend/api/portfolio.py`
- `backend/api/socketio_server.py`
- `backend/integrations/alpaca_stream.py`
- `backend/services/portfolio_service.py`
- `docs/engineering/MONDAY_CI_READINESS.md`
- `frontend/src/components/layout/GlobalStatusBar.test.tsx`
- `frontend/src/components/layout/GlobalStatusBar.tsx`
- `frontend/src/features/dashboard/Dashboard.test.tsx`
- `frontend/src/features/dashboard/Dashboard.tsx`
- `frontend/src/features/organism/OrganismDashboard.tsx`
- `frontend/src/features/organism/__tests__/OrganismDashboard.test.tsx`
- `frontend/src/features/portfolio/PortfolioPage.test.tsx`
- `frontend/src/features/portfolio/PortfolioPage.tsx`
- `frontend/src/hooks/useData.ts`
- `frontend/src/hooks/usePortfolio.test.tsx`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/services/api.test.ts`
- `frontend/src/services/api.ts`
- `frontend/src/services/authService.test.tsx`
- `frontend/src/services/authService.ts`
- `frontend/src/services/websocketManager.test.tsx`
- `frontend/src/services/websocketManager.ts`
- `frontend/src/store/portfolioStore.ts`
- `frontend/src/test/portfolioFixture.ts`
- `frontend/src/utils/portfolioSnapshot.test.ts`
- `frontend/src/utils/portfolioSnapshot.ts`
- `reports/PLATFORM_AUDIT_FROZEN_REPAIR_SCOPE_2026-09-26.md`
- `reports/platform_audit_20260926/PLATFORM_REVIEW.md`
- `reports/platform_audit_20260926/research_readiness.md`
- `reports/platform_audit_20260926/research_readiness_sources.json`
- `scripts/ci/nightly_test_contract.py`
- `tests/test_adversarial_inputs_v7.py`
- `tests/test_fill_accounting_integrity.py`
- `tests/test_fill_accounting_postgres.py`
- `tests/test_monday_ci_workflows.py`
- `tests/test_nightly_test_contract.py`
- `tests/test_portfolio_availability_contract.py`
- `tests/test_portfolio_service_comprehensive.py`
- `tests/test_socketio_topic_authorization.py`
- `tests/test_wave43_fixes.py`
- `tests/test_wave52_fixes.py`
- `tests/unit/test_alpaca_stream_comprehensive.py`
- `tests/unit/test_api_routes_mocked_coverage.py`

## Configuration resolution (not engine observation)

Source: `resolved_config_snapshot.json`
Evidence scope: `offline_source_and_process_defaults_not_runtime_observation`
These values describe this generator's configuration inputs. Offline runs can contain source defaults and test-process paths; they do not establish the installed paper configuration.

```json
{
  "timeframe": "1Day",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.05,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": false,
  "phase9_shadow_engines_enabled": false
}
```

## Snapshot files

- Source/process defaults: `artifacts/runtime_defaults_snapshot.json`
- Expected configuration resolution: `artifacts/resolved_config_snapshot.json`
- Separate live-process evidence (check reachability and field provenance): `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- Displayed configuration is expected configuration, not observed engine state; inspect the separate live-process evidence and its reachability.
- 5 backend runtime file(s) changed — require targeted verification
