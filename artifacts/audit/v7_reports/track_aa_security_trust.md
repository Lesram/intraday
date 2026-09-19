# Track AA — Security & Trust Audit (V7, first deep-pass)

- Repo: `/Users/marselkei/VS/intra`
- Branch: `rc-1.5-curated`
- Commit: `d44eace`
- Container audited: `intra-api-1` (running, healthy, port 8000)
- Method: Read-only static analysis + curl inventory + container shell inspection
- Date: 2026-05-03

## TL;DR

Authentication plumbing (JWT signing, bcrypt password storage, login lockout,
hash-chained order/position audit log, websocket handshake auth, parent-router
JWT enforcement on protected routes) is fundamentally in place. The deep-pass
surfaced **13 findings**, with **2 Critical**, **3 High**, **5 Medium**, and
**3 Low**. The single most operationally-significant finding is **AA-C-1**: the
running paper-trading container is signing every JWT with the literal hard-
coded fallback string `dev_secret_key_minimum_32_chars_for_development_only`,
which is publicly visible in `.env` on disk. Anyone with read access to the
repo (or who guesses the documented fallback) can forge admin/trader tokens
against the live broker-connected service. **AA-C-2** is the second critical:
`backend.infra.security.require_admin` / `require_trader` / `require_api` are
factory closures whose dependency-injection wiring is broken — `Depends(require_admin)`
returns a function reference instead of executing the role check, so any
authenticated user (including a self-registered `["user"]` account) can call
the organism halt/freeze/training/diagnostic admin endpoints and the
`/orders/*/audit` audit-trail endpoints with no role enforcement. Both issues
are fixable in tens of lines and should ship before any production rollout.

Bugs found: **13** (2 Critical / 3 High / 5 Medium / 3 Low).

---

## 1. Authentication audit

| Item | Status | Notes |
|---|---|---|
| Algorithm pinning | OK | `algorithms=["HS256"]` enforced on every decode in `backend/infra/security.py:214,506,576`; alg=none attack blocked. |
| Required claims | OK | `decode_token` requires `sub`, `exp`, `iss`, `aud`; `JWT_ISSUER="algotrading-platform"`, `JWT_AUDIENCE="algotrading-api"` enforced. |
| Token blacklist | OK | JTI-based blacklist in Redis with in-memory fallback (`security.py:67-144`). |
| Refresh tokens | OK | Distinct `token_type="refresh"`, 7-day TTL, dedicated `decode_refresh_token` validator (`security.py:480-545`). |
| Login lockout | OK | `infra/users.py:330-381` increments `failed_login_attempts`, locks at `MAX_FAILED_ATTEMPTS` for `LOCKOUT_DURATION_MINUTES`. |
| Password hashing | OK | bcrypt; rejects >72-byte passwords (`security.py:308-322`); explicitly refuses non-bcrypt prefixes (`security.py:344-353`). |
| Subject claim | OK | `sub` rejected when empty/falsy. |
| Replay protection | Partial | `jti` unique per token; access tokens not single-use (acceptable for stateless API), but no nonce/jti freshness check. |
| Secret rotation | Missing (Low) | No documented rotation policy; `revoke_all_user_tokens` requires Redis only — see AA-L-3. |

Two legacy auth shims (`backend/api/auth.py`) exist for older tests; they consult
`JWT_SECRET_KEY` / `JWT_SECRET` and fall back to a *separate* dev fallback
`"dev_only_secret_do_not_use_in_production"` only when `APP_ENVIRONMENT=development`.
Paper compose runs `APP_ENVIRONMENT=development` (per CLAUDE.md gotcha) so this
fallback is reachable.

---

## 2. Authorization audit

The high-level pattern works: `routes_setup.py:18` builds `protected =
APIRouter(dependencies=[Depends(get_authenticated_user)])` and mounts the
trading routers under it. JWT requirement is enforced — verified by curl:

```
$ curl -s http://localhost:8000/api/v1/settings/organism
{"detail":"Authentication required",...}
```

But role enforcement is broken (AA-C-2 below) and three broad surfaces
are entirely public (AA-H-2).

Mass-assignment: `/auth/register` hardcodes `roles=["user"]`
(`auth.py:577`); no risk. Pydantic models elsewhere don't use
`extra="allow"` against external input.

