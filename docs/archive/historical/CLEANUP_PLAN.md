# Platform Cleanup Plan

**Generated:** 2026-02-08  
**Workspace:** `c:\Users\Marsel\intra\algotrading_platform`

---

## Summary

| Category | DELETE | GITIGNORE | MOVE | MERGE | KEEP | Total |
|---|---|---|---|---|---|---|
| Root-level scripts | 3 | 2 | 0 | 0 | 1 | 6 |
| Root-level artifacts | 3 | 1 | 0 | 0 | 0 | 4 |
| Scripts directory | 16 | 0 | 0 | 3 | ~15 | ~34 |
| Docker/Config duplication | 1 | 0 | 0 | 1 | 4 | 6 |
| Test files | ~165 | 0 | 0 | 0 | ~198 | ~363 |
| Reports/Logs/Temp | 3 | 3 | 0 | 0 | 0 | 6 |
| Dead directories | 7 | 1 | 0 | 0 | 0 | 8 |
| Git-tracked artifacts | 2 | 2 | 0 | 0 | 0 | 4 |
| Makefile stale refs | 1 | 0 | 0 | 0 | 0 | 1 |

**Estimated disk savings:** ~1.6 GB (mostly logs, .trash, test_results, coverage)

---

## 1. Root-Level Python Scripts

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `main.py` | **KEEP** | Primary app entry point, used by Dockerfile/uvicorn | — |
| `start_backend.py` | **DELETE** | Debug startup script — duplicates `main.py` with verbose logging; not referenced in any workflow | safe |
| `reset_admin.py` | **DELETE** | One-time admin reset script with hardcoded creds. Functionality exists in `scripts/db/create_admin_user.py`. If needed, move to `scripts/db/` | safe |
| `reset_password.py` | **DELETE** | One-off script with hardcoded DB URL and password. Security risk to keep in repo | safe |
| `hash.txt` | **DELETE** | Contains a bcrypt hash — generated artifact, likely from `reset_password.py`. Git-tracked but serves no purpose | safe |
| `test_output.txt` | **GITIGNORE + DELETE** | Pytest output dump — generated artifact, should not be tracked | safe |
| `audit_trail.log` | **GITIGNORE** | Already in .gitignore pattern `*.log` — verify not tracked; 14MB log file | safe |
| `predictions.log` | **GITIGNORE** | Already matched by `.gitignore` `*.log` — 0-byte file | safe |

---

## 2. Scripts Directory

### scripts/ root-level scripts

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `analyze_failures.py` | **DELETE** | One-off debug analysis script | safe |
| `backtest_all_strategies.py` | **KEEP** | Active development/research utility | — |
| `backtest_diagnostics.py` | **DELETE** | One-off diagnostic script | low-risk |
| `backtest_feedback_loop.py` | **KEEP** | Referenced in reports and configs | — |
| `backtest_sanity_check.py` | **DELETE** | One-off validation script | safe |
| `check_bundle_size.py` | **KEEP** | Useful frontend build check | — |
| `check_imports.py` | **KEEP** | Code quality utility | — |
| `compare_optuna_holdout_api.py` | **KEEP** | References active config files | — |
| `compare_optuna_vs_ui_backtest.py` | **KEEP** | References active config files | — |
| `extended_3year_backtest.py` | **KEEP** | Research utility | — |
| `full_optimization_pipeline.py` | **KEEP** | Active pipeline script | — |
| `optimize_all_strategies.py` | **KEEP** | Active optimization | — |
| `optuna_meta_strategy_optimizer.py` | **KEEP** | Active optimization | — |
| `run_best_harder_holdout2025.ps1` | **KEEP** | References active config | — |
| `run_full_backtest.py` | **KEEP** | Active utility | — |
| `smoke_alpaca_market_data.py` | **KEEP** | Smoke test utility | — |
| `smoke_real_api_endpoints.py` | **KEEP** | Active smoke test (run recently) | — |
| `validate_indicators.py` | **KEEP** | Validation utility | — |
| `validate_indicator_accuracy.py` | **KEEP** | Validation utility | — |

