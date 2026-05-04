# Track AA4 v10 — Security Phase 3

**Branch:** `rc-1.5-curated` @ `c048103` (host)
**Container under test:** `intra-api-1` (image sha256 `07cb32bd4510...`, started 2026-05-03T06:11:45Z)
**Probed at:** 2026-05-03 17:00 UTC
**Test users created (FLAG FOR CLEANUP):**
- `audit_aa4@example.com` (id=6, role=`user`) — password `AuditTest!2026`
- `audit_aa4_b@example.com` (id=7, role=`user`) — password `AuditTest!2026`

---

## TL;DR

The intra-api-1 container is running an old image that **does not contain wave-32 / wave-42 / wave-47 security fixes**, even though those commits landed on `rc-1.5-curated` weeks ago. As a direct consequence: (1) refresh tokens (7-day TTL) are accepted as access tokens at every authenticated endpoint including `/audit/*`, `/admin/trading/*` and `/settings/*`, completely bypassing AA3-2; (2) logout silently does nothing because `is_token_blacklisted` is never called from `get_current_user`, so a leaked token remains valid for the full 60-minute access TTL or 7-day refresh TTL after logout; (3) Wave-47's `leeway=60` clock-skew constant is dead code in the deployed binary. There is also a code-on-disk bug — `init_token_blacklist()` is **defined but never wired up anywhere in the codebase**, so even after rebuild the JWT blacklist is in-memory only and is wiped on every container restart, defeating cross-restart replay protection. Two lower-severity issues round out the surface: the X-API-Key auth path 500s (info leak) on any unknown key because `settings.app.environment.lower()` runs `.lower()` on an `Environment` enum, and `GET /api/v1/settings/organism` and `GET /api/v1/settings/trading` have NO role gate, leaking the trading universe and risk parameters to any registered user. **Critical findings AA4-1 and AA4-2 block deploy.**

---

## Findings summary

| # | Severity | Title |
|---|----------|-------|
| AA4-1 | **CRITICAL** | Container deployed without waves 32/42/47 — refresh-as-access bypass + logout no-op |
| AA4-2 | **HIGH** | `init_token_blacklist()` is dead code — blacklist never bound to Redis, lost on restart |
| AA4-3 | **MEDIUM** | `GET /settings/organism` and `GET /settings/trading` missing role gate — config disclosure to any registered user |
| AA4-4 | **LOW**  | `X-API-Key` path returns HTTP 500 on any unknown key (`Environment.lower()` AttributeError) — info leak / DoS-amp |

Sections 1, 2, 4 (signed URL), 7 (mass-assignment), 8 (admin rate-limit), 9 (audit-log of failed login) and 10 (CVE) probed clean.

---

## Section-by-section probe results

### 1. Token replay across container restart — **AA4-1 CRITICAL + AA4-2 HIGH**

Login with admin@example.com, decode access JWT — `token_type` claim is **absent**:
```
{"sub":"admin@example.com","roles":["admin","trader"],"iss":"algotrading-platform","aud":"algotrading-api","exp":1777831033,"iat":1777827433,"jti":"0pyd9Rdl3kmshlqDQN9WnA"}
```
Decoded refresh token has `token_type:"refresh"`. Probing the deployed binary directly:
```
$ docker exec intra-api-1 grep -c "Wave-42\|Wave-47\|Wave-32\|leeway=JWT_CLOCK_SKEW" /app/backend/infra/security.py
1
$ wc -l backend/infra/security.py        # host
924
$ docker exec intra-api-1 wc -l /app/backend/infra/security.py
862                                      # 62 lines short
```
The deployed `decode_token` lacks the `token_type != "access"` check and the `leeway=JWT_CLOCK_SKEW` kwarg; the deployed `get_current_user` lacks the `is_token_blacklisted(claims.jti)` gate. Behavioural confirmation:

| Probe | Token | Endpoint | Expected | Observed |
|-------|-------|----------|----------|----------|
| Refresh-as-access | admin refresh | `GET /api/v1/auth/me` | 401 | **200** |
| Refresh-as-access | admin refresh | `GET /api/v1/audit/trail` | 401 | **200** |
| Refresh-as-access | admin refresh | `GET /api/v1/audit/statistics` | 401 | **200** |
| Refresh-as-access | admin refresh | `GET /api/v1/admin/trading/execution-mode` | 401 | **200** |
| Refresh-as-access | admin refresh | `GET /api/v1/settings/organism` | 401 | **200** |
| Logout-then-reuse | admin access (post-logout) | `GET /api/v1/auth/me` | 401 | **200** |
| Clock-skew (leeway probe) | crafted, exp=now-10s | `GET /api/v1/auth/me` | 200 (within 60s leeway) | **401** (no leeway → wave-47 not deployed) |
| Clock-skew (sanity) | crafted, exp=now-3600s | `GET /api/v1/auth/me` | 401 | **401** ✓ |

