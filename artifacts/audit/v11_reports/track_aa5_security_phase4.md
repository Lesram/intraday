# Track AA5 v11 — Security Phase 4

- **Date**: 2026-05-03 (UTC ~18:40)
- **Branch / commit**: `main` (working tree contains rc-1.5-curated content) @ `3778344`
  - Note: prompt specified branch `rc-1.5-curated` @ `11c2275`/`3778344`. Repo HEAD reports `main`, but `/app/backend/infra/security.py` line count and recent fixes (wave-47, wave-50, wave-59) match the post-fix tree, confirming the freshly built image is exercising the intended code.
- **Container**: `intra-api-1` healthy; image `intra-api:latest` built `2026-05-03T18:29:02Z` (≈10 min before audit), running as `appuser`, exposing only 8000.
- **Probe scope**: read-only on prod DB; ephemeral logins and one logout against the running API; no writes.

## TL;DR

| # | Severity | Finding |
|---|----------|---------|
| AA5-1 | **CRITICAL** | Wave-47 `leeway=JWT_CLOCK_SKEW` kwarg is incompatible with `python-jose 3.5.0`. `decode_token()` raises `TypeError` on every call → caught by the bare `except Exception:` → 401 `invalid_token`. Effect: **every JWT-authenticated endpoint is broken** in the freshly-built image. AA4-1 logout/blacklist gate cannot even be re-tested because no token survives one hop. |
| AA5-2 | **HIGH** | Wave-47 regression test (`tests/test_wave47_fixes.py::test_aa3_4_jwt_decode_passes_leeway`) is a **source grep**, not a behavioral test. It asserts the literal string `"leeway=JWT_CLOCK_SKEW"` appears in `security.py` and never actually decodes a JWT. The bug in AA5-1 sails through CI as green. Several other wave-47/50/59 tests in this file have the same pattern. |
| AA5-3 | **MEDIUM** | Login rate-limit (`/api/v1/auth/login`, 5/min) is keyed `ip:<ip>:<path>` because `request.state.user_id` is **never populated by any middleware** (`grep -rn 'request.state.user_id' backend/` returns 0 hits). Effect: per-user fairness claim is false; corporate NAT or shared-IP bypasses one user via another's quota. The rate-limit middleware retains a `user:{user_id}:{path}` branch that is unreachable. |
| AA5-4 | **LOW / INFO** | Audit log only emits `user.login` and `user.login_failed`. No `user.logout`, no `auth.token.refresh`, no `order.placed`, no `order.filled`. Wave-42 logout blacklists the jti but does not append an audit row. Wave-52 `ORDER_FILLED` emission claim is unverifiable from the data (entirely consistent with no orders + auth being broken, but should be re-validated once AA5-1 is fixed). |

---

## 1. AA4-1 deploy gate re-probe — BLOCKED by AA5-1

Container line count matches host (`941`), so the wave-50 source IS in the image. But the gate cannot be re-verified because **logout cannot be exercised end-to-end**:

```
$ ACCESS=<fresh login token>
$ curl -H "Authorization: Bearer $ACCESS" /api/v1/auth/me
HTTP 401  {"detail":"Authentication required"}
```

A token returned by `/auth/login` 200 OK is rejected by `/auth/me` ~50 ms later. The same token is rejected at `/positions`, `/organism/status`, `/auth/me` — every route guarded by `get_current_user` / `get_authenticated_user`.

Reproduction inside the container:

```python
docker exec intra-api-1 python3 -c "
from backend.infra.security import decode_token
import os, time
from jose import jwt
secret = os.environ['SECURITY_JWT_SECRET']
tok = jwt.encode(
  {'sub':'a','roles':['admin'],'iss':'algotrading-platform','aud':'algotrading-api',
   'exp':int(time.time())+3600,'iat':int(time.time()),'jti':'x','token_type':'access'},
  secret, algorithm='HS256')
print(decode_token(tok))
"
# → HTTPException 401: invalid_token
```

Direct cause:

```python
docker exec intra-api-1 python3 -c "
import os; from jose import jwt
jwt.decode(<tok>, os.environ['SECURITY_JWT_SECRET'],
           algorithms=['HS256'],
           issuer='algotrading-platform', audience='algotrading-api',
           leeway=60)
"
# → TypeError: decode() got an unexpected keyword argument 'leeway'
```

