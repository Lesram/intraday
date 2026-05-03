# Track UU v9 — Error Handling Consistency (NEW LENS)

V8 OO meta-audit observed the cycle has under-invested in the "error handling" finding class. Bare `except Exception: pass`, swallowed errors, and fail-open paths can mask real problems for weeks (V5 S-J3-1 took 4 audit rounds to find). **Track UU systematically catalogs every `except` clause in the codebase and assesses each.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`.

## Method

### 1. Bare-except inventory

```
grep -rn "except:" backend/ --include='*.py' | head -30
grep -rn "except Exception" backend/ --include='*.py' | wc -l
grep -rn "except Exception:" backend/ --include='*.py' | head -30
grep -rn "except Exception as " backend/ --include='*.py' | wc -l
```

Bare `except:` is almost always wrong (catches BaseException, masks SystemExit/KeyboardInterrupt). Find every such site.

### 2. `except Exception: pass` swallowed sites

```
./venv/bin/python - <<'PY'
import ast, pathlib

for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # Check for `pass` body or just-log body.
            if len(node.body) == 1:
                stmt = node.body[0]
                if isinstance(stmt, ast.Pass):
                    print(f"PASS: {p}:{node.lineno}")
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    func = stmt.value.func
                    if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "logger"
                        and func.attr in ("debug", "info")):
                        print(f"LOGONLY-{func.attr.upper()}: {p}:{node.lineno}")
PY
```

For each `PASS:` site, classify:
- **Tier 1 (Critical)**: in tick path, broker path, brain-save path. Silent failure could lose money.
- **Tier 2 (High)**: in audit-log path, alert-dispatch path. Silent failure breaks compliance / alerting.
- **Tier 3 (Medium)**: in scanner / universe / metrics path. Silent failure degrades but doesn't break.
- **Tier 4 (Low)**: cosmetic (e.g. ignoring a `KeyError` on a known-optional dict lookup).

### 3. `except` without specifying type

Find sites that catch overly-broad exceptions where a specific class would be safer:

```
./venv/bin/python - <<'PY'
import ast, pathlib

for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            print(f"BARE-EXCEPT: {p}:{node.lineno}")
PY
```

Each is a finding (bare except).

### 4. Fail-open paths

Identify any path where an exception causes the system to continue with degraded but PERMISSIVE behavior (e.g. a check that's supposed to BLOCK if it can't run, but silently allows on error).

Focus areas:
- Authorization / RBAC (require_admin / require_trader): if claim parsing fails, do we 401 or pass? (Wave-32 closed for malformed UserClaims; verify other checks.)
- Risk gates (max_loss, drawdown, liquidity): if computation fails, do we block or allow?
- Brain restore on startup: if brain is corrupt, do we degrade to fresh state or refuse to start?

### 5. Error-message consistency

For HTTP 4xx/5xx responses, are messages:
- Specific enough for debugging (e.g. "JWT alg=none rejected" vs "invalid_token")?
- Sanitized so no internal state leaks (e.g. file paths, SQL fragments)?
- Consistent across sibling endpoints (admin halt error vs governance halt error)?

### 6. Retry / backoff inventory

For external calls (Alpaca submit, broker WS connect, Postgres connect), enumerate:
- Is there a retry?
- Is the retry exponential or linear?
- Is there a max-retry circuit breaker?
- Is there a deadline (after N seconds, give up)?

### 7. `try` without finally for resource cleanup

For each context manager not used with `async with` / `with`, audit whether cleanup happens on exception:

```
grep -rn "session = " backend/ --include='*.py' | head -10
grep -rn "client = " backend/ --include='*.py' | head -10
```

Look for sites that take a session/client manually and might leak on error.

### 8. Logging consistency

- Are exception logs at ERROR level (or higher) where they should be?
- Are logs structured (logger.warning("Foo failed: %s", exc) vs logger.warning(f"Foo failed: {exc}"))?
- Is there a single canonical "exception happened, log + continue" helper, or 50 ad-hoc copies?

## Output

`artifacts/audit/v9_reports/track_uu_error_handling_consistency.md` with:
- Total `except` clause count + breakdown by type
- Tier 1 / Tier 2 swallowed-exception findings (the dangerous ones)
- Bare-except findings
- Fail-open findings
- Retry / backoff inventory
- Recommended canonical pattern (proposal for V10 to enforce via lint rule)

Quality bar: 2-5 findings. End with one-paragraph TL;DR. **Tier 1 swallowed exceptions are blockers**; document but do not fix in V9.
