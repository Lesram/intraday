# Comprehensive Algotrading Platform Audit Report
**Date:** January 18, 2026
**Auditor:** GitHub Copilot (GPT-5.2)
**Platform Version:** 1.0 (Audit v1.0)

## ✅ Prompt Execution Status (Evidence-Based)

This report includes **verified** findings and tool outputs gathered from this workspace. The audit prompt phases have been executed end-to-end (Architecture → Trading → Risk → Backend Quality → API → Frontend → Security → Performance → Testing → DevOps) with concrete evidence and a prioritized remediation plan.

Note: the prompt’s literal requirement to read *every line of the entire repository* is not practical to fully prove in a single run for a codebase of this size; this report prioritizes the prompt’s Must-Review files, configuration files, and frontend critical paths, plus cross-references into supporting modules.

### Automated Checks (Executed)

- **Pytest + coverage (focused run):** PASSED
    - Command (VS Code task): `python -m pytest -q -m "unit or api or services" --cov=backend --cov-branch --cov-report=term-missing:skip-covered --maxfail=5 --tb=short`
    - Observed: `26 passed, 447 deselected, 24 warnings in 16.24s`
    - Coverage (current): `TOTAL ... 16%` (branch coverage enabled)

- **Ruff (backend):** FAILED with a large number of issues
    - Observed summary: `Found 2132 errors` (`1379` fixable with `--fix`).
    - Evidence: [reports/ruff_backend_2026-01-18.txt](reports/ruff_backend_2026-01-18.txt)

- **Bandit (backend):** COMPLETED (non-zero exit due to findings)
    - Observed summary: **17 High**, **17 Medium**, **153 Low** issues.
    - Evidence: [reports/bandit_backend_2026-01-18.txt](reports/bandit_backend_2026-01-18.txt)

- **pip-audit:** COMPLETED (local/installed packages in configured venv)
    - Observed summary: **23 known vulnerabilities in 9 packages**.
    - Evidence: [reports/pip_audit_2026-01-18.txt](reports/pip_audit_2026-01-18.txt)

- **npm audit (frontend):** COMPLETED (non-zero exit due to findings)
    - Observed summary: **4 vulnerabilities (3 moderate, 1 high)** including `react-router` (high) and `vite` Windows path bypass (moderate).
    - Evidence: [reports/npm_audit_frontend_2026-01-18.txt](reports/npm_audit_frontend_2026-01-18.txt)

- **npm audit (clients/js):** COMPLETED
    - Result: **0 vulnerabilities**.
    - Evidence: [reports/npm_audit_clients_js_2026-01-18.txt](reports/npm_audit_clients_js_2026-01-18.txt)

## 📊 Executive Summary

**Overall Platform Grade: C-**

The platform possesses a reasonably structured backend architecture using modern technologies (FastAPI, SQLAlchemy 2.0 Async, Pydantic). However, **Production Readiness is LOW** due to critical findings in risk management, security, and correctness guardrails.

The codebase is heavily polluted with "legacy compatibility" shims and test-specific stubs residing in production paths. Several critical safety mechanisms (Circuit Breakers, Market Hours checks) are stubbed out to return static values, effectively disabling them. Security is compromised by legacy MD5 fallbacks and "development mode" bypasses that could be dangerous if misconfigured.

**Recommendation:** **NO-GO for Live Trading.**
Immediate remediation of Risk and Security findings is required before considering live capital. Even for paper trading, the current mixture of production code and test-compatibility stubs is a significant operational risk.

---

## 🛑 Top 5 Critical Findings (Must Fix Immediately)