### scripts/cleanup/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `audit_platform.py` | **DELETE** | One-off audit script, already executed | safe |
| `cleanup_platform.ps1` | **DELETE** | One-off cleanup already executed | safe |
| `cleanup_root_files.ps1` | **DELETE** | One-off cleanup already executed | safe |
| `cleanup_root_python_files.ps1` | **DELETE** | One-off cleanup already executed | safe |
| `fix_bom_encoding.py` | **DELETE** | One-off encoding fix | safe |
| `generate_env_catalog.py` | **DELETE** | One-off report generator | safe |
| `generate_env_catalog.zip` | **DELETE** | Artifact zip file in source tree | safe |
| `move_service_blueprints.py` | **DELETE** | One-off migration script | safe |
| `phase2_cleanup.ps1` | **DELETE** | One-off cleanup already executed | safe |
| `remove_consolidation_archive.py` | **DELETE** | One-off cleanup | safe |
| `remove_dead_files.sh` | **DELETE** | One-off cleanup | safe |

**Recommendation: Delete entire `scripts/cleanup/` directory.** These are all one-shot scripts whose work is done.

### scripts/ci/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `AutoCommit.ps1` | **DELETE** | Auto-commit script — dangerous in production repo | low-risk |
| `autocommit.sh` | **DELETE** | Same as above, shell version | low-risk |
| `AutoPushLog.ps1` | **DELETE** | Auto-push — dangerous for production | low-risk |
| `check_coverage.py` | **KEEP** | Referenced in Makefile `coverage-quality-gate` target | — |
| `check_coverage_clean.py` | **MERGE** | Likely duplicate of `check_coverage.py` | needs-review |
| `check_coverage_ratchet.py` | **MERGE** | Likely duplicate of `check_coverage.py` | needs-review |
| `check_metrics_labels.py` | **KEEP** | Referenced in CI workflow `.github/workflows/ci.yml` | — |
| `ci_full.ps1` | **KEEP** | CI pipeline script | — |
| `ci_minimal.ps1` | **KEEP** | CI pipeline script | — |
| `merge_junit.py` | **KEEP** | Test report utility | — |
| `quality_gates.ps1` | **KEEP** | Quality gate script | — |
| `run_ci_locally.bat` | **KEEP** | Local CI runner | — |
| `run_ci_locally.sh` | **KEEP** | Local CI runner | — |
| `stop_all_tests.ps1` | **DELETE** | One-off debug utility | safe |
| `test_phase3_api.ps1` | **DELETE** | Phase-specific test runner — phase completed | safe |
| `validate_checklist.py` | **DELETE** | One-off validation | safe |
| `validate_pipeline.py` | **DELETE** | One-off validation | safe |
| `verify_critical_fixes.py` | **DELETE** | One-off verification | safe |
| `verify_integration.py` | **DELETE** | One-off verification | safe |
| `verify_phase1_implementation.py` | **DELETE** | Phase-specific, completed | safe |
| `view_coverage.bat` | **KEEP** | Useful developer utility | — |

### scripts/dev/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `Capture.ps1` | **DELETE** | One-off debug capture | safe |
| `capture.sh` | **DELETE** | Same, shell version | safe |
| `check_config_import.py` | **DELETE** | One-off debug | safe |
| `configure_alpaca.ps1` | **KEEP** | Setup utility | — |
| `dump_routes.py` | **KEEP** | Useful debugging tool | — |
| `export_openapi.py` | **KEEP** | API documentation generator | — |
| `get_token.py` | **KEEP** | Development utility | — |
| `pre_burnin_checklist.ps1` | **KEEP** | Deployment checklist | — |
| `quick_http.py` | **KEEP** | Quick HTTP test utility | — |
| `quick_validation.ps1` | **KEEP** | Validation utility | — |
| `restart-vite.ps1` | **KEEP** | Frontend dev utility | — |
| `restart_backend.ps1` | **KEEP** | Backend dev utility | — |
| `setup_localtunnel.ps1` | **MERGE** | Multiple tunnel setup scripts — consolidate | needs-review |
| `setup_localtunnel_no_password.ps1` | **MERGE** | Merge into one tunnel script | needs-review |
| `setup_ngrok_complete.ps1` | **MERGE** | Merge with other ngrok scripts | needs-review |
| `setup_ngrok_tunnels.ps1` | **MERGE** | Four ngrok/localtunnel scripts → consolidate to 1 | needs-review |
| `STAGING_MONITORING_SCRIPT.ps1` | **KEEP** | Staging monitoring | — |
| `start-server.ps1` | **KEEP** | Server start utility | — |
| `update_frontend_for_ngrok.ps1` | **DELETE** | One-off script for ngrok frontend config | safe |

