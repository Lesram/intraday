# Track W2 v7 — CI Rule Verification (V6 W follow-up)

V6 W proposed three CI rules to prevent the "fix that didn't actually fix"
pattern (V5 Pattern 1). Track W2 verifies whether those rules actually
shipped into the PR template / CI workflow.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## V6 W's three CI proposals

1. PR matching `audit-wave\d+` must add ≥1 new comment line containing the
   finding-ID it closes (block on empty diff).
2. Same-class grep + asserted-zero must appear in commit body; CI re-runs
   and blocks if count > 0.
3. Critical/High findings require a *behavioral* test (revert-to-fail),
   not a structural grep.

## Method

### 1. PR template inventory

- Check `.github/pull_request_template.md` (or equivalent) — does it exist?
- If yes: does it ask the contributor to declare finding-IDs and same-class
  scan results?
- If no: that's a finding.

### 2. CI workflow inventory

- List every workflow under `.github/workflows/`.
- For each: which triggers, what does it run?
- Specifically check whether ANY workflow:
  - Greps the commit body / PR description for finding-IDs.
  - Runs the same-class scan declared in the commit body.
  - Asserts behavioral test count delta on Critical/High wave commits.

### 3. Marker convention enforcement

- W found 3 marker gaps (U-1, U-2, P-P0-3 in V6).
- Wave-21 backfilled U-1/U-2.
- Is there an automated check that prevents future marker gaps?
- If not: propose one (grep against the wave commit's diff).

### 4. Wave-counts since W shipped

- W shipped at V6 round (commit eae3fb1, 2026-05-03).
- Since then, Wave 20, 21, 22 shipped.
- For each, did the contributor follow W's rules?
  - Wave 20 commit body: includes finding-IDs? same-class scan asserted? behavioral test cited?
  - Wave 21: same checks.
  - Wave 22: same checks.
- Tabulate compliance per wave.

### 5. Process gap inventory

For each W rule that hasn't shipped to CI:
- Why? (Time? Knowledge? Tooling?)
- Concrete blocker — what file would the rule live in?
- Effort estimate to implement.

### 6. Recommended PR template

Draft a `.github/pull_request_template.md` block that, when added, would
enforce W's rules at human-review time even before CI catches up:

```
## Audit-wave PR checklist (if commit message starts with `fix(audit-wave...)`)

- [ ] Finding-ID(s) closed:
- [ ] Same-class scan command:
- [ ] Same-class grep result count: 0 (assert)
- [ ] Behavioral test added (Critical/High): tests/test_...
- [ ] Source-of-truth marker comment added in changed code
```

## Output

`artifacts/audit/v7_reports/track_w2_ci_rule_verification.md` with:
- PR template state
- Workflow inventory + gap analysis
- Per-wave compliance audit (waves 20-22)
- Marker convention enforcement state
- Recommended PR template
- "CI rule shipping gaps: N" + TL;DR

## Constraints

Read-only. `git log`, `grep`, file inspection only.

## Quality bar

Expect 1-3 ship gaps. The deliverable is process feedback, not bug count.

End with a one-paragraph summary.
