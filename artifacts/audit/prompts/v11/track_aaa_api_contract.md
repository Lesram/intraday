# Track AAA v11 — API Contract Audit (NEW LENS)

Every endpoint's auth requirement, error surface, rate-limit, idempotency, request validation. **First-time lens; expect 3-7 findings.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. Endpoint inventory

```
docker exec intra-api-1 curl -s http://localhost:8000/openapi.json | jq '.paths | to_entries | length'
```

Count total paths. V10 reported 197.

```
docker exec intra-api-1 curl -s http://localhost:8000/openapi.json | jq -r '.paths | to_entries | .[] | "\(.key)\t\(.value | keys | join(","))"' | head -30
```

List every path + methods.

### 2. Auth classification

For each path:
- Public (intentional): /system/health, /healthz, /auth/login, /auth/register, /auth/token
- Public (questionable): grep `Depends(get_authenticated_user)` for the route handler
- Admin: should have `Depends(require_admin)`
- Trader: `Depends(require_trader)` (post-wave-32 should be admin-only for audit_logs)

Build a table: path → method → expected_auth → actual_auth → mismatch?

### 3. Idempotency on state-mutating endpoints

POST/PUT/DELETE endpoints should accept an `Idempotency-Key` header (or `client_idempotency_key` in body). Audit:
- /api/v1/orders POST
- /api/v1/admin/trading/halt POST
- /api/v1/positions/import POST

Which honor it?

### 4. Rate-limit per endpoint

```
grep -rn "rate_limit\|@limiter\|RateLimitMiddleware" backend/api/routes/ --include='*.py' | head -15
```

Only login is rate-limited (5/window per V8 AA2). Should other state-mutating endpoints have rate limits? Specifically /admin/trading/* and /organism/halt.

### 5. Request validation strictness

For each pydantic request schema, check:
- `model_config = ConfigDict(extra="forbid")` to reject unknown fields?
- Field constraints (min/max, regex)?

Sample 5 critical schemas (OrderCreate, RiskLimit, OrganismFreeze).

### 6. Error response shape consistency

For 4 different endpoints, deliberately trigger 400, 401, 403, 422, 500. Are response bodies consistent (`{"detail": ...}` vs `{"error": ...}` vs plain text)?

### 7. Pagination defaults + limits

For list endpoints (`/orders`, `/positions`, `/audit/trail`, `/lots`):
- Default `limit` value?
- Max `limit` enforced?
- Cursor vs offset pagination?

Identify any that allow unbounded fetches (DoS via memory).

### 8. Sensitive-data leakage in error responses

Specifically:
- Does a 500 expose stack traces in production env? (Wave-32 closed AA2-NEW-2 for malformed JWTs.)
- Does 400 leak the full request body?
- Does 422 leak schema details that help attackers?

### 9. CORS inheritance

Sub-paths inherit parent's CORS? Verify by probing a sample.

### 10. Versioning

- Are v1 paths frozen?
- Is there a deprecation header on any route?

## Output

`artifacts/audit/v11_reports/track_aaa_api_contract.md` with the full endpoint table + per-section findings.

Quality bar: 3-7 findings. **First-time lens; high yield expected**.