`python-jose 3.5.0`'s `jwt.decode` signature is `(token, key, algorithms=None, options=None, audience=None, issuer=None, subject=None, access_token=None)` — no `leeway` parameter. The python-jose project tracks this in their option dict (`options={'leeway': N}`), not as a kwarg. (PyJWT exposes `leeway=` as a kwarg; the wave-47 author likely confused the two libraries.)

`decode_token()`'s catch-all (`except Exception:`) at line 629 swallows the `TypeError` and raises 401 `invalid_token`, which is why nobody saw a 500 stack trace.

**Severity: CRITICAL**. The platform paper-traded successfully because the trading loop runs server-side and doesn't go through HTTP auth — but every operator/UI/automation surface is dead. AA4-1 (token revocation) cannot be tested because the prerequisite (a working bearer token) doesn't exist.

**Fix**: replace `leeway=JWT_CLOCK_SKEW,` with `options={...other..., "leeway": JWT_CLOCK_SKEW}` OR move to PyJWT. Add an actual behavioral test (next finding).

## 2. Wave-47 test is fake-positive

`tests/test_wave47_fixes.py:74-80`:

```python
def test_aa3_4_jwt_decode_passes_leeway():
    """decode_token must pass JWT_CLOCK_SKEW as leeway= to jwt.decode."""
    src = Path(...).read_text()
    assert "leeway=JWT_CLOCK_SKEW" in src, (
        "AA3-4 regression: JWT_CLOCK_SKEW is dead code again — ..."
    )
```

The test asserts the **literal source string is present**, not that `decode_token()` actually decodes a token. An equivalent behavioral test would be:

```python
def test_decode_token_round_trip():
    tok = create_access_token(...)
    claims = decode_token(tok)  # currently raises 401
    assert claims['sub'] == ...
```