### scripts/db/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `clear_outbox.sql` | **KEEP** | Operational utility | — |
| `clear_stuck_outbox_events.ps1` | **KEEP** | Production operations utility | — |
| `create_admin_user.py` | **KEEP** | Replaces root-level `reset_admin.py` | — |
| `init-db.sql` | **KEEP** | Database initialization | — |
| `migrate.py` | **KEEP** | Migration utility | — |
| `run_users_migration.py` | **DELETE** | One-off migration, already applied | low-risk |
| `seed_staging.py` | **KEEP** | Staging seed data | — |

### scripts/testing/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `ai_enhancement_integration_test.py` | **DELETE** | One-off AI integration test | low-risk |
| `automated_promotion_gates.py` | **KEEP** | Part of test infrastructure | — |
| `burn_in_framework.py` | **KEEP** | Test framework | — |
| `check_services_availability.py` | **KEEP** | Health check utility | — |
| `comprehensive.py` | **DELETE** | Vague name, likely one-off comprehensive test | needs-review |
| `k6_cache_manager.py` | **KEEP** | Performance test infrastructure | — |
| `k6_enhanced_comprehensive_test.js` | **KEEP** | Performance test | — |
| `minimal.py` | **DELETE** | One-off minimal test | safe |
| `paper_trading_smoke.py` | **KEEP** | Paper trading smoke test | — |
| `performance_test.py` | **KEEP** | Performance test | — |
| `PHASE_G_MIGRATION_SUMMARY.md` | **DELETE** | Completed phase summary | safe |
| `run_complete_five_layer_tests.py` | **DELETE** | Test runner that duplicates pytest | low-risk |
| `run_k6_smoke.ps1` | **KEEP** | Performance test runner | — |
| `run_matrix.ps1` | **KEEP** | Test matrix runner | — |
| `run_matrix.py` | **KEEP** | Test matrix runner | — |
| `run_one.ps1` | **KEEP** | Single test runner | — |
| `run_single.py` | **KEEP** | Single test runner | — |
| `test_layer5_business_workflows.py` | **DELETE** | One-off layered test | low-risk |
| `test_layers_1_to_4_consolidated.py` | **DELETE** | One-off layered test | low-risk |
| `test_output_enhanced.py` | **DELETE** | One-off test output parser | safe |
| `test_parsing_logic.py` | **DELETE** | One-off parser test | safe |
| `test_results/` | **DELETE** | Nested test results directory — should be gitignored | safe |
| `verify_test_framework.py` | **DELETE** | One-off verification | safe |

### scripts/deploy/

All **KEEP** — active deployment scripts.

### scripts/backup/ and scripts/chaos/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `scripts/backup/rehearsal.py` | **KEEP** | Backup rehearsal utility | — |
| `scripts/chaos/kill_pod.ps1` | **KEEP** | Chaos engineering utility | — |
| `scripts/chaos/kill_pod.sh` | **KEEP** | Chaos engineering utility | — |

### scripts/migrations/

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `001_create_users_table.sql` | **DELETE** | Already applied, managed by alembic now | low-risk |
| `001_create_users_table_sqlite.sql` | **DELETE** | SQLite variant, never used in production | safe |
| `002_add_brute_force_protection.sql` | **DELETE** | Already applied, managed by alembic | low-risk |

**Recommendation: Delete entire `scripts/migrations/` directory.** Alembic is the migration system.

---

## 3. Duplicate/Redundant Test Files

### Critical finding: 363 test files across 4 locations

