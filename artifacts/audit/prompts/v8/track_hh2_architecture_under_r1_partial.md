# Track HH2 v8 — Architecture Coupling Under HH R-1 Partial

V7 HH found 10 architecture issues; HH R-1 (the 2,510-line `_live_tick_inner`) was deferred. Wave-29 shipped Stage 0a (`_stage_expire_cooldowns`) + a 13-stage planning doc. **HH2 verifies Stage 0a doesn't introduce regression** + identifies which next stages are safest to extract.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Method

### 1. Stage 0a regression check

Wave-29 extracted `_stage_expire_cooldowns()`. Verify:
- The 4 maps it now mutates (`_exit_cooldown`, `_pending_entry`, `_pending_entry_order_ids`, plus the pending-exit cooldown) are mutated **identically** to the inline V7 code.
- No state mutation got lost in extraction.
- Run `tests/test_organism_live_engine.py` and `tests/test_multi_tick_state.py` — do they still pass on rc-1.5-curated @ 79b38fb? (Skip if you don't have a working test env; just confirm via reading.)

### 2. Replay-vs-live diff for Stage 0a

If a replay harness is available, run a 10-trade replay before+after wave-29 commit and diff the outputs. If the diff shows ANY non-determinism introduced by the extraction, that's a wave-29 regression.

### 3. Identify next-easiest stages to extract

Read `docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md`. For each of the 12 remaining stages, score:
- **LOC**: lines of code in that stage.
- **Coupling**: how many `self.*` attributes does it touch?
- **External effects**: does it call broker / DB / network?
- **State mutation**: pure read or read+write?

Rank by `(LOC × Coupling × ExternalEffects)` ascending — lowest score = safest next extraction.

Recommend 2-3 stages for waves 32-34.

### 4. Same-class coupling scan

Look for OTHER god-classes that V7 didn't flag (V7 focused on `_live_tick_inner`):

```
# Find files with classes >800 LOC.
find backend/ -name '*.py' -not -path '*/test*' \
  | while read f; do
      lines=$(wc -l < "$f")
      [ "$lines" -gt 800 ] && echo "$lines $f"
  done | sort -rn | head -10

# Find single methods >150 LOC.
./venv/bin/python - <<'PY'
import ast, pathlib
for p in pathlib.Path("backend").rglob("*.py"):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = (node.end_lineno or 0) - node.lineno
            if n > 150:
                print(f"{n}\t{p}:{node.lineno} {node.name}")
PY
```

Anything >150 LOC that V7 didn't flag = new HH2 finding.

### 5. Import-graph coupling

Does `backend/organism/live_engine.py` import from too many modules (a sign of a god-class consuming half the codebase)?

```
grep -E "^(from|import)" backend/organism/live_engine.py | wc -l
grep -E "^(from|import)" backend/organism/live_engine.py | head -40
```

Compare against `feature_engineering.py`, `brain.py`, `self_evolution.py`. Is live_engine an outlier? By how much?

### 6. Circular imports

```
./venv/bin/python - <<'PY'
import importlib, sys
# Try importing every module under backend/. Any ImportError on circular
# import shows up immediately.
import pathlib
for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    mod = ".".join(p.with_suffix("").parts)
    try:
        importlib.import_module(mod)
    except Exception as e:
        if "circular" in str(e).lower() or isinstance(e, ImportError):
            print(f"{mod}: {e}")
PY
```

Each circular = HH2 finding.

### 7. Layer violations

backend/api/routes/ should NOT import from backend/organism/ deeply (only via service interfaces). Verify:

```
grep -rn "from backend\.organism" backend/api/routes/ | head -30
```

Routes pulling organism internals = layer violation = finding.

## Output

`artifacts/audit/v8_reports/track_hh2_architecture_under_r1_partial.md` with:
- Stage 0a regression status (pass/fail with evidence)
- Replay-vs-live diff result (if run)
- Top-3 recommended next stages (waves 32-34) with score table
- New god-classes found (>800 LOC files, >150 LOC methods)
- Import coupling outliers
- Circular imports (if any)
- Layer violations
- "Architecture findings: N. Wave-29 status: clean/regressed." + TL;DR

Quality bar: 1-3 findings. End with one-paragraph summary. Stage 0a should be clean; finding a regression here would be unexpected and Critical.