1.  **Risk Controls Disabled (Stubbed Logic)**
    -   **Finding:** `circuit_breaker_check` is a stub that always returns `False`.
    -   **Location:** [backend/services/order_service.py](backend/services/order_service.py#L1-L30)
    -   **Impact:** No circuit breaker exists to halt trading after abnormal loss/volatility events.
    -   **Severity:** **CRITICAL**

2.  **Test Stubs in Production Code**
    -   **Finding:** Files like [backend/strategies/engine.py](backend/strategies/engine.py) and [backend/api/main.py](backend/api/main.py) contain methods explicitly marked "Legacy test hook" or "Test compatibility".
    -   **Impact:** Increases attack surface, technical debt, and risk of unintended behavior in production.
    -   **Severity:** **HIGH**

3.  **Security Bypasses**
    -   **Finding:** [backend/infra/security.py](backend/infra/security.py) allows MD5 password verification fallback and accepts a special token string in dev/test.
    -   **Locations:**
        - MD5 fallback: [backend/infra/security.py](backend/infra/security.py#L160-L190)
        - Special token bypass: [backend/infra/security.py](backend/infra/security.py#L260-L285)
    -   **Impact:** weak password hashing could be exploited. Dev bypasses might leak into production.
    -   **Severity:** **CRITICAL**

4.  **ASGI Lifespan/Startup Ordering Risk (Socket.IO Wrapper)**
    -   **Finding:** Root entrypoint initializes DB before Uvicorn because the Socket.IO wrapper may not forward ASGI lifespan events.
    -   **Locations:** [main.py](main.py#L21-L69), [backend/api/main.py](backend/api/main.py#L1-L40)
    -   **Impact:** Startup becomes order-dependent and harder to reason about; easy to regress in deploys.
    -   **Severity:** **HIGH**

5.  **Low Effective Test Coverage (Current)**
        -   **Finding:** Focused test run passes, but overall backend coverage is currently ~16%.
        -   **Impact:** High regression risk in core trading + risk paths.
        -   **Severity:** **HIGH**

---

## 🧭 Phase 1: Architecture & Data Flow (Evidence-Based)

### Entry Points & ASGI Wiring

- Root process entrypoint runs Uvicorn against the Socket.IO wrapped ASGI app: [main.py](main.py#L15-L83)
- FastAPI app is created via factory, then wrapped with Socket.IO ASGI app: [backend/api/main.py](backend/api/main.py#L1-L20)
- The Socket.IO wrapper is created with `socketio.ASGIApp(... other_asgi_app=fastapi_app ...)`: [backend/api/socketio_server.py](backend/api/socketio_server.py#L415-L435)

### Router Topology (Observed)

- Central `APIRouter(prefix="/api/v1")` + `protected = APIRouter(dependencies=[Depends(get_authenticated_user)])`: [backend/api/factory.py](backend/api/factory.py#L560-L660)
- A second route registration function later in the same module adds additional “compatibility” endpoints and aliases: [backend/api/factory.py](backend/api/factory.py#L1060-L1165)

### Architecture Diagram (Mermaid)

```mermaid
flowchart TD
    main[main.py] -->|uvicorn runs| asgi[socketio_app (ASGI)]
    asgi -->|other_asgi_app| fastapi[FastAPI app]
    fastapi --> factory[create_app() in backend/api/factory.py]

    factory --> apiV1[/api/v1 router/]
    apiV1 --> public[Public routers: system, monitoring, auth]
    apiV1 --> protected[Protected router (Depends(get_authenticated_user))]
    protected --> orders[/orders routes/]
    protected --> portfolio[/portfolio routes/]
    protected --> risk[/risk routes/]

    orders --> orderSvc[OrderService]
    orderSvc --> ordersRepo[OrdersRepo]
    orderSvc --> outbox[OutboxRepo]
    outbox --> worker[Outbox worker -> broker]

    fastapi --> sio[Socket.IO server]
    sio --> broadcast[Broadcast helpers]
    broadcast --> ui[Frontend socket.io-client]
```


---

## 📝 Detailed Findings

### Phase 1: Architecture & Structure

#### [MEDIUM] Confusing Configuration Layering
**Location:** [backend/config.py](backend/config.py#L1-L34), [backend/settings.py](backend/settings.py#L1-L31)
**Description:** There are multiple layers of configuration shims (`SettingsProxy`, `LegacySettings`) to support backward compatibility.
**Recommendation:** Consolidate into a single, authoritative `Settings` class using Pydantic. Remove all shims.

#### [HIGH] Test Stubs in API Entry Point
**Location:** [backend/api/main.py](backend/api/main.py#L1-L80)
**Description:** The file contains numerous stub functions (`get_metrics`, `submit_order`) purely for "test compatibility".
**Evidence:**
```python
# Compatibility functions that some tests might import directly
def health_check(request=None) -> dict[str, str]: ...
```
**Recommendation:** Remove these stubs. Tests should import from actual service modules or use proper mocking.

---

### Phase 2: Trading Algorithm Logic

#### [HIGH] Production Code Polluted with Test Hooks
**Location:** [backend/strategies/engine.py](backend/strategies/engine.py#L1-L120)
**Description:** Methods like `net_signals` and `is_throttled` are defined just to satisfy legacy tests.
**Evidence:**
```python
def net_signals(self, signals: list[TradingSignal]):  # pragma: no cover - legacy sync hook
    """Legacy test hook: return signals unchanged."""
    return signals
```
**Recommendation:** Refactor tests to mock the strategy engine properly instead of forcing the engine to adapt to the tests.

#### [CRITICAL] Backtesting Has Look-Ahead Bias + Unrealistic Fills
**Location:** [backend/services/backtest_service.py](backend/services/backtest_service.py#L440-L670)
**Description:** Signal generation uses same-day OHLC (including `close`) and trade execution fills at the same bar’s `close`. This creates look-ahead bias (deciding using close while also filling at close). Commissions are hard-coded to `0.0` and no slippage model is applied.
**Impact:** Backtest results materially overstate performance and understate risk; any strategy evaluation is unreliable.
**Evidence:**
```python
if data.close > data.open * 1.02:  # 2% gain
...
entry_price=data.close,
commission=0.0,
```
**Recommendation:** Separate signal time from execution time (e.g., generate on close, execute next open; or generate on previous close). Add slippage + commission models and enforce fill constraints.
**Effort:** Medium  **Priority:** P1

#### [INFO] Potential Numpy Type Leak
**Location:** [backend/services/indicators.py](backend/services/indicators.py#L1-L130)
**Description:** Indicators return `.tolist()`. Verify that this handles `np.nan` conversion to `None` or Python `float` correctly for JSON serialization.

#### [HIGH] StrategyEngine Uses Mock Prices For Sizing
**Location:** [backend/strategies/engine.py](backend/strategies/engine.py#L364-L405)
**Description:** `_exposure_to_qty()` uses a hardcoded `mock_prices` map and a default price of `$100` for any unknown symbol.
**Impact:** Position sizing and notional calculations become detached from reality; risk gating can approve orders whose actual notional differs materially.
**Recommendation:** Fetch prices from a real market-data source (or a single injected quote adapter) and make it impossible to run this path in production with mock pricing.
**Effort:** Medium  **Priority:** P1

#### [HIGH] Indicators Can Emit NaN/Infinity and Division-By-Zero Results
**Location:**
- RSI: [backend/services/indicators.py](backend/services/indicators.py#L65-L101)
- Stochastic %K: [backend/services/indicators.py](backend/services/indicators.py#L244-L259)
**Description:** Several indicator calculations can produce `NaN` / `inf` (e.g., division by zero when denominators are 0) and return them via `.tolist()`.
**Impact:** Downstream JSON encoding and UI rendering becomes inconsistent. The indicators API currently filters `NaN` values, which can result in empty responses and confusing UX.
**Recommendation:** Standardize output hygiene: replace invalid values with `None` inside the indicator functions, and explicitly guard denominators (e.g., when `highest_high == lowest_low`).
**Effort:** Medium  **Priority:** P1

#### [MEDIUM] Duplicate Technical Indicator Implementations (Divergent Behavior)
**Location:**
- Service indicators: [backend/services/indicators.py](backend/services/indicators.py#L1-L120)
- “Resilient” indicators: [backend/features/technical_indicators.py](backend/features/technical_indicators.py#L1-L120)
- ML indicators: [backend/ml/feature_engineering.py](backend/ml/feature_engineering.py#L1-L120)
- Strategy uses a different module: [backend/strategies/basic.py](backend/strategies/basic.py#L1-L20)
**Description:** There are multiple `TechnicalIndicators` implementations with different input validation, NaN handling, and formulas.
**Impact:** The same named indicator (e.g., RSI) can differ across subsystems (scanner/API vs strategies vs ML), making results non-reproducible and harder to test.
**Recommendation:** Consolidate to a single authoritative indicator library (or a single interface with implementations per domain) and add contract tests to ensure consistent outputs.
**Effort:** Medium  **Priority:** P2

---

### Phase 3: Risk Management

#### [CRITICAL] Circuit Breaker Disabled
**Location:** [backend/services/order_service.py](backend/services/order_service.py#L1-L60)
**Description:** The `circuit_breaker_check` function is a stub.
**Evidence:**
```python
def circuit_breaker_check(*args, **kwargs):
    """Circuit breaker check function stub for testing."""
    return False  # Default to not triggering circuit breaker
```
**Recommendation:** Implement real circuit breaker logic (e.g., checking recent loss count, volatility status) immediately.

#### [CRITICAL] Market Hours Check Disabled
**Location:** [backend/risk/risk_manager.py](backend/risk/risk_manager.py#L31-L47)
**Description:** `is_market_hours()` is a simplistic local-time check (9:30–16:00) with no timezone/calendar/holiday/early-close awareness. Comment indicates test intent.
**Recommendation:** Use broker clock/calendar (e.g., Alpaca clock) and an exchange calendar to enforce real market hours reliably.

#### [CRITICAL] Order Service Contains Simulated Cancel/Modify/Status Paths
**Location:** [backend/services/order_service.py](backend/services/order_service.py#L240-L460)
**Description:** Core order behaviors are “simulated” (e.g., `cancel_order`, `modify_order`) and `submit_order()` returns mock “accepted” responses in async contexts when dependencies are missing. `get_order_status()` contains hardcoded test IDs and fallback in-memory behavior.
**Impact:** High risk of silently accepting orders without durable persistence/outbox; behavior differs across runtime contexts; easy to ship “test-mode” behavior into production.
**Recommendation:** Remove simulated production paths or hard-gate them behind explicit test-only flags; require DB + outbox for all submissions/cancels in production.
**Effort:** Medium  **Priority:** P1

#### [HIGH] RiskManager Uses Fallback Portfolio + Empty Positions
**Location:** [backend/risk/risk_manager.py](backend/risk/risk_manager.py#L430-L456)
**Description:** `_get_portfolio_value()` falls back to `$250,000` and `_get_current_positions()` returns `{}` “for testing” (with TODO to integrate real positions). This means symbol exposure checks ignore existing exposure.
**Impact:** Risk controls can approve trades that exceed concentration/position limits in real portfolios.
**Recommendation:** Wire portfolio state + positions from a single source of truth (DB snapshot or broker account) and make “empty positions” impossible in production.
**Effort:** High  **Priority:** P1

#### [HIGH] Risk Market Price Fetch Does Blocking Sync I/O Inside Async
**Location:** [backend/risk/risk_manager.py](backend/risk/risk_manager.py#L458-L507)
**Description:** `_get_market_price()` calls synchronous Alpaca SDK methods from an async function (no `asyncio.to_thread`), and will hard-fail if Alpaca keys are absent.
**Impact:** Event-loop blocking under load + risk checks failing open/closed unpredictably depending on exception handling upstream.
**Recommendation:** Move broker calls behind an async adapter (or `to_thread`) and provide deterministic fallbacks for missing quotes.
**Effort:** Medium  **Priority:** P1

---

### Phase 4: Backend Code Quality

#### [MEDIUM] Sync/Async Mixing
**Location:** [backend/services/order_service.py](backend/services/order_service.py#L1-L140)
**Description:** `submit_order` tries to run `submit_order_async` by checking for a running loop or using `asyncio.run`.
**Recommendation:** Make the entire call chain async. Avoid sync wrappers for core async logic.

#### [HIGH] Async Endpoints Call a Rate Limiter That Uses time.sleep
**Location:** [backend/data/alpaca_client.py](backend/data/alpaca_client.py#L378-L423), [backend/data/alpaca_client.py](backend/data/alpaca_client.py#L812-L823)
**Description:** Alpaca client async methods call `self._rate_limit()`, which uses `time.sleep()`. This blocks the event loop.
**Impact:** Under concurrent load, request latency spikes and can cause cascading timeouts across the API.
**Recommendation:** Replace with an async rate limiter (`await asyncio.sleep(...)`) or move rate limiting into the `to_thread` section.
**Effort:** Low  **Priority:** P1

---

### Phase 5: API Design Review

#### [HIGH] Auth "me" Endpoint Appears to Violate Its Response Model
**Location:** [backend/api/routes/auth.py](backend/api/routes/auth.py#L404-L438)
**Description:** `get_current_user_info()` returns `roles` and `authenticated` fields, but `UserInfoResponse` (as defined in this module) only declares `user_id` and `username`.
**Impact:** Response validation errors (500s) or inconsistent client payloads.
**Recommendation:** Align `UserInfoResponse` with the actual response shape (or change the handler to return only declared fields) and add a unit test for `/auth/me`.
**Effort:** Low  **Priority:** P1

#### [MEDIUM] Password Change Uses Wrong Type Accessor
**Location:** [backend/api/routes/auth.py](backend/api/routes/auth.py#L651-L720)
**Description:** `change_password()` treats `current_user` like a dict (`current_user.get("sub")`), but the dependency provides an `AuthenticatedUser` model.
**Impact:** Endpoint will error at runtime once implemented; indicates type drift in the auth subsystem.
**Recommendation:** Use `current_user.username` (or the correct attribute) and add tests covering auth dependencies.
**Effort:** Low  **Priority:** P2

#### [LOW] Token Validation Returns Synthetic Expiration
**Location:** [backend/api/routes/auth.py](backend/api/routes/auth.py#L360-L402)
**Description:** `/auth/token/validate` sets `expires_at = now + 3600` instead of reading the token’s real `exp`.
**Impact:** Clients may incorrectly assume token validity windows.
**Recommendation:** Parse and return the real `exp` claim from the verified token.
**Effort:** Low  **Priority:** P3

### Phase 6: Frontend Analysis

#### [HIGH] Frontend dependency vulnerabilities (react-router)
**Location:** [frontend/package.json](frontend/package.json#L31)
**Description:** Frontend depends on `react-router-dom` v7.9.3; `npm audit --audit-level=high` reported a **high severity** vulnerability in the `react-router` dependency chain.
**Impact:** Potential CSRF / open redirect / SSR XSS class issues (per advisory). This can become a real security risk depending on route/action usage patterns.
**Recommendation:** Run `npm audit fix` (review changes) and pin/upgrade to the patched versions; add CI gating for `npm audit --audit-level=high`.

#### [MEDIUM] Global suppression of runtime errors and warnings
**Location:** [frontend/src/main.tsx](frontend/src/main.tsx#L10-L45)
**Description:** The app globally suppresses certain `unhandledrejection` errors and overrides `console.warn` to silence Ant Design warnings.
**Impact:** Risk of masking real production issues; harder incident triage; potential loss of telemetry signal if errors are filtered too broadly.
**Recommendation:** Restrict suppression to development-only builds; log suppressed events to observability pipeline with throttling.

#### [MEDIUM] Market Data WebSocket Defaults to Insecure `ws://` (Mixed Content Risk)
**Location:** [frontend/src/services/marketDataWebSocketService.ts](frontend/src/services/marketDataWebSocketService.ts#L19-L25)
**Description:** Default market-data WS URL is `ws://...` derived from `window.location.hostname`.
**Impact:** Breaks when the UI is served over HTTPS (browser blocks mixed content). Also increases exposure to on-path interference if used outside localhost.
**Recommendation:** Build WS URL from `window.location.protocol` (`wss` for `https`) or require explicit `VITE_*` configuration per environment.
**Effort:** Low  **Priority:** P2

#### [MEDIUM] Unbounded Offline WebSocket Message Queue
**Location:**
- Queueing: [frontend/src/services/marketDataWebSocketService.ts](frontend/src/services/marketDataWebSocketService.ts#L289-L299)
- Flush: [frontend/src/services/marketDataWebSocketService.ts](frontend/src/services/marketDataWebSocketService.ts#L546-L558)
**Description:** Messages are queued indefinitely while disconnected; there is no max queue size or dedupe.
**Impact:** Memory growth over long disconnects; reconnect spikes when flushing; noisy logs.
**Recommendation:** Add a bounded queue (size/time-based), coalesce duplicate subscribe/unsubscribe actions, and drop stale messages.
**Effort:** Medium  **Priority:** P2

#### [LOW] Sensitive/Verbose Console Logging in Trading Flows
**Location:** [frontend/src/services/ordersService.ts](frontend/src/services/ordersService.ts#L69-L78)
**Description:** Logs order payloads to the browser console.
**Impact:** Trade intent data can leak via shared machines/screenshots; increases noise in production debugging.
**Recommendation:** Gate logs behind dev builds and avoid printing full payloads.
**Effort:** Low  **Priority:** P3

### Phase 7: Security

#### [CRITICAL] MD5 Password Fallback
**Location:** [backend/infra/security.py](backend/infra/security.py#L170-L187)
**Description:** `verify_password` falls back to MD5 if the hash looks like MD5.
**Evidence:**
```python
if len(hashed_password) == 32 ...:
    return hashlib.md5(plain_password.encode()).hexdigest() == hashed_password
```
**Recommendation:** Remove this immediately. Force password resets for any legacy accounts if they exist.

#### [HIGH] UserRepository Creates MD5 Users in Fallback Storage
**Location:** [backend/infra/users.py](backend/infra/users.py#L46-L121)
**Description:** When the repository runs without a DB session it creates default users and hashes passwords using MD5. The async `create_user()` also supports `use_fast_hash=True` (MD5).
**Impact:** If the “fallback” mode is reachable in non-test environments, credentials are weak and trivially crackable; it also normalizes MD5 acceptance elsewhere.
**Recommendation:** Remove MD5 entirely; for tests, use bcrypt with reduced cost or a dedicated test-only password hasher guarded by environment.
**Effort:** Medium  **Priority:** P1

#### [HIGH] Orders API Implements a Local “ProductionRiskManager” With Hardcoded Defaults
**Location:** [backend/api/routes/orders.py](backend/api/routes/orders.py#L170-L360)
**Description:** `get_risk_manager()` defines an inner `ProductionRiskManager` using hardcoded limits and default price estimation (`price or 100.0`), plus conservative placeholder portfolio values and TODOs.
**Impact:** Risk assessment becomes inconsistent with the core risk subsystem; approvals/blocks depend on the endpoint implementation rather than a single authoritative risk engine.
**Recommendation:** Remove the inline risk manager and depend on a single `AsyncRiskManager` wired with real portfolio/position sources.
**Effort:** High  **Priority:** P1

#### [HIGH] Development Token Bypass
**Location:** [backend/infra/security.py](backend/infra/security.py#L260-L285)
**Description:** `decode_token` accepts "valid_token" if environment is test/dev.
**Impact:** Accidental exposure in production if env vars are misconfigured.
**Recommendation:** Remove the bypass entirely; if tests need it, inject an auth dependency override in tests rather than shipping bypass logic in production code.
**Effort:** Low  **Priority:** P1

#### [HIGH] Code Defaults Include a JWT Secret + Auto-Loads `.env`
**Location:**
- `.env` auto-load: [backend/config/base_settings.py](backend/config/base_settings.py#L15-L22)
- Default JWT secret value: [backend/config/base_settings.py](backend/config/base_settings.py#L88-L107)
**Description:** Configuration defaults include a non-empty JWT secret fallback and the module loads `.env` automatically at import-time.
**Impact:** In misconfigured deployments, the app can run with a known/default secret; implicit `.env` loading makes production configuration less explicit and easier to drift.
**Recommendation:** Fail fast in production if JWT secret is unset, and do not auto-load `.env` except in explicit local/dev tooling.
**Effort:** Low  **Priority:** P1

---

### Phase 8: Performance & Scalability (Evidence-Based)

#### [HIGH] Event Loop Blocking Risks In Core Paths
**Location:**
- Blocking rate limiter in async methods: [backend/data/alpaca_client.py](backend/data/alpaca_client.py#L378-L423)
- Sync broker calls inside async risk pricing: [backend/risk/risk_manager.py](backend/risk/risk_manager.py#L458-L507)
**Description:** Async code paths contain blocking operations (e.g., `time.sleep` and sync SDK calls).
**Impact:** Under concurrent load, the API’s tail latency will spike and may cascade into timeouts (especially around order placement and risk checks).
**Recommendation:** Replace blocking sleeps with `await asyncio.sleep(...)` and move sync broker calls behind an async adapter (`asyncio.to_thread` at minimum).
**Effort:** Medium  **Priority:** P1

#### [MEDIUM] Market Data Client Can Accumulate Backpressure
**Location:** [frontend/src/services/marketDataWebSocketService.ts](frontend/src/services/marketDataWebSocketService.ts#L289-L299)
**Description:** The unbounded offline message queue can grow without limit during prolonged disconnects.
**Impact:** Memory growth and reconnect spikes; can degrade UI responsiveness.
**Recommendation:** Add bounded queue + coalescing (subscribe/unsubscribe dedupe) and backpressure metrics.
**Effort:** Medium  **Priority:** P2

---

### Phase 9: Testing & Quality Assurance (Evidence-Based)

#### [HIGH] Coverage Is Low Relative To Trading/Risk Criticality
**Location:** See Automated Checks (Pytest + coverage)
**Description:** Focused marker-based run passes, but overall backend coverage is ~16%.
**Impact:** High regression risk across order/risk/auth flows.
**Recommendation:** Add module-level coverage gates for [backend/services/order_service.py](backend/services/order_service.py), [backend/risk/risk_manager.py](backend/risk/risk_manager.py), and auth routes; add an integration lane using an ephemeral Postgres.
**Effort:** Medium  **Priority:** P1

---

### Phase 10: DevOps & Infrastructure

#### [HIGH] Hardcoded Docker Secrets
**Location:** [docker-compose.yml](docker-compose.yml#L17-L40)
**Description:** `docker-compose.yml` includes hardcoded development credentials (DB password, JWT secret, and Alpaca dummy keys) directly in `environment:`.
**Evidence:**
- DB URL w/ password: [docker-compose.yml](docker-compose.yml#L22)
- Dummy broker keys: [docker-compose.yml](docker-compose.yml#L28-L30)
- Hardcoded JWT secret: [docker-compose.yml](docker-compose.yml#L33)
**Recommendation:** Use `.env` files and do not commit default credentials even for development.

#### [CRITICAL] Committed env files include production JWT secret values
**Location:** [.env.production](.env.production#L88)
**Description:** A long `SECURITY_JWT_SECRET=...` value is present in a committed file.
**Impact:** Secrets in version control are frequently exfiltrated (forks, logs, backups). If this value was ever used in a deployed environment, it must be rotated.
**Recommendation:** Remove secrets from repo history (rotate immediately, then rewrite history if appropriate). Keep only `.env.example` / templates without real secrets.

#### [HIGH] Startup script sets a default JWT secret if unset
**Location:** [start-server.ps1](start-server.ps1#L53-L54)
**Description:** If `SECURITY_JWT_SECRET` is missing, the script assigns a default hardcoded string.
**Impact:** Easy to accidentally run with a known secret (especially on dev boxes); increases risk of misconfiguration leaking into staging/prod.
**Recommendation:** Fail fast unless `SECURITY_JWT_SECRET` is provided; allow an explicit `-Development` shortcut only if it clearly tags the environment and cannot be used in production.

#### [HIGH] JWT Secret Env Var Name Mismatch Can Cause Silent Insecure Defaults
**Location:**
- Script sets `SECURITY_JWT_SECRET`: [start-server.ps1](start-server.ps1#L53-L54)
- Compose sets `JWT_SECRET_KEY`: [docker-compose.yml](docker-compose.yml#L33)
- Settings maps legacy `JWT_SECRET_KEY` but not `SECURITY_JWT_SECRET`: [backend/config/base_settings.py](backend/config/base_settings.py#L872-L889)
**Description:** Multiple secret env var names are used across the repo. `SecurityConfig` expects `SECURITY_JWT_SECRET_KEY` (pydantic field `jwt_secret_key` with `env_prefix="SECURITY_"`), but the startup script sets `SECURITY_JWT_SECRET`, and compose uses `JWT_SECRET_KEY`.
**Impact:** It becomes easy to accidentally run with the code-default JWT secret in [backend/config/base_settings.py](backend/config/base_settings.py#L101-L106) (or with unintended legacy mapping), especially in production/staging where `.env` loading differs.
**Recommendation:** Choose one canonical variable (`SECURITY_JWT_SECRET_KEY` recommended), remove ambiguous aliases, and fail fast in production if it’s missing.
**Effort:** Low  **Priority:** P1

#### [medium] Unreliable Test Environment
**Location:** [pytest.ini](pytest.ini)
**Description:** Focused unit/api/services test selection passes (see “Automated Checks”), but overall backend coverage remains low and many tests are currently deselected by marker selection.
**Recommendation:** Add CI jobs for (1) unit-only fast lane, (2) integration tests with ephemeral DB (pytest-docker/testcontainers), and (3) coverage thresholds on critical modules (risk/order/auth).

---

## 🗺️ Remediation Roadmap

1.  **Sprint 1: Safety & Security (Priority: Critical)**
    -   Remove MD5 fallback.
    -   Remove "valid_token" bypass.
    -   Implement real `circuit_breaker_check`.
    -   Implement real `is_market_hours`.
    -   Rotate any committed secrets (`.env.production`, docker-compose defaults) and add secret scanning in CI.

2.  **Sprint 2: Architecture Cleanup (Priority: High)**
    -   Remove [backend/api/main.py](backend/api/main.py) stubs.
    -   Remove [backend/strategies/engine.py](backend/strategies/engine.py) test hooks.
    -   Remove inline `ProductionRiskManager` from orders routes; depend on one authoritative risk engine.
    -   Remove simulated order flows in `OrderService` (`cancel_order`, `modify_order`, hardcoded test IDs) or hard-gate behind test-only mode.
    -   Refactor tests to use dependency overrides/mocking instead of production shims.
    -   Consolidate the 3+ technical indicator implementations into one authoritative interface/module.

3.  **Sprint 3: Technical Debt (Priority: Medium)**
    -   Consolidate Configuration.
    -   Fix `order_service.py` sync/async mixing.
    -   Fix async blocking: replace `time.sleep` rate limiter in Alpaca client; move sync Alpaca calls in risk pricing behind async adapters.
    -   Fix auth API correctness (`/auth/me` response model mismatch; incorrect `AuthenticatedUser` usage).
    -   Fix Docker setup and secrets management.

4.  **Sprint 4: Trading Correctness (Priority: Medium)**
    -   Remove look-ahead bias in backtesting (signal time vs execution time); add slippage + commission models.
    -   Add deterministic fixtures for market data and fill simulation.

---

## 🧪 Test Gap Analysis (Recommended Additions)

1. **Order submission invariants**
   - Unit tests for `OrderService.submit_order_async` requiring both `OrdersRepo` + `OutboxRepo` (no “accepted mock” path in production).
   - Idempotency tests: repeated requests with same key result in single order + single outbox event.

2. **Risk correctness + data wiring**
   - Integration test with seeded positions verifying symbol concentration checks (risk must account for existing exposure).
   - Test that risk pricing never blocks the event loop (use a fake async quote adapter).
   - Negative tests: risk blocks should return structured 422 responses consistently.

3. **Backtesting validity**
   - Tests that ensure no same-bar look-ahead (signals use $t$ data, fills at $t+1$).
   - Tests that commission/slippage are applied and impact P&L.

4. **Auth correctness**
   - Contract tests for `/auth/me`, `/auth/login`, `/auth/token/validate` (response schema + correct expiry extraction).
   - Ensure no test-only bypass token is accepted in production configuration.

5. **Indicator math + serialization**
    - Unit tests for indicator edge cases (flat series, zero-range highs/lows, missing volumes) asserting outputs are `None` (not `NaN`/`inf`).
    - Contract test for indicators API ensuring responses never include `NaN` and never return an empty `values` dict for valid inputs.