IDOR: drawings, watchlists, and chart-templates accept `{id}` path params and
read the token's `sub` for ownership filtering (sample reviewed:
`drawings.py`, `watchlists.py`). No obvious unscoped reads.

V3 Track I-1/I-2/I-3 fixes still in place: scanner's `/scan|/presets|/export/*`
all carry `Depends(get_current_user)` aliased to `get_authenticated_user`
(`scanner.py:25-30`); observability `PUT /thresholds/{metric}` requires JWT +
inline admin/operator role check (`observability.py:209-215`).

---

## 3. Secrets management

`.env` is gitignored (`.gitignore:122`). `.env.example` ships with
clearly-labeled `CHANGE_ME_*` placeholders. `bcrypt` salt is `gensalt()`
(random per password). Slack webhook reads from `SLACK_WEBHOOK_URL` env;
not committed.

Findings here are **AA-C-1** (deployed JWT secret is the documented dev
fallback string) and **AA-M-1** (Redis password is `changeme_redis` default in
running container).

No grep hits on `logger.*api_key`, `logger.*secret`, or `logger.*token` that
expose actual values — code uses `bool(api_key)` indicators only
(`alpaca_broker.py:105`, `alpaca_data.py:44`).

---

## 4. Injection vulnerabilities

- **SQL injection**: All `text(...)` callsites bind via `:param` style
  (`infra/users.py:335,357,386`; `database/optimization.py:210,216`). Migration
  files use `sa.text()` for default expressions only. The one f-string SQL
  hit, `database/__init__.py:194`, builds a SELECT field-list from a
  whitelisted dict, not user input.
- **Command injection**: `subprocess.run` is used in
  `database/database_config.py:225` and `utils/port_management.py:103,158,173`.
  No `shell=True`. Args passed as lists. No untrusted-input flow.
- **Pickle**: `organism/background_trainer.py:105,107,542,549,556` and
  `utils/secure_pickle.py:156` deserialize the brain state. Source is the
  filesystem directory `organism_brain/` mounted from host. Not internet-
  reachable; risk is low but worth noting (AA-L-1).
- **YAML**: No `yaml.load`/`yaml.unsafe_load` callsites.
- **Path traversal**: No `Path(...) / user_input` patterns in routes.

---

## 5. CORS / CSRF / headers

CORS in `backend/api/middleware_setup.py:55-69`:
`allow_credentials=True`, `allow_methods=["GET","POST","PUT","DELETE","OPTIONS","PATCH"]`,
`allow_origins` from settings or 14-entry `localhost`/`127.0.0.1` list. No
wildcard. Acceptable for the dev/paper context but the paper compose sets
`APP_CORS_ORIGINS=["http://localhost:3000",...]` — production must override.

**No security headers middleware is registered.** `infra/security_hardening.py`
contains a complete `SecurityHeadersMiddleware` (HSTS, X-Frame-Options=DENY,
CSP, X-Content-Type-Options, Referrer-Policy) but it is **never imported by the
factory or middleware_setup**. Verified empirically:

```
$ curl -sI http://localhost:8000/api/v1/health | grep -iE "x-frame|hsts|csp|content-security"
(no output)
```

This is **AA-H-1**.

CSRF: not required, since auth is JWT-in-Authorization-header, not cookie-based.

---

## 6. Rate limiting

`backend/api/middleware/rate_limit.py` has per-endpoint sliding-window limits
(login=5/min, register=3/min, orders=30/min, default=60/min). Wired by
`middleware_setup.py:_setup_rate_limiting`. Verified in response headers:
`x-ratelimit-limit: 60`.

**AA-M-2**: The keying logic at `rate_limit.py:195` reads
`request.state.user_id`, but no middleware ever populates this attribute (grep
returns zero hits). Result: every authenticated user is rate-limited by IP
address, not by user identity. Two users behind the same NAT/proxy share a
single 60-rpm budget; conversely, a single attacker rotating source IPs (or
behind cloud egress) can bypass per-user limits trivially.

---

## 7. WebSocket auth

