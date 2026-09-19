# Track AA2 v8 — Security Re-Audit + External Probing

**Date**: 2026-05-02
**Branch**: `main` @ `5bc4046` (rc-1.5-curated lineage; prompt referenced `79b38fb`, but live tree is `5bc4046`)
**Container**: `intra-api-1` (healthy, 11 min uptime)
**Auditor**: AA2 (external probe + same-class scan)
**Method**: read-only — `curl`, hand-minted JWTs from live secret read via `docker exec printenv`. No mutations on the API. Brute-force probe at /login (50 wrong-password POSTs) is the only quantity-write probe; it triggered the rate-limiter as expected.

---

## TL;DR / Verdict

V7 wave-23/24 fixes for **AA-C-1** (public-default JWT secret) and **AA-H-3** (login audit gap) **landed correctly** under external probing. **AA-C-2** (require_roles factory) **also landed correctly** for the admin-role boundary — non-admin tokens are 403'd consistently across organism mutate routes and `/admin/trading/*`. However, the same-class scan surfaced **two new findings of concern** and **one medium gap**:

1. **HIGH — Audit-trail RBAC tier is too low** (`/api/v1/audit/*` accepts `trader` role; should be admin-only). A trader-role token reads admin login records, role memberships, and forensic event payloads — useful for an attacker who has compromised a trader account.
2. **HIGH — Auth path crashes (HTTP 500) on signed JWTs with malformed claims**. Any token signed with the live secret but missing `roles` (or with `roles` as a string/null, or missing `iat`/`jti`) causes `verify_token()` to raise an unhandled `pydantic.ValidationError` in `get_current_user`, returning 500. This is a low-cost DoS / information-leak vector that can be triggered by anyone in possession of a real token (e.g. a stolen one) — and a stack trace is logged on every request.
3. **MEDIUM — HSTS not emitted under reverse-proxy TLS termination**. Middleware checks `request.url.scheme == "https"`, but doesn't honour `X-Forwarded-Proto`. In production behind a TLS terminator, HSTS never lands.

Plus one informational note: scanner/market-data routers (`api_router.include_router(... market_data_router)` and `... scanner_router`) sit OUTSIDE the `protected` router that auto-applies `Depends(get_authenticated_user)`. Coverage is currently saved by per-route deps inside those files, but the pattern is fragile — any new endpoint added without a per-route `Depends` is silently public. Documented as a structural risk, not a finding.

Security regressions vs. V7: **0**.
New findings: **3** (1 High, 1 High, 1 Medium).
Critical/High are blockers per V8 protocol — documented, not fixed.

---

## 1 — External probe of wave-23/24 fixes (the "did the security actually land" check)

### AA-C-1 — Public default JWT secret rejection

Forge a token with the V7-era leaked default `change-me-in-production` and call admin endpoints:

| Endpoint | Method | Expected | Actual | Verdict |
|---|---|---|---|---|
| `/api/v1/admin/trading/execution-mode` | GET | 401 | **401** | PASS |
| `/api/v1/audit/trail` | GET | 401 | **401** | PASS |
| `/api/v1/organism/halt` | POST | 401 | **401** | PASS |
| `/api/v1/organism/freeze` | POST | 401 | **401** | PASS |
| `/api/v1/organism/unfreeze` | POST | 401 | **401** | PASS |
| `/api/v1/organism/resume` | POST | 401 | **401** | PASS |
| `/api/v1/organism/save` | POST | 401 | **401** | PASS |

**Verdict: AA-C-1 closed.** Default-secret tokens are rejected. Live container has `SECURITY_JWT_SECRET` and `JWT_SECRET_KEY` set to a 64-char value (verified via `docker exec intra-api-1 printenv`).

### AA-C-2 — `require_roles` factory rejects non-admin tokens

Mint role-specific tokens from the live secret with proper `iss=algotrading-platform` / `aud=algotrading-api` claims and probe:

| Endpoint | Method | Token role | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| `/api/v1/admin/trading/execution-mode` | GET | user | 403 | **403** | PASS |
| `/api/v1/admin/trading/execution-mode` | GET | trader | 403 | **403** | PASS |
| `/api/v1/admin/trading/execution-mode` | GET | admin | 200 | **200** | PASS |
| `/api/v1/audit/trail` | GET | user | 403 | **403** | PASS |
| `/api/v1/audit/trail` | GET | trader | 403 | **200** | **FAIL — see Finding AA2-NEW-1** |
| `/api/v1/audit/trail` | GET | admin | 200 | **200** | PASS |
| `/api/v1/organism/halt` | POST | user | 403 | **403** | PASS |
| `/api/v1/organism/freeze` | POST | user | 403 | **403** | PASS |
| `/api/v1/organism/promote` | POST | user | 403 | **403** | PASS |
| `/api/v1/organism/rollback` | POST | user | 403 | **403** | PASS |
| `/api/v1/organism/save` | POST | user | 403 | **403** | PASS |

