# Track UU3 v11 — Error-Handling Phase 3

V10 wave-57 shipped the UU2-B ruff lint rule + grandfather ratchet. **UU3 verifies the rule is actually enforced + audits compliance of post-V10 code.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. ruff config check

```
./venv/bin/ruff check backend/ --select S110,S112,BLE001,G004,TRY401,LOG007 2>&1 | tail -30
```

Count violations. Compare to grandfather list (7 files) — should match (existing backlog).

### 2. Compliance of post-V10 code

For each new/modified file in waves 50-65, run ruff with the new rules:
```
git diff --name-only e0df067..HEAD | grep '\.py$' | xargs ./venv/bin/ruff check --select S110,S112,BLE001,G004,TRY401,LOG007 2>&1 | head -20
```

Any new violations = UU3 finding (the lint rule isn't being respected).

### 3. Pre-commit hook check

If a pre-commit hook is wired:
```
ls .pre-commit-config.yaml .github/workflows/*.yml | head -5
grep -l "ruff" .pre-commit-config.yaml .github/workflows/*.yml 2>/dev/null
```

Is the rule enforced at commit-time, in CI, or both?

### 4. ValidationError + CancelledError audit re-do

Post-V10 wave-50-65, count:
```
grep -rn "except asyncio.CancelledError\b\|except CancelledError\b" backend/ --include='*.py'
```

Each should re-raise after cleanup.

### 5. Logger.warning patterns from waves 50-65

The wave-41/52/62 fixes added many logger.warning calls. Sample 5; verify the canonical "best-effort + warn" pattern from docs/engineering/error-handling.md.

### 6. Grandfather-ratchet ROI

For each of the 7 grandfathered files, count:
- pass-only handlers (S110+S112)
- f-string-in-handler (G004)
- bare-except / blind-except

Identify the top-1 file with the most violations as the V12 surgical-cleanup target.

### 7. New error-handling helpers introduced post-V10

Did wave 50-65 introduce any new `try/except` patterns that should also be audited?

### 8. dispatch_alert_from_thread audit

Verify EVERY new alert site since V10 uses `dispatch_alert_from_thread` (not bare `asyncio.create_task(send_alert(...))`):
```
grep -rn "asyncio.create_task(send_alert\|_aio.create_task(send_alert" backend/ --include='*.py' | head -10
```

Expected: 0 (or only test fixtures).

### 9. Missing exc_info=True

```
grep -rn "logger\.error(" backend/ --include='*.py' | grep -v "exc_info" | head -20
```

Sample 5. Are they in `except` blocks where `exc_info=True` would be valuable?

## Output

`artifacts/audit/v11_reports/track_uu3_error_handling_phase3.md` with violation counts + findings.

Quality bar: 1-3 findings.