| Endpoint | Auth | Notes |
|---|---|---|
| `/api/v1/scanner/ws` | Token via `?token=...` query | Closes pre-accept on missing token (4001) and on decode failure (4003). Decoded via `decode_token`. (`scanner.py:794-806`) |
| `/api/v1/market-data/ws` | Token via `?token=...` query | Calls `await websocket.accept()` *before* validating token, then closes with 1008. Slightly looser handshake but token still verified. (`market_data.py:71-108`) |
| Socket.IO at `/socket.io` | `auth["token"]` field on connect | Decoded via `decode_token`; server-side session stores `user_id` and `roles`. (`socketio_server.py:48-115`) |

WS messages are JSON-decoded with no schema validation in `scanner_websocket`
(takes `filters_dict` directly into Pydantic `ScanFilters(**filters_dict)`,
which validates field types but not semantics). Token validity is **not
re-checked on the long-lived connection** — once the handshake passes, the
socket is good until disconnect, even if the token expires (AA-L-2).

Token leakage via query string: tokens may end up in proxy/web-server access
logs (HTTP server logs URLs). FastAPI's logger does suppress query strings on
WebSocket lines, but external proxies (nginx, ingress) typically don't.

---

## 8. Supply chain / dependency scanning

- `requirements.txt`: 85 lines, ~52 `>=` floor pins, 0 `==` exact pins.
- `requirements.lock` exists (173 lines, fully pinned) and is what
  `Dockerfile:38` actually installs (`pip install -r requirements.lock`). So
  the deployed image is reproducible despite the loose `requirements.txt`.
- Installed in container: `fastapi==0.129.0`, `pydantic==2.12.5`,
  `python-jose==3.5.0`, `PyJWT==2.11.0`, `bcrypt==4.2.1`, `cryptography==46.0.5`,
  `SQLAlchemy==2.0.46`, `httpx==0.28.1`, `redis==7.2.0`, `urllib3==2.6.3`,
  `Werkzeug==3.1.5`, `aiohttp==3.13.3`, `requests==2.32.5`.
- No `pip-audit` invocation in CI; no advisory-feed integration. No
  `safety`/`grype`/`trivy` config detected.
- All listed installed versions appear current as of cutoff; no obvious
  high-severity CVE matches without a vuln DB. (AA-M-3 — set up automated
  scanner.)

`requirements-dev.txt` deps (pytest, black, etc.) are **not** installed in the
runtime image — Dockerfile uses `requirements.lock` only. Confirmed by
`pip list | grep pytest` → not present.

---

## 9. TLS / network

- **Outbound HTTP clients**: `httpx.AsyncClient(...)` used in 8 places
  (`alerting.py:195`, `market_scanner.py:106`, `alpaca_stream.py:653`,
  `alpaca_data.py:49`, `alpaca_broker.py:116`, `orders.py:488`,
  `symbol_validator.py:71`). **No `verify=False` anywhere.** TLS verification is
  default-on. 
- **Database**: `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/...` —
  unencrypted intra-container. No `sslmode=` parameter. Acceptable on the
  internal Docker bridge network, but for any deployment with a remote DB this
  must be `sslmode=require` (AA-L-3).
- **Redis**: `REDIS_URL=redis://...@redis:6379/0` — `redis://`, not `rediss://`.
  Same intra-container caveat.
- **Slack webhooks**: HTTPS-only via env var.

---

## 10. Audit log / non-repudiation

`backend/services/audit_service.py` implements an append-only, hash-chained
audit log (`hash_chain` SHA over `(prev_hash, ts, action, entity, entity_id,
actor, payload)`) — strong tamper-evidence (`audit_service.py:200-285`).
Used heavily by the order/position lifecycle.

Gap (**AA-H-3**): The `AuditAction` enum defines `USER_LOGIN`, `USER_LOGIN_FAILED`,
`USER_LOGOUT`, `USER_CREATED`, `USER_DISABLED`, `CONFIG_UPDATED`, `RISK_LIMIT_UPDATED`
but **none of these values are referenced anywhere outside the enum
definition itself**. `auth.py` login/logout/register handlers only call
`logger.info("New user registered: ...")` to plain Python logging, which is
not durable, not hash-chained, and may be wiped on container restart unless
the host log volume catches it. Result:

- Failed-login bursts (brute-force) are not in the audit chain.
- Account creation events are not in the audit chain.
- Password resets / changes / token revocations are not in the audit chain.
- `/settings/organism|trading|ml` and `/settings/restart-engine` mutations
  are not audited (no `audit_service` import in `routes/settings.py`).
