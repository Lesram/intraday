# Track AA5 v11 — Security Phase 4

V10 AA4 closed 4 security findings. **AA5 drills deeper**: supply chain, container image, multi-tenancy, secrets-in-env, deeper auth probes against the FRESHLY-REBUILT container.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`. Container `intra-api-1` running freshly-built image (post wave 50-65).

## Method

### 1. Re-probe AA4-1 deploy gate (now should be CLOSED)

The container was rebuilt today — verify:
- `docker exec intra-api-1 wc -l /app/backend/infra/security.py` ≈ host (934).
- `/auth/logout` actually blacklists tokens now.
- Refresh tokens rejected at admin endpoints.
- Post-logout token: try `curl -H "Authorization: Bearer <revoked>" /api/v1/auth/me` → expect 401.

If these still fail, V10 wave-50 fix didn't actually deploy.

### 2. Multi-tenancy probe

If multiple users exist:
- Mint user A's token, request user B's resources (`/positions`, `/orders`, `/audit/entity/user/B@`).
- Expect: 403 or empty result, NOT user B's data.

If only `admin@example.com` exists, this is a single-tenant setup; document as INFO.

### 3. Secrets-in-env scan inside the container

```
docker exec intra-api-1 env | grep -iE 'secret|key|token|password' | head -20
```

Identify any plaintext secrets that would be visible to a process introspecting `/proc/<pid>/environ`. Specifically look for:
- `JWT_SECRET_KEY` value (should be set, but not in logs)
- Database password
- Alpaca API keys
- Slack webhook URL

### 4. Container image surface

```
docker image inspect intra-api:latest | jq '.[0] | {Architecture, Os, Size, Created, Config: {Env: .Config.Env, ExposedPorts: .Config.ExposedPorts, User: .Config.User}}' | head -40
```

Check:
- Image runs as root or non-root user?
- Exposed ports include only 8000?
- Env vars don't leak secrets?

### 5. Supply chain: pip-audit + base image

```
./venv/bin/pip-audit -r requirements.txt --strict 2>&1 | tail -30
```

Then check Dockerfile base image:
```
grep "^FROM" Dockerfile | head -3
```

If `python:3.12-slim` or similar, note the version. Outdated base = potential CVE.

### 6. Rate-limit fairness

V8 AA2 verified login is rate-limited. Verify per-user fairness:
- User A burns through 5/window login attempts → blocked.
- Does user B's login (same IP) also get blocked? (Should NOT — rate limit should be per-user not per-IP.)
- Probe the actual implementation in `backend/api/middleware/rate_limit.py`.

### 7. CSRF protection on state-mutating endpoints

V8 AA2 confirmed CORS rejects evil origins. But does the backend validate `Origin` / `Referer` independently for state-mutating routes?
- POST `/api/v1/admin/trading/halt` with `Origin: https://evil.example.com` and a valid token.
- Expected: rejected even with valid token.

### 8. JWT-in-URL leakage

Check the codebase for any place that puts a JWT in a URL (logged, redirected):
```
grep -rn "redirect.*token\|url.*token=\|?token=" backend/ --include='*.py' | head -10
```

### 9. Audit log integrity post-deploy

Re-verify hash chain since wave-52 added ORDER_FILLED emissions:
```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), MAX(ts) FROM audit_logs;"
```

Compare to pre-rebuild count. Should have grown if any auth events fired since restart.

### 10. New attack surface introduced by wave 50-65

Any new endpoints, headers, or authentication paths added that need security review?

## Output

`artifacts/audit/v11_reports/track_aa5_security_phase4.md` with per-section probe results, severity tags, TL;DR.

Quality bar: 1-4 findings.
