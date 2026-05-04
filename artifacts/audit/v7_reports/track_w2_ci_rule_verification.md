# Track W2 v7 — CI Rule Verification (V6 W Follow-up)

**Repo:** /Users/marselkei/VS/intra
**Branch:** rc-1.5-curated @ `d44eace`
**Method:** Read-only inventory of `.github/`, `scripts/ci/`, and the
wave-20 → wave-22 commit bodies. Cross-checked against the seven CI
proposals from `artifacts/audit/v6_reports/track_w_wave_cycle_audit.md`
(§4 "CI Rule Proposal") and the prompt's three-rule subset.

---

## TL;DR

**CI rule shipping gaps: 3 of 3 prompt-listed rules unshipped.**
W's three CI proposals (finding-ID delta, same-class grep + zero-count
assertion, behavioral-test-required-on-Critical/High) are all *not* in
the PR template (which doesn't exist) and *not* in any
`.github/workflows/*.yml`. Wave-21 self-applied the spirit of rule #1
(markers backfilled) and rule #3 (behavioral test added for the worst-hit
wave 18), and wave-22 added a CI-determinism smoke test, but these are
contributor-discipline, not enforced gates. The check script W referenced
(`scripts/ci/check_wave_invariants.py`) does not exist. There is no
automated enforcement of marker discipline, same-class scans, or
behavioral-test count deltas anywhere in the repo. Per-wave compliance
audit shows wave-20 = 0/3, wave-21 = 1.5/3, wave-22 = 1/3 — informally
trending in the right direction, formally still bypassed.

---

## 1. PR Template State

```
$ find .github -iname "*pull_request*" -o -iname "PULL*"
(no matches)
$ find . -maxdepth 4 -iname "pull_request*"
(no matches)
```

**Result: no PR template exists** at any of the four standard
GitHub-recognised paths (`/.github/pull_request_template.md`,
`/.github/PULL_REQUEST_TEMPLATE/*`, `/docs/pull_request_template.md`,
root `pull_request_template.md`). `.github/` contains only
`ISSUE_TEMPLATE/automation_task.yml` and `ISSUE_TEMPLATE/strategy_bug.yml`
(both shipped 2026-03-07 with the AIA control-plane bundle).

This is **gap #1**. W's rule #1 ("PR matching `audit-wave\d+` must add
≥1 new comment line containing the finding-ID") and rule #2 (same-class
grep command + asserted zero in commit body / PR description) cannot be
human-enforced because contributors have no template prompting them to
declare those things.

---

## 2. Workflow Inventory + Gap Analysis

`.github/workflows/` contents (8 files):

| File | Trigger | Jobs |
|---|---|---|
| `pr-verify.yml` | PR to main/master | detect (paths-filter) → organism-tests, config-tests, artifact-pack, spec-drift, secret-scan |
| `ci.yml` | push + PR to main/develop | lint (ruff), types (mypy strict), security (bandit/pip-audit/safety), test (pytest + coverage ratchet), quality-summary |
| `nightly.yml` | cron 02:00 UTC | deep-tests + auto-issue-on-failure |
| `paper-postclose-audit.yml` | cron 22:15 UTC weekdays | KPI threshold check + issue-open |
| `security-scan.yml` | push/PR/weekly | Trivy image + filesystem + SBOM |
| `staging.yml` | (not read — unrelated to W) | deployment |
| `canary-deployment.yml` | (not read — unrelated to W) | deployment |
| `codex-review-trigger.yml` | PR open/sync/reopen | placeholder echo (no logic) |

**Per-rule check:**

### W rule #1 — finding-ID delta gate

> "PR matching `audit-wave\d+` must add ≥1 new comment line containing
> the finding-ID it closes (block on empty diff)."

- `grep -rln "audit-wave" .github/ scripts/ci/` → **0 matches.**
- No workflow filters on commit-message regex; `pr-verify.yml`
  filters on changed paths only.