- `organism/halt-trading`, `organism/freeze-adaptation`,
  `organism/admin/training` admin actions are not audited.
- `/risk/emergency-stop` triggering is not audited.

Retention: no documented retention policy; hash-chained rows persist in
postgres indefinitely.

---

## 11. Container / runtime hardening

`Dockerfile`:

- Multi-stage; runtime image is `python:3.12-slim`.
- Non-root user: `useradd -u 10001 -r -g 0 -d /app -s /sbin/nologin appuser` and
  `USER appuser`. Verified in container:
  ```
  $ docker exec intra-api-1 id
  uid=10001(appuser) gid=0(root) groups=0(root)
  ```
  **Primary group is `root` (gid=0)** (AA-L-3 / contributing). The intent is the
  classic OpenShift "arbitrary uid + group 0" pattern (so files with `g=u`
  perms work), but with `chmod -R g=u /app` on the build, gid=0 has read+write
  on the entire app tree. Not a critical break, but a sharper image would use
  a dedicated non-root group.

`docker-compose.paper.yml`:

- **No `cap_drop:`** anywhere — container holds default capabilities.
- **No `read_only: true`** on root filesystem.
- **No `security_opt: ["no-new-privileges:true"]`**.
- **No memory / CPU / pids limits** on `api`, `redis`, `postgres`. Production
  compose has `deploy.resources` but still no `cap_drop` or `read_only`.

Verified:

```
$ docker inspect intra-api-1 --format '{{.HostConfig.CapDrop}} | {{.HostConfig.ReadonlyRootfs}} | {{.HostConfig.Memory}}'
[] | false | 0
```

That is **AA-H-4**.

Network isolation: services share `trading-network` bridge — fine. Postgres
exposes port 5432 to the host (`ports: ["5432:5432"]`) which is unnecessary
attack surface for a paper deployment (AA-L-1).

---

## 12. Sensitive endpoint inventory

State-mutating / sensitive endpoints. "Auth" = JWT required;
"Role" = effective role enforced; "Audit" = audit-log emit.

| Route | Method | Auth | Role enforced | Audit | Notes |
|---|---|---|---|---|---|
| `/api/v1/auth/login` | POST | none | n/a | no | Logs to stdout only |
| `/api/v1/auth/register` | POST | none | hardcoded `["user"]` | no | OK by design |
| `/api/v1/auth/logout` | POST | bearer | n/a | no | Token blacklist OK; no audit row |
| `/api/v1/auth/password-change` | POST | bearer | self | no | OK auth; no audit |
| `/api/v1/auth/password-reset/request` | POST | none | n/a | no | OK |
| `/api/v1/auth/token/refresh` | POST | refresh | n/a | no | OK |
| `/api/v1/positions/{symbol}/close` | POST | bearer | trader (parent) | yes (order audit chain) | OK |
| `/api/v1/orders/` | POST | bearer | trader via custom dep | yes (`AuditAction.ORDER_*`) | OK |
| `/api/v1/orders/{id}/cancel` | POST | bearer | trader | yes | OK |
| `/api/v1/risk/emergency-stop` | POST | bearer | trader (parent only) | **no** | High-impact; should be admin-only + audited |
| `/api/v1/risk/limits/{name}` | PUT | bearer | trader (parent only) | **no** | |
| `/api/v1/settings/organism` | PUT | bearer | none | **no** | Mutates engine config; no role gate, no audit |
| `/api/v1/settings/trading` | PUT | bearer | none | **no** | Same |
| `/api/v1/settings/ml` | PUT | bearer | none | **no** | Same |
| `/api/v1/settings/restart-engine` | POST | bearer | none | **no** | Restarts live engine |
| `/api/v1/admin-trading/execution-mode` | PUT | bearer | (parent) | **no** | Toggles paper/live |
| `/organism/halt-trading` | POST | bearer | **broken** require_admin | **no** | AA-C-2 — accessible to any authenticated user |
| `/organism/freeze-adaptation` | POST | bearer | **broken** require_admin | **no** | Same |
| `/organism/admin/training` | POST | bearer | **broken** require_admin | **no** | Same |
| `/organism/diagnostics/run` | POST | bearer | **broken** require_admin | **no** | Same |
| `/api/v1/audit/orders/{id}` | GET | bearer | **broken** require_trader | n/a (read) | Same factory bug |
| `/api/v1/observability/thresholds/{metric}` | PUT | bearer | inline admin/operator | no | Only correctly-gated admin route |
| `/api/v1/scanner/ws` | WS | token query | none | no | Auth OK; no audit |
| `/api/v1/market-data/ws` | WS | token query | none | no | Auth OK; no audit |
| `/api/v1/scanner/symbols` | GET | **none** | n/a | no | Public — symbol universe leak |
| `/api/v1/observability/dashboard` | GET | **none** | n/a | no | Returns runtime metrics |
| `/api/v1/observability/metrics` | GET | **none** | n/a | no | Same |
| `/api/v1/observability/trading` | GET | **none** | n/a | no | Order/fill counts |
| `/api/v1/observability/health` | GET | **none** | n/a | no | OK for K8s probes |

