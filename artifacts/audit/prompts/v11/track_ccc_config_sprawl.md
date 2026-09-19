# Track CCC v11 — Configuration Sprawl (NEW LENS)

Env-var inventory + .env vs settings.py vs docker-compose drift + secrets handling. **First-time lens; expect 2-5 findings.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. Env-var reference inventory

```
grep -rEho "os\.(getenv|environ\.get|environ\[)['\"]([A-Z_]+)['\"]" backend/ --include='*.py' | grep -oE "[A-Z_]+" | sort -u | head -50
```

Build the full set of env vars referenced in code.

### 2. settings.py inventory

```
grep -nE "^[ ]*[a-z_]+:.*Field\b\|^[ ]*[a-z_]+:.*=.*os\.getenv\b\|^[ ]*[a-z_]+_url" backend/config/settings.py backend/config/base_settings.py 2>/dev/null | head -30
```

Identify every settings field.

### 3. .env / docker-compose / settings cross-reference

For each env var in the inventory:
- Is it in `.env` (or `.env.example`)?
- Is it in `docker-compose*.yml`?
- Is it in `settings.py`?
- Drift = referenced in code but missing from one or more above.

### 4. Secrets handling

Look for:
- Plaintext secrets committed to repo (.env, configs).
- Secrets in docker-compose.yml (vs docker secrets / vault).
- Secrets in env that are visible via `docker exec env`.

```
grep -rEn "(sk_live|APCA-API-(KEY|SECRET))-?KEY|BEGIN PRIVATE KEY|password\s*[:=]\s*['\"]" \
  backend/ docker-compose*.yml --include='*.py' --include='*.yml' --exclude-dir=venv
```

### 5. Default-value policy audit

For every settings field:
- Sensible default?
- Production-safe default? (e.g. JWT_SECRET should NOT default to "change-me-in-production").
- env-required (no default) for security-critical keys?

V7 wave-23 closed AA-C-1 (JWT secret default-published). Are there others?

### 6. Configuration validation at startup

Does `lifespan.py` (or equivalent) validate critical env vars before starting trading? E.g. ALPACA_API_KEY_ID, JWT_SECRET_KEY.

If trading starts with missing keys, document as finding.

### 7. Hot-reload / config-change handling

Can config be changed at runtime? If yes, what's reloaded? If no, what's the redeploy path?

### 8. Multiple compose files drift

```
diff -u docker-compose.yml docker-compose.paper.yml | head -40
```

Drift between compose files = forks of truth. Document any drift that affects the audit cycle (e.g. paper vs prod env vars).

### 9. ENV vs settings.py.value priority

If both an env var AND a settings.py default exist, who wins? Is this consistent across 5+ sample fields?

### 10. Documentation freshness

Is there a `docs/configuration.md` or similar? Is it current (mentions all env vars in inventory)?

## Output

`artifacts/audit/v11_reports/track_ccc_config_sprawl.md` with inventory diff + findings.

Quality bar: 2-5 findings.
