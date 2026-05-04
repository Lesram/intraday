# Track NN v8 — Reachability Audit (NEW LENS)

The post-V7 root-cause analysis identified **dead code with live-looking telemetry** as one of the 4 failure modes (BB-8, BB-10, parts of HH). Wave-31 added 12 reachability tests for known cases. **Track NN scales the reachability lens systematically across the codebase**: for every test, is the production path actually reached, or is the test passing on dead code?

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Method

This is the new lens V8 ships. Read first; don't fix.

### 1. Tests-vs-imports divergence

For every `tests/test_*.py` file, identify the modules-under-test (the `from backend.X import Y` lines). Then verify those modules are actually imported on a production path (not just by sibling tests).

```
./venv/bin/python - <<'PY'
import ast, pathlib, collections
test_imports = collections.defaultdict(set)
for p in pathlib.Path("tests").glob("test_*.py"):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend"):
            test_imports[p.name].add(node.module)

# Aggregate the production import surface (what does the app actually import on startup?)
prod_imports = set()
for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend"):
            prod_imports.add(node.module)

# Tests targeting modules NEVER imported in production:
orphan_modules = set()
for tested in test_imports.values():
    for m in tested:
        if m not in prod_imports:
            orphan_modules.add(m)
for m in sorted(orphan_modules):
    print(m)
PY
```

Each module in this list is a candidate for "tested but unreachable in production." Triage manually — some may legitimately be utility modules imported via dynamic dispatch (e.g. strategy plug-ins), others are genuinely dead code.

### 2. Function-level reachability sample

Pick 20 random functions from `backend/organism/`. For each, grep the codebase (excluding `tests/`) to see if it's called from any non-test path.

```
./venv/bin/python - <<'PY'
import ast, pathlib, random
random.seed(8)  # reproducible
funcs = []
for p in pathlib.Path("backend/organism").rglob("*.py"):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            funcs.append((p, node.name, node.lineno))

sample = random.sample(funcs, min(20, len(funcs)))
for p, name, line in sample:
    print(f"{p}:{line}\t{name}")
PY
```

Then for each `name`:
```
grep -rn "\.${name}(\|\b${name}(" backend/ --include='*.py' \
  | grep -v "/tests/" | grep -v "def ${name}(" | head -5
```

If 0 hits → orphan. If only test hits → tested but unreachable.

### 3. Class instantiation reachability

Same as above but for classes. A class with a heavy `__init__` that's never instantiated outside tests = orphan.

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
        if isinstance(node, ast.ClassDef):
            print(f"{p}:{node.lineno}\t{node.name}")
PY > /tmp/all_classes.txt

# For each class, grep for instantiation in non-test code.
while read line; do
    cls=$(echo "$line" | awk '{print $NF}')
    hits=$(grep -rn "${cls}(" backend/ --include='*.py' | grep -v "/tests/" | grep -v "class ${cls}" | wc -l)
    [ "$hits" -eq 0 ] && echo "ORPHAN: $line"
done < /tmp/all_classes.txt | head -30
```

Triage: some classes are exported for downstream use (e.g. data classes, enums) and won't show instantiations in this repo — exclude `Enum`, `Pydantic BaseModel`, `dataclass`. Focus on plain classes with logic.

### 4. Endpoint reachability

For every `@router.X` route in `backend/api/routes/`, verify:
- The router is included in `backend/api/main.py` (or wherever the app is constructed).
- A startup grep for the path string finds it actually mounted.

```
grep -rn "@router\.\(get\|post\|put\|delete\|patch\)" backend/api/routes/ \
  | head -30
```

Then for each route, confirm the parent router is registered in `main.py`. If not → unreachable endpoint.

### 5. Database table reachability

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
```

For each table, grep `backend/` for the table name. If 0 hits in non-migration code → orphan table.

### 6. Worker / background task reachability

V7 noted some background tasks. Verify each is actually scheduled (look for `asyncio.create_task`, `BackgroundTasks`, `apscheduler`, etc.). If a task module exists but is never scheduled → orphan.

### 7. Strategy plug-in reachability

`backend/strategies/` has 4,872 LOC of BaseStrategy subclasses. V7 HH flagged these as "barely wired live." Re-verify:
- Which subclasses are instantiated by `live_engine.py` or `alpha_scanner.py`?
- Which are tested but never instantiated outside tests?

Output a table: strategy, tested?, instantiated in live path?, verdict.

## Output

`artifacts/audit/v8_reports/track_nn_reachability_audit.md` with:
- Orphan modules list (Section 1)
- Sample function reachability table (Section 2, 20 rows)
- Orphan classes list (Section 3, top 30)
- Orphan endpoints (Section 4)
- Orphan tables (Section 5)
- Orphan workers (Section 6)
- Strategy plug-in reachability table (Section 7)
- Severity tiers: Critical (security/financial path), High (audit/compliance path), Medium (logic path), Low (utilities)
- "Reachability findings: N. Largest orphan: <name>." + TL;DR

Quality bar: 5-10 findings. This is V8's biggest yield-expectation track. End with one-paragraph summary.