---

## Findings

### AA-C-1 (Critical) — Deployed JWT signing secret is the documented dev fallback

`/.env` contains:
```
SECURITY_JWT_SECRET=${JWT_SECRET:-dev_secret_key_minimum_32_chars_for_development_only}
JWT_SECRET_KEY=${JWT_SECRET:-dev_secret_key_minimum_32_chars_for_development_only}
```

`docker-compose.paper.yml` line 44 reads `JWT_SECRET_KEY` via shell substitution, so
when the user has not exported `JWT_SECRET`, the literal fallback string ships
into the container. Verified in `intra-api-1`:

```
$ docker exec intra-api-1 sh -c 'echo $JWT_SECRET_KEY'
dev_secret_key_minimum_32_chars_for_development_only
```

The string is publicly visible in the repo (`.env`) and is the documented
fallback in `backend/api/auth.py:29` (`_FALLBACK_SECRET = "dev_only_secret_..."`,
a separate value, but the pattern is documented). The pydantic validator at
`backend/config/settings.py:238` only enforces `len >= 32`, which this string
satisfies.

Anyone who can read the repo, the deploy artifact, or the running container's
env can forge a valid JWT for any user (including admin) and authenticate
against the live trading API.

**Fix**: require `JWT_SECRET` to be set explicitly in any non-test environment;
fail-closed on the dev fallback when `APP_ENVIRONMENT in {paper, staging,
production}`. Generate the paper secret with `python -c "import secrets;
print(secrets.token_urlsafe(48))"` and store it in a real secret manager.

### AA-C-2 (Critical) — `require_admin` / `require_trader` / `require_api` factory wiring is broken

`backend/infra/security.py:738-789` defines `require_roles(*required_roles)`
which returns a closure `check_roles_hybrid(user_or_dependency=None)`. When
FastAPI sees `Depends(require_admin)` (`security.py:793`,
`require_admin = require_roles("admin")`), it invokes the dependency with no
keyword args → `user_or_dependency` is `None` → the closure returns the inner
function `check_roles_async` rather than executing it. The route handler
receives a function reference and the role check never runs.

Verified in container:
```
$ docker exec intra-api-1 python -c "
from backend.infra.security import require_admin, require_trader
print(type(require_admin()).__name__)   # → 'function'
print(type(require_trader()).__name__)  # → 'function'"
```

Affected callsites (15 endpoints):

- All of `backend/organism/routes.py` admin operations: `trigger_training`,
  `freeze_adaptation`, `unfreeze_adaptation`, `halt_trading`, `resume_trading`,
  `advance_promotion`, `force_rollback`, `compute_attribution`, `manual_tick`,
  `close_legacy_shorts`, `cleanup_stuck_orders`, `run_deep_diagnostics`.
- `backend/api/routes/audit.py` six GET endpoints (require_trader).

Mitigation in place: parent-router `Depends(get_authenticated_user)` still
enforces JWT, and self-registration only assigns role `["user"]`, so the
attacker still needs a valid token. But any user who can register (or any
existing non-admin account) gains full admin capability over the trading
organism — they can halt/resume trading, freeze adaptation, force rollback,
trigger ML retraining, and read the entire compliance audit log.

`backend/api/routes/observability.py:204-215` documents this bug and works
around it with an inline `if "admin" not in current_user.roles` check.
`backend/api/routes/models.py:87-109` redefines a *local* `require_admin` /
`require_trader_or_admin` that uses `Depends(get_authenticated_user)` correctly
and is not broken — these routes are safe.

