# Track AA2 v8 — Security Re-Audit + External Probing

V7 wave-23/24 closed AA-C-1 (JWT public default), AA-C-2 (require_roles broken factory), AA-H-3 (login audit gap), and adjacent issues. **AA2 verifies these from outside the running container** + same-class scans for new gaps that the V7 lens missed.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`. Container `intra-api-1` running on `:8000`.

## Method

### 1. External probe of wave-23 fixes (the "did the security actually land" check)

The container is running. Probe from outside:

```
# AA-C-1 — JWT secret should be required, not public-default. Verify by
# trying to forge a token with the V7-era leaked default and confirm 401.
PUBLIC_DEFAULT_SECRET="change-me-in-production"
TOKEN=$(./venv/bin/python - <<'PY'
import jwt, datetime
print(jwt.encode({"sub":"admin","exp":datetime.datetime.utcnow()+datetime.timedelta(hours=1)},
                  "change-me-in-production", algorithm="HS256"))
PY
)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/admin/users
# Expected: 401. If 200 → AA-C-1 still open.

# AA-C-2 — require_roles must reject non-admin tokens. Mint a "user"-role
# token from the live secret (read it from container env, NOT from the
# default), call admin route, expect 403.
LIVE_SECRET=$(docker exec intra-api-1 printenv JWT_SECRET_KEY)
USER_TOKEN=$(./venv/bin/python - <<PY
import jwt, datetime, os
print(jwt.encode({"sub":"user@x","role":"user","exp":datetime.datetime.utcnow()+datetime.timedelta(hours=1)},
                  "$LIVE_SECRET", algorithm="HS256"))
PY
)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $USER_TOKEN" \
  http://localhost:8000/api/admin/trading/halt
# Expected: 403. If 200 → AA-C-2 still open (factory pattern bug).
```

Also probe a sample of 5 admin endpoints (use `grep -rn "require_admin\|require_roles" backend/api/routes/`) to catch any route that imports the factory but uses it incorrectly.

### 2. Same-class scan for new auth gaps

```
# Find any FastAPI router endpoint that does NOT have a Depends(require_*)
# in its signature.
grep -rn "@router\.\(get\|post\|put\|delete\|patch\)" backend/api/routes/ \
  | while read line; do
      file=$(echo "$line" | cut -d: -f1)
      lineno=$(echo "$line" | cut -d: -f2)
      # Check next 10 lines for a Depends(require_)
      sed -n "${lineno},$((lineno+10))p" "$file" | grep -q "Depends(require" \
        || echo "UNGUARDED: $line"
  done
```

Triage: which `UNGUARDED:` are intentional (e.g. /health, /login, /register) vs accidentally public.

### 3. SecurityHeadersMiddleware verification

V7 wave-23 added HSTS / CSP / X-Frame headers. Verify:

```
curl -sI http://localhost:8000/api/health | grep -iE "strict-transport|content-security|x-frame"
```

Expect 3 headers present. Missing → middleware not wired or got reverted.

### 4. CORS posture under wave-23 hardening

```
curl -sI -H "Origin: https://evil.example.com" http://localhost:8000/api/health \
  | grep -i access-control
```

If `Access-Control-Allow-Origin: *` or echoes evil.example.com → CORS misconfig.

### 5. Rate-limit / brute-force re-test

V7 AA-H-? noted login is unrate-limited. Run 50 wrong-password POSTs against /login; confirm whether middleware blocks at N or accepts all 50.

### 6. Secret-scan re-run

```
grep -RnE 'APCA-API-(KEY|SECRET)-KEY|sk_live|BEGIN PRIVATE KEY|JWT_SECRET' . \
  --exclude-dir=.git --exclude-dir=venv --exclude-dir=node_modules \
  --exclude-dir=artifacts --exclude='*.pyc'
```

Any hit in committed code = Critical. Hits in `.env*` ignored if `.gitignore`'d.

### 7. Dependencies CVE scan

```
./venv/bin/pip install pip-audit 2>/dev/null || true
./venv/bin/pip-audit -r requirements.txt --strict 2>&1 | head -40
```

Document Critical/High CVEs. Defer Lows.

## Output

`artifacts/audit/v8_reports/track_aa2_security_re_audit.md` with:
- External probe results (table: endpoint, expected, actual, verdict)
- New unguarded endpoints (if any)
- Headers probe results
- CORS posture
- Login brute-force result
- Secret-scan deltas vs. V7
- CVE table (Crit/High only)
- "Security regressions: N. New findings: N." + TL;DR

Quality bar: 2-5 findings. End with one-paragraph summary. **Critical/High are blockers**; document but do not fix in V8.