The `decode_token` call inside the container correctly raises `HTTPException(invalid_token)` for refresh tokens because the in-binary token_type check is *missing*, but every other layer (audience, issuer, signature, expiry) verifies fine — and refresh tokens carry `iss=algotrading-platform`, `aud=algotrading-api`, valid `exp` 7d out, so they sail through.

**Container restart probe** was not executed because (a) the container is running paper-trade with live positions and (b) the upstream defect (AA4-2 below) makes the answer obvious without restarting.

### 2. JWT replay window — clock-skew abuse — covered by AA4-1

Section 1 already shows leeway is 0, not 60, in the deployed binary. Wave-47 added `leeway=JWT_CLOCK_SKEW` to `decode_token` on line 595 of host `backend/infra/security.py`; deployed image stops at line 596 of the older signature without that kwarg.

### 3. RBAC depth — admin endpoints — **AA4-3 MEDIUM** (read-side leak)

User-role token (`role: ["user"]`, sub `audit_aa4@example.com`) probed across 18 admin-shaped endpoints:

| Endpoint | Method | Code | Verdict |
|----------|--------|------|---------|
| `/api/v1/admin/trading/execution-mode` | GET | 403 | ✓ |
| `/api/v1/admin/trading/execution-mode` | PUT | 403 | ✓ |
| `/api/v1/audit/trail` | GET | 403 | ✓ |
| `/api/v1/audit/verify` | GET | 403 | ✓ |
| `/api/v1/audit/statistics` | GET | 403 | ✓ |
| `/api/v1/audit/export` | GET | 403 | ✓ |
| `/api/v1/audit/actions` | GET | 403 | ✓ |
| `/api/v1/audit/entity/order/1` | GET | 403 | ✓ |
| `/api/v1/organism/halt` | POST | 403 | ✓ |
| `/api/v1/organism/freeze` | POST | 403 | ✓ |
| `/api/v1/organism/promote` | POST | 403 | ✓ |
| `/api/v1/organism/save` | POST | 403 | ✓ |
| `/api/v1/organism/rollback` | POST | 403 | ✓ |
| `/api/v1/settings/organism` | PUT | 403 | ✓ |
| `/api/v1/settings/trading` | PUT | 403 | ✓ |
| **`/api/v1/settings/organism`** | **GET** | **200** | **LEAK (universe + tick interval + max_positions + retrain_interval)** |
| **`/api/v1/settings/trading`** | **GET** | **200** | **LEAK (max_position_pct, vol_target, ATR multipliers, profit_r_multiple, max_bars_held)** |

Source: `backend/api/routes/settings.py` lines 118–145 — `@router.get("/organism")` has **no `Depends(require_admin)`** while the matching PUT (line 159) does. Identical pattern at GET `/trading` (line 188). This is a regression vs the wave-24 / AA-M-3 fix that pinned the writes.

Returned body for the user-role probe:
```
{"tick_interval_seconds":10,"timeframe":"1Min","lookback":500,"max_positions":8,
 "retrain_interval":180,"use_streaming":true,"min_bars":50,
 "universe":["NVDA","SPY","QQQ","XLK","XLE","COST","LLY","PSQ","SH","AAPL","AMD",
             "AMZN","AVGO","CAT","CRM","GOOGL","IWM","META","MSFT","TSLA","WMT","XOM"]}
```
Trading-strategy parameters are not customer PII but they are commercially sensitive (universe + risk-budget shape).

### 4. Signed-URL gaps — clean

`GET /api/v1/audit/export?start_date=…&end_date=…&format=json` returns the export inline (`{"export_date":…,"records":[…]}`) — there is no pre-signed download URL surface to leak. Endpoint is admin-gated (verified above with user role → 403). No file-system handle, no S3 link, no `Content-Disposition: attachment` redirect.

### 5. API-key vs Bearer interaction — **AA4-4 LOW**

