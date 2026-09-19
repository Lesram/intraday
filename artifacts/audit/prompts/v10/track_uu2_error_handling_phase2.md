# Track UU2 v10 — Error Handling Phase 2

V9 UU found 4 findings (2 Tier 1 closed in wave-41). Wave-49 deferred UU-4 (cargo-cult try/except) to V10 lint rule. **UU2 designs the lint rule + retroactively scans remaining swallow sites for any not yet identified.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

## Method

### 1. Re-run V9 UU census post-waves 41-49

```
./venv/bin/python - <<'PY'
import ast, pathlib

total_handlers = 0
pass_only = []
log_only_debug = []
broad_exception = 0
bare_except = 0

for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            total_handlers += 1
            if node.type is None:
                bare_except += 1
            elif (isinstance(node.type, ast.Name)
                  and node.type.id == "Exception"):
                broad_exception += 1
            if len(node.body) == 1:
                stmt = node.body[0]
                if isinstance(stmt, ast.Pass):
                    pass_only.append(f"{p}:{node.lineno}")
                elif (isinstance(stmt, ast.Expr)
                      and isinstance(stmt.value, ast.Call)):
                    func = stmt.value.func
                    if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "logger"
                        and func.attr in ("debug", "info")):
                        log_only_debug.append(
                            f"{p}:{node.lineno} ({func.attr})"
                        )

print(f"Total handlers: {total_handlers}")
print(f"Bare except: {bare_except}")
print(f"Broad Exception: {broad_exception}")
print(f"Pass-only: {len(pass_only)}")
print(f"Log-debug/info-only: {len(log_only_debug)}")
print()
print("PASS-ONLY SITES:")
for s in pass_only[:30]:
    print(f"  {s}")
print()
print("LOG-DEBUG/INFO-ONLY SITES:")
for s in log_only_debug[:30]:
    print(f"  {s}")
PY
```

V9 UU census reported: 1487 handlers, 0 bare, 161 pass-only.
After waves 41-49 fixes: re-count. Expected: pass-only count REDUCED by N where N is the sites we fixed (UU-1, UU-2, UU-3, plus collateral from PP-3 / DD-* paths).

### 2. Tier the remaining pass-only sites

For each remaining `except Exception: pass` site, classify:
- **Tier 1**: trading-path / brain-save / broker-path. Silent failure could lose money.
- **Tier 2**: alert / audit / metrics path.
- **Tier 3**: cosmetic (e.g. ignoring a file-stat call that may not exist).

### 3. Design the V11 ruff lint rule

Propose a config that:
- Flags `try/except Exception: pass` blocks where the wrapped body has > 1 statement (likely doing real work that could mask failure).
- Allows blocks with `# noqa: UU-4` or a comment explaining why.
- Flags `try/except: pass` (bare) always.
- Flags `try/except Exception as e: pass` always (even worse — captures the exception then drops it).

Output the proposed `pyproject.toml` ruff config snippet.

### 4. Identify "fail-open" patterns in waves 41-49

The new code added in waves 41-49 should NOT introduce new fail-open paths. Audit:
- Wave-41 brain-save: any `except: pass` we added?
- Wave-42 JWT lifecycle: any silent paths?
- Wave-43 LotTracker: incremental qty has `except Exception as _lot_err` — is the rollback path correct?
- Wave-44 EOD-cancel: pending-entry cancel uses `except Exception` — log level appropriate?

For each, verify the failure logs at WARNING+ AND surfaces an alert if user-impacting.

### 5. Logger pattern audit

V9 UU census noted: 513 eager f-strings vs 131 lazy `%s` in handlers. Re-count.
- Identify the worst offenders (handlers in tight loops where f-string evaluation is wasteful).
- Document the migration path (f-strings → %s) as a future cleanup.

### 6. ValidationError handling consistency

Wave-32 AA2-NEW-2 wrapped UserClaims construction. Are there OTHER pydantic constructors in request paths that swallow ValidationError?

```
grep -rn "BaseModel(\|\.parse_obj(\|model_validate(" backend/ --include='*.py' | head -20
```

For each, check whether ValidationError is caught (and how).

### 7. Async cancellation handling

`asyncio.CancelledError` should NOT be swallowed silently — it propagates a deliberate cancellation. Audit:

```
grep -rn "except asyncio\.CancelledError\|except CancelledError" backend/ --include='*.py'
```

For each, verify the handler re-raises after cleanup.

## Output

`artifacts/audit/v10_reports/track_uu2_error_handling_phase2.md` with:
- Updated UU census numbers
- Tier classification of remaining pass-only sites
- Proposed V11 ruff lint rule config
- New fail-open paths from waves 41-49 (if any)
- ValidationError / CancelledError consistency findings

Quality bar: 1-3 findings. The lint-rule proposal is the core deliverable.
