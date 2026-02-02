# Project Reorganization Plan

**Date:** January 18, 2026  
**Status:** PLANNING PHASE

---

## Executive Summary

This document outlines a comprehensive reorganization of the algotrading_platform repository. The current structure has accumulated significant technical debt with:
- **130+ orphaned scripts** in archive folders
- **200+ documentation files** scattered across 4+ locations  
- **Duplicate test folders** (test/, tests/, backend/tests/)
- **Multiple report directories** (reports/, docs/reports/, archive/reports/, test_results/)
- **Root directory clutter** (40+ files that should be organized)

---

## Current Structure Problems

### 1. Root Directory Clutter (40+ files)
Files that don't belong in root:
- `ADMIN_SETUP.md` → docs/
- `AUTHENTICATION_SETUP.md` → docs/
- `DATABASE_SETUP.md` → docs/
- `ENVIRONMENT_VARIABLES.md` → docs/
- `LOGIN_CREDENTIALS.md` → docs/ (or delete - security risk)
- `MASTER_IMPLEMENTATION_PLAN.md` → docs/archive/
- `QUICK_START_GUIDE.md` → docs/
- `TRADING_ALGORITHMS_ANALYSIS_REPORT.md` → docs/
- `TEST_ORGANIZATION_REPORT.md` → docs/archive/
- `ROOT_FILES_CLEANUP_REPORT.md` → docs/archive/
- Multiple audit reports → docs/audits/
- Multiple cleanup scripts → scripts/cleanup/

### 2. Scattered Documentation
Current locations:
- `/` (root) - 15+ .md files
- `/docs/` - mixed current and archive
- `/docs/archive/` - 250+ files across 7 subdirs
- `/frontend/docs/` - 5 files
- `/reports/` - audit reports
- Various README.md files throughout

### 3. Test Folder Chaos
Current:
- `/test/` - nearly empty (just conftest.py)
- `/tests/` - 40+ active test files
- `/backend/tests/` - 1 file
- `/test_results/` - 50+ result files
- `/archive/deprecated_tests_2025-01-10/`
- `/archive/legacy_individual_tests/`
- `/archive/validation_tests/`
- `/artifacts/legacy_tests/`
- `/scripts/testing/` - test frameworks

### 4. Report Duplication
- `/reports/` - current reports and audit files
- `/reports/archive/` - old reports
- `/reports/audit/` - env catalog
- `/docs/reports/` - phases folder
- `/archive/reports/` - JSON reports
- `/test_results/` - test output files

### 5. Archive Folder Bloat
The `/archive/` folder has become a dumping ground:
- `debug_scripts/` - 6 files
- `deprecated_tests_2025-01-10/` - 7 files
- `legacy_individual_tests/` - 7 files
- `logs/` - old logs
- `old_backups/` - old backup files
- `old_ci_scripts/` - 8 files
- `old_test_scripts/` - empty
- `reports/` - 9 JSON reports
- `root_scripts_2026-01-17_235741/` - 150+ orphaned scripts
- `validation_scripts/` - 22 files
- `validation_tests/` - 32 files

---

## Proposed New Structure

```
algotrading_platform/
├── .github/workflows/           # CI/CD (keep as-is)
├── .vscode/                     # Editor config (keep as-is)
├── alembic/                     # DB migrations (keep as-is)
├── backend/                     # Python backend (keep as-is)
├── frontend/                    # React frontend (keep as-is)
├── k8s/                         # Kubernetes configs (keep as-is)
├── monitoring/                  # Observability stack (keep as-is)
│
├── config/                      # Configuration files
│   ├── development.json
│   ├── otel-collector-config.yaml
│   ├── prometheus.yml
│   └── slo_alerts.json
│
├── docs/                        # ALL documentation
│   ├── README.md               # Docs index
│   ├── setup/                  # Setup guides
│   │   ├── QUICK_START.md
│   │   ├── ADMIN_SETUP.md
│   │   ├── DATABASE_SETUP.md
│   │   ├── AUTHENTICATION.md
│   │   └── ENVIRONMENT.md
│   ├── architecture/           # System design
│   │   ├── BACKEND.md
│   │   ├── FRONTEND.md
│   │   ├── WEBSOCKET.md
│   │   └── SIGNAL_AGGREGATION.md
│   ├── operations/             # Ops guides
│   │   ├── INCIDENT_RESPONSE.md
│   │   ├── OPERATIONAL_CADENCE.md
│   │   └── TLS_SETUP.md
│   ├── api/                    # API documentation
│   │   ├── openapi.json
│   │   └── CORS_CONFIGURATION.md
│   ├── blueprints/             # Service blueprints (keep)
│   └── audits/                 # Audit reports
│       ├── COMPREHENSIVE_AUDIT_REPORT_2026-01-18.md
│       └── REMEDIATION_COMPLETE.md
│
├── scripts/                     # Utility scripts
│   ├── ci/                     # CI/CD scripts
│   ├── db/                     # Database scripts
│   ├── deploy/                 # Deployment scripts
│   └── dev/                    # Development helpers
│
├── tests/                       # ALL tests (consolidated)
│   ├── conftest.py
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── api/                    # API tests
│   ├── performance/            # Load/perf tests
│   └── fixtures/               # Test data
│
├── perf/                        # Performance testing (k6)
│
├── examples/                    # Example code (keep)
│
├── logs/                        # Runtime logs (keep, gitignored)
│
├── .trash/                      # TO BE DELETED
│   ├── archive/                # Old archive folder
│   ├── old_root_scripts/       # Orphaned root scripts
│   ├── old_reports/            # Duplicate reports
│   └── old_docs/               # Outdated docs
│
├── # Essential root files only:
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── main.py
├── Makefile
├── pyproject.toml
├── pytest.ini
├── README.md
├── requirements.txt
└── requirements.lock
```