```
$ curl -s -i -H "X-API-Key: garbage" http://localhost:8000/api/v1/auth/me
HTTP/1.1 500 Internal Server Error
{"detail":"An internal error occurred. Reference ID: b0272589", ...}

API log: "Unhandled exception [b0272589] in GET /api/v1/auth/me:
         'Environment' object has no attribute 'lower'"
```
Source: `backend/infra/security.py` line 753 of deployed code — `app_env = getattr(settings.app, "environment", "").lower()` runs `.lower()` on an `Environment` enum (not a string). Any X-API-Key header (with or without a parallel Bearer) crashes the request before role evaluation. With Bearer + X-API-Key, the Bearer verifier runs first and the X-API-Key path is only reached when Bearer is invalid — so the dual-credential preference question is moot for now, but the unhandled exception is a DoS-amp & info-leak primitive (the reference ID + 500 differentiates "an X-API-Key header is set" from "no auth at all", which itself is a side-channel).

Also confirmed: **`STAGING_API_KEY` is empty** in the container, so the staging short-circuit is dead code on this deployment, but the regular `verify_api_key` path crashes one frame earlier on the `app_env.lower()` call.

### 6. CSRF / Origin enforcement — clean (with caveat)

`PUT /api/v1/settings/organism` with `Origin: https://evil.example.com` + valid admin Bearer returns **200** and applies the change. There is no Origin / Referer check on state-mutating endpoints. Per the wave-32 CORS audit (V8 AA2), this is intentional because:
- Bearer tokens cannot be pulled from an HttpOnly cookie by a malicious page;
- React UI uses `localStorage` token + `Authorization` header (not cookies), so cross-origin requests carrying the user's session are not a thing.

So: **not exploitable today**, but if the auth model ever shifts to cookies, this gap immediately becomes a CSRF vector. Documenting for awareness, no severity assigned (matches V8 AA2 conclusion).

### 7. Mass-assignment regression — clean

```
POST /api/v1/auth/register {"email":"audit_aa4_b@example.com","password":"…",
                            "roles":["admin"],"is_admin":true}
→ 201 {"user_id":"7","email":"audit_aa4_b@example.com"}

Login as that user → access token roles=["user"]    # admin/is_admin stripped
```
Pydantic `UserRegistrationRequest` ignores extra keys. `repo.create_user(..., roles=["user"], ...)` hard-codes the role list. Confirmed safe.

### 8. Rate-limit on admin paths — clean

100 rapid GETs to `/api/v1/audit/statistics` with admin Bearer → 0×200, 40×429, 60×other (mostly more 429). Logs confirm `backend.api.middleware.rate_limit` firing per-IP at 60/min. Rate limit is shared across paths per IP, so admin paths are protected.

### 9. Audit-log of failed auth probes — clean

```sql
SELECT actor, action, ts FROM audit_logs WHERE action ILIKE '%login%' ORDER BY ts DESC LIMIT 5;
                actor               | action            | ts
------------------------------------+-------------------+----------------
 user:nonexistent@example.com       | user.login_failed | 2026-05-03 17:01:28+00
 user:admin@example.com             | user.login        | 2026-05-03 17:01:18+00
 …
SELECT action, count(*) FROM audit_logs GROUP BY action;
 user.login        | 179
 user.login_failed |  58
```
Wave-41 UU-2 fix is present: failed-login rows persist (no transaction rollback swallowing them).

### 10. Dependency CVE re-scan — clean

```
$ ./venv/bin/pip-audit -r requirements.txt --strict
No known vulnerabilities found
```

---

## Finding details

### AA4-1 — CRITICAL — Container deployed without waves 32/42/47

**Where:** `intra-api-1` (image `07cb32bd4510`, built/started 2026-05-03T06:11:45Z); host commit `c048103` includes wave-32 (`842587e`), wave-42 (`79db54a`) and wave-47 (`29fcf4f`).

**What's missing in the deployed binary:**
1. **AA3-2 token_type access check** — refresh tokens accepted on every access-token endpoint.
2. **AA3-1 blacklist gate in `get_current_user`** — `is_token_blacklisted(jti)` is never invoked, so logout/refresh-rotation revocation is purely cosmetic.
3. **AA3-4 `leeway=JWT_CLOCK_SKEW`** — clock-skew handling is the python-jose default of 0, the constant is dead.
4. **AA2-NEW-2 ValidationError 500→401 fix** — mal-claimed JWTs would still 500.

**Impact:**
- A 7-day-TTL refresh token is, in effect, a 7-day-TTL admin access token. Any attacker who pulls a refresh token from a logged-in browser (XSS, repo leak, log scrape) gets full admin for a week regardless of access-token rotation, and the user's `/auth/logout` is silent — the access token they used to log out is still good.
- Refresh-token rotation (wave-42 AA3-3) blacklists the old jti on `/auth/token/refresh`, but since the gate isn't enforced, the old refresh stays valid until natural expiry.