Several other tests in this file follow the same anti-pattern (text assertions on source). Reviewer note: this is the second wave (after wave-23b's silent-role-loss bug) where a fix shipped behind a green test that didn't actually exercise the changed path. Recommend **a CI guard** that flags new tests using `Path(...).read_text()` + `assert "..." in src` — these are change-detector tests, not regression tests.

**Severity: HIGH** (process; no exploitability on its own, but it directly enabled AA5-1 to ship into a fresh build undetected).

## 3. Login rate-limit is per-IP only, not per-user

`backend/api/middleware/rate_limit.py:194-201`:

```python
user_id = getattr(request.state, "user_id", None)
if user_id:
    key = f"user:{user_id}:{path}"
else:
    client_ip = request.client.host if request.client else "unknown"
    key = f"ip:{client_ip}:{path}"
```

Search confirms the `user:` branch is **dead code**:

```
$ grep -rn "request.state.user_id\|state\.user_id" backend/
(no output)
```

Nothing in the request pipeline assigns `request.state.user_id`. `get_current_user` returns an `AuthenticatedUser` to the route function; it does not stash anything on `request.state`. Therefore:

- Every request — authenticated or not — is rate-limited by IP-and-path.
- `/auth/login` (5/min) is necessarily IP-keyed (no user yet), but post-auth `/orders`, `/portfolio`, etc. are also IP-keyed despite the code looking like it would be per-user.
- Effect on auth: a NAT'd or shared-IP attacker burns the 5/min quota and locks out everyone behind that IP. Since there are 3 users (admin@example.com, monitor@local.dev, test_audit_…) and only one observed login source (192.168.65.1, the Docker host bridge), the practical exposure is small **today**, but the code reads as if per-user fairness exists.

**Severity: MEDIUM**. Fix: in `get_current_user` (or a thin auth middleware), set `request.state.user_id = claims.sub` on success. Add an integration test that two users on the same IP do not share quota.

## 4. Audit log emission gaps

`audit_logs` table since rebuild (≈10 min): 352 total rows (291 historical), recent additions only `user.login` (148 since rebuild) and `user.login_failed` (8). No row exists for any of:

- `user.logout` — wave-42 logout blacklists the jti but doesn't write an audit row. The blacklist is in Redis/memory, not in the chain-of-custody table.
- `auth.token.refresh` — refresh path doesn't emit either.
- `order.placed`, `order.filled` — wave-52's claimed `ORDER_FILLED` emission produced zero rows. Two possible reasons: (a) no orders placed in this window, (b) auth-broken state means the order endpoint is unreachable from operator/UI side. The trading-loop path is server-internal so ought to emit regardless of HTTP auth — re-check after AA5-1 is fixed.
- `system.startup`, `governance.*` — not present.

`hash_chain` is non-null on all 352 rows (no missing-hash gaps). Chain integrity itself is intact for what's there. The concern is **completeness**, not integrity.

**Severity: LOW / INFO** (no compliance regime is being claimed; flag for the audit-coverage roadmap).

---

## Sections probed but no finding

- **Image surface (Section 4)**: runs as non-root `appuser`, only port 8000 exposed, no secrets in `Config.Env` (only `GPG_KEY` from base image, which is the Debian repo signing key not a runtime secret). Image size 1.96 GB is on the larger side for a slim base — review opportunity, not a security finding.
- **Supply chain (Section 5)**: `pip-audit -r requirements.txt --strict` → `No known vulnerabilities found`. Base image `python:3.12-slim` (Debian-based) — current; no advisories at audit time.
- **Secrets-in-env (Section 3)**: All sensitive values present in container env (`JWT_SECRET_KEY`, `JWT_SECRET`, `SECURITY_JWT_SECRET` — three names sharing the same secret value; `ALPACA_API_*`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD=admin`). This is expected for `env_file: .env` paper deploys; visible to any process in the container's PID namespace via `/proc/<pid>/environ`. Two minor cleanliness notes (not raised as findings): (a) three env-var aliases for the JWT secret invite drift if one is rotated and others aren't; (b) `GRAFANA_ADMIN_PASSWORD=admin` is the default — if Grafana is reachable from outside the host, that's a separate finding outside this track.
- **CSRF / forged Origin (Section 7)**: `OPTIONS /api/v1/risk/emergency-stop` with `Origin: https://evil.example.com` returns **400 Bad Request** (CORSMiddleware rejects the preflight cleanly). Direct POST without preflight returns 401 (auth gate, currently broken-but-still-rejecting). No browser-side CSRF surface observed beyond the standard CORS posture.
- **JWT-in-URL leakage (Section 8)**: two matches — both intentional WebSocket auth via query string (`/ws?token=YOUR_JWT_TOKEN`) since browsers can't set headers on WS upgrades. Logging hygiene was not deeply validated; recommend a follow-up that greps access-log middleware to confirm `?token=...` is redacted (out of scope for this phase).
- **Multi-tenancy (Section 2)**: 3 users exist. Cross-tenant probing **could not be performed** because AA5-1 makes every authenticated request return 401 — no token can be exchanged for resource access. Code review of `routes/orders.py:88` shows orders are scoped `Order.user_id == user.username OR == "system"`, which is sound *if* `user.username` resolves to the real authenticated identity. Re-probe after AA5-1 is fixed.
- **New attack surface from waves 50-65 (Section 10)**: scanned route diff during prep — no net-new external endpoints; waves 50/52/59 are defensive fixes (env coercion, audit emission scaffolding, api_keys getattr). Nothing introduced that needs new threat-modeling beyond what's already in this report.

## Recommended remediation order

1. **AA5-1 immediate**: revert `leeway=JWT_CLOCK_SKEW` → `options['leeway'] = JWT_CLOCK_SKEW` (one-line fix, then rebuild). Re-run AA4-1 logout/blacklist probe afterwards.
2. **AA5-2 same PR**: replace the source-grep test with a real round-trip test, `create_access_token → decode_token → assert claims`. Audit `tests/test_wave47_fixes.py` for other source-grep tests in the same file and convert.
3. **AA5-3 next sprint**: assign `request.state.user_id` in `get_current_user`. Backfill an integration test for shared-IP users + separate quotas.
4. **AA5-4 backlog**: extend audit emission (logout, refresh, order lifecycle). Will compose with AA5-1 fix because emissions need a working auth path to be testable end-to-end.

