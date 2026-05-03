# Track W3 v8 — Verify CI Rules ACTUALLY Enforce

V6 W proposed rules. V7 W2 found they hadn't shipped. Wave-26 shipped warn-mode. Wave-28 flipped to required. **Track W3 verifies the rules now actually block bad PRs.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Method

### 1. Construct synthetic bad-wave commits

Use `git commit-tree` or a sandboxed git worktree to construct synthetic commits with:

- (a) `fix(audit-wave99a): test` — body has finding-ID but NO grep, NO assert-zero, NO test. Should FAIL rule #2 + #3.
- (b) `fix(audit-wave99b): test (CRITICAL)` — body has grep `grep -rn "test" tests/` (returns >0), AND no test added. Should FAIL re-run-grep + behavioral-test.
- (c) `fix(audit-wave99c): test` — body has grep that returns 0 + assert-zero + finding-ID. Should PASS (the canonical good-shape commit).

Run `scripts/ci/check_wave_markers.py --base <synth-base> --head <synth-head>` against each. Verify exit code: (a) 1, (b) 1, (c) 0.

### 2. Verify required-mode is wired to pr-verify.yml

`grep "continue-on-error" .github/workflows/pr-verify.yml` should NOT match the wave-marker step. Verified by `tests/test_reachability_v8.py::test_pr_verify_workflow_uses_required_mode`.

### 3. Verify PR template is the human-enforcement surface

`.github/pull_request_template.md` exists, contains "Audit-wave PR checklist" + 6 checkbox items. Already covered by reachability test.

### 4. CI dry-run on actual recent waves

Run check_wave_markers.py against `HEAD~5..HEAD` in REQUIRED mode:

```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~5 --head HEAD
```

Expected: most waves still missing grep-cited bodies (they pre-date wave-28). Document which waves are pre-ship-grace and which are post.

### 5. Identify gaps

- Does the script handle commits with multiple grep blocks correctly?
- Does it handle Critical/High detection on free-form prose (not just IDs)?
- What happens if a grep command times out? (We capped at 30s; verify behavior.)
- What about commits with no diff in `tests/` but a behavioral test added in conftest?

## Output

`artifacts/audit/v8_reports/track_w3_ci_rule_actual_enforcement.md` with:
- Synthetic commit test results (a/b/c)
- pr-verify.yml inspection
- Actual-recent-wave CI dry-run results
- Identified gaps (if any)
- "CI rule blockers found: N" + TL;DR

Quality bar: 1-3 gaps. The track confirms that the recommendation actually works under load. End with one-paragraph summary.