**Verdict: AA-C-2 admin-boundary closed**, but the "what counts as admin" choice in the audit router is wrong. Trader-tier tokens get full audit access — see Finding AA2-NEW-1.

### AA-H-3 — Login audit-log entries

| Step | `audit_logs.user.login` count | `audit_logs.user.login_failed` count |
|---|---|---|
| Before probe | 26 | 7 |
| After 1 failed login | 26 | 8 |

**Verdict: AA-H-3 closed.** Failed login produces an audit row. The 50 brute-force POSTs earlier in the run only ticked the counter once (the rate-limiter short-circuited the rest **before** the audit-write path), which is intentional and consistent with the rate-limiter being upstream of the audit hook. Implication: failed-login audit count under-reports brute-force attempts. Acceptable trade-off (rate-limiter blocks 49/50 reaching the auth path) but worth noting for forensic interpretation.

---

## 2 — Same-class scan for new auth gaps

Scanned `backend/api/routes/**/*.py` for FastAPI route decorators (`@router.{get,post,put,delete,patch}`) without an auth dependency in the function signature. **166 total routes**; **43 missing per-route `Depends(require_*|get_current_user|get_authenticated_user|verify_token)`**.

Investigation found that `backend/api/routes_setup.py:18` defines a `protected = APIRouter(dependencies=[Depends(get_authenticated_user)])` and includes most routers under it. So 35 of those 43 are guarded by a router-level dep, not a per-route dep. The remaining 8 fall into two groups:

**Intentionally public (verified — pass):**
- `auth.py`: `/login`, `/token`, `/token/validate`, `/logout`, `/register`, `/token/refresh`, `/password-reset/request`, `/password-reset/confirm`
- `system.py`: `/`, `/status`, `/metrics`, `/health`, `/healthz`, `/sli-metrics`
- `monitoring.py`: `/sli-metrics`, `/slo-status`
- `observability.py`: `/health`, `/health/live`, `/health/ready`
- `chart_templates.py:public_router`: `/presets`

**Not in `protected` router but enforced via per-route `Depends` (probed — pass):**
- `market_data.py`: every route uses `Depends(get_authenticated_user)`
- `scanner.py`: every route uses `Depends(get_current_user)`

**Probe results — every probed unguarded path returned 401 without a token:**
- `/api/v1/risk/dashboard`, `/api/v1/risk/metrics`, `/api/v1/lots/open`, `/api/v1/positions/`, `/api/v1/watchlists/`, `/api/v1/strategies/`, `/api/v1/settings/organism`, `/api/v1/settings/trading`, `/api/v1/observability/dashboard`, `/api/v1/market-data/stats`, `/api/v1/scanner/symbols`, `/api/v1/multi-strategy-live/run-once`, `/api/v1/strategies/signals/submit`, `/api/v1/indicators/list`, `/api/v1/optimizations`, `/api/v1/chart-templates/`, `/api/v1/portfolio/`, `/api/v1/portfolio/performance` — all **401**.

**Structural risk (informational, not a finding):** `market_data` and `scanner` routers are mounted on `api_router` (line 92-93 of `routes_setup.py`), bypassing the `protected` group's dependency injection. Today every route inside still has its own `Depends`; tomorrow the next contributor adds a route without one and it silently becomes public. Recommendation (defer): move `market_data_router` and `scanner_router` under `protected.include_router(...)` and let the public WebSocket endpoints opt out individually.

**No new unguarded routes.**

---

## 3 — SecurityHeadersMiddleware verification

Probe `curl -sI http://localhost:8000/api/v1/system/health`:

| Header | Present? | Value |
|---|---|---|
| `X-Content-Type-Options` | YES | `nosniff` |
| `X-Frame-Options` | YES | `DENY` |
| `X-XSS-Protection` | YES | `1; mode=block` |
| `Referrer-Policy` | YES | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | YES | `geolocation=(), microphone=(), camera=()` |
| `Content-Security-Policy` | YES | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` |
| `Strict-Transport-Security` | **NO** | — |

HSTS source: `backend/infra/security_hardening.py:337-341` — only emits when `request.url.scheme == "https"`. The middleware does NOT honour `X-Forwarded-Proto: https`, so when the API runs behind a TLS-terminating proxy (the canonical production deployment), HSTS will never land in client browsers. **See Finding AA2-NEW-3.**

---

## 4 — CORS posture

| Probe | Header | Outcome |
|---|---|---|
| `Origin: https://evil.example.com` GET | `Access-Control-Allow-Origin` | **(absent)** → CORS reflex correct |
| `Origin: https://evil.example.com` OPTIONS preflight | response status | **400 Bad Request** → preflight rejected |
| `Origin: http://localhost:5173` GET | `Access-Control-Allow-Origin: http://localhost:5173` | localhost dev origin allowed (expected) |
| `Access-Control-Allow-Credentials` | always `true` | OK because origin is restrictive |

**Verdict: CORS posture is correct.** No wildcard, no echo of attacker origin.

---

## 5 — Login rate-limit / brute-force re-test

Sent 50 POSTs to `/api/v1/auth/login` with body `{"username":"admin@example.com","password":"wrongpass<i>"}`:

```
50 × HTTP 429 Too Many Requests
```

Rate-limit response headers on a fresh attempt: `X-RateLimit-Limit: 5`, `X-RateLimit-Remaining: 0`, `Retry-After: 30`. The **login route has its own limit (5/window)**, distinct from the global limit (120) seen on `/system/health`. This is wave-23 hardening working as designed.

**Verdict: brute-force protection is in place.** Note that this means failed-login `audit_logs` rows under-count attacker volume by ~10x — see AA-H-3 commentary above.

---

## 6 — Secret-scan re-run

```
grep -RnE 'APCA-API-(KEY|SECRET)-KEY|sk_live|BEGIN PRIVATE KEY|JWT_SECRET' . \
  --exclude-dir={.git,venv,node_modules,artifacts,docs} --exclude='*.pyc'
```

All hits in committed code are: env-var references in compose files (`${JWT_SECRET_KEY}`), test fixtures (`tests/conftest.py: "test-jwt-secret-not-for-production"`, `tests/test_production.py: "supersecretkeythatisatleast32chars"`), or documentation. **No hardcoded production secrets.**

**Verdict: no delta vs. V7. No secret leaks.**

---

## 7 — Dependencies CVE scan

```
./venv/bin/pip-audit -r requirements.txt --strict
→ No known vulnerabilities found
```

**Verdict: clean.** No Critical/High CVEs.

---

## Findings (new, this audit)

### AA2-NEW-1 (HIGH) — Audit forensic data accessible to trader role

**Where**: `backend/api/routes/audit.py:22,109,199,254,290,313,348` — every audit endpoint is gated by `Depends(require_trader)` instead of `Depends(require_admin)`. Comment says `# M-09 FIX: Added authentication`, but the wrong RBAC tier was chosen.

**Impact**:
- A `trader`-role token reads `/api/v1/audit/trail`, `/audit/statistics`, `/audit/actions`, `/audit/verify`, `/audit/entity/{type}/{id}`.
- Forensic content visible includes: admin login timestamps, password-reset requests, RBAC role grants (`payload.roles=["admin","trader"]`), entity-level histories, hash-chain integrity. Body sample retrieved successfully:
  ```json
  {"items":[{"action":"user.login","entity":"user","entity_id":"admin@example.com",
   "actor":"user:admin@example.com","payload":{"roles":["admin","trader"]}, ...}]}
  ```
- Pivot risk: an attacker who phishes a trader-tier credential learns **who the admins are, when they log in, what reset flows they triggered** — material for targeted follow-on attacks.

**Repro**: mint a JWT with `roles=["trader"]` from `SECURITY_JWT_SECRET`, GET `/api/v1/audit/trail` → HTTP 200 + full payload.

**Fix (do NOT apply in V8)**: change `require_trader` → `require_admin` on all six audit endpoints, OR introduce a new `require_audit_reader` role that's distinct from trader. Add a regression test that mints a trader token and asserts 403.

**Severity**: HIGH. The audit log is the system-of-record for forensic and compliance review; widening read access defeats its purpose.

---

### AA2-NEW-2 (HIGH) — Auth path returns 500 on signed JWTs with malformed claims

**Where**: `backend/infra/security.py:629` — `verify_token()` calls `UserClaims(**payload)` without try/except around the pydantic constructor. Any signed token whose payload doesn't match `UserClaims` schema raises `pydantic_core._pydantic_core.ValidationError`, which propagates out of `get_current_user()` and is rendered as a 500 by the FastAPI error handler.

