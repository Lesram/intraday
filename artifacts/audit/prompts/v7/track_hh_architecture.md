# Track HH v7 — Architecture / Code Organization (NEW SURFACE)

V1-V6 found per-file bugs. Track HH steps back and audits **structural
quality**: coupling, cohesion, god classes, circular deps, layering.
The deliverable is a set of refactoring proposals, ranked by ROI.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Method

### 1. Module size + complexity inventory

`wc -l backend/organism/*.py | sort -n` — what are the largest files?
Memory.md noted `live_engine.py` is ~3,600 lines. Updated count?

For each file > 1,000 lines:
- Cohesion: does it have one responsibility, or many?
- Suggested split candidates.

For each file > 3,000 lines (god-file class):
- Top 3 responsibilities.
- Refactoring sketch — what would a 3-way split look like?

### 2. Class size inventory

`grep -n "^class " backend/organism/live_engine.py` and similar — how
many methods per class?
- `OrganismLiveEngine.__init__` line count.
- Method count per class.
- Any class > 50 methods is a god class.

### 3. Import / coupling graph

- For each `backend/organism/*.py`, count its `from backend.* import`
  statements.
- Build a dependency graph (text-table form is fine).
- Identify circular dependencies (A imports B, B imports A).
- Identify "import everything" modules (god-aggregator).

### 4. Layering violations

The intended layering is roughly:
- `backend/api/` (HTTP layer)
- `backend/services/` (domain services)
- `backend/organism/` (strategy logic)
- `backend/integrations/` (broker / market data)
- `backend/infra/` (DB, cache, security, alerting)

Audit for violations:
- `backend/organism/` importing from `backend/api/`?
- `backend/integrations/` importing from `backend/services/` (instead
  of the other way)?
- `backend/infra/` importing from `backend/organism/`?

### 5. Lazy imports

`grep -rn "^        from \|^            from " backend/` — count of
lazy imports inside functions/methods. Sometimes necessary (avoiding
circular deps), often a smell. The wave-20c X-1 fix made replay-simulator
eagerly import `dotenv` to break a determinism bug — same class of
issue applies elsewhere?

For each lazy import:
- Why is it lazy? (Comment explains?)
- Could it be eager?

### 6. Inheritance vs composition

Sample classes with deep inheritance hierarchies:
- `class X(Y)` where Y itself inherits — chain depth 2+?
- For each: defensible? Or composition would be cleaner?

### 7. Public surface cleanup

For each module in `backend/organism/`, what's exported via the public
API (no `_` prefix) vs what's actually consumed externally?
- Public functions/classes never imported elsewhere = candidate for `_` prefix.
- Underscore-prefixed functions/classes that are imported elsewhere =
  bug (private accessed across module boundary).

### 8. Repeated patterns

`grep -rn "lambda: datetime.now" backend/organism/` and similar — every
"this same 3-line pattern appears in 5+ places" is a refactor candidate.

Top patterns:
- The `_now_fn` initialization stanza (post wave 17b/19/22). Could
  this be a mixin or decorator?
- The `dispatch_alert_from_thread` wrapping pattern (post wave 17a/20a).
  Could this be a context manager?
- The `_write_json` atomic-write pattern (post wave-19) — already a
  helper; verify all sites use it.

### 9. Configuration sprawl

- How many `os.getenv(...)` calls across `backend/`?
- Are they centralized in a settings class? Or scattered?
- Wave-19 N-M class touched a few; the broader pattern.

### 10. Strategy module coupling

`backend/organism/live_engine.py` is the central tick loop. Audit its
direct dependencies:
- How many other organism modules does it import?
- How many infra modules?
- Could the tick loop be refactored as orchestrator-of-clean-pieces
  rather than god-file?

## Output

`artifacts/audit/v7_reports/track_hh_architecture.md` with:
- Top-10 largest files / classes
- Coupling matrix (top 10 modules × dependency count)
- Circular dependency list
- Layering violation list
- Lazy-import inventory
- Inheritance depth audit
- Public surface cleanup candidates
- Repeated-pattern catalog (top 5)
- "Refactoring proposals ranked by ROI" — a top-5 list with effort estimate
- TL;DR

## Constraints

Read-only. The deliverable is *proposals*, not implementations.

## Quality bar

Expect 5-10 structural findings. The point of this track is to surface
big-picture structural debt that the per-file tracks miss.

End with a one-paragraph synthesis: where the architecture is healthy
vs where the technical debt is loudest.