| Location | Count | Notes |
|---|---|---|
| `tests/` root | 117 | Mix of comprehensive, extended, edge-case tests |
| `tests/unit/` | 81 | Hand-written unit tests |
| `tests/unit/generated/` | 165 | Auto-generated `test_auto_*.py` files |
| `tests/integration/` | 1 | Nearly empty |
| `tests/real_tests/` | 10 | Real API/DB integration tests |

### Recommendations

| Item | Recommendation | Reason | Risk |
|---|---|---|---|
| `tests/unit/generated/` (165 files) | **DELETE** | Auto-generated tests with `test_auto_` prefix — low-value coverage padding that masks real coverage gaps. Can be regenerated if needed | needs-review |
| `tests/test_route_registry.py` + `tests/test_routes_registry.py` | **MERGE** | Duplicate test files for same module (note singular vs plural) | low-risk |
| `tests/test_risk_manager_comprehensive.py` + `tests/test_risk_manager_extended.py` + `tests/test_risk_manager_positions.py` + `tests/test_risk_manager_service_comprehensive.py` + `tests/test_risk_management_complete.py` | **MERGE** | 5 test files for risk_manager — consolidate | needs-review |
| `tests/test_cache_service_comprehensive.py` + `tests/test_cache_service_extended.py` | **MERGE** | Duplicate coverage | low-risk |
| `tests/test_quote_manager_comprehensive.py` + `tests/test_quote_manager_extended.py` | **MERGE** | Duplicate coverage | low-risk |
| `tests/test_indicators_comprehensive.py` + `tests/test_indicators_extended.py` + `tests/test_indicators_additional.py` | **MERGE** | 3 files for indicators | low-risk |
| `tests/test_trading_strategies_comprehensive.py` + `tests/test_trading_strategies_extended.py` | **MERGE** | Duplicate coverage | low-risk |
| `tests/test_models_api.py` + `tests/test_models_api_simple.py` | **MERGE** | Duplicate coverage | low-risk |
| `tests/test_analytics_diagnostic.py` + `tests/test_analytics_endpoint.py` + `tests/test_analytics_api_full.py` | **MERGE** | 3 files for analytics | low-risk |
| `tests/integration/test_optimization_import_flow.py` | **MOVE** | Only file in `tests/integration/` — move to `tests/` root or delete if covered elsewhere | low-risk |
| `tests/TEST_COVERAGE_STATUS.md` | **DELETE** | Stale status doc, quickly outdated | safe |
| Test `.ps1` runners in `tests/` | **DELETE** | `test_one_by_one.ps1`, `run_ml_tests.ps1`, `run_alpaca_tests.ps1`, `quick_coverage_check.ps1` — duplicates VS Code task definitions and pytest CLI | low-risk |

---

## 4. Reports / Logs / Temporary Files

### reports/ — Git-tracked audit reports

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| All files in `reports/` | **GITIGNORE** | Generated audit reports with dates — should not be tracked. Add `reports/` to `.gitignore` (keep a `reports/.gitkeep`) | safe |
| `reports/changes_today.md` | **DELETE** | Stale changelog unlikely to stay current | safe |
| `reports/ENV_CATALOG.md` | Already gitignored | Contains secret values per `.gitignore` comment | — |

### logs/ — 1.5 GB of log files

| Item | Recommendation | Reason | Risk |
|---|---|---|---|
| `logs/` directory | **Already gitignored** (mostly) | But contains **1,488 MB** of log files locally. Run `rm logs/application.log.*` to reclaim disk space | safe |
| Root `audit_trail.log` (14 MB) | **DELETE locally** | Matched by `*.log` gitignore, but exists — delete the local file | safe |
| Root `predictions.log` | **DELETE locally** | Empty file, already gitignored | safe |

### test_results/ — 42.6 MB, already gitignored

| Item | Recommendation | Reason | Risk |
|---|---|---|---|
| Old junit XML files (27 files) | **DELETE locally** | Generated test artifacts accumulating since Jan 28 | safe |
| Old pytest log files (27 files) | **DELETE locally** | Same | safe |
| `test_db.sqlite3` | **DELETE** | Test database artifact | safe |
| Optuna result text files (20+) | **DELETE locally** | Old optimization run outputs | safe |