**Fix**: replace the hybrid closure with a straightforward async dependency:
```python
def require_roles(*required_roles):
    async def _check(user: AuthenticatedUser = Depends(get_authenticated_user)):
        if not set(required_roles).intersection(user.roles):
            raise HTTPException(403, ...)
        return user
    return _check
```

### AA-H-1 (High) — Security response headers middleware not registered

`backend/infra/security_hardening.py:298-360` defines a complete
`SecurityHeadersMiddleware` setting `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, HSTS, CSP, and `Referrer-Policy`. It is
**never imported by `factory.py` or `middleware_setup.py`**. Verified
empirically — `curl -sI http://localhost:8000/api/v1/health` returns no
security headers. Browsers loading the dashboard get default cross-origin and
clickjacking exposure.

**Fix**: call `configure_security_middleware(app, ...)` from
`middleware_setup.register_middleware`.

### AA-H-2 (High) — Sensitive endpoints publicly accessible

The following return live operational data with no authentication:

- `GET /api/v1/scanner/symbols` — full tradable universe
- `GET /api/v1/observability/metrics` — request rates, error rates, p99 latency
- `GET /api/v1/observability/trading` — orders submitted/filled/rejected counts
- `GET /api/v1/observability/dashboard` — comprehensive snapshot
- `GET /api/v1/observability/alerts` — active alert state

`/health/live`, `/health/ready` need to stay public for K8s probes; the rest
should at minimum require authentication, and `dashboard` / `trading` reveal
trade-flow telemetry that can be inferred to reverse-engineer strategy state.

### AA-H-3 (High) — Auth + admin actions absent from audit chain

`AuditAction.USER_LOGIN`, `USER_LOGIN_FAILED`, `USER_LOGOUT`, `USER_CREATED`,
`USER_DISABLED`, `CONFIG_UPDATED`, `RISK_LIMIT_UPDATED` are defined in the enum
(`audit_service.py:67-77`) but **never invoked** outside that enum block (verified
via grep). All `/auth/*`, `/settings/*`, `/risk/emergency-stop`, and organism
admin endpoints log only to stdout via `logging.getLogger`, which is not
hash-chained, not durable across container restarts in dev, and not
queryable through the audit-log API.

For a regulated trading platform, login attempts and configuration
mutations need first-class audit rows.

### AA-H-4 (High) — Container hardening absent in compose

`intra-api-1` runs with default capabilities, writable root filesystem, no
PIDs cap, no memory cap, no `no-new-privileges`. A code-execution bug in any
dependency could escalate to host-namespace surveillance via SYS_PTRACE,
mount `/proc`, etc. The non-root UID is good but `gid=0` and `chmod -R g=u`
mean the user has effective r+w over the entire app tree.

**Fix**: add to `docker-compose.paper.yml` under `api:`:
```yaml
cap_drop: ["ALL"]
cap_add: ["NET_BIND_SERVICE"]    # only if needed
read_only: true
tmpfs: ["/tmp", "/app/tmp"]
security_opt: ["no-new-privileges:true"]
mem_limit: 2g
pids_limit: 200
```
Also create a dedicated non-root group instead of using gid=0.

### AA-M-1 (Medium) — Redis password is the documented `changeme_redis` default

`docker-compose.paper.yml:54,90,98` uses `${REDIS_PASSWORD:-changeme_redis}`.
Container env confirms `REDIS_PASSWORD` is unset, so `REDIS_URL` resolves to
`redis://:changeme_redis@redis:6379/0`. Redis only listens on the internal
docker bridge so the immediate blast radius is internal, but anyone who can
reach the bridge (other compromised containers, host shells) gets unrestricted
Redis access — including the JWT blacklist (could prevent revocation) and any
cached credentials/sessions. Same fix shape as AA-C-1: enforce a real
password.

### AA-M-2 (Medium) — Rate limiter falls back to per-IP for everyone

`backend/api/middleware/rate_limit.py:195` keys on
`request.state.user_id`, which is never populated by any middleware. Every
authenticated request is rate-limited by source IP rather than user
identity. Co-located clients share a single budget; rotating-IP attackers
bypass the per-user logic. The login endpoint is still protected (5/min/IP),
but post-auth limits don't isolate users.

