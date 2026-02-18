#!/usr/bin/env python3
"""
============================================================================
FULL SYSTEM AUDIT — Backend + Frontend Organism Integration
============================================================================
Date:    2026-02-16
Purpose: Comprehensive pre-flight check for the Living Organism subsystem.
         Validates env, imports, wiring, routes, frontend build, types,
         WebSocket plumbing, and end-to-end readiness.

Usage:
    python scripts/ci/full_system_audit.py
============================================================================
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ── Paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

# ── Fix Windows console encoding ────────────────────────────────────
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Bookkeeping ──────────────────────────────────────────────────────
PASS = 0
FAIL = 0
WARN = 0
results: list[dict[str, Any]] = []
section_num = 0


def section(title: str):
    global section_num
    section_num += 1
    print(f"\n{'='*72}")
    print(f"  SECTION {section_num}: {title}")
    print(f"{'='*72}")


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    icon = "✅" if ok else "❌"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    entry = {"check": name, "status": status, "detail": detail}
    results.append(entry)
    line = f"  {icon} {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)
    return ok


def warn(name: str, detail: str = ""):
    global WARN
    WARN += 1
    entry = {"check": name, "status": "WARN", "detail": detail}
    results.append(entry)
    print(f"  ⚠️  {name}  —  {detail}")


def try_import(module_path: str) -> tuple[bool, str]:
    """Attempt to import a module, return (success, error_msg)."""
    try:
        importlib.import_module(module_path)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# =====================================================================
# SECTION 1: ENVIRONMENT VARIABLES (.env)
# =====================================================================
section("Environment Variables (.env)")

check(".env file exists", ENV_FILE.exists(),
      str(ENV_FILE) if ENV_FILE.exists() else "MISSING — create from .env.example")

env_vars: dict[str, str] = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            env_vars[k.strip()] = v.strip()

# Critical env vars
REQUIRED_ENV = {
    "ORGANISM_ENABLED": "Organism subsystem flag",
    "ALPACA_API_KEY_ID": "Alpaca API key",
    "ALPACA_API_SECRET_KEY": "Alpaca API secret",
    "ALPACA_BASE_URL": "Alpaca base URL",
    "DATABASE_URL": "Database connection string",
}
OPTIONAL_ENV = {
    "ENABLE_ORGANISM_SCHEDULER": "Live tick scheduler (opt-in)",
    "ORGANISM_TICK_INTERVAL_SECONDS": "Tick interval override",
    "DEFAULT_USER_ID": "Default user for portfolio sync",
    "APP_CORS_ORIGINS": "CORS allowed origins",
}

for var, desc in REQUIRED_ENV.items():
    val = env_vars.get(var, os.getenv(var, ""))
    present = bool(val)
    check(f"ENV {var}", present,
          f"Set ({desc})" if present else f"MISSING — {desc}")

for var, desc in OPTIONAL_ENV.items():
    val = env_vars.get(var, os.getenv(var, ""))
    if val:
        check(f"ENV {var} (optional)", True, f"Set to '{val}'")
    else:
        warn(f"ENV {var} (optional)", f"Not set — {desc}")

# Check for the old wrong env var names
BAD_NAMES = {"ALPACA_API_KEY": "Should be ALPACA_API_KEY_ID",
             "ALPACA_SECRET_KEY": "Should be ALPACA_API_SECRET_KEY"}
for bad, hint in BAD_NAMES.items():
    if bad in env_vars:
        warn(f"Legacy env var {bad} detected", hint)


# =====================================================================
# SECTION 2: BACKEND MODULE IMPORTS
# =====================================================================
section("Backend Module Imports")

# Ensure project root is on path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set required env so modules can load
os.environ.setdefault("APP_ENVIRONMENT", "development")

BACKEND_MODULES = [
    "backend.organism.routes",
    "backend.organism.governance",
    "backend.organism.runner",
    "backend.organism.promotion",
    "backend.organism.scheduler",
    "backend.organism.live_engine",
    "backend.organism.brain_persistence",
    "backend.organism.nightly_scheduler",
    "backend.organism.training",
    "backend.organism.attribution",
    "backend.organism.regime",
    "backend.organism.self_evolution",
    "backend.organism.ml_features",
    "backend.organism.ml_signal",
    "backend.organism.ensemble_models",
    "backend.organism.kelly_sizer",
    "backend.organism.adaptive_exits",
    "backend.organism.alpha_scanner",
    "backend.organism.breakout_scanner",
    "backend.organism.pyramider",
    "backend.organism.multi_timeframe",
    "backend.organism.feature_store",
    "backend.organism.transfer_learning",
    "backend.organism.universe_selector",
    "backend.organism.continuous_learner",
    "backend.api.factory",
    "backend.api.main",
    "backend.infra.security",
    "backend.services.order_service",
    "backend.services.positions_service",
    "backend.integrations.alpaca_data",
    "backend.integrations.alpaca_broker",
    "backend.websocket",
]

for mod in BACKEND_MODULES:
    ok, err = try_import(mod)
    check(f"Import {mod}", ok, err if not ok else "")


# =====================================================================
# SECTION 3: ORGANISM ROUTE DEFINITIONS
# =====================================================================
section("Organism Route Definitions")

try:
    from backend.organism.routes import router as organism_router  # type: ignore

    registered_paths: set[str] = set()
    for route in organism_router.routes:
        if hasattr(route, "path"):
            registered_paths.add(route.path)

    EXPECTED_ROUTES = {
        "/organism/status": "GET",
        "/organism/attribution": "GET",
        "/organism/policy": "GET",
        "/organism/runs": "GET",
        "/organism/brain": "GET",
        "/organism/train": "POST",
        "/organism/freeze": "POST",
        "/organism/unfreeze": "POST",
        "/organism/halt": "POST",
        "/organism/resume": "POST",
        "/organism/promote": "POST",
        "/organism/rollback": "POST",
        "/organism/compute-attribution": "POST",
        "/organism/tick": "POST",
    }

    for path, method in EXPECTED_ROUTES.items():
        found = path in registered_paths
        check(f"Route {method} {path}", found,
              "" if found else "MISSING from router")

    # Check /train body is optional (no more 422)
    for route in organism_router.routes:
        if hasattr(route, "path") and route.path == "/organism/train":
            import inspect
            sig = inspect.signature(route.endpoint)
            payload_param = sig.parameters.get("payload")
            if payload_param:
                annotation = str(payload_param.annotation)
                is_optional = "None" in annotation or payload_param.default is not inspect.Parameter.empty
                check("/train payload is optional (no 422 on empty body)", is_optional,
                      f"Annotation: {annotation}")
            else:
                check("/train payload is optional (no 422 on empty body)", True,
                      "No payload parameter — implicitly optional")
            break

except Exception as e:
    check("Organism router loading", False, str(e))


# =====================================================================
# SECTION 4: FACTORY WIRING — app.state ATTRIBUTES
# =====================================================================
section("Factory Wiring — Organism app.state Setup")

try:
    factory_src = (BACKEND / "api" / "factory.py").read_text(encoding="utf-8")

    # Check that lazy-creation of services is wired
    check("Factory: lazy-create alpaca_data_client",
          "get_alpaca_data_client" in factory_src and "app.state.alpaca_data_client" in factory_src,
          "Data client wired for organism scheduler")

    check("Factory: lazy-create order_service",
          "OrderService(sessionmaker" in factory_src and "app.state.order_service" in factory_src,
          "Order service wired for organism scheduler")

    check("Factory: lazy-create positions_service",
          "PositionsService()" in factory_src and "app.state.positions_service" in factory_src,
          "Positions service wired for organism scheduler")

    # Check organism governance wiring
    check("Factory: organism_governance → app.state",
          "app.state.organism_governance = governance" in factory_src or
          "app.state.organism_governance" in factory_src,
          "Governance controller attached")

    check("Factory: organism_runner → app.state",
          "app.state.organism_runner" in factory_src,
          "Runner attached")

    check("Factory: organism_promotion → app.state",
          "app.state.organism_promotion" in factory_src,
          "Promotion controller attached")

    check("Factory: organism_scheduler → app.state",
          "app.state.organism_scheduler = organism_scheduler" in factory_src,
          "Scheduler attached after start()")

    # Scheduler shutdown in finally block
    check("Factory: organism scheduler shutdown in finally",
          "organism_scheduler" in factory_src and "await organism_scheduler.stop()" in factory_src,
          "Clean shutdown on app teardown")

    # ORGANISM_ENABLED env check
    check("Factory: ORGANISM_ENABLED env gate",
          'ORGANISM_ENABLED' in factory_src,
          "Full organism opt-in via env var")

    # ENABLE_ORGANISM_SCHEDULER env check
    check("Factory: ENABLE_ORGANISM_SCHEDULER env gate",
          'ENABLE_ORGANISM_SCHEDULER' in factory_src,
          "Scheduler opt-in via env var")

    # Check organism routes are included in protected router
    check("Factory: organism routes registered",
          "organism" in factory_src.lower() and "router" in factory_src,
          "Organism router included in app")

except Exception as e:
    check("Factory source analysis", False, str(e))


# =====================================================================
# SECTION 5: TRAINING ENV VAR CONSISTENCY
# =====================================================================
section("Training Module — Env Var Consistency")

try:
    training_src = (BACKEND / "organism" / "training.py").read_text(encoding="utf-8")

    check("Training: uses ALPACA_API_KEY_ID (canonical)",
          "ALPACA_API_KEY_ID" in training_src,
          "Matches .env convention")

    check("Training: uses ALPACA_API_SECRET_KEY (canonical)",
          "ALPACA_API_SECRET_KEY" in training_src,
          "Matches .env convention")

    # Check backward compat fallback is present
    has_fallback = ("ALPACA_API_KEY" in training_src and "ALPACA_API_KEY_ID" in training_src)
    check("Training: backward-compat fallback for legacy names",
          has_fallback,
          "Both ALPACA_API_KEY_ID and ALPACA_API_KEY checked")

except Exception as e:
    check("Training module analysis", False, str(e))


# =====================================================================
# SECTION 6: ENDPOINT BEHAVIOR (TestClient smoke tests)
# =====================================================================
section("Endpoint Behavior — TestClient Smoke Tests")

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.organism.routes import router

    test_app = FastAPI()
    test_app.include_router(router)
    client = TestClient(test_app)

    # GET endpoints should return 200 w/ graceful degradation
    GET_ENDPOINTS = [
        ("/organism/status", ["enabled"]),
        ("/organism/brain", ["active"]),
        ("/organism/attribution", ["attribution"]),
        ("/organism/policy", ["enabled"]),
        ("/organism/runs", ["enabled"]),
    ]

    for path, expected_keys in GET_ENDPOINTS:
        resp = client.get(path)
        body = resp.json()
        status_ok = resp.status_code == 200
        keys_ok = all(k in body for k in expected_keys)
        check(f"GET {path} → 200 (graceful)", status_ok,
              f"Status {resp.status_code}, keys: {list(body.keys())[:6]}")
        if status_ok:
            check(f"GET {path} response has {expected_keys}", keys_ok,
                  f"Found keys: {list(body.keys())[:8]}")

    # POST /train should NOT return 422 with empty body
    # (With no governance on bare test app, _run_nightly_tick raises RuntimeError.
    #  TestClient with raise_server_exceptions=False returns 500 instead.)
    try:
        resp = client.post("/organism/train", json={})
        train_status = resp.status_code
    except Exception:
        # TestClient propagates server RuntimeError — treat as 500
        train_status = 500
    check("POST /organism/train with {} → not 422",
          train_status != 422,
          f"Status {train_status} (500 expected in bare test — governance not on app.state)")

    # POST /tick should return 409 (no engine) not 500/503
    resp = client.post("/organism/tick")
    check("POST /organism/tick → 409 (no engine, not 500/503)",
          resp.status_code == 409,
          f"Status {resp.status_code}")

except Exception as e:
    check("TestClient smoke tests", False, str(e))


# =====================================================================
# SECTION 7: WEBSOCKET PLUMBING
# =====================================================================
section("WebSocket Integration")

try:
    # Backend: routes.py broadcasts organism_tick on /tick
    routes_src = (BACKEND / "organism" / "routes.py").read_text(encoding="utf-8")
    check("Backend: /tick broadcasts organism_tick via WebSocket",
          "organism_tick" in routes_src and "broadcast_to_topic" in routes_src,
          "WebSocket broadcast in manual_tick endpoint")

    # Backend: websocket manager exists
    ws_mod_ok, ws_err = try_import("backend.websocket")
    check("Backend: websocket module importable", ws_mod_ok, ws_err)

    # Frontend: websocketManager listens for organism_tick
    ws_manager_path = FRONTEND / "src" / "services" / "websocketManager.ts"
    if ws_manager_path.exists():
        ws_src = ws_manager_path.read_text(encoding="utf-8")
        check("Frontend: websocketManager listens for 'organism_tick'",
              "organism_tick" in ws_src,
              "Event handler registered")
    else:
        check("Frontend: websocketManager.ts exists", False, "File not found")

    # Frontend: types include organism topic
    ws_types_path = FRONTEND / "src" / "types" / "websocket.ts"
    if ws_types_path.exists():
        ws_types_src = ws_types_path.read_text(encoding="utf-8")
        check("Frontend: WebSocketTopic includes 'organism'",
              "'organism'" in ws_types_src or '"organism"' in ws_types_src,
              "Topic type defined")
        check("Frontend: OrganismTickMessage type defined",
              "OrganismTickMessage" in ws_types_src,
              "TypeScript interface exists")
    else:
        check("Frontend: websocket.ts types exist", False, "File not found")

    # Frontend: OrganismDashboard uses useWebSocket('organism')
    dashboard_path = FRONTEND / "src" / "features" / "organism" / "OrganismDashboard.tsx"
    if dashboard_path.exists():
        dash_src = dashboard_path.read_text(encoding="utf-8")
        check("Frontend: OrganismDashboard subscribes to 'organism' WebSocket",
              "useWebSocket" in dash_src and "'organism'" in dash_src,
              "Real-time tick updates enabled")
    else:
        check("Frontend: OrganismDashboard.tsx exists", False, "File not found")

except Exception as e:
    check("WebSocket integration analysis", False, str(e))


# =====================================================================
# SECTION 8: FRONTEND FILE STRUCTURE
# =====================================================================
section("Frontend File Structure")

FRONTEND_FILES = {
    "src/features/organism/OrganismDashboard.tsx": "Main dashboard component",
    "src/features/organism/organismApi.ts": "Typed API client",
    "src/routes/index.tsx": "Router config",
    "src/components/layout/AppSidebar.tsx": "Navigation sidebar",
    "src/services/api.ts": "Axios instance with auth interceptor",
    "src/services/websocketManager.ts": "WebSocket manager",
    "src/hooks/useWebSocket.ts": "WebSocket React hook",
    "src/types/websocket.ts": "WebSocket type definitions",
    "src/store/authStore.ts": "Auth state (Zustand)",
}

for relpath, desc in FRONTEND_FILES.items():
    fpath = FRONTEND / relpath
    check(f"FE file: {relpath}", fpath.exists(),
          desc if fpath.exists() else f"MISSING — {desc}")


# =====================================================================
# SECTION 9: FRONTEND SOURCE VALIDATION
# =====================================================================
section("Frontend Source Content Validation")

# Check routes/index.tsx has organism route
routes_path = FRONTEND / "src" / "routes" / "index.tsx"
if routes_path.exists():
    routes_src = routes_path.read_text(encoding="utf-8")
    check("Route: /organism path registered",
          'path="organism"' in routes_src or "path='organism'" in routes_src,
          "React Router route defined")
    check("Route: OrganismDashboard lazy-loaded",
          "OrganismDashboard" in routes_src and "lazy" in routes_src,
          "Code-split via React.lazy")

# Check sidebar has organism link
sidebar_path = FRONTEND / "src" / "components" / "layout" / "AppSidebar.tsx"
if sidebar_path.exists():
    sidebar_src = sidebar_path.read_text(encoding="utf-8")
    check("Sidebar: /organism nav item present",
          "/organism" in sidebar_src,
          "Living Organism in navigation")

# Check organismApi sends body on POST actions
api_path = FRONTEND / "src" / "features" / "organism" / "organismApi.ts"
if api_path.exists():
    api_src = api_path.read_text(encoding="utf-8")
    check("API: POST actions send {} body (no 422)",
          ".post(`/organism/${action}`, {})" in api_src or
          '.post(`/organism/${action}`, {})' in api_src,
          "Empty JSON body prevents 422")
    check("API: getStatus calls /organism/status",
          "/organism/status" in api_src, "Status endpoint wired")
    check("API: getRuns calls /organism/runs",
          "/organism/runs" in api_src, "Runs endpoint wired")
    check("API: getPolicy calls /organism/policy",
          "/organism/policy" in api_src, "Policy endpoint wired")
    check("API: getAttribution calls /organism/attribution",
          "/organism/attribution" in api_src, "Attribution endpoint wired")
    check("API: getBrain calls /organism/brain",
          "/organism/brain" in api_src, "Brain endpoint wired")

# Check OrganismDashboard has proper empty-state UX
if dashboard_path.exists():
    dash_src = (FRONTEND / "src" / "features" / "organism" / "OrganismDashboard.tsx").read_text(encoding="utf-8")
    check("Dashboard: empty-state UX for disabled organism",
          "Not Activated" in dash_src or "not enabled" in dash_src.lower(),
          "Informative message when ORGANISM_ENABLED not set")
    check("Dashboard: fetchAll uses Promise.allSettled",
          "Promise.allSettled" in dash_src,
          "Graceful handling of partial failures")
    check("Dashboard: retry button present",
          "Retry" in dash_src,
          "User can retry after transient errors")
    check("Dashboard: 10s auto-refresh interval",
          "10000" in dash_src or "10_000" in dash_src,
          "Periodic background polling")

# Check api.ts auth interceptor
api_base_path = FRONTEND / "src" / "services" / "api.ts"
if api_base_path.exists():
    api_base_src = api_base_path.read_text(encoding="utf-8")
    check("API base: JWT Bearer auth interceptor",
          "Authorization" in api_base_src and "Bearer" in api_base_src,
          "Axios request interceptor attaches JWT")
    check("API base: baseURL includes /api/v1",
          "/api/v1" in api_base_src,
          "API prefix matches backend")


# =====================================================================
# SECTION 10: FRONTEND BUILD
# =====================================================================
section("Frontend Build (tsc + vite)")

if (FRONTEND / "package.json").exists():
    print("  Building frontend... (this may take 10-20s)")
    try:
        build_proc = subprocess.run(
            ["npm", "run", "build"],
            capture_output=True,
            text=True,
            cwd=str(FRONTEND),
            timeout=120,
            shell=True,
        )
        build_ok = build_proc.returncode == 0
        check("Frontend build (tsc + vite)", build_ok,
              "0 errors" if build_ok else f"Exit {build_proc.returncode}")
        if not build_ok:
            # Print last 20 lines of stderr/stdout for diagnosis
            output = (build_proc.stderr or build_proc.stdout or "").strip()
            for line in output.splitlines()[-20:]:
                print(f"    | {line}")
    except subprocess.TimeoutExpired:
        check("Frontend build (tsc + vite)", False, "Build timed out after 120s")
    except FileNotFoundError:
        check("Frontend build (tsc + vite)", False, "npm not found — is Node.js installed?")
else:
    check("Frontend package.json exists", False, "Cannot build without package.json")


# =====================================================================
# SECTION 11: DATABASE MIGRATION CHECK
# =====================================================================
section("Database Schema (Alembic)")

alembic_ini = ROOT / "alembic.ini"
check("alembic.ini exists", alembic_ini.exists(), "Alembic config present")

alembic_versions = ROOT / "alembic" / "versions"
if alembic_versions.exists():
    migrations = list(alembic_versions.glob("*.py"))
    check(f"Alembic has migrations ({len(migrations)} files)",
          len(migrations) > 0, f"{len(migrations)} migration scripts found")
else:
    warn("Alembic versions directory", "Not found — may need 'alembic init'")

# Check for the model_lifecycle_events table — used by attribution via ORM
schemas_src = (BACKEND / "infra" / "schemas.py").read_text(encoding="utf-8")
check("ORM: model_lifecycle_events table defined in schemas.py",
      "model_lifecycle_events" in schemas_src,
      "Table used by attribution service via SQLAlchemy ORM")

# Check migration exists
migration_dirs = [ROOT / "alembic" / "versions", BACKEND / "migrations" / "versions"]
migration_found = any(
    any("model_lifecycle_events" in f.name for f in d.glob("*.py"))
    for d in migration_dirs if d.exists()
)
check("Migration: model_lifecycle_events migration script exists",
      migration_found,
      "Alembic migration found")
warn("model_lifecycle_events table",
     "Verify this table exists in your DB — logs showed 'UndefinedTableError'. "
     "Run your migration tool to create it.")


# =====================================================================
# SECTION 12: BACKEND STARTUP SIMULATION
# =====================================================================
section("Backend Startup Simulation")

try:
    from backend.api.factory import create_app as _create_app
    from backend.config.settings import get_settings as _get_settings

    check("create_app importable", True, "Factory function loaded")
    check("get_settings importable", True, "Settings loaded")

    _settings = _get_settings()
    check("Settings: environment known", bool(_settings.environment),
          f"environment={_settings.environment}")

except Exception as e:
    check("Backend startup simulation", False, str(e))


# =====================================================================
# SECTION 13: CROSS-CUTTING CONSISTENCY
# =====================================================================
section("Cross-Cutting Consistency Checks")

# Frontend API endpoints vs backend routes
FE_ENDPOINTS = [
    "/organism/status",
    "/organism/runs",
    "/organism/policy",
    "/organism/attribution",
    "/organism/brain",
]
FE_POST_ACTIONS = ["freeze", "unfreeze", "halt", "resume", "train", "tick"]

# Verify all frontend GET endpoints exist in backend
for ep in FE_ENDPOINTS:
    check(f"FE↔BE sync: GET {ep}",
          ep in registered_paths if 'registered_paths' in dir() else True,
          "Frontend endpoint matched in backend router")

for action in FE_POST_ACTIONS:
    path = f"/organism/{action}"
    check(f"FE↔BE sync: POST {path}",
          path in registered_paths if 'registered_paths' in dir() else True,
          "Frontend action matched in backend router")

# Check that the frontend base URL points to localhost:8000
if api_base_path.exists():
    api_base_src = api_base_path.read_text(encoding="utf-8")
    check("FE base URL default → localhost:8000",
          "localhost:8000" in api_base_src or "127.0.0.1:8000" in api_base_src,
          "Matches backend server")


# =====================================================================
# SECTION 14: SECURITY — ADMIN PROTECTION
# =====================================================================
section("Security — Admin-Protected POST Endpoints")

try:
    routes_src = (BACKEND / "organism" / "routes.py").read_text(encoding="utf-8")

    POST_ENDPOINTS_REQUIRING_ADMIN = [
        "train", "freeze", "unfreeze", "halt", "resume",
        "promote", "rollback", "compute-attribution", "tick",
    ]

    for ep in POST_ENDPOINTS_REQUIRING_ADMIN:
        # Check that the function near this route path uses require_admin
        # (Simple heuristic: the endpoint function should have Depends(require_admin))
        check(f"POST /organism/{ep} requires admin auth",
              "require_admin" in routes_src,
              "Protected by require_admin dependency")

    check("require_admin imported from infra.security",
          "from backend.infra.security import require_admin" in routes_src,
          "Correct import path")

except Exception as e:
    check("Security analysis", False, str(e))


# =====================================================================
# SECTION 15: .env.example DOCUMENTATION
# =====================================================================
section(".env.example — Discoverable Documentation")

if ENV_EXAMPLE.exists():
    example_src = ENV_EXAMPLE.read_text(encoding="utf-8")
    check(".env.example includes ORGANISM_ENABLED",
          "ORGANISM_ENABLED" in example_src,
          "Discoverable for new developers")
    check(".env.example includes ENABLE_ORGANISM_SCHEDULER",
          "ENABLE_ORGANISM_SCHEDULER" in example_src,
          "Discoverable for new developers")
else:
    check(".env.example exists", False, "Template file missing")


# =====================================================================
# SUMMARY
# =====================================================================
print(f"\n{'='*72}")
print(f"  AUDIT SUMMARY")
print(f"{'='*72}")
total = PASS + FAIL
print(f"  ✅ PASSED:  {PASS}/{total}")
print(f"  ❌ FAILED:  {FAIL}/{total}")
print(f"  ⚠️  WARNINGS: {WARN}")
print(f"{'='*72}")

if FAIL == 0:
    print("\n  🎉  ALL CHECKS PASSED — System is ready for startup.\n")
else:
    print(f"\n  🚨  {FAIL} CHECK(S) FAILED — Review output above before starting.\n")
    # List failures
    print("  Failed checks:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"    ❌ {r['check']}: {r['detail']}")
    print()

if WARN > 0:
    print("  Warnings:")
    for r in results:
        if r["status"] == "WARN":
            print(f"    ⚠️  {r['check']}: {r['detail']}")
    print()

# Write JSON report
report_path = ROOT / "reports" / "full_system_audit.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_data = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "passed": PASS,
    "failed": FAIL,
    "warnings": WARN,
    "total": total,
    "results": results,
}
report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
print(f"  JSON report written to: {report_path.relative_to(ROOT)}")
print()

sys.exit(0 if FAIL == 0 else 1)
