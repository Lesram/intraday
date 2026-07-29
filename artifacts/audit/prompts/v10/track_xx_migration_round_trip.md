# Track XX v10 — Migration Round-Trip on Snapshot (NEW LENS)

V8 OO recommended; wave-37 shipped a single-headed-tree smoke check but didn't exercise apply→rollback→re-apply. **XX exercises every recent migration on a SCRATCH DB snapshot.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

**SCRATCH-ONLY.** Use a temporary `algotrading_xx_test` database; never touch `algotrading`.

## Method

### 1. Setup scratch DB

```
docker exec trading_platform_db_paper psql -U trading -d postgres -c \
  "CREATE DATABASE algotrading_xx_test;"
```

Apply migrations to base:

```
DATABASE_URL="postgresql://trading:CHANGEME@localhost:5432/algotrading_xx_test" \
  ./venv/bin/python -m alembic upgrade head
```

(Read the actual env-var format used; settings.py determines this.)

### 2. Round-trip the most recent migration

Latest migration head: `20260503_000001` (orders CHECK constraints, per V9 BB3).

```
./venv/bin/python -m alembic upgrade head  # baseline
./venv/bin/python -m alembic downgrade -1
./venv/bin/python -m alembic upgrade +1
```

After each step, capture schema:

```
docker exec trading_platform_db_paper pg_dump -U trading -d algotrading_xx_test \
  --schema-only --no-comments | grep -E "CREATE TABLE|ALTER TABLE|CHECK|UNIQUE INDEX"
```

Compare:
- baseline ↔ post-downgrade-then-upgrade

Expected: identical (modulo ordering / whitespace).

### 3. Round-trip 3 most recent migrations

Same pattern, downgrade -3 then upgrade +3.

### 4. Check downgrade() completeness

For each of the 3 most recent migrations, verify `downgrade()` is non-empty AND inverts every operation in `upgrade()`. AST-walk:

```
./venv/bin/python - <<'PY'
import ast, pathlib

for p in sorted(pathlib.Path("backend/migrations/versions").glob("*.py"))[-3:]:
    print(f"=== {p.name} ===")
    src = p.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade"):
            stmts = [
                ast.unparse(s).split('\n', 1)[0][:80]
                for s in node.body
            ]
            print(f"  {node.name}: {len(stmts)} stmts")
            for s in stmts[:5]:
                print(f"    {s}")
PY
```

If `downgrade()` has fewer ops than `upgrade()` or has `pass` only: flag.

### 5. Test data round-trip

After upgrade, INSERT a row into `orders`. After downgrade, the orders row may or may not survive (depending on whether downgrade drops the column the row depends on). Capture the behavior; document.

### 6. Migration ordering safety

Are there migrations that depend on each other being applied in a specific order? Check by running them in reverse:

```
./venv/bin/python -m alembic downgrade base
./venv/bin/python -m alembic upgrade head  # forward
```

This MUST work since alembic enforces ordering. But verify the forward path doesn't error mid-stream (e.g. on missing FK targets).

### 7. Schema vs ORM drift

Run:

```
./venv/bin/python scripts/runtime/write_runtime_snapshot.py
./venv/bin/python scripts/ci/check_spec_drift.py
```

If runtime ORM (SQLAlchemy schema) doesn't match the most recent alembic-applied schema, that's a finding.

### 8. Migration lock-time on production-sized table

The `orders` table has ~1,400 rows in paper. In production it might have millions.
- Estimate: how long would each recent migration take with 10M rows?
- Are any operations blocking (ALTER TABLE without CONCURRENTLY)?

This is a forward-planning finding (preparing for production scale).

### 9. Cleanup

```
docker exec trading_platform_db_paper psql -U trading -d postgres -c \
  "DROP DATABASE algotrading_xx_test;"
```

## Output

`artifacts/audit/v10_reports/track_xx_migration_round_trip.md` with:
- Round-trip results (3 latest)
- downgrade() completeness audit
- Test-data round-trip behavior
- Schema vs ORM drift
- Lock-time estimates
- Cleanup confirmation

Quality bar: 1-3 findings. Most likely findings: incomplete downgrade()s, lock-time on production-sized data.