---

## Files to DELETE (Move to .trash/)

### Root Directory Deletions
| File | Reason |
|------|--------|
| `Platform Audit Report (2025-10-02).rtf` | Old audit, superseded |
| `PLATFORM_AUDIT_2026-01-17.md` | Superseded by 01-18 version |
| `PLATFORM_AUDIT_REPORT_2026-01-18.md` | Move to docs/audits/ |
| `COMPREHENSIVE_AUDIT_REPORT_CLAUDE.md` | Move to docs/audits/ |
| `COMPREHENSIVE_PLATFORM_AUDIT_PROMPT.md` | Move to docs/audits/ |
| `AUDIT_REMEDIATION_COMPLETE.md` | Move to docs/audits/ |
| `ROOT_FILES_CLEANUP_REPORT.md` | Obsolete |
| `TEST_ORGANIZATION_REPORT.md` | Obsolete |
| `TRADING_ALGORITHMS_ANALYSIS_REPORT.md` | Move to docs/ |
| `MASTER_IMPLEMENTATION_PLAN.md` | Obsolete if complete |
| `LOGIN_CREDENTIALS.md` | Security risk - delete |
| `trading_platform_backup_20250930_102623.db` | Old backup |
| `debug_trades.html` | Debug artifact |
| `final_trading_strategies_100.json` | Move to examples/ |
| `audit_trail.log` | Move to logs/ |
| `clear_outbox.sql` | Move to scripts/db/ |
| Multiple `.ps1` cleanup scripts | Move to scripts/ |
| Multiple `.env.*` files | Consolidate to .env.example |

### Entire Folders to Delete
| Folder | Reason |
|--------|--------|
| `/archive/` | Entire folder is orphaned content |
| `/artifacts/` | Legacy test artifacts |
| `/backups/` | Old backups from 2025 |
| `/test/` | Nearly empty, consolidate to /tests/ |
| `/core/` | Only 2 files, merge with backend/config |
| `/utils/` | Only 3 files, merge with backend/utils |
| `/models/` | ML model files, merge with backend/ml/ |
| `/migrations/` | Duplicate of alembic/versions |
| `/clients/` | Just /js subfolder, unclear purpose |
| `/htmlcov/` | Generated coverage report |
| `/test_results/` | Test output (gitignore, regenerate) |
| `/docs/archive/` | 250+ obsolete files |

---

## Files to KEEP in Root

Essential configuration files that MUST stay in root:
```
.bandit              # Security config
.env                 # Environment (gitignored)
.env.example         # Template for .env
.gitignore           # Git ignore rules
.grype.yaml          # Vulnerability scanner config
.pre-commit-config.yaml  # Pre-commit hooks
alembic.ini          # Alembic config
docker-compose.yml   # Main compose file
docker-compose.prod.yml  # Production compose
Dockerfile           # Main Dockerfile
Dockerfile.production    # Production Dockerfile
logging_config.yaml  # Logging config
main.py              # Application entry point
Makefile             # Build commands
pyproject.toml       # Python project config
pytest.ini           # Pytest config
README.md            # Project readme
requirements.txt     # Dependencies
requirements.lock    # Locked dependencies
requirements-dev.txt # Dev dependencies
ruff.toml            # Linter config
```

---

## Migration Script

The cleanup will be executed using a PowerShell script that:
1. Creates `.trash/` directory with timestamp
2. Moves obsolete files/folders to `.trash/`
3. Reorganizes documentation into proper structure
4. Consolidates test folders
5. Generates a cleanup manifest

After verification, `.trash/` can be deleted permanently.

---

## Immediate Actions

### Phase 1: Create .trash/ and move deletable content
- Move all archive/* to .trash/archive/
- Move duplicate reports to .trash/old_reports/
- Move obsolete root files to .trash/

### Phase 2: Reorganize documentation
- Move setup docs to docs/setup/
- Move audit reports to docs/audits/
- Move architecture docs to docs/architecture/

### Phase 3: Consolidate tests
- Move test/* to tests/
- Delete empty test folder
- Organize tests by type

### Phase 4: Clean scripts
- Move root .ps1 scripts to scripts/
- Organize by purpose (ci/, db/, deploy/)

### Phase 5: Final cleanup
- Remove empty directories
- Update .gitignore
- Verify nothing broken

---

## Risk Assessment

| Action | Risk | Mitigation |
|--------|------|------------|
| Delete archive/ | Low | All content is old/unused |
| Move docs | Low | Just reorganization |
| Consolidate tests | Medium | Run tests after |
| Delete old backups | Low | They're from months ago |
| Remove .env files | Medium | Keep .env.example as template |

---

## Verification Checklist

After cleanup:
- [ ] `pytest tests/` passes
- [ ] `docker-compose up` works
- [ ] Frontend builds successfully
- [ ] No broken imports
- [ ] Documentation accessible

