# Track AA4 v10 — Security Phase 3

V9 AA3 closed JWT lifecycle holes (logout blacklist, token_type gate, refresh single-use). **AA4 drills into NEW edges**: replay protection across restarts, RBAC depth at endpoint level, signed-URL gaps, API-key vs Bearer interaction.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`. Container `intra-api-1` running on `:8000`.

## Method

### 1. Token replay across container restart

V9 AA3-1 wired blacklist_token to logout. But:
- Is the blacklist BACKEND Redis-only, or in-memory fallback?
- If Redis-only, what happens on Redis restart? Are blacklist entries lost?
- If in-memory only, what happens on container restart? Same.
- Probe: get a token, logout, restart container, retry the token. Should still 401.

### 2. JWT replay window — clock-skew abuse

Wave-47 AA3-4 added `leeway=60` to `jwt.decode`. Verify:
- A token issued NOW with `exp = now + 60s` is rejected after 121s (60s exp + 60s leeway = 120s).
- A token with `nbf = now + 30s` is accepted now (within 60s leeway window).
- Probe with carefully-crafted exp/nbf values.

### 3. RBAC depth — admin endpoints accept TIER bypass?

V8 AA2-NEW-1 (wave-32) closed audit-trail trader bypass. V9 AA3 didn't re-test the entire admin surface. Probe each endpoint with each role:
- `/admin/trading/*` — admin only?
- `/admin/users/*` — admin only?
- `/organism/halt`, `/organism/freeze`, `/organism/promote`, `/organism/rollback`, `/organism/save` — admin only?
- `/audit/*` — admin only? (post-wave-32)
- `/settings/organism`, `/settings/trading` — admin only?

For each, mint user/trader/admin tokens and probe; document who CAN access vs SHOULD access.

### 4. Signed-URL gaps

For artifact downloads (audit exports, brain backups, etc.):
- Are URLs signed?
- TTL?
- Do they leak in logs / error responses?
- Probe `/api/v1/audit/export` with a non-admin token — does the response leak data?

### 5. API-key vs Bearer interaction

V9 AA3 didn't test API-key path post-wave-42. Verify:
- Does X-API-Key still work (per AA2 verification)?
- Does presenting BOTH X-API-Key + Bearer prefer one? Which? Is that secure?
- Does X-API-Key respect role-gates?

### 6. CSRF / Origin enforcement on state-mutating endpoints

V8 AA2 confirmed CORS rejects evil origins on preflight. But:
- Do POST endpoints check `Origin` / `Referer` independently?
- Probe POST with `Origin: https://evil.example.com` AND a valid token.

### 7. Mass-assignment regression

V8 AA2 said pydantic strips unknown fields. Re-verify on a few specific routes that take BOTH user-mutable AND admin-mutable fields:
- `PATCH /api/v1/users/{id}` (if exists) with `is_admin=true` from non-admin token.

### 8. Rate-limit interaction with admin paths

V8 AA2 verified login is rate-limited (5/window). Are admin endpoints rate-limited?
- Probe 50 rapid `GET /admin/users` — do they all 200?

### 9. Audit-log of failed auth probes

V9 wave-41 UU-2 surfaced auth audit-log rollback failure. Verify the AUDITS LANDED:
- Probe with bad creds; check `audit_logs` for `user.login_failed` entries via DB SELECT.

### 10. Dependency CVE re-scan

```
./venv/bin/pip-audit -r requirements.txt --strict 2>&1 | head -30
```

## Output

`artifacts/audit/v10_reports/track_aa4_security_phase3.md` with per-section probe results, severity-tagged findings, TL;DR.

Quality bar: 1-4 findings.
