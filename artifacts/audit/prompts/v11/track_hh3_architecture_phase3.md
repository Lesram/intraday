# Track HH3 v11 — Architecture Phase 3

V10 HH2 verified wave-29 stage 0a + flagged 2 god-methods (HH2-N-1, HH2-N-2). Wave-63 partially split HH2-N-1. **HH3 audits post-wave-40 architecture for next-easiest improvements + identifies the new god-class to tackle.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. _live_tick_inner residual size

```
./venv/bin/python -c "
import ast, pathlib
p = pathlib.Path('backend/organism/live_engine.py')
tree = ast.parse(p.read_text())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name == '_live_tick_inner':
            print(f'_live_tick_inner: {node.end_lineno - node.lineno} LOC')
            break
"
```

Pre-V8: 2510 LOC. Post-wave-29 + wave-40 (stages 0a, 1, 1.1, 1.2 extracted): expected smaller. Document current size.

### 2. New god-classes since V10

Re-run V8 HH2 god-class scan:
```
./venv/bin/python - <<'PY'
import ast, pathlib
for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try: tree = ast.parse(p.read_text())
    except Exception: continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = (node.end_lineno or 0) - node.lineno
            if n > 150:
                print(f"{n}\t{p}:{node.lineno} {node.name}")
PY
```

Compare to V8 HH2 list:
- live_engine._live_tick_inner: ~2200 (post-wave-40, deep)
- routes/indicators.py:calculate_indicator: ~580 (post-wave-63)
- routes/orders.py:validate_order_pre_trade: 477 (untouched, HH2-N-2)
- kelly_sizer.py:size_positions: 424 (untouched, HH2-N-3)

Identify any NEW (since V8) > 150 LOC functions.

### 3. Import-graph coupling re-audit

```
grep -E "^(from|import)" backend/organism/live_engine.py | wc -l
```

V8 reported 35 imports for live_engine. What's it now?

### 4. Circular imports check

```
./venv/bin/python - <<'PY'
import importlib, pathlib
for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    mod = ".".join(p.with_suffix("").parts)
    try:
        importlib.import_module(mod)
    except Exception as e:
        if "circular" in str(e).lower():
            print(f"{mod}: {e}")
PY
```

Expect: 0.

### 5. Layer violations

Routes importing from organism internals = layer violation:
```
grep -rn "from backend\.organism" backend/api/routes/ --include='*.py' | head -10
```

### 6. Recommend next 3 stages for HH R-1 sequence

Per `docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md`, what's the lowest-risk next extraction?

### 7. Stage 1.3 EOD entry block extraction analysis

Wave-44 DD3-4 added inline EOD-cancel logic + wave-35 DD2-9 added the time bound. The full Stage 1.3 (EOD entry block + flatten orchestration) could be extracted as `_stage_eod_orchestration`. Estimate LOC + risk.

### 8. Test coverage hot-path

```
./venv/bin/python -m pytest --co -q tests/ 2>&1 | grep -c "<Function"
```

How many test functions cover the live_engine.py 6500-LOC module specifically?

## Output

`artifacts/audit/v11_reports/track_hh3_architecture_phase3.md` with per-section findings + recommended next stages.

Quality bar: 1-3 findings.
