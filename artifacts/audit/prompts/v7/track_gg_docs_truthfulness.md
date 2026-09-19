# Track GG v7 — Documentation Truthfulness (NEW SURFACE)

The repo has many docs (`AGENTS.md`, `CLAUDE.md`, `mapss.md`, runbooks,
docstrings). After 22 fix waves and 6 audit rounds, are they still
accurate? This track audits **whether documentation matches reality**.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Files in scope

- `AGENTS.md`, `CLAUDE.md`, `README.md`
- `docs/architecture/mapss.md`
- `docs/architecture/improve9.md` (and similar improve* docs)
- `docs/engineering/CONTROL_PLANE.md`
- `OPERATOR_COMMAND_SHEET.md`
- `MONDAY_DEPLOY_eb90fa3.md` and similar deploy docs
- Module / class / function docstrings across `backend/organism/`
- Test docstrings

## Method

### 1. AGENTS.md / CLAUDE.md accuracy

For each claim about the system in these meta-docs:
- Is it still true post wave-22?
- Especially: branch / commit / deploy state references — current?
- File paths referenced — still exist?
- Commands documented — still work?

### 2. mapss.md accuracy

`docs/architecture/mapss.md` is the comprehensive platform map.
For each component listed:
- Still in the codebase?
- Same import path?
- Same responsibility?
- Module-level docstring matches mapss description?

### 3. Improve docs

`improve3-9.md` are historical (per memory). Are they still listed in
docs/ as if current? Should they be archived?

### 4. Runbook freshness

- `OPERATOR_COMMAND_SHEET.md`: every command — still works?
- `MONDAY_DEPLOY_eb90fa3.md`: refers to a specific commit; is that
  commit still relevant or is the doc stale?
- Any runbook that references a deprecated route, command, or file
  path.

### 5. Module docstrings

For each `backend/organism/*.py` module-level docstring:
- Is the description accurate?
- Does it list responsibilities the module no longer has?
- Does it omit responsibilities the module DOES have now?

### 6. Class docstrings

For high-blast classes (`OrganismLiveEngine`, `OrganismBrain`,
`KellySizer`, `RegimeDetector`, `ContinuousLearner`,
`AlpacaBrokerClient`, `AlpacaStreamClient`):
- Class docstring matches behavior?
- Listed methods still exist?

### 7. Function/method docstrings

Sample 30 random functions from `backend/organism/`. For each:
- Args documented match actual signature?
- Returns documented match actual return type?
- Side effects documented?
- Behavior described matches code?

### 8. README setup reproducibility

- `README.md` setup instructions: try to follow them in a fresh shell
  (DON'T actually wipe the venv — just verify the documented steps
  are syntactically valid and reference real commands/files).
- Any step that requires undocumented prereq?

### 9. Audit cycle docs

`artifacts/audit/`:
- AUDIT_PROCESS.md — current?
- PROMPT_LESSONS_v1.md — supersedes? Add v7 lessons.
- FINDINGS_LEDGER.md — current up to wave-22?
- Each MASTER_AUDIT_SYNTHESIS_v* — committed and findable?

### 10. Audit-marker comment density

V7 W found marker gaps. Sample 50 audit markers in source (`grep -rn
"V[0-9].*Wave-[0-9]" backend/`). For each:
- Marker still references a real finding ID?
- Code at that location still relates to the marker?
- Any orphan markers (code refactored away, marker remains)?

## Output

`artifacts/audit/v7_reports/track_gg_docs_truthfulness.md` with:
- AGENTS.md / CLAUDE.md accuracy verdict
- mapss.md component-by-component verification
- Stale runbook list
- Module docstring drift inventory
- Class/method docstring sample audit (30 functions)
- README reproducibility check
- Audit-cycle doc state
- Orphan marker list
- "Documentation drift items: N" + TL;DR

## Constraints

Read-only. No file rewrites in this audit (the FIX is wave 23+).

## Quality bar

Expect 3-8 findings. Especially:
- A runbook command that doesn't work
- A mapss.md component that's been removed or renamed
- A class docstring that lists deprecated methods
- An orphan audit marker pointing at code that no longer matches

End with a one-paragraph summary.
