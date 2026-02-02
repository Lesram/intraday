# Comprehensive Algotrading Platform Audit Report
**Date:** January 18, 2026
**Auditor:** GitHub Copilot (GPT-5.2)
**Scope:** Repo-wide line-by-line scan + must-review deep dives (see sections)

## 1) Architecture & Structure

### Directory Map (Top Level)
- **(root files)**
  - ADMIN_SETUP.md
  - alembic.ini
  - audit_trail.log
  - AUTHENTICATION_SETUP.md
  - cleanup_platform.ps1
  - cleanup_root_files.ps1
  - cleanup_root_python_files.ps1
  - clear_outbox.sql
  - clear_stuck_outbox_events.ps1
  - COMPREHENSIVE_PLATFORM_AUDIT_PROMPT.md
  - configure_alpaca.ps1
  - DATABASE_SETUP.md
  - debug_trades.html
  - deploy-production.ps1
  - deploy.ps1
  - deploy.sh
  - docker-compose.paper.yml
  - docker-compose.prod.yml
  - docker-compose.production.yml
  - docker-compose.yml
  - Dockerfile
  - Dockerfile.production
  - ENVIRONMENT_VARIABLES.md
  - final_trading_strategies_100.json
  - logging_config.yaml
- **alembic/**
  - versions/
- **backend/**
  - __init__.py
  - __pycache__/
  - analytics/
  - api/
  - brokers/
  - config/
  - config.py
  - config_helpers.py
  - data/
  - database/
  - database.py
  - deployment/
  - features/
  - infra/
  - integrations/
  - migrations/
  - ml/
  - mlops/
  - models/
  - monitoring/
  - observability/
  - optimization/
  - risk/
  - security/
  - services/
- **clients/**
  - js/
- **config/**
  - development.json
  - otel-collector-config.yaml
  - prometheus.yml
  - slo_alerts.json
- **core/**
  - __init__.py
  - config.py
- **docs/**
  - ai/
  - ALPACA_PORTFOLIO_SYNC.md
  - ALPACA_SYNC_COMPLETE.md
  - archive/
  - BACKEND_ARCHITECTURE_ANALYSIS.md
  - blueprints/
  - CORS_CONFIGURATION.md
  - deployment/
  - integration/
  - openapi.json
  - operations/
  - PHASE4_GATE_IMPLEMENTATION.md
  - POST_LAUNCH_MONITORING.md
  - reports/
  - runbooks/
  - SIGNAL_AGGREGATION_DESIGN.md
  - TLS_SETUP_GUIDE.md
  - WEBSOCKET_FIX_SUMMARY.md
  - WEBSOCKET_GUIDE.md
- **examples/**
  - basic_trading_bot.py
  - live_trading.py
  - model_training.py
  - simple_demo.py
- **frontend/**
  - .env.example
  - .env.local
  - .gitignore
  - .prettierignore
  - .prettierrc.json
  - dist/
  - docs/
  - eslint.config.js
  - index.html
  - node_modules/
  - package-lock.json
  - package.json
  - PHASE2_COMPLETE.md
  - PHASE_1_COMPLETE.md
  - PHASE_1_KICKOFF.md
  - PHASE_2_DETAILED_STEPS.md
  - public/
  - QUICK_START.md
  - README.md
  - src/
  - TROUBLESHOOTING.md
  - tsconfig.app.json
  - tsconfig.json
  - tsconfig.node.json
  - vite.config.ts
- **k8s/**
  - admin-user-job.yaml
  - deployment.yaml
  - kustomization.yaml
  - namespace.yaml
  - otel-collector.yaml
  - patches/
  - postgres.yaml
  - prometheus.yaml
  - redis.yaml
  - secrets.yaml
  - service.yaml
  - tls/
- **migrations/**
  - versions/
- **models/**
  - ensemble/
  - model_registry.json
  - noop_test_1.0.0.pkl
  - storage/
  - unknown/
  - unknown_1.0.0.pkl
- **monitoring/**
  - docker-compose.yml
  - grafana/
  - memory_monitoring.json
  - production_dashboard.py
  - prometheus/
- **perf/**
  - .env.k6
  - python_k6_alternative.py
  - run_k6_order_flow.ps1
  - simple_test.js
  - summary.json
- **reports/**
  - archive/
  - audit/
  - CLEANUP_PLAN.csv
  - comprehensive_audit_findings.jsonl
  - ENV_CATALOG.md
  - FALSE_POSITIVES_ACTIONS.csv
  - FALSE_POSITIVES_AUDIT.md
  - FALSE_POSITIVES_EXECUTIVE_SUMMARY.md
  - FALSE_POSITIVES_FINAL_LOOP_CLOSURE.md
  - FALSE_POSITIVES_IMPLEMENTATION_SUMMARY.md
  - FALSE_POSITIVES_NEXT_STEPS.md
- **scripts/**
  - AutoCommit.ps1
  - autocommit.sh
  - AutoPushLog.ps1
  - backup/
  - Capture.ps1
  - capture.sh
  - chaos/
  - check_config_import.py
  - check_coverage.py
  - check_coverage_clean.py
  - ci/
  - ci_full.ps1
  - ci_minimal.ps1
  - cleanup/
  - comprehensive.py
  - create_admin_user.py
  - db/
  - dump_routes.py
  - export_openapi.py
  - get_token.py
  - init-db.sql
  - merge_junit.py
  - migrate.py
  - migrations/
  - minimal.py
- **security/**
  - waivers.yml
- **test/**
  - __init__.py
  - __pycache__/
  - conftest.py
- **tests/**
  - __pycache__/
  - conftest.py
  - test_advanced_risk.py
  - test_alembic_head.py
  - test_alerting.py
  - test_analytics_api_full.py
  - test_analytics_diagnostic.py
  - test_analytics_endpoint.py
  - test_api_endpoint_validation.py
  - test_backtest_api_integration.py
  - test_backtest_service_comprehensive.py
  - test_credentials.py
  - test_edge_cases_automated.py
  - test_ensemble_framework.py
  - test_health_endpoints.py
  - test_idempotency.py
  - test_models_api.py
  - test_models_api_simple.py
  - test_observability_service.py
  - test_order_lifecycle.py
  - test_order_validation.py
  - test_performance.py
  - test_performance_slo.py
  - test_phase1_best_worst_trade.py
  - test_phase2_lot_tracking.py
- **tools/**
  - audit/
  - debug/
- **utils/**
  - __init__.py
  - logging.py
  - validators.py

## 2) Findings (Auto-Extracted)

### CRITICAL (69)

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database.py` lines 186-186

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database.py` lines 196-196

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
f"Expected: postgresql+asyncpg://... or postgresql+psycopg2://...\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/api/factory.py` lines 147-147

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"  export DATABASE_URL='postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading'\n\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/api/factory.py` lines 149-149

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"  $env:DATABASE_URL='postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading'\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/config/base_settings.py` lines 214-214

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
description="Database connection URL (REQUIRED). Example: postgresql+asyncpg://user:pass@host:5432/dbname"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `backend/config/base_settings.py` lines 949-949

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
self.security.jwt_secret_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `backend/config/base_settings.py` lines 1015-1015

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
settings.security.jwt_secret_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/config/coordinator.py` lines 105-105

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
return os.getenv('DATABASE_URL', 'postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading')
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/config/unified.py` lines 29-29

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
default="postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading",
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database/database_config.py` lines 34-34

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"  export DATABASE_URL='postgresql://trading:trading_password@localhost:5432/algotrading'\\n\\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database/database_config.py` lines 36-36

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"  $env:DATABASE_URL='postgresql://trading:trading_password@localhost:5432/algotrading'\\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database/unified_config.py` lines 52-52

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"))
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database/__init__.py` lines 230-230

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `backend/database/__init__.py` lines 240-240

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
f"Expected: postgresql+asyncpg://... or postgresql+psycopg2://...\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `backend/deployment/validator.py` lines 333-333

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e JWT_SECRET_KEY="your_production_jwt_secret" \\
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `clear_stuck_outbox_events.ps1` lines 16-16

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
Write-Host '  $env:DATABASE_URL = "postgresql://user:password@localhost:5432/algotrading"' -ForegroundColor Gray
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `clear_stuck_outbox_events.ps1` lines 24-24

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
if ($dbUrl -match "postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)") {
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `start-server.ps1` lines 75-75

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
Write-Host "  `$env:DATABASE_URL='postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading'" -ForegroundColor Cyan
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `start-server.ps1` lines 54-54

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
$env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-change-in-production-minimum-32-chars"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docker-compose.paper.yml` lines 21-21

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- DATABASE_URL=postgresql+asyncpg://trading_user:trading_password_secure_2024@postgres:5432/trading_platform
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `docker-compose.paper.yml` lines 35-35

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- JWT_SECRET_KEY=<REDACTED>
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docker-compose.prod.yml` lines 19-19

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- DATABASE_URL=postgresql+asyncpg://trading_user:trading_password_secure_2024@postgres:5432/trading_platform
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `docker-compose.prod.yml` lines 32-32

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- JWT_SECRET_KEY=<REDACTED>
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docker-compose.production.yml` lines 29-29

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- DATABASE_URL=postgresql+asyncpg://${DB_USER:-algo}:${DB_PASSWORD}@postgres:5432/${DB_NAME:-algotrading}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docker-compose.yml` lines 22-22

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- DATABASE_URL=postgresql+asyncpg://trading:trading_password@db:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `docker-compose.yml` lines 33-33

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- JWT_SECRET_KEY=development-secret-key-change-in-production
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `.github/workflows/ci.yml` lines 185-185

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `.github/workflows/ci.yml` lines 197-197

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `.github/workflows/nightly.yml` lines 63-63

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `.github/workflows/nightly.yml` lines 75-75

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `.github/workflows/nightly.yml` lines 89-89

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `k8s/kustomization.yaml` lines 38-38

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- database-url=postgresql+asyncpg://trading:CHANGEME@postgres-service:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `k8s/namespace.yaml` lines 96-96

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
database-url: "postgresql+asyncpg://trading:CHANGEME@postgres-service:5432/algotrading"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `k8s/secrets.yaml` lines 15-15

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
database-url: "postgresql+asyncpg://trading_user:CHANGE_DB_PASSWORD@postgres:5432/trading_platform"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `ADMIN_SETUP.md` lines 85-85

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trading_db
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `AUTHENTICATION_SETUP.md` lines 66-66

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `AUTHENTICATION_SETUP.md` lines 93-93

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
export DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `AUTHENTICATION_SETUP.md` lines 453-453

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
psql postgresql://trading:trading_password@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `AUTHENTICATION_SETUP.md` lines 69-69

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
JWT_SECRET_KEY=your-secret-key-here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `DATABASE_SETUP.md` lines 26-26

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
$env:DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `DATABASE_SETUP.md` lines 31-31

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
export DATABASE_URL="postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `DATABASE_SETUP.md` lines 85-85

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
$env:DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `DATABASE_SETUP.md` lines 109-109

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `DATABASE_SETUP.md` lines 230-230

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
postgresql+asyncpg://username:password@prod-db.example.com:5432/algotrading?ssl=require
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `DATABASE_SETUP.md` lines 120-120

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
JWT_SECRET_KEY=your-secret-key-here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `ENVIRONMENT_VARIABLES.md` lines 46-46

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://algotrading_user:password@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `ENVIRONMENT_VARIABLES.md` lines 168-168

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://...  # Production database
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 49-49

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
JWT_SECRET_KEY=your_random_64_character_secret_key_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `PLATFORM_AUDIT_REPORT_2026-01-18.md` lines 191-191

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- `docker-compose.yml` lines 32-34 (`JWT_SECRET_KEY=development-secret-key-change-in-production`)
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] JWT secret present in file
**Location:** `PLATFORM_AUDIT_REPORT_2026-01-18.md` lines 196-196

**Description:**
Pattern match for: JWT secret present in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
**Description:** A long `SECURITY_JWT_SECRET=...` value is present in a committed file.
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `README.md` lines 569-569

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/trading \
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `README.md` lines 589-589

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
--from-literal=database-url="postgresql+asyncpg://user:pass@postgres:5432/trading" \
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 221-221

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `docs/ALPACA_SYNC_COMPLETE.md` lines 263-263

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/algotrading
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] AWS credential material
**Location:** `frontend/PHASE_1_KICKOFF.md` lines 917-917

**Description:**
Pattern match for: AWS credential material.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] AWS credential material
**Location:** `frontend/PHASE_1_KICKOFF.md` lines 917-917

**Description:**
Pattern match for: AWS credential material.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] AWS credential material
**Location:** `frontend/PHASE_1_KICKOFF.md` lines 918-918

**Description:**
Pattern match for: AWS credential material.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] AWS credential material
**Location:** `frontend/PHASE_1_KICKOFF.md` lines 918-918

**Description:**
Pattern match for: AWS credential material.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_AUDIT.md` lines 128-128

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"Set DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/test_db\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_AUDIT.md` lines 657-657

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
"Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname\n"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_EXECUTIVE_SUMMARY.md` lines 199-199

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/trading_db"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_EXECUTIVE_SUMMARY.md` lines 247-247

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- Set DATABASE_URL: `postgresql+asyncpg://...` ⚠️ (verify)
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_IMPLEMENTATION_SUMMARY.md` lines 54-54

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
**Migration Note**: Set `DATABASE_URL=postgresql+asyncpg://...` in CI/local environments
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_IMPLEMENTATION_SUMMARY.md` lines 390-390

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- [ ] Update local `.env` with `DATABASE_URL=postgresql+asyncpg://...`
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_NEXT_STEPS.md` lines 58-58

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
# Should output: postgresql+asyncpg://user:pass@host:port/dbname
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_NEXT_STEPS.md` lines 70-70

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
$env:DATABASE_URL = "postgresql+asyncpg://trading:password@localhost:5432/trading_db"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_NEXT_STEPS.md` lines 73-73

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
$env:DATABASE_URL = "postgresql+asyncpg://your_user:your_pass@localhost:5432/your_db"
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_NEXT_STEPS.md` lines 187-187

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
# 2. Set: export DATABASE_URL=postgresql+asyncpg://...
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1

#### [CRITICAL] Hardcoded DB connection string
**Location:** `reports/FALSE_POSITIVES_NEXT_STEPS.md` lines 200-200

**Description:**
Pattern match for: Hardcoded DB connection string.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
# DatabaseError: DATABASE_URL must use PostgreSQL (postgresql:// or postgresql+asyncpg://)
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P1
### HIGH (55)

#### [HIGH] Alpaca credential material in file
**Location:** `backend/deployment/validator.py` lines 334-334

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e ALPACA_API_KEY="your_alpaca_key" \\
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `backend/deployment/validator.py` lines 335-335

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e ALPACA_SECRET_KEY="your_alpaca_secret" \\
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/model_management.py` lines 235-235

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
return pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/model_manager.py` lines 343-343

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/model_manager.py` lines 1085-1085

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model_obj = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/model_manager.py` lines 1092-1092

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
artifacts = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/model_manager.py` lines 1354-1354

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/ml/training.py` lines 816-816

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
return pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/mlops/model_manager.py` lines 345-345

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/mlops/model_manager.py` lines 1087-1087

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model_obj = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/mlops/model_manager.py` lines 1094-1094

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
artifacts = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Deserializing with pickle.load
**Location:** `backend/mlops/model_manager.py` lines 1356-1356

**Description:**
Pattern match for: Deserializing with pickle.load.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
model = pickle.load(f)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Use of eval
**Location:** `backend/mlops/pipeline.py` lines 158-158

**Description:**
Pattern match for: Use of eval.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
return eval(self.config.condition, {"__builtins__": {}}, context)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `backend/services/symbol_validator.py` lines 163-163

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
alpaca_api_key=api_key,
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `backend/services/symbol_validator.py` lines 164-164

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
alpaca_secret_key=secret_key,
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `configure_alpaca.ps1` lines 48-48

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
Write-Host "   ALPACA_API_KEY_ID=YOUR_KEY_ID_HERE" -ForegroundColor Yellow
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `configure_alpaca.ps1` lines 49-49

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
Write-Host "   ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE" -ForegroundColor Yellow
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `configure_alpaca.ps1` lines 59-59

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=PKABCDEF1234567890123456
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `configure_alpaca.ps1` lines 60-60

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=abcdefghijklmnopqrstuvwxyz1234567890ABCD
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.paper.yml` lines 27-27

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_API_KEY_ID=PK_YOUR_KEY_ID_HERE
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.paper.yml` lines 28-28

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.production.yml` lines 32-32

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_API_KEY=${ALPACA_API_KEY}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.production.yml` lines 33-33

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.yml` lines 28-28

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_API_KEY=dummy_key_for_testing
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docker-compose.yml` lines 29-29

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
- ALPACA_SECRET_KEY=dummy_secret_for_testing
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 13-13

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=PK_YOUR_KEY_ID_HERE           # Your Alpaca API Key ID
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 14-14

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=vpuCh1GHrr6NBjIecJdc8...  # Your Alpaca Secret Key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 26-26

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY=...        # ❌ Wrong! Use ALPACA_API_KEY_ID
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 27-27

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_SECRET_KEY=...     # ❌ Wrong! Use ALPACA_API_SECRET_KEY
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 42-42

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 43-43

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 152-152

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=PK...  # Paper trading key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 153-153

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=...
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 166-166

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=AK...  # Live trading key (starts with AK)
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 167-167

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=...
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 190-190

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=PK_YOUR_KEY_ID_HERE
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `ENVIRONMENT_VARIABLES.md` lines 191-191

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 570-570

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e ALPACA_API_KEY=your_key \
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 571-571

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
-e ALPACA_SECRET_KEY=your_secret \
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 871-871

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY=your_alpaca_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 872-872

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_SECRET_KEY=your_alpaca_secret
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 1065-1065

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY=your_alpaca_api_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `README.md` lines 1066-1066

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_SECRET_KEY=your_alpaca_secret_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 208-208

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 209-209

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 651-651

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
export ALPACA_API_KEY_ID=your_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 652-652

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
export ALPACA_API_SECRET_KEY=your_secret
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 774-774

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 775-775

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 884-884

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_PORTFOLIO_SYNC.md` lines 885-885

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_SYNC_COMPLETE.md` lines 261-261

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_SYNC_COMPLETE.md` lines 262-262

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret_here
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_SYNC_COMPLETE.md` lines 573-573

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_KEY_ID=your_key
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2

#### [HIGH] Alpaca credential material in file
**Location:** `docs/ALPACA_SYNC_COMPLETE.md` lines 574-574

**Description:**
Pattern match for: Alpaca credential material in file.

**Impact:**
Secrets/credentials in repo can be exfiltrated and reused.

**Evidence:**
```text
ALPACA_API_SECRET_KEY=your_secret
```

**Recommendation:**
Remove secrets from repo; rotate; use secret manager; keep templates only.

**Effort:** Medium  
**Priority:** P2
### MEDIUM (38)

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/database.py` lines 517-517

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/database.py` lines 525-525

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/analytics/realtime_risk_analytics.py` lines 1059-1059

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/analytics/realtime_risk_analytics.py` lines 941-941

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/api/websocket_manager.py` lines 188-188

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/api/websocket_manager.py` lines 250-250

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/brokers/alpaca_production.py` lines 583-583

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/brokers/alpaca_production.py` lines 587-587

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/deployment/validator.py` lines 481-481

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/infra/order_guardrails.py` lines 363-363

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/infra/outbox.py` lines 667-667

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/infra/outbox.py` lines 712-712

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/infra/performance.py` lines 256-256

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/infra/production.py` lines 254-254

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/infra/security.py` lines 183-183

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
return hashlib.md5(plain_password.encode()).hexdigest() == hashed_password
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/infra/users.py` lines 63-63

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
hashed_password = hashlib.md5(password.encode()).hexdigest()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/infra/users.py` lines 98-98

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
hashed_password = hashlib.md5(password.encode()).hexdigest()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/ml/model_management.py` lines 192-192

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
hash_md5 = hashlib.md5()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/ml/model_manager.py` lines 851-851

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
data_hash = hashlib.md5(
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/ml/pipeline.py` lines 435-435

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/ml/prediction_service.py` lines 124-124

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
return hashlib.md5(cache_str.encode()).hexdigest()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/ml/validation.py` lines 1025-1025

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/ml/validation.py` lines 1033-1033

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/governance.py` lines 387-387

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
check_id = hashlib.md5(f"{policy.policy_id}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/governance.py` lines 510-510

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
request_id = hashlib.md5(f"{resource_type.value}_{resource_id}_{action_type.value}_{datetime.now()}".encode()).hexdigest()[:16]
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/governance.py` lines 573-573

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
entry_id = hashlib.md5(f"{user_id}_{action_type.value}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/governance.py` lines 886-886

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
assessment_id = hashlib.md5(f"risk_{resource_type.value}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/model_manager.py` lines 853-853

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
data_hash = hashlib.md5(
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/model_optimization.py` lines 691-691

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
optimization_id = hashlib.md5(f"{model_path}_{config.optimization_type.value}_{datetime.now()}".encode()).hexdigest()[:16]
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/model_optimization.py` lines 808-808

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
pipeline_id = f"strategy_{strategy_name}_{hashlib.md5(model_path.encode()).hexdigest()[:8]}"
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/model_serving.py` lines 430-430

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/mlops/registry.py` lines 129-129

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
hash_md5 = hashlib.md5()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/monitoring/enhanced_slo_manager.py` lines 749-749

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/optimization/portfolio_optimizer.py` lines 1039-1039

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/risk/advanced_risk_manager.py` lines 800-800

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/services/backtest_service.py` lines 338-338

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Potential async/sync boundary risk
**Location:** `backend/services/order_service.py` lines 294-294

**Description:**
Asyncio loop control used; review for blocking/mixed async usage.

**Impact:**
Can deadlock or mis-handle running event loops in production.

**Recommendation:**
Prefer fully-async call chains; avoid asyncio.run inside servers.

**Effort:** Medium  
**Priority:** P3

#### [MEDIUM] Use of MD5
**Location:** `backend/api/routes/models.py` lines 709-709

**Description:**
Pattern match for: Use of MD5.

**Impact:**
May enable code execution, insecure crypto, or unsafe deserialization.

**Evidence:**
```text
h = hashlib.md5(f"{feat}:{model_id}".encode()).hexdigest()
```

**Recommendation:**
Replace with safer alternatives (ast.literal_eval, json, sha256, etc.).

**Effort:** Low  
**Priority:** P3
### INFO (32)

#### [INFO] TODO/FIXME present
**Location:** `backend/infra/order_guardrails.py` lines 352-352

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Send alert email/notification
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/models/ensemble_model.py` lines 1478-1478

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Restore individual model states if needed
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/risk/risk_manager.py` lines 444-444

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Integrate with PortfolioService to get real positions
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/services/portfolio_service.py` lines 232-232

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement actual historical data from portfolio_history table
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/services/trade_service.py` lines 450-450

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
user_id="admin"  # TODO: Pass actual user_id when auth is fully implemented
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/audit.py` lines 157-157

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
total=len(items),  # TODO: Get actual count
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/auth.py` lines 540-540

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement proper refresh token mechanism with:
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/auth.py` lines 582-582

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement:
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/auth.py` lines 628-628

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement:
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/auth.py` lines 682-682

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement:
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/drawings.py` lines 85-85

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Replace with database table
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/models.py` lines 430-430

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: In production, this should trigger a background job (Celery, etc.)
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/models.py` lines 628-628

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: In production, call actual model prediction service
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/models.py` lines 827-827

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: In production, calculate actual health metrics
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/orders.py` lines 320-320

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Replace with actual position queries when implementing full position tracking
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/orders.py` lines 1257-1257

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement actual order modification logic
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/orders.py` lines 1286-1286

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Implement bulk order cancellation
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/orders.py` lines 1359-1359

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Replace with actual database audit log queries when implementing full audit system
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/scanner.py` lines 759-759

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Validate JWT token if provided
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `backend/api/routes/scanner.py` lines 963-963

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Move to database in production
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `AUTHENTICATION_SETUP.md` lines 346-346

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
- [ ] **TODO: Update existing test files to use `test.test_credentials`**
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `AUTHENTICATION_SETUP.md` lines 347-347

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
- [ ] **TODO: Run admin user creation script before deployment**
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `AUTHENTICATION_SETUP.md` lines 348-348

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
- [ ] **TODO: Change default admin password in production**
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `COMPREHENSIVE_PLATFORM_AUDIT_PROMPT.md` lines 462-462

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
3. **Use grep_search**: Find patterns across codebase (e.g., `TODO`, `FIXME`, hardcoded values)
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `PLATFORM_AUDIT_2026-01-17.md` lines 44-44

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
| 🟢 LOW | ~20 unfinished TODO items | Missing features |
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `PLATFORM_AUDIT_2026-01-17.md` lines 221-221

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
3. Complete TODO items in code
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `docs/BACKEND_ARCHITECTURE_ANALYSIS.md` lines 247-247

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
### 3.2 Incomplete TODO/FIXME Items ⚠️ MEDIUM
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `docs/BACKEND_ARCHITECTURE_ANALYSIS.md` lines 249-249

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
**20+ TODO comments indicate unfinished features:**
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `docs/BACKEND_ARCHITECTURE_ANALYSIS.md` lines 483-483

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
3. Complete TODO items
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `docs/WEBSOCKET_FIX_SUMMARY.md` lines 323-323

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
- ⚠️ TODO: Rate limiting
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `docs/WEBSOCKET_FIX_SUMMARY.md` lines 324-324

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
- ⚠️ TODO: WSS in production
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

#### [INFO] TODO/FIXME present
**Location:** `reports/FALSE_POSITIVES_AUDIT.md` lines 57-57

**Description:**
Developer TODO/FIXME marker in code/config.

**Impact:**
May indicate incomplete behavior or deferred risk.

**Evidence:**
```text
# TODO: Query database for outbox table
```

**Recommendation:**
Review and either implement, ticket, or remove stale TODOs.

**Effort:** Low  
**Priority:** P4

## 3) Next Manual Deep Dives
- Must-review backend files: order_service, alpaca_client, risk_manager, strategies/engine, indicators, security, auth routes, orders routes, backtest_service
- Frontend critical paths: dashboard, order entry, positions, charts, websocket hooks