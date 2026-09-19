# V9 Track AA3 — Security Phase 2

- **Branch / commit**: `rc-1.5-curated` @ `ccba97f` (working-dir audit; latest in-tree)
- **Container**: `intra-api-1` (healthy, port 8000)
- **Date**: 2026-05-03
- **Scope**: JWT lifecycle, session, CSRF, request smuggling, IDOR/authorization, mass-assignment, header bypass, info disclosure, dependency CVEs
- **Constraint**: read-only probes only. No real password resets. **One side-effect**: created throwaway non-admin user `audit_aa3_test@example.com` (role `["user"]`) to exercise IDOR — should be cleaned up post-audit.

## Method

All probes use the same admin login (`admin@example.com` / `admin123`) plus a non-admin throwaway. Tokens minted via the live `/api/v1/auth/login` route. Forged tokens use the actual `SECURITY_JWT_SECRET` extracted from `intra-api-1`'s env (HMAC HS256). No mutating endpoints were exercised beyond `/auth/register` (one user) and `/auth/logout` (no DB side effect).

## Per-section probe results

### 1. JWT lifecycle

| Probe | Result | Status |
| --- | --- | --- |
| `alg=none` forge → `/auth/me` | `401 invalid_token` | OK |
| `alg=RS256` confusion → `/auth/me` | `401` | OK |
| HS256 with wrong secret → `/auth/me` | `401 Invalid signature` | OK |
| Token forged with `sub="admin\r\n\r\nX-Injected: true"` | Accepted as JWT (sig valid); CRLF sequence safely JSON-encoded in response body, no header-injection | OK |
| Token with `exp = now + 1`, sleep 5 → `/auth/me` | `401 token_expired` | OK |
| Token with `exp = now − 30` (well within stated 60s skew) → `/auth/me` | `401 token_expired` | NOTE — `JWT_CLOCK_SKEW = 60` constant (security.py:27) is **never plumbed** into `jwt.decode()`. `python-jose`'s default leeway = 0, so the constant is dead code. Behavior is *safer* than documented; flagged as informational. |
| Re-login while old token valid | Old token still works post-rotation | See **F-AA3-3** |
| Logout (`POST /auth/logout`) → re-use same token at `/auth/me` and `/audit/...` | `200` (token still valid post-logout) | **F-AA3-1 — High** |
| Refresh token (7-day TTL) presented as access token at `/auth/me`, `/auth/verify`, `/audit/entity/user/admin@example.com`, `/system/health` | All `200` | **F-AA3-2 — High** |
| Same refresh token replayed twice at `/auth/token/refresh` | Both return `200` with new (access, refresh) pairs — **previous refresh not invalidated** | **F-AA3-3 — Medium** |
| `is_token_blacklisted` / `blacklist_token` reachable from any code path | Grep across `backend/`: defined in `security.py` but **zero call sites** | Supporting evidence for F-AA3-1 |

### 2. Session fixation

- No `Set-Cookie` headers on `/login`, `/me`, or any other route. Pure stateless JWT in `Authorization: Bearer`. Session-fixation surface = N/A.

### 3. CSRF

- `OPTIONS /api/v1/auth/logout` with `Origin: https://evil.example.com` → `400` (no `Access-Control-Allow-Origin`). With `Origin: http://localhost:5173` → `200` with reflection. AA2 wave-23/24 CORS allow-list verified intact.
- `POST /auth/logout` with valid bearer + `Origin: https://evil.example.com` returns 200 — but logout is intentionally non-mutating ("client drops the token"); no CSRF impact even if it were callable cross-site (browser would block the response read on a non-allow-listed origin).

### 4. HTTP request smuggling

- Single request with both `Content-Length: 36` and `Transfer-Encoding: chunked` → uvicorn returned `400 Invalid HTTP request received.` and closed the connection. No CL/TE smuggling vector at the ASGI front-door.
- CRLF in JWT `sub` claim → JSON-encoded in response body (`"username":"admin\r\n\r\nX-Injected: true"`), no response-splitting.

### 5. IDOR / authorization

- AA2-NEW-1 regression — non-admin token GET `/api/v1/audit/entity/user/admin@example.com` → `403`. Self and nonexistent IDs also `403`. Wave-32 fix intact.
- `GET /api/v1/orders` returns the same 100 system orders to admin and non-admin (sha256-identical). Investigated: filter is `Order.user_id == user.username OR Order.user_id == "system"`, and **all 1369 rows in the `orders` table have `user_id='system'`** (organism-generated). API masks `user_id` to empty string on output. This is by-design single-tenant organism visibility, not horizontal IDOR. Per-order-id paths (`/orders/{id}`, `PATCH /orders/{id}`, `cancel-all`) do enforce per-user filtering (orders.py:1049, 1106, 1167, 1233).

### 6. Mass-assignment / over-posting

- `POST /api/v1/auth/register` with body `{"email":"...", "password":"...", "is_admin":true, "roles":["admin"], "user_id":999}` → 201 created **with role `["user"]`**, `is_admin: false`. Pydantic `UserRegistrationRequest` silently strips unknown fields (default behavior). Safe.

### 7. Header-based auth bypass

- `X-Forwarded-User: admin` with no Authorization → `401`. OK.
- `X-Forwarded-For: 127.0.0.1` + `X-Real-IP: 127.0.0.1` with no Authorization → `401`. No IP-trust bypass.

### 8. Race / concurrent login

- Could not measure JTI collision under concurrency: brute-force protection (25 s back-off after a few logins) gates the experiment. JTI generation uses `secrets.token_urlsafe(16)` (16 random bytes, ~128 bits) — collision probability is computationally negligible. Concurrent re-login does **not** invalidate prior tokens (see F-AA3-3); both remain valid until natural exp.

### 9. Information disclosure

- Wrong-password vs. nonexistent-user at `/auth/login`: identical 401 response body and timing. No user enumeration.
- Malformed JWT (`Bearer not.a.jwt`, `Bearer aaaa.bbbb.cccc`) → `401 Authentication required`. No stack trace. AA2-NEW-2 fix intact.
- Security headers present and correct: `x-content-type-options`, `x-frame-options: DENY`, `referrer-policy`, CSP including `frame-ancestors 'none'`.

### 10. Dependency CVE re-scan

```
$ ./venv/bin/pip-audit -r requirements.txt --strict --skip-editable
No known vulnerabilities found
```

Clean.

---

## Findings

### F-AA3-1 — High — Logout does not blacklist the JWT

**Severity**: High. **Blocks deploy if the platform is publicly exposed and tokens may leak via shared devices, browser extensions, or bug-bounty submissions.**

**Evidence**:
1. `POST /api/v1/auth/logout` with valid bearer returns `200 {"ok":true,"message":"Logged out: admin@example.com"}`.
2. Same token used immediately at `/api/v1/auth/me` returns `200` with full admin claims.
3. Same token used at `/api/v1/audit/entity/user/admin@example.com` (admin-gated route) returns `200`.
4. `audit_logs` action distribution shows `user.login=106, user.login_failed=19` — **no `token_revoked` / `blacklist` action** despite the `blacklist_token()` helper existing.
5. Grep across `backend/` shows `blacklist_token(` and `is_token_blacklisted(` are **defined in `backend/infra/security.py` (lines 67, 106) but never invoked anywhere**, including in `decode_token`, `verify_token`, and `routes/auth.py:logout`.

**Code at fault** (`backend/api/routes/auth.py:502-524`):

```python
@router.post("/logout", ...)
async def logout(request: Request) -> LogoutResponse:
    """This platform uses stateless JWTs, so 'logout' is client-side (drop token).
    This endpoint exists to avoid 404s ..."""
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            claims = verify_jwt_token(token)
            username = getattr(claims, "sub", None)
            if username:
                return LogoutResponse(ok=True, message=f"Logged out: {username}")
        except Exception:
            pass
    return LogoutResponse(ok=True, message="Logged out")
```

**Impact**: Any leaked token remains valid until natural `exp` (60 minutes for access, 7 days for refresh — see F-AA3-2 for refresh-as-access). User-initiated logout is purely cosmetic. The full Redis-backed blacklist machinery (`init_token_blacklist`, `_memory_blacklist` fallback, `TOKEN_BLACKLIST_TTL = 7 days`) is built but unwired.

**Fix**: In `routes/auth.py:logout`, after `verify_jwt_token(token)`, call `await blacklist_token(claims.jti, expires_in=remaining_ttl)`. In `backend/infra/security.py:decode_token` (or `verify_token`), check `await is_token_blacklisted(payload['jti'])` and raise 401 if revoked. Also wire `init_token_blacklist(redis_client)` into app startup.

---

### F-AA3-2 — High — Refresh tokens accepted as access tokens (audience/type confusion)

**Severity**: High. **Blocks deploy.**

**Evidence**:
- Refresh token from `/auth/login` (claims include `"token_type":"refresh"`, 7-day TTL) submitted as `Authorization: Bearer <refresh>`:
  - `GET /api/v1/auth/me` → `200`
  - `GET /api/v1/auth/verify` → `200`
  - `GET /api/v1/audit/entity/user/admin@example.com` (admin-only) → `200`
  - `GET /api/v1/system/health` → `200`

