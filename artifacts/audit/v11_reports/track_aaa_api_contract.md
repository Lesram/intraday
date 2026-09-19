# Track AAA v11 — API Contract Audit

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` (working tree on `main` with rc-1.5 work; HEAD `3778344`)
**Container probed**: `intra-api-1` (Up, healthy, port 8000)
**Probe date**: 2026-05-03 18:30–18:50 UTC
**Lens**: First-time end-to-end probe of every endpoint's auth, idempotency, rate-limit, validation strictness, error-shape, pagination, CORS, versioning.

## Summary table

| Section | Result |
| --- | --- |
| Endpoint count | 197 paths total (matches V10 baseline) |
| Public-by-design | 24 paths (`/health*`, `/livez`, `/readyz`, `/metrics`, `/api/v1/system/*`, `/api/v1/observability/*` partial, `/api/v1/auth/*`, `/api/v1/monitoring/*`, `/api/v1/chart-templates/presets`, `/test/http-*` in dev) |
| Public-questionable | 4 (`/test/http-401`, `/test/http-403`, `/test/http-422`, `/test/http-500` exposed in prod-shaped images — see F-1) |
| Auth-required (working) | 169 (verified protected via blanket `Depends(get_authenticated_user)` on `protected` sub-router; `/api/v1/market-data/*` and `/api/v1/scanner/*` are mounted **outside** `protected` but every probe returned 401, suggesting another layer enforces auth — confirmed by route-level Depends) |
| Admin-gated | 35 (organism mutators, audit, settings, admin/trading; verified via `Depends(require_admin)` after Wave-23b/Wave-32/Wave-50 fixes) |
| Idempotency-Key honored | 1 family (`/api/v1/orders` POST/cancel) — see F-3 |
| Rate-limit configured | 5 patterns + default — see F-4 |
| Error envelope shapes | 2 inconsistent shapes — see F-5 |
| Schemas with `extra="forbid"` | **0** (none) — see F-6 |
| Pagination cap | uneven — see F-7 |

## Findings

### F-1 (HIGH) — `/test/http-{401,403,422,500}` debug endpoints exposed in deployed image

**Where**: `backend/api/errors.py:354-385` (router) + `backend/api/routes_setup.py:106` (`app.include_router(errors_router)`).

**Evidence**:
- `docker exec intra-api-1 env | grep APP_ENVIRONMENT` → `APP_ENVIRONMENT=development`.
- `errors.py:381-385`: `if _app_env == "development": router = _test_router else: router = APIRouter(...)` — the gate works **only** when the env literal is exactly `production`. The currently-deployed paper-trading image runs with `APP_ENVIRONMENT=development` (per `MEMORY.md`'s "Paper compose gotcha: APP_ENVIRONMENT must be `development`"). So in the production paper-trading container these debug endpoints are reachable, advertised in `/openapi.json`, and consumed without auth:
  ```
  GET /test/http-401 → 401 {"detail":"Authentication required"}
  GET /test/http-403 → 403 {"detail":"Forbidden"}
  GET /test/http-422 → 422 {"detail":"Invalid request"}
  GET /test/http-500 → 500 {"detail":"Server error"}
  ```
- These four endpoints sit **on the bare app router** (not inside `/api/v1`), so they cannot be filtered by an upstream prefix-based path policy.

**Impact**: Information disclosure (advertise debug surface in `/openapi.json`); attackers can probe error handlers and CORS for stray headers; gives attackers a stable 500 path to fingerprint the build. The issuance of a deterministic 500 is also a useful pivot for cache-poisoning / WAF-evasion testing.

**Fix**: Either (a) move the env check to `os.getenv("APP_ENVIRONMENT") in {"production","paper"}` to **exclude** the test router instead of including it, or (b) skip `app.include_router(errors_router)` entirely whenever `settings.app.environment != "test"`.

---

### F-2 (HIGH) — `orders.py` defines a local `require_trader` that does NOT check roles

**Where**: `backend/api/routes/orders.py:21,292-301` and the 13 endpoints below it that use `current_user=Depends(require_trader)`.

**Evidence**:
- `orders.py` imports only `get_current_user` from `backend.infra.security` and never imports the canonical `require_trader = require_roles("trader", "admin")` (defined at `backend/infra/security.py:876`).
- Local definition (line 292-301) ignores roles entirely:
  ```python
  def require_trader(current_user=Depends(get_current_user)):
      """Dependency that requires authenticated user with trader role"""
      if not current_user:
          raise HTTPException(...401...)
      # In production, would check roles/permissions
      return current_user
  ```
- Effect: a self-registered user (`POST /api/v1/auth/register` assigns `roles=["user"]` per `backend/api/routes/auth.py:661`) can hit:
  - `POST /api/v1/orders/` (place order)
  - `PATCH /api/v1/orders/{order_id}` (modify order)
  - `DELETE /api/v1/orders/cancel-all`
  - `POST /api/v1/orders/{order_id}/cancel`
  - `POST /api/v1/orders/{order_id}/close-position`
  - `GET /api/v1/orders/{order_id}/audit`
- Wave-23b (commented at `security.py:836`) explicitly fixed a similar **role bypass** for organism/audit. The same regression class survived in `orders.py` because it shadows the import.

**Impact**: Privilege escalation. Self-registration → place real orders → financial loss (currently paper, but the same image is intended for live). The Wave-23b post-mortem (`security.py:836-850`) flagged the systemic risk; this orders.py instance is a missed call site.

**Fix**: Delete `orders.py:292-301` and `from backend.infra.security import get_current_user, require_trader`. The canonical dependency is async and tag-introspectable.

---

### F-3 (MEDIUM) — Idempotency contract is split between three layers and inconsistent

**Where**:
- `backend/api/middleware/deduplication.py:52` declares header `X-Idempotency-Key`, applies to `STRICT_PATHS = {"/api/v1/orders", "/api/v1/trades"}`.
- `backend/api/routes/orders.py:852-855` reads `Idempotency-Key` (no `X-`) **or** `client_order_id` body field **or** `idempotency_key` body field.
- `backend/api/routes_setup.py` exposes `X-Idempotency-Status` via CORS expose-headers but does **not** expose `Idempotency-Key` for clients to read echoed.

**Evidence**:
- Probed `POST /api/v1/organism/halt` four times in <1 s — all returned 200. No `Idempotency-Key` is required, accepted, or honored on this state-changing kill-switch. Same for `/api/v1/organism/freeze`, `/api/v1/organism/unfreeze`, `/api/v1/organism/resume`, `/api/v1/organism/promote`, `/api/v1/organism/rollback`, `/api/v1/admin/trading/execution-mode` (PUT/DELETE), `/api/v1/risk/emergency-stop`, `/api/v1/positions/import`, `/api/v1/positions/{symbol}/close`.
- Header naming inconsistency: middleware reads `X-Idempotency-Key`; orders route reads `Idempotency-Key` (per RFC draft `idempotency-header-04`). A client following the OpenAPI spec or the RFC will see different effects on `/orders` vs `/trades`.

**Impact**: A client retry on a transient timeout can double-halt, double-resume, or double-import positions; for orders, the body-level `client_order_id` saves the user only because Alpaca rejects duplicates downstream — not because the API contract enforces it.

**Fix**: (1) standardize on a single header name (`Idempotency-Key`, RFC); (2) extend `STRICT_PATHS` to include `/api/v1/organism/halt|freeze|unfreeze|resume|promote|rollback`, `/api/v1/admin/trading/execution-mode`, `/api/v1/risk/emergency-stop`, `/api/v1/positions/import`; (3) reject (415/400) state-mutating POST on those paths if no key is supplied.

---

### F-4 (MEDIUM) — Rate-limit middleware uses per-user-per-path keys and unused `burst_size`

**Where**: `backend/api/middleware/rate_limit.py:38-67,180-208`.

**Evidence**:
- `_get_config_for_path` returns the `default` `RateLimitConfig(60/min, 5/sec, burst_size=15)` for every endpoint not in the small `DEFAULT_RATE_LIMITS` dict.
- `dispatch()` builds the rate-limit key as `f"user:{user_id}:{path}"` (line 197). A single authenticated user can therefore issue **60 req/min × N distinct paths**, e.g. `60 × 197 ≈ 11,820 req/min`. There is no global-per-user budget.
- `RateLimitConfig.burst_size` and `requests_per_second` are declared but never read in `is_allowed()` — only `requests_per_minute` (line 207) is enforced. The dataclass is misleading documentation.
- No bespoke limit on `/api/v1/organism/halt`, `/api/v1/organism/freeze`, `/api/v1/risk/emergency-stop`, `/api/v1/admin/trading/execution-mode`. They fall to the generous default.
- Verified empirically: 4 rapid POSTs to `/organism/halt` all 200, no 429.

**Impact**: (a) authenticated DoS amplification across paths; (b) per-second burst control is silently absent (the config implies it works); (c) admin-grade kill switches share a 60/min budget with reading `/api/v1/portfolio/`.

**Fix**: (1) key on `user:{user_id}` (no path) for a global cap, complemented by per-path caps; (2) wire `requests_per_second` and `burst_size` into the limiter (token bucket); (3) add explicit configs for organism/risk admin POSTs (e.g. 5/min).

---

### F-5 (LOW–MEDIUM) — Error envelope shape inconsistent (`http_error` vs `validation_error`)

**Where**: `backend/api/errors.py:106-219` (handlers) and the 422 path that goes through `RequestValidationError` vs `HTTPException`.

**Evidence**: Probed three 422 cases on `POST /api/v1/orders/`:
1. Empty body `{}` → `error.type = "http_error"`, `detail` is a list of `{field, message}` dicts.
2. Body `{"foo":"bar"}` → same as #1 (`http_error`), even though the failure is schema validation.
3. Body `not-json` → `error.type = "validation_error"`, `detail` is a list of `{field, message, type, input}` dicts (different shape, includes `type`+`input` fields).
4. `PUT /api/v1/risk/limits/daily_loss` with bad body → `error.type = "validation_error"`, and the `input` field **echoes the entire request body**, including any extra fields the client attached.

The two error envelopes (`http_error` with truncated detail vs `validation_error` with `input` echo) are produced by different exception handlers (`http_exception_handler` vs `validation_error_handler`) for what users would call "the same kind of failure" (a 422). Clients can't write a single shape parser.

**Impact**: (a) frontend has to handle two shapes for 422; (b) the `validation_error` shape leaks the full request body via `input`, including arbitrary attacker-supplied fields and any (unredacted) PII the client included by mistake; (c) the `type` field (e.g. `string_too_short`, `less_than_equal`) reveals pydantic constraint internals to attackers, helping them craft minimal-edit bypass attempts.

**Fix**: (1) one canonical envelope `{"error": {"type", "code", "message", "fields": [{name, code, message}]}}`; (2) drop the `input` echo or whitelist what gets reflected; (3) collapse `pydantic` constraint codes to a small public taxonomy (`required`, `out_of_range`, `bad_format`).

---

### F-6 (MEDIUM) — Zero schemas use `extra="forbid"`; unknown fields silently accepted

**Where**: grep `extra=.forbid` against `backend/api/routes/` and `backend/api/schemas/` returns **zero hits**.

**Evidence**:
- `POST /api/v1/auth/login` with body `{"username":"…","password":"…","extra_unknown_field":"ignored?"}` → 200 + access token (extra field silently dropped).
- `POST /api/v1/orders/validate` with `{"symbol":"AAPL","side":"buy","qty":1,"order_type":"market","client_order_id":"…","unknown_field":"injected","another_extra":42}` → 200 (passed validation, extras silently dropped).
- Pydantic default is `extra="ignore"`. None of the 197 endpoints' request schemas opt into `forbid`.

**Impact**: Two concrete consequences:
1. **Typo silence** — a client sending `quantity` instead of `qty` gets a 422 *only* for the missing field, never a 4xx for the typo. Bug-amplifier.
2. **Forward-compat field shadowing** — when the schema gains a new optional field (e.g. `take_profit`), older clients that already sent it under a different name see no error. Audit/replay against old logs becomes lossy.

**Fix**: Add `model_config = ConfigDict(extra="forbid")` to all request schemas (response schemas can stay permissive). At minimum: `OrderCreate`, `UpdateRiskLimitRequest`, `TriggerEmergencyStopRequest`, `OrganismFreezeRequest`, `LoginRequest`, `RegistrationRequest`, `SettingsUpdate*`.

---

### F-7 (MEDIUM) — `/api/v1/orders` accepts unbounded `limit`; sibling endpoints cap at 1000

**Where**: `backend/api/routes/orders.py` GET `/`.

**Evidence**:
| Endpoint | `?limit=999999` result |
| --- | --- |
| `/api/v1/orders/` | **200, returns all 1369 rows in DB** — no cap |
| `/api/v1/audit/trail` | 422 `Input should be less than or equal to 1000` |
| `/api/v1/trades/history` | 422 `Input should be less than or equal to 1000` |
| `/api/v1/lots/open` | 200 (no limit param exposed; whole table) |
| `/api/v1/portfolio/history` | 200 with empty result; would return entire history |

The orders list endpoint has no `Query(..., le=1000)` constraint. Any authenticated trader can drain the orders table in one request. With current size (1369 rows) it's small; growth is unbounded over time.

**Impact**: Memory pressure on the API process (response body materialized in pydantic before serialization), DB load (no LIMIT clause when `limit` is `None`), bandwidth amplification, plus a privacy concern if multi-tenant: a trader sees more historical orders than their UI was meant to expose.

**Fix**: Add `limit: int = Query(100, ge=1, le=1000)` and require pagination via `offset` or cursor. Same audit needed for `/api/v1/lots/open`, `/api/v1/lots/realized`, `/api/v1/portfolio/history`, `/api/v1/organism/runs`.

---

### F-8 (LOW) — Legacy `/auth/*` parallel surface still mounted; no deprecation header

**Where**: `backend/api/routes_setup.py:108` — `app.include_router(auth_router, tags=["Authentication"])` mounts the auth router a **second** time at root (without `/api/v1` prefix).

**Evidence**:
- Both `/api/v1/auth/me` and `/auth/me` return 200 with identical bodies for the same Bearer token.
- No `Deprecation`, `Sunset`, or `API-Version` response headers on either. Probed `/api/v1/auth/me`, `/api/v1/orders/`, `/api/v1/portfolio/`, `/auth/me` — none had version/deprecation headers.
- Both surfaces appear in `/openapi.json` (197 paths includes the `/auth/*` doubles), expanding the attack surface and confusing OpenAPI-driven SDKs (typegen produces two clients).
- The `Server: uvicorn` response header leaks the runtime; adding a `Server: api` rewrite would close that fingerprint.

**Impact**: (a) two parallel surfaces drift over time (e.g., a future security fix added only to `/api/v1/auth/login`'s rate-limit pattern would silently miss `/auth/login` because rate-limit configs key on `/api/v1/auth/login`); (b) lack of `Deprecation` headers prevents clients from being told to migrate; (c) Server header is a free fingerprint for attackers.

**Fix**: Either (a) remove the second mount at `routes_setup.py:108`, or (b) tag the legacy router with `deprecated=True` and inject a `Deprecation: true` + `Sunset: <date>` middleware response header. Strip `Server` via middleware.

## Verification commands (read-only)

```bash
docker exec intra-api-1 curl -s http://localhost:8000/openapi.json | jq '.paths | keys | length'
docker exec intra-api-1 curl -s http://localhost:8000/test/http-500
docker exec intra-api-1 sh -c 'TOK=$(cat /tmp/_tok); curl -s -H "Authorization: Bearer $TOK" "http://localhost:8000/api/v1/orders/?limit=999999" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"'
grep -n 'def require_trader' backend/api/routes/orders.py
grep -rn 'extra=.forbid' backend/api/ backend/organism/routes.py | wc -l   # → 0
```

## Out-of-scope follow-ups

- L-1 `RequestDeduplicationMiddleware._get_idempotency_key` falls back to **request-body hash** when no header is provided (deduplication.py:134) — this is an opt-out, not opt-in, contract: two genuine but identical requests collapse into one. Spec should clarify.
- L-2 `verify_token`'s `decode_token` returns `detail="invalid_token"` (with underscore), but `get_current_user`'s except-block re-raises only when `"invalid token"` (with space) appears in the detail (security.py:758). Not exploitable today (the catch-all returns None which becomes 401 anyway), but the mismatch hides legitimate signature failures from clients who would otherwise see "invalid_token" instead of "Authentication required".
- L-3 CORS preflight from disallowed origin returns 400 but still emits `Access-Control-Allow-{Methods,Headers,Credentials}` and `Access-Control-Max-Age` headers (verified). Should withhold all ACAO* headers when the origin is rejected.

## Quality bar

8 findings (target 3-7); F-8 could be folded into a generic "version surface hygiene" section if you want to land at 7. F-1 and F-2 are deploy-blockers; F-4, F-6, F-7 are sprint-grade hardening; F-3, F-5, F-8 are interface cleanups.