### coverage_report/ — 29.9 MB, already gitignored ✓

Not tracked. Local cleanup only.

### htmlcov/ — Already gitignored ✓

### .coverage, .pytest_cache/ — Already gitignored ✓

---

## 5. Dead Directories and Empty Folders

| Directory | Recommendation | Reason | Risk |
|---|---|---|---|
| `.trash/` (40.9 MB) | **DELETE** | Already gitignored. Contains old cleanup from 2026-01-18. No reason to keep | safe |
| `model_optimization/` | **DELETE** | Empty directory, already gitignored | safe |
| `model_serving/` | **DELETE** | Empty directory, already gitignored | safe |
| `data/` | **DELETE** | Empty directory | safe |
| `governance/` | **DELETE or KEEP** | Empty — if governance framework is planned, keep with `.gitkeep` | safe |
| `experiments/artifacts/` | **DELETE** | Empty nested directory | safe |
| `models/active_models/` (76 tmp files) | **GITIGNORE + DELETE locally** | 76 temp files from test runs — add `models/active_models/` to `.gitignore`. These are **git-tracked** (66 files!) | **needs-review** |
| `models/registry/` | **GITIGNORE** | Model registry — runtime artifact | needs-review |
| `models/storage/` | **DELETE** | Empty | safe |
| `backups/` (12 SQL dumps) | **GITIGNORE + DELETE** | Verification backups from Feb 1 — all git-tracked. **Should NOT be in repo**. Add `backups/` to `.gitignore` and `git rm --cached` | **safe** |

---

## 6. Docker/Config Duplication

### Docker Compose files (4 files)

| File | Lines | Recommendation | Reason | Risk |
|---|---|---|---|---|
| `docker-compose.yml` | ~100 | **KEEP** | Development/staging — primary compose file | — |
| `docker-compose.paper.yml` | ~100 | **KEEP** | Paper trading env — distinct config. **BUT** contains hardcoded API keys/secrets — needs sanitization | — |
| `docker-compose.prod.yml` | 137 | **MERGE into production.yml, then DELETE** | Simpler/older prod config. `docker-compose.production.yml` is the comprehensive version (275 lines) used by deploy scripts. `prod.yml` is not referenced in any deploy script or CI workflow | low-risk |
| `docker-compose.production.yml` | 275 | **KEEP** | Referenced in `scripts/deploy/deploy-production.ps1`. Uses env vars properly (no hardcoded secrets) | — |
| `Dockerfile` | — | **KEEP** | Development Dockerfile | — |
| `Dockerfile.production` | — | **KEEP** | Production Dockerfile | — |

### Config directories (2 directories)

| Directory | Recommendation | Reason | Risk |
|---|---|---|---|
| `config/` | **KEEP** | Infrastructure config (PostgreSQL, Prometheus, OTEL, SLO) | — |
| `configs/` | **KEEP** | Strategy/optimization configs — actively referenced in scripts | — |

No duplication between `config/` and `configs/` — they serve different purposes (infra vs strategy).

### Kubernetes manifests

| File | Recommendation | Reason | Risk |
|---|---|---|---|
| `k8s/` (all files) | **KEEP** | Complete K8s deployment manifests — appears actively maintained | — |

---

## 7. Makefile Issues

| Issue | Recommendation | Reason | Risk |
|---|---|---|---|
| `test-fast` target references 18 non-existent files/dirs | **FIX** | References `tests/services/`, `tests/security/`, `tests/api/`, `tests/config/`, `tests/strategies/`, `tests/risk/`, `tests/mlops/`, `tests/utils/`, `tests/test_coverage_boost.py`, `tests/test_config_working.py` — **none of these exist**. This target is **completely broken** | **needs-review** |
| `coverage` target references `tests/contract/` | **FIX** | `tests/contract/` does not exist | needs-review |
| `auto` target references `scripts/autofix_and_test.sh` | **FIX** | File doesn't exist. `create-autofix-script` target has a duplicate label bug | low-risk |
| CI reference to `scripts/ci/check_performance_regression.py` | **OK** | Nightly workflow uses `|| true` so it won't fail if missing | — |

---

## 8. .gitignore Gaps