**Code at fault** (`backend/infra/security.py:548-612, 615-649`):
- `decode_token()` validates `iss`, `aud`, `exp`, signature — but **does not check `token_type`**.
- Both access and refresh tokens are minted with the **same `iss` and `aud`** (`algotrading-platform`, `algotrading-api`).
- The only place `token_type == "refresh"` is enforced is `decode_refresh_token()` (line 519) — used solely by `/auth/token/refresh`. The reverse check (reject refresh tokens on access paths) is missing.

**Impact**: Refresh tokens have a **7-day TTL** (vs. 60 minutes for access). They are typically stored differently on clients, transmitted on a different code path, and have a different threat model. Treating them as access tokens means: (a) compromise of a refresh token grants 7 days of full API access — including admin endpoints if the user is admin; (b) the entire access/refresh split provides zero security benefit; (c) the rotation comments in the code (`# New refresh token (rotation for security)`) are misleading.

**Fix**: In `backend/infra/security.py:decode_token`, after validating the JWT, reject any token where `payload.get("token_type") == REFRESH_TOKEN_TYPE`:

```python
if payload.get("token_type") == REFRESH_TOKEN_TYPE:
    raise HTTPException(status_code=401, detail="invalid_token_type")
```

A cleaner long-term fix: distinct `aud` claim per token type (`algotrading-api` vs. `algotrading-api-refresh`).

---

### F-AA3-3 — Medium — Refresh tokens are replayable (no single-use enforcement, no rotation reuse detection)

**Severity**: Medium.

**Evidence**:
- Same refresh token submitted twice in succession to `POST /api/v1/auth/token/refresh` — both calls return `200` with fresh (access, refresh) pairs. The first issued refresh token is **not invalidated** when redeemed.
- Re-login (`POST /auth/login`) on the same credentials issues a new (access, refresh) pair, **and the prior access token still works** at `/auth/me` (verified in TEST 9).
- No JTI-tracking, no refresh-token store, no audit_logs entry on refresh. Comment in `routes/auth.py:706` says "This invalidates the old refresh token by issuing a new one" — **incorrect**; the old one remains valid.

**Code at fault** (`backend/api/routes/auth.py:655-727`): the `refresh_token` route mints new tokens but does not record or invalidate the presented refresh JTI.

**Impact**: A stolen refresh token can be redeemed indefinitely (within its 7-day TTL). The "rotation" pattern provides no replay protection without a server-side allowlist or single-use store. Combined with F-AA3-1 (no blacklist on logout) and F-AA3-2 (refresh-as-access), an attacker with a one-time refresh-token leak retains 7 days of full API access plus the ability to mint fresh access tokens at any time.

**Fix**: Track refresh-token JTIs in Redis with TTL = refresh-exp. On every redemption: (a) verify JTI is in the allowlist, (b) atomically delete the old JTI and insert the new one (`SET NX` with `DEL`), (c) on a JTI replay, blacklist the **entire user's tokens** and force re-login (refresh-token reuse-detection per OAuth 2.1 §6.1).

---

### F-AA3-4 — Informational — `JWT_CLOCK_SKEW = 60` constant is dead code

**Severity**: Informational (not a security issue; documentation drift).

`backend/infra/security.py:27` declares `JWT_CLOCK_SKEW = 60` and a comment elsewhere claims tokens have a "+60s clock-skew tolerance". Probing exp = `now − 30` (well inside that window) returns `401 token_expired`. Inspection of `jwt.decode()` calls (lines 211, 503, 573) confirms no `leeway=` argument is passed. python-jose's default leeway is 0. The current behavior (no leeway) is the safer choice; the constant should either be removed or actually wired through (then explicitly tested).

---

## TL;DR

Two **High** findings block deploy: `POST /auth/logout` does not revoke the presented JWT (the entire blacklist machinery in `backend/infra/security.py` exists but has zero call sites), and refresh tokens (7-day TTL) are accepted on every access-token path including admin endpoints because `decode_token()` does not check `token_type`. A **Medium** F-AA3-3 compounds these: refresh tokens are not single-use, so a one-time leak grants 7 days of compounding access. Positive controls all hold — alg=none / RS256 / wrong-secret JWTs are rejected, AA2 IDOR fix on `/audit/entity/user/{id}` is intact, mass-assignment via `/auth/register` is safely stripped by pydantic, CORS rejects evil origins, ASGI front-door rejects CL/TE smuggling, no Set-Cookie surface (so no session fixation), no info disclosure across login enumeration or malformed-JWT 500s, and `pip-audit -r requirements.txt --strict` is clean. Recommend wiring `blacklist_token()` into `/logout` plus a `token_type` reject in `decode_token()` before the next deploy. (Side-effect to clean up: throwaway user `audit_aa3_test@example.com` was created during over-posting probe.)
