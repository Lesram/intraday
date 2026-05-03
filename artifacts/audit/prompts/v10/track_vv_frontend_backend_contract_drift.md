# Track VV v10 — Frontend/Backend Contract Drift (NEW LENS)

V8 OO recommended this lens; V9 didn't ship it. **VV inventories every FastAPI route's pydantic schema and cross-references against TypeScript types in the frontend** to catch drift that breaks the UI.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

## Method

### 1. Frontend type-source inventory

```
find frontend -type d -name "types" -o -name "interfaces" 2>/dev/null | head
ls frontend/src/types/ 2>/dev/null || ls frontend/src/ | head
find frontend/src -name "*.ts" -o -name "*.tsx" | head -20
```

Identify where frontend types live (types/, interfaces/, generated/). If there's a generated OpenAPI client, record its location and freshness.

### 2. OpenAPI freshness

```
docker exec intra-api-1 curl -s http://localhost:8000/openapi.json | jq '.paths | keys | length'
```

Count paths. Compare to last-generated frontend client (if applicable).

### 3. Pydantic schema inventory

```
./venv/bin/python - <<'PY'
import ast, pathlib

schemas = []
for p in pathlib.Path("backend/api/routes").rglob("*.py"):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "BaseModel":
                    fields = [
                        s.target.id for s in node.body
                        if isinstance(s, ast.AnnAssign)
                        and isinstance(s.target, ast.Name)
                    ]
                    schemas.append((p.name, node.name, fields))

for path, name, fields in schemas[:40]:
    print(f"{path}::{name}: {fields[:8]}")
PY
```

### 4. Cross-reference: top 20 routes

For each of the top 20 routes (orders, positions, audit, settings, etc.):
- Pull the pydantic response schema from FastAPI source.
- Pull the frontend's TS interface for the same route.
- Diff fields.

If frontend types are auto-generated from OpenAPI, this should be clean — but verify the generation step has been run since wave-49.

### 5. WebSocket contract

The platform uses Socket.IO and/or raw WebSockets. For each event type:
- What fields does the backend emit?
- What does the frontend listen for?
- Are there any silently-renamed fields?

### 6. Enum drift

For each Python enum exposed in API responses (`OrderStatus`, `Side`, `AuditAction`, etc.):
- List the values.
- Cross-check the frontend's TS enum (or string-literal type) for the same values.
- Drift = missing value on either side.

### 7. Field rename rate-of-change

Walk recent commits to backend/api/routes/ and look for renamed pydantic fields. Each rename without a corresponding frontend change = drift.

```
git log --since=6.month --oneline --diff-filter=M -p -- backend/api/routes/ \
  | grep -E "^[+-].*: " | head -30
```

### 8. Backwards-compatibility audit

When the backend renames a field (e.g. `pnl` → `realized_pnl`), is there a transition period where both are emitted? Or is it a hard cutover?

### 9. Error response format drift

Are HTTP errors (4xx/5xx) consistently structured?
- `{"detail": "..."}` (FastAPI default)
- `{"error": "...", "code": ...}` (custom)
- Plain text

Drift here breaks frontend error rendering.

### 10. CORS allowed-origins drift

The backend's CORS config (`CORS_ORIGINS` env var or hardcoded list) must match the frontend's deployment URL. Verify alignment.

## Output

`artifacts/audit/v10_reports/track_vv_frontend_backend_contract_drift.md` with:
- Frontend type source location
- OpenAPI freshness vs frontend
- Top-20 route schema diffs
- WebSocket contract review
- Enum drift findings
- Recent renames vs frontend status
- Error format consistency

Quality bar: 2-5 findings. **First-time lens; expect ~5 first-round findings**.