Items that are **NOT gitignored but should be**:

| Pattern | Recommendation | Why |
|---|---|---|
| `backups/` | **ADD to .gitignore** | 12 SQL dumps currently tracked |
| `models/active_models/` | **ADD to .gitignore** | 76 temp files currently tracked |
| `models/registry/` | **ADD to .gitignore** | Runtime model registry artifacts |
| `reports/*.txt` | **ADD to .gitignore** | Generated audit report artifacts |
| `reports/*.jsonl` | **ADD to .gitignore** | Generated findings files |
| `reports/*.md` (except README) | **ADD to .gitignore** | Generated report markdown |
| `hash.txt` | **ADD to .gitignore** | Generated credential hash |
| `test_output.txt` | **ADD to .gitignore** | Generated test output |
| `__pycache__/` in `scripts/` | Already covered by `__pycache__/` pattern ✓ | |

---

## 9. Priority Action Items

### Phase 1: Immediate / Safe Deletes (no risk)

```
# Root-level cruft
DELETE  start_backend.py
DELETE  reset_password.py
DELETE  reset_admin.py
DELETE  hash.txt
DELETE  test_output.txt
DELETE  audit_trail.log (local)
DELETE  predictions.log (local)

# Entire directories
DELETE  .trash/                    # 40.9 MB reclaimed
DELETE  scripts/cleanup/           # 11 one-off scripts
DELETE  scripts/migrations/        # 3 files, alembic manages this
DELETE  model_optimization/        # empty
DELETE  model_serving/             # empty  
DELETE  data/                      # empty
DELETE  experiments/artifacts/     # empty
DELETE  models/storage/            # empty
```

### Phase 2: Git Untrack + Gitignore

```
# Add to .gitignore
backups/
models/active_models/
models/registry/
reports/
hash.txt
test_output.txt

# Then run:
git rm --cached -r backups/
git rm --cached -r models/active_models/
git rm --cached hash.txt
git rm --cached -r reports/  # keep reports/.gitkeep
```

### Phase 3: Local Disk Cleanup

```
# ~1.5 GB in logs
Remove-Item logs/application.log.* -Force
Remove-Item logs/audit_trail.log -Force

# ~42 MB in test_results  
Remove-Item test_results/junit_*.xml -Force
Remove-Item test_results/pytest_*.log -Force
Remove-Item test_results/optuna_*.txt -Force
Remove-Item test_results/test_db.sqlite3 -Force

# ~30 MB in coverage_report
Remove-Item coverage_report -Recurse -Force

# ~41 MB in .trash
Remove-Item .trash -Recurse -Force
```

### Phase 4: Merge Docker Compose (needs-review)

```
# Delete docker-compose.prod.yml after confirming docker-compose.production.yml is the canonical one
DELETE  docker-compose.prod.yml
```

### Phase 5: Fix Broken Makefile (needs-review)

The `test-fast` and `coverage` targets reference directories and files that don't exist. Either:
- Update paths to match current test structure, or
- Remove those targets and use VS Code tasks / pytest directly

### Phase 6: Test File Consolidation (longer-term)

- Review `tests/unit/generated/` (165 auto-generated files) — delete if not providing meaningful coverage
- Merge duplicate test files covering the same modules (8+ merge opportunities listed above)
- Remove test `.ps1` runners from `tests/` that duplicate VS Code task definitions

---

## 10. Security Notes (from audit)

| Issue | Location | Severity |
|---|---|---|
| Hardcoded API keys | `docker-compose.paper.yml` | **CRITICAL** — rotate Alpaca keys immediately |
| Hardcoded JWT secret | `docker-compose.paper.yml`, `docker-compose.prod.yml` | **CRITICAL** — rotate JWT secret |
| Hardcoded DB password | `docker-compose.paper.yml`, `docker-compose.prod.yml` | **HIGH** |
| `.env.production` tracked | Root directory | **HIGH** — should only have `.env.production.template` |
| `reset_password.py` has hardcoded DB URL | Root | **MEDIUM** — delete this file |

These were flagged in the existing `reports/comprehensive_audit_findings.jsonl` but should be acted on urgently.