**Repro matrix** (all tokens signed with live `SECURITY_JWT_SECRET`, all hit `/api/v1/auth/me`):

| Mutation | HTTP code |
|---|---|
| `roles` claim missing | **500** |
| `roles` is string `"admin"` (not list) | **500** |
| `roles` is `null` | **500** |
| `iat`/`jti` missing | **500** |
| `sub` missing | 401 (handled cleanly) |
| `roles=[]` | 200 (allowed, no admin access) |

**Stack trace logged on every 500** (from container logs):
```
File "/app/backend/infra/security.py", line 629, in verify_token
  return UserClaims(**payload)
File "pydantic/main.py", line 250, in __init__
  validated_self = self.__pydantic_validator__.validate_python(...)
pydantic_core.ValidationError: 1 validation error for UserClaims
roles
  Field required [type=missing, input_value={...}, ...]
```

**Impact**:
- DoS / amplification: anyone in possession of a stolen or otherwise-acquired live secret (e.g. an old token leaked in a log) can craft a payload that turns every authenticated request into a 500. Not a privilege escalation, but it pins the auth path on an exception path that logs noisily.
- Information leak: `Reference ID` in the 500 body is unique per failure, but repeat probing reveals the exact pydantic field-validation behaviour, narrowing the schema attackers must guess to mint a valid token.
- Fail-open risk vector: any path that catches `HTTPException` but not `ValidationError` could mistakenly let a request through. Today the FastAPI default error handler catches everything, so the failure mode is fail-closed (500). Worth a regression test.

**Fix (do NOT apply in V8)**: wrap `UserClaims(**payload)` in `try/except (ValidationError, TypeError)` and raise `HTTPException(401, "invalid_token")`. Also inspect `decode_token()` (line ~570) for the same pattern.

**Severity**: HIGH because it's a foothold and any dependency on the auth path being non-crashing (e.g. metrics, alerting) is broken under attack.

---

### AA2-NEW-3 (MEDIUM) — HSTS header dropped behind TLS-terminating proxy

**Where**: `backend/infra/security_hardening.py:337-341`:
```python
# HSTS for HTTPS
if request.url.scheme == "https":
    headers["Strict-Transport-Security"] = (
        f"max-age={self.hsts_max_age}; includeSubDomains"
    )
```

**Probe**: `curl -sI -H 'X-Forwarded-Proto: https' http://localhost:8000/api/v1/system/health` returns no HSTS header. In production behind nginx/ALB/Cloudfront, the upstream sees `scheme=http` always, so HSTS never lands.

**Impact**: clients don't learn to upgrade to HTTPS. SSL-strip / downgrade attacks remain feasible against fresh sessions. Note: this only matters for end-user browser flows; API-only clients are unaffected.

**Fix (do NOT apply in V8)**: detect via `X-Forwarded-Proto` header (plus a settings flag like `TRUST_FORWARDED_HEADERS=true` to scope to known-trusted deployments). Or always emit HSTS in production environment regardless of scheme — it's harmless on HTTP (browsers ignore it) but instructs HTTPS-aware clients correctly.

**Severity**: MEDIUM (real, but only meaningful for browser clients behind a proxy).

---

## Summary

**Security regressions (vs. V7): 0.**
**New findings: 3** (HIGH AA2-NEW-1 trader-tier audit access; HIGH AA2-NEW-2 malformed-JWT 500; MEDIUM AA2-NEW-3 HSTS proxy gap).

V7 wave-23/24 fixes for AA-C-1, AA-C-2, AA-H-3 land correctly when probed externally — default-secret tokens 401, non-admin tokens 403 across the organism mutate surface and `/admin/trading/*`, and failed logins increment `audit_logs.user.login_failed`. The same-class scan found no new fully-unguarded routes (the 8 unguarded endpoints are auth/health/observability/public-presets, all intentional). However, the audit router uses `require_trader` instead of `require_admin`, exposing forensic compliance data to any trader-role token — a meaningful pivot vector. Separately, signed JWTs with malformed `roles`/`iat`/`jti` claims crash the auth path with HTTP 500 instead of 401, leaking schema details and creating a low-cost attack surface. The HSTS middleware doesn't honour `X-Forwarded-Proto`, so production-behind-proxy deployments emit no HSTS. CORS, secret-scan, and CVE posture are clean. All three findings are documented as V8 blockers; do **not** fix them in V8 per protocol.
