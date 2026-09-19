# Track AA3 v9 — Security Phase 2

V8 AA2 verified wave-23/24 fixes externally and surfaced 3 new findings (closed in wave-32). **AA3 goes a level deeper**: JWT lifecycle, session fixation, CSRF, request smuggling, IDOR / authorization bypass.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`. Container `intra-api-1` running on `:8000`.

## Method

### 1. JWT lifecycle audit

- **Token rotation**: when a user re-logs in, is the old token blacklisted? Does the rate limiter reset? Probe `/login` twice with same creds; check audit_logs for "blacklist" entries.
- **Token expiry math**: forge a token with `exp` 1 second in the future; sleep 5; probe `/api/v1/auth/me`. Expected 401. Verify the +60s clock-skew (`JWT_CLOCK_SKEW`) behaves correctly at the boundary.
- **Refresh token misuse**: take a refresh token, present it as an access token at `/api/v1/auth/me`. Expected 401 (audience mismatch).
- **JWT alg-confusion**: forge a token with `alg=none` or `alg=RS256` (asymmetric). Expected 401.
- **Token blacklist after logout**: POST `/api/v1/auth/logout` with token T; then probe `/auth/me` with T. Expected 401.

### 2. Session fixation

- After login, does the session token (or JWT) change? Does the SAME token remain valid before and after `/login` from a fresh browser session?
- Are there any `Set-Cookie: session=...` headers in responses? If yes, are HttpOnly + Secure + SameSite set?

### 3. CSRF

- Are there any state-mutating endpoints that accept `application/x-www-form-urlencoded` or simple `application/json` without an Origin/Referer check?
- Probe POST /api/v1/admin/trading/halt with an attacker-controlled Origin (`Origin: https://evil.example.com`) and a valid token. CORS should reject (verified in AA2). Verify nothing leaks beyond CORS.

### 4. HTTP request smuggling

Mostly a transport-layer issue, but verify:
- `Content-Length` and `Transfer-Encoding: chunked` together in a single request — does the server return 400, or does it pass through?
- `\r\n\r\n` injection in JWT subject claim — does it break the response stream?

### 5. IDOR / authorization bypass

For each endpoint that takes an entity ID in the path (e.g. `/api/v1/audit/entity/user/{id}`, `/api/v1/positions/{id}`, `/api/v1/lots/{id}`):
- Mint user A's token, GET user B's entity. Expected: 403 OR a filtered response (no leak).
- Specifically test `/api/v1/audit/entity/user/admin@example.com` with a non-admin token. Wave-32 fixed this (AA2-NEW-1) — confirm it's still 403.

### 6. Mass-assignment / over-posting

For endpoints that accept a JSON body (e.g. `POST /api/v1/orders`), submit a body with extra fields (`is_admin: true`, `user_id: 999`, `imported: true`). Verify FastAPI / pydantic schema rejects unknown fields OR strips them silently.

### 7. Header-based auth bypass

- `X-Forwarded-User: admin` in headers — does the server trust it? (Should not.)
- `X-Forwarded-For` with a 192.168.1.1 IP — does it bypass any IP whitelist?
- `X-Real-IP: 127.0.0.1` — does it grant local-only privileges?

### 8. Race-condition: concurrent login + token reuse

Mint 2 tokens from the same login pair concurrently. Are both valid? Are JTIs unique?

### 9. Information disclosure

- 404 vs 401 vs 403 distinction across endpoints — does the server leak existence of resources (e.g. `/users/{nonexistent}` returns 404 but `/users/{exists}` returns 403 → confirms username)?
- Stack traces in 500 responses (wave-32 closed AA2-NEW-2 for malformed JWT, but other 500-paths may leak).

### 10. Dependency CVE re-scan with severity flag

```
./venv/bin/pip-audit -r requirements.txt --strict --skip-editable 2>&1 | head -50
```

Same as V8 AA2; confirms no new CVEs landed.

## Output

`artifacts/audit/v9_reports/track_aa3_security_phase2.md` with per-section probe results, severity-tagged findings, and the standard TL;DR.

Quality bar: 2-5 findings. Critical/High block deploy.