- No script enforces the "new comment containing finding-ID" diff
  rule.

**Status: NOT SHIPPED.**

### W rule #2 — same-class grep + asserted zero, CI re-runs

> "The wave PR must include (in commit body or PR description) the
> exact `grep` command + asserted-zero result that proves the
> same-bug-class is gone. CI re-runs the grep and blocks if the count > 0."

- No workflow parses commit body for a grep command, let alone executes it.
- `check_spec_drift.py` is a fixed runtime-vs-spec drift check, not a
  PR-supplied scan executor.
- Wave-20 commit body mentions the *concept* "S-J3-1 same-class miss"
  in narrative prose (`grep -i "same-class" wave20-body` → 1 hit) but
  cites neither a `grep` command nor an asserted count.
- Wave-21 and wave-22 commit bodies contain zero "same-class" mentions
  and zero `grep` command citations.

**Status: NOT SHIPPED.**

### W rule #3 — behavioral test required for Critical/High

> "PRs closing findings tagged `Critical` or `High` must add a test
> that *fails when the fix is reverted* … CI cannot enforce, but PR
> template forces the evidence."

- W explicitly noted "CI cannot enforce" — the PR template is the
  control point. **No PR template exists** (see §1), so even the
  intended enforcement surface is missing.
- `pr-verify.yml::organism-tests` runs a fixed test list; it does not
  diff `tests/` for new files or assert a count delta.
- No workflow asserts that a wave commit modifies `tests/` at all.

**Status: NOT SHIPPED.**

### Bonus — W's other four proposals (rules 4-7)

| Rule | Status | Evidence |
|---|---|---|
| #4 No marker erasure | NOT SHIPPED | No script/hook checks `git diff` for removed `# V<n> <id> / Wave-<n>` lines. |
| #5 Wave coverage report (nightly W self-run) | NOT SHIPPED | Nightly workflow runs deep tests only; no `track_w_wave_cycle_audit` re-run. |
| #6 Behavioral-test-ratio quota (≥50%/7d) | NOT SHIPPED | No tracking script. Test files have no category-marker docstring convention enforced. |
| #7 Z-track scans → cron-weekly with PD on count > 0 | NOT SHIPPED | No closure-regression workflow exists; Z-tests run only inside the regular pytest suite. |

---

## 3. Marker Convention Enforcement

W found 3 marker gaps in V6: U-1, U-2 (both `live_engine.py`,
wave-19) and P-P0-3 (wave-12f marker overwritten by wave-17a).

**Wave-21 backfill** (commit `8430bf6`): added markers at
`backend/organism/live_engine.py:4708` (U-1) and `:4833` (U-2):

```
# V5 U-1 / Wave-19 (2026-05-03): route through self._now_fn()
# V5 U-2 / Wave-19 (2026-05-03): route through self._now_fn()
```

Both confirmed present at HEAD (`d44eace`). Provenance restored after
the fact — the underlying gap (markers can ship missing without CI
catching it) is unfixed.

**Automated check status: NOT SHIPPED.** No `scripts/ci/check_wave_markers.py`
or equivalent. Concrete proposal (small, ~25 lines):

```python
# scripts/ci/check_wave_markers.py — wired into pr-verify.yml
import re, subprocess, sys
msg = subprocess.check_output(["git","log","-1","--format=%s%n%n%b"]).decode()
m = re.search(r"audit-wave(\d+).*?\(([^)]+)\)", msg)
if not m: sys.exit(0)
ids = [i.strip() for i in re.split(r"[,/]", m.group(2)) if re.match(r"[A-Z]", i.strip())]
diff = subprocess.check_output(["git","diff","--unified=0","HEAD~1","--","backend/"]).decode()
missing = [fid for fid in ids if fid not in diff]
if missing:
    print(f"FAIL: wave commit closes {ids} but diff has no marker for: {missing}")
    sys.exit(1)
```