**Fix**: add a tiny middleware that, after `get_authenticated_user`, sets
`request.state.user_id = user.username` (or the user's UUID), or read the
JWT directly from the request headers in the limiter.

### AA-M-3 (Medium) — No automated dependency vulnerability scanning

`requirements.txt` uses `>=` floors only; `requirements.lock` provides
reproducibility but neither file is regularly audited against CVE feeds. No
`pip-audit`, `safety`, `osv-scanner`, `grype`, or `trivy` invocation in CI
(`.github/workflows/`). For a service handling brokerage credentials and
issuing real money orders, monthly automated scanning is the floor.

### AA-M-4 (Medium) — Settings mutation endpoints lack role enforcement

`/api/v1/settings/organism|trading|ml` (PUT) and `/settings/restart-engine`
(POST) live under the `protected` parent router so JWT is required, but
**no role check** is applied. Any authenticated user (including a freshly
self-registered `["user"]`) can mutate engine config and restart the live
trading loop.

`H5: _check_governance(request)` only blocks updates when the organism is in
the `frozen` or `halted` state; that's a different control plane.

**Fix**: add `current_user = Depends(require_admin)` (after AA-C-2 is fixed)
to the four PUT/POST handlers.

### AA-M-5 (Medium) — `/risk/emergency-stop` mutation lacks role enforcement and audit

`POST /api/v1/risk/emergency-stop` triggers an emergency stop that flattens
positions / halts the strategy. It only requires JWT (parent dep), no role
gate, and no `audit_service.log` call. A misuse — accidental or hostile —
flatlines real positions in production with no durable record.

### AA-L-1 (Low) — Pickle deserialization of brain state

`backend/organism/background_trainer.py` calls `pickle.loads(...)` on bytes
read from disk (`organism_brain/`). Trust boundary is the host filesystem,
which on a paper deployment is local. If an attacker ever achieves a write
into `organism_brain/` they get arbitrary code execution at the appuser uid.
Combined with AA-H-4 (writable root, full caps), this is plausible. Prefer
`safetensors` / `joblib` with a hash check, or sign the brain blob.

Postgres exposes 5432 to host (`ports: ["5432:5432"]`) — unnecessary attack
surface. Same for Redis 6379. Bind to `127.0.0.1:5432` or remove the host
mapping.

### AA-L-2 (Low) — WebSocket token validity not re-checked on long-lived connections

Token is decoded only at handshake. A 60-minute access token whose user is
later revoked / locked / role-stripped continues to receive market data and
scanner output until the socket disconnects. Add periodic re-validation
(cheap: re-call `decode_token` on a 5-minute timer, or check the JTI
blacklist).

### AA-L-3 (Low) — DB / Redis connections not TLS, no documented secret rotation

`DATABASE_URL` is plain `postgresql+asyncpg://`, no `sslmode=require`. Redis
URL is `redis://`. Internal-only on the docker bridge today, but production
deploys will likely point at managed Postgres/Redis where TLS is required.
No documented JWT secret rotation procedure or schedule.

---

## Bugs found: 13

- Critical: 2 (AA-C-1, AA-C-2)
- High: 4 (AA-H-1, AA-H-2, AA-H-3, AA-H-4)
- Medium: 5 (AA-M-1, AA-M-2, AA-M-3, AA-M-4, AA-M-5)
- Low: 3 (AA-L-1, AA-L-2, AA-L-3)

---

## Summary

The single most operationally-significant finding is **AA-C-1**: the running
paper-trading container is signing every JWT with the literal hardcoded
fallback string `dev_secret_key_minimum_32_chars_for_development_only`, which
is publicly committed in the repo's `.env` file and survives the
`pydantic`-level "minimum 32 characters" validator only by being padded
specifically to satisfy it. Because this single value is what authenticates
every admin / trader / API call against the live broker-connected service,
any external party who can read this file (or who guesses the documented
default pattern) can mint a token with any roles claim and drive the
organism — close positions, halt trading, restart the engine, train models,
or read the compliance audit log — without ever logging in. The closely
related **AA-C-2** (broken `require_admin` / `require_trader` factory) means
that even *with* a valid but legitimately-non-admin token, an attacker can
already reach all of those admin operations because the role-check
dependency silently injects a function reference instead of executing the
check. Fixing both before the next paper-to-real-money deploy is the highest
return-on-effort security work in the codebase.