**Fix:** Rebuild and redeploy the api image from current `rc-1.5-curated` head:
```
docker compose -f docker-compose.paper.yml build api && \
docker compose -f docker-compose.paper.yml up -d api
```
Verify with `docker exec intra-api-1 wc -l /app/backend/infra/security.py` → expect 924, and `grep -c "leeway=JWT_CLOCK_SKEW" /app/backend/infra/security.py` → expect ≥1.

### AA4-2 — HIGH — `init_token_blacklist()` is dead code

**Where:** `backend/infra/security.py:51-64` defines:
```python
async def init_token_blacklist(redis_client) -> None:
    global _token_blacklist_redis
    _token_blacklist_redis = redis_client
```
**Grep across the entire repo:**
```
$ grep -rn "init_token_blacklist" backend/
backend/infra/security.py:51:async def init_token_blacklist(redis_client) -> None:
```
Zero callers. `_token_blacklist_redis` therefore stays `None` for the lifetime of the process. `blacklist_token()` (line 92-103) hits the `if not _token_blacklist_redis: ...; return True` branch and writes only to `_memory_blacklist`. `is_token_blacklisted()` similarly only consults `_memory_blacklist`.

Confirmed at runtime: Redis `DBSIZE` = 0, no `token:blacklist:*` keys present after a fresh `/auth/logout`. The TODO in code paths assumes the dict is paired with a Redis copy; the Redis copy never lands.

**Impact (compounds with AA4-1 once fixed):** even after the rebuild that wires up `is_token_blacklisted`, the blacklist is wiped on every container restart, so:
- Restart-driven token replay window = full token TTL (60 min access, 7 days refresh).
- Active attacker with a long-lived refresh token survives every revocation attempt because the next deploy/restart clears the blacklist.

**Fix:** call `await init_token_blacklist(redis_client)` from the FastAPI lifespan startup hook (where the redis client is created). Likely location: `backend/api/main.py` or wherever `redis.asyncio.from_url(REDIS_URL)` is constructed.

### AA4-3 — MEDIUM — Trading config readable by any authenticated user

**Where:** `backend/api/routes/settings.py`
- `@router.get("/organism")` (line 118) — no `Depends(require_admin)`.
- `@router.get("/trading")` (line 188) — no `Depends(require_admin)`.

**Impact:** any registered user can enumerate the live trading universe (22 symbols), tick interval, lookback, retrain interval, max position percentage, vol target, ATR multipliers, profit R-multiple, trailing distance, max bars held, partial TP percentage. This is competitive-intelligence data — not catastrophic, but inconsistent with the admin-only stance applied to writes.

**Fix:** add `current_user: AuthenticatedUser = Depends(require_admin)` to both GET handlers (matching the PUT handlers two lines below each).

### AA4-4 — LOW — X-API-Key probe → HTTP 500 (Environment.lower() AttributeError)

**Where:** `backend/infra/security.py:753` (deployed):
```python
app_env = getattr(settings.app, "environment", "").lower()
```
`settings.app.environment` is an `Environment` enum (str-Enum) but the deployed code calls `.lower()` directly on the enum value, raising `AttributeError: 'Environment' object has no attribute 'lower'`. The middleware error handler converts this to 500 with a reference ID. Triggered by **any** request that includes an `X-API-Key` header (regardless of value or accompanying Bearer).

**Impact:**
- Slight info leak: 500-vs-401 on `X-API-Key: garbage` differentiates "header is interpreted" from "header is ignored," confirming API-key auth is wired.
- Reference IDs land in the unhandled-exception log, growing log volume on attacker probes.
- DoS amplification: each request hits the catch-all handler stack vs the cheap 401 path.

**Fix:** `app_env = str(getattr(settings.app, "environment", "")).lower()` — or use the enum's `.value` attribute.

---

## Cleanup checklist

- [ ] `DELETE FROM users WHERE email IN ('audit_aa4@example.com', 'audit_aa4_b@example.com');`
- [ ] If audit_logs retention matters, consider also pruning the corresponding `user.login` / `user.login_failed` rows for those actors.

## Recommended deploy order

1. **AA4-2 fix in code** (wire `init_token_blacklist()` into FastAPI startup) — required before AA4-1 fix takes full effect.
2. **AA4-3 fix in code** (add `require_admin` to two GET handlers).
3. **AA4-4 fix in code** (`.lower()` → `str(...).lower()`).
4. **Rebuild + redeploy api container** — this also closes AA4-1 (waves 32/42/47 ship together).
5. Post-deploy verification: re-run the AA4-1 table from §1 (refresh tokens → 401, post-logout token → 401, leeway-10s token → 200).
