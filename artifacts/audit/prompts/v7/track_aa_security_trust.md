# Track AA v7 — Security & Trust Audit (NEW SURFACE)

V3 Track I touched API auth in 3 findings. V7 Track AA does the first
**comprehensive security audit** of the platform: authentication,
authorization, secrets management, injection, supply chain, TLS,
audit trail.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Files in scope

- `backend/infra/security.py` — JWT, auth dependencies
- `backend/api/routes/*.py` — every protected route
- `backend/api/middleware/` — request/response middleware
- `backend/database/scheme.py` (or equivalent) — User model, roles
- `backend/services/auth*.py`
- `requirements.txt` + `requirements-dev.txt` — dependency scan
- `Dockerfile` + `docker-compose.*.yml` — runtime hardening
- `.env`, `.env.example` — secrets handling
- All HTTP client constructions (alpaca, slack, postgres connection strings)

## Method

### 1. Authentication audit

- **JWT secret strength**: minimum length? default vs override? rotation policy?
- **Token lifetime**: `JWT_EXPIRE_MINUTES` default. Refresh token semantics.
- **Algorithm pinning**: `algorithms=["HS256"]` enforced on decode (prevents alg=none attack)?
- **Subject claim handling**: any path where a malformed `sub` claim could escalate?
- **Replay protection**: are tokens single-use anywhere they should be?
- **Login lockout**: failed_login_attempts column exists; is it actually enforced?
- **Password storage**: bcrypt/argon2/scrypt? Cost factor? salt handling?
- **Password reset flow** (if any): single-use token? expiry? email-verified?

### 2. Authorization audit

- For every route, classify: public / authenticated / role-required.
- Re-test V3 I-1/I-2/I-3 fixes are still in place.
- **IDOR**: any route taking `user_id` / `account_id` / `order_id` as a path/query param without checking ownership against the JWT subject?
- **Privilege escalation**: any path where a regular user could trigger admin behavior?
- **Mass assignment**: any Pydantic model with `extra="allow"` that takes too many fields?
- **Role check uniformity**: `Depends(require_admin)` vs `Depends(get_authenticated_user)` + inline check — any inconsistencies?

### 3. Secrets management

- `grep -rn "api_key\|secret_key\|password\|token" backend/ --include="*.py"` — any hardcoded?
- `.env.example` checked into repo with placeholder values? `.env` gitignored?
- Are secrets ever logged? grep `logger.*api_key|logger.*secret|logger.*token` in error/exception paths.
- Secrets in Docker layers (`docker history`)?
- `JWT_SECRET_KEY` minimum length: enforced?
- Database password complexity: enforced?

### 4. Injection vulnerabilities

- **SQL injection**: every raw `text(...)` or string-formatted SQL query — find via `grep -rn 'text(\|f".*SELECT\|"SELECT.*{' backend/`. Is every parameter parameterized?
- **Command injection**: any `subprocess.run` / `os.system` / `shell=True`? Inputs sanitized?
- **JSON deserialization**: any `pickle.loads` or `yaml.unsafe_load` on untrusted input?
- **Path traversal**: any `Path(...) / user_input` without validation?

### 5. CORS / CSRF / headers

- `APP_CORS_ORIGINS` value — wildcard? specific origins?
- CSRF protection on state-mutating routes (FastAPI default: header-based auth, no CSRF needed for JWT-in-header; but if cookie-based, CSRF required).
- Security headers: HSTS, X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy.
- Where do they come from? FastAPI middleware? `python-secure`?

### 6. Rate limiting

- Login endpoint: rate-limited?
- State-mutating routes: rate-limited?
- Per-user vs per-IP?
- `slowapi` / `fastapi-limiter` in requirements?

### 7. WebSocket auth

- WS routes (scanner, market-data) — token in query param? header? upgrade-time check?
- Token validity re-checked on long-lived connection? Or just at handshake?
- WS message validation — schema? size limits?

### 8. Supply chain / dependency scanning

- `requirements.txt`: count direct deps. Run `pip list --outdated` (read-only).
- Known CVEs: pip-audit (if available) or grep against advisory feeds.
- Pin specificity: `>=` vs `==`? Floor pins are CVE-vulnerable as upstream releases new versions.
- `requirements-dev.txt` deps don't ship to prod, but check Dockerfile to confirm.

### 9. TLS / network

- Outbound HTTP calls: `verify=False` anywhere? grep for `httpx.AsyncClient` constructors.
- DB connection: TLS configured? `sslmode=require` in DATABASE_URL?
- Redis: TLS configured? `rediss://`?
- Slack/webhook URLs: HTTPS-only?

### 10. Audit log / non-repudiation

- Are auth events (login, logout, failed login, password change) logged with timestamp + user + IP?
- Are admin actions (settings changes, kill-switch) logged?
- Is the audit log tamper-evident? Append-only?
- Retention policy?

### 11. Container / runtime hardening

- Dockerfile: USER directive (running as non-root)?
- Capabilities dropped (`docker-compose: cap_drop`)?
- Read-only root filesystem?
- Resource limits (memory, CPU)?
- Network isolation?

### 12. Sensitive endpoint inventory

For each endpoint that performs a state-mutating or sensitive action,
verify auth + audit log:

| Route | Auth | Role | Audit log |
|---|---|---|---|
| POST /auth/login | none | n/a | needed |
| POST /auth/logout | bearer | n/a | needed |
| POST /positions/{symbol}/close | bearer | trader | needed |
| PUT /governance/halt | bearer | admin | needed |
| ... |

## Output

`artifacts/audit/v7_reports/track_aa_security_trust.md` with:
- 12 sections per the method
- Endpoint × auth × role × audit-log matrix
- "Bugs found: N" by severity (Critical / High / Med / Low)
- TL;DR

## Constraints

- Read-only. `curl` (no auth bypass attempts beyond reading public surface).
- No actual exploit attempts.
- `pip list` ok; do not modify env.

## Quality bar

This is the first deep security audit. Expect 8-15 findings. Especially:
- A secret with too low entropy / default value
- Outbound HTTP with TLS verification off
- A route missing role check
- Logged-but-unredacted PII or token
- Container running as root

End with a one-paragraph summary including the most operationally-significant
finding.
