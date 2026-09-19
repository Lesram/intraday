# Track DDD v11 — Dependency Posture (NEW LENS)

pip-audit deep + Dockerfile base-image scan + transitive CVE depth + npm audit. **First-time lens; expect 1-4 findings.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. pip-audit with OSV vulnerability service

```
./venv/bin/pip install pip-audit 2>/dev/null || true
./venv/bin/pip-audit -r requirements.txt --strict --vulnerability-service=osv 2>&1 | tail -50
```

Note any HIGH/CRITICAL CVEs.

### 2. pip-audit with PyPI vulnerability service (default)

```
./venv/bin/pip-audit -r requirements.txt --strict 2>&1 | tail -30
```

V8 AA2 said "no vulnerabilities found." Re-confirm.

### 3. Pinned vs floating

```
grep -E "^[a-zA-Z0-9_-]+>=|^[a-zA-Z0-9_-]+~=|^[a-zA-Z0-9_-]+==" requirements.txt | head -20
```

Audit:
- `>=` (floating) vs `==` (pinned)?
- Critical packages (alpaca-py, sqlalchemy, fastapi, jose, bcrypt) — pinned?

### 4. Docker base image

```
grep "^FROM" Dockerfile
```

Note the base image + tag. If `python:3.12-slim` (no patch version), document as finding (not reproducible).

### 5. Frontend npm audit

```
cd frontend && npm audit --json 2>&1 | head -30
```

Categorize: critical / high / moderate / low.

### 6. Outdated packages (informational)

```
./venv/bin/pip list --outdated 2>&1 | head -20
```

Note any > 1 major version behind.

### 7. Transitive dependency depth

```
./venv/bin/pip list 2>&1 | wc -l
```

Total installed packages. > 200 = supply-chain surface area concern.

### 8. License compliance

```
./venv/bin/pip-licenses 2>/dev/null | head -20
```

Any GPL / AGPL packages incompatible with the platform's license?

### 9. Pre-built wheel vs source

```
grep -E "^https://|^git\+" requirements.txt | head -5
```

Direct git URLs / unpinned source = risk.

### 10. Dependabot / renovate config

Is there a `.github/dependabot.yml` or `renovate.json`?

## Output

`artifacts/audit/v11_reports/track_ddd_dependency_posture.md` with CVE inventory + outdated list + recommended pins.

Quality bar: 1-4 findings.