Hooked into `pr-verify.yml::detect` job under an
`if: contains(github.event.pull_request.title, 'audit-wave')` step.

---

## 4. Per-Wave Compliance Audit (waves 20-22)

W shipped at v6 commit `eae3fb1` on 2026-05-03. Wave 20-22 all shipped
on 2026-05-02 to 2026-05-03 (chronologically *after* W's report).
Compliance is scored against the prompt's three rules:

| Wave | Commit | (1) Finding-IDs in body? | (2) Same-class grep + zero asserted? | (3) Behavioral test cited? | Score |
|---|---|---|---|---|---|
| 20 | `643ba6d` | YES — title lists V-T-1/V-T-2/V-T-3, X-1..X-6, X-8; body annotates each sub-wave by ID. | NO — body narratively mentions "S-J3-1 same-class miss" once (referencing the *bug class*, not a current scan); no grep command, no count assertion. | NO — body cites no test file. The 153-test pass count claim is unattributed. | 1 / 3 |
| 21 | `8430bf6` | YES — title lists V-T-4/V-T-6/V-T-7, T2-pin, U-1/U-2 markers; body sections per ID. | NO — zero "same-class" / "grep" mentions in body. | YES — explicitly cites `tests/test_wave18_behavioral_backfill.py` with 8 named tests (B-T-1, B-T-7, B-T-3, S-NET-CB-1, S-NET-T-1, S-OUTBOX-1). Note: this is a *backfill* for prior Wave-18 work, not for wave-21's own V-T-4/V-T-6/V-T-7 alert wiring (which has no behavioral test). | 1.5 / 3 |
| 22 | `3baefb4` | YES — title lists V-T-5/V-T-9, X-7; body sections per ID. | NO — zero "same-class" / "grep" mentions in body. | PARTIAL — cites `tests/test_ci_determinism_smoke.py` (6 tests) for X-7 / X-1 / now-fn injection contracts. V-T-5 (CRITICAL alert on DB startup failure) has no behavioral test cited; V-T-9 (log-level demotion) is policy-only. | 1 / 3 |

**Aggregate:** 3.5 / 9 prompt-rule slots filled across the three
post-W waves. Wave-21 is the strongest because it self-consciously
acknowledged W and backfilled both markers (rule #1 spirit) and a
behavioral test bundle (rule #3 spirit). None of the three waves
carries a same-class grep with an asserted zero count (rule #2).

---

## 5. Process Gap Inventory — Why CI Hasn't Caught Up

For each unshipped W rule, the blocker:

### Rule #1 — finding-ID delta gate
- **Why unshipped:** Rule needs both a PR template (so contributors
  declare which IDs the PR closes) *and* a CI script that diffs the
  declared IDs against the actual code diff. Neither exists.
- **File it would live in:** `.github/pull_request_template.md` +
  `scripts/ci/check_wave_markers.py` (new, ~25 LOC) + ~10 LOC step in
  `pr-verify.yml`.
- **Effort:** ~30 min. No external deps; runs in existing
  `pr-verify.yml::detect` job.

### Rule #2 — same-class grep + zero count
- **Why unshipped:** Highest-effort of the three. Needs a
  body-parsing convention (e.g. fenced block ``` ```same-class\n<grep
  cmd>\n``` ```), a parser, and a sandboxed executor in CI. Likely
  blocked by ambiguity in spec ("commit body or PR description") plus
  no contributor has yet been disciplined enough to write the grep.
- **File it would live in:** `.github/pull_request_template.md` (with
  fenced template) + `scripts/ci/run_same_class_scan.py` (~80 LOC,
  must whitelist the grep flags actually allowed) + step in `pr-verify.yml`.
- **Effort:** ~2-3 hours. Security: must reject any non-`grep -E`
  invocation to keep CI sandbox safe.

### Rule #3 — behavioral test for Critical/High
- **Why unshipped:** W flagged "CI cannot enforce" — true behavior
  diff (does test fail when fix reverted?) needs git checkout +
  rerun, expensive. Lighter version: assert that `tests/` has at
  least one new file or one new test function with a docstring tag
  matching the closed finding-ID.
- **File it would live in:** `.github/pull_request_template.md`
  checkbox + `scripts/ci/check_behavioral_test_present.py` (~40 LOC).
- **Effort:** ~1 hour for the lighter version. The full revert-rerun
  variant is ~half a day and doubles CI time per audit-wave PR.

---

## 6. Recommended PR Template

A drop-in `.github/pull_request_template.md` that enforces W's rules at
human-review time even before CI catches up:

```markdown
## Summary

<!-- 1-3 sentences -->

## Audit-wave PR checklist

*Skip this section if the commit message does not start with*
*`fix(audit-wave...)` or `docs(audit...)`.*

- [ ] **Finding-ID(s) closed** (use V<n> format, comma-separated):
  e.g. `V6 V-T-4, V6 V-T-7`
- [ ] **Source markers added** for each finding-ID (a `# V<n> <id>
  / Wave-<n>` comment in changed code):
  e.g. `backend/organism/live_engine.py:4708 → V5 U-1 / Wave-19`
- [ ] **Same-class scan** — paste the grep command and result count
  inside the fenced block below. Count must be 0 for the wave to
  be considered closing the *bug class*, not just a single site.

  ```same-class-scan
  $ grep -rEn "datetime\.now\([^)]*\)" backend/organism/ | wc -l
  0
  ```

- [ ] **Behavioral test added** (REQUIRED if any closed finding is
  Critical or High severity). Cite test path + test names. The test
  must fail when the fix is reverted. Reviewer: please verify
  locally with `git revert <wave-commit> && pytest <test path>` and
  confirm RED → GREEN.
  - Test file: `tests/test_<wave>_<area>.py`
  - Test names: `test_<finding>_<behavior>`, …
- [ ] **Marker erasure check** — confirm no existing `# V<n>
  <finding-id>` lines were deleted. If any were intentionally
  superseded, link the new marker that replaces it.

## Deploy verification

- [ ] Container `up -d --build` succeeded
- [ ] gen / trades count unchanged across recreate
- [ ] Tests cited above all pass

## Reviewer notes

<!-- anything ChatGPT architect or codex should focus on -->
```

Once this lands, wire `scripts/ci/check_wave_markers.py` (rule #1) and
`scripts/ci/run_same_class_scan.py` (rule #2) into a new
`audit-wave-gate` job in `pr-verify.yml`, conditional on PR title
matching `^(fix|docs)\(audit-wave`. Behavioral-test-presence (rule #3
lighter version) can be a third step in the same job.

---

## Summary

V6 W proposed three core CI rules and four follow-on rules to harden
the wave-cycle audit process; at v7 head (`d44eace`, three weeks on),
**zero have shipped to CI and no PR template exists** — the human-review
control surface W explicitly relied on for rule #3 is also missing.
Wave-21 internalised the *spirit* of W's findings by backfilling the
U-1 / U-2 markers in `live_engine.py` and shipping
`tests/test_wave18_behavioral_backfill.py` (8 tests for the
zero-behavioral-test wave 18 bundle), and wave-22 added
`tests/test_ci_determinism_smoke.py` for the `_now_fn` injection
contract; both are contributor-discipline wins, not enforced gates. Of
the post-W waves, none carries a same-class grep with an asserted zero
count in its commit body, so W's rule #2 — the most direct counter to
V5 Pattern 1 ("fix that didn't actually fix") — remains entirely
manual. Net: 3 of 3 prompt-listed rules unshipped (matching the prompt's
1-3 ship-gap quality bar at the upper end), and the recommended one-day
remediation is the PR template above plus two ~50 LOC CI scripts wired
into the existing `pr-verify.yml::detect` job.
