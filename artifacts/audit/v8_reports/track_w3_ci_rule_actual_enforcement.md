# Track W3 v8 — CI Wave-Marker Rule Actual Enforcement

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` @ `5bc4046`
**Script under test**: `scripts/ci/check_wave_markers.py`
**Workflow**: `.github/workflows/pr-verify.yml`
**Date**: 2026-05-02

## 1. Synthetic bad-wave commit results (a/b/c)

Built three synthetic commits in a temp clone of the real repo (`/tmp/w3_audit/w3_repo`, branch `w3-synth`, parented at `5bc4046`). Real branch was never touched.

| Commit | Body shape | Expected | Actual exit | Detail |
|---|---|---|---|---|
| (a) `e78bb31` `fix(audit-wave99a): test commit a` | finding-ID `AA-C-1` only; no grep, no assert-zero, no test | FAIL (1) | **1** | 3 fails: missing grep, missing assert-zero, Critical/High behavioral-test missing (severity inferred from `-C-` in ID) |
| (b) `b96aa4a` `fix(audit-wave99b): test commit b (CRITICAL)` | finding-ID `BB-C-1`; grep `grep -rn "test" tests/` (re-runs to 18158); assert-zero present; no test added | FAIL (1) | **1** | 2 fails: re-run grep count=18158, Critical/High behavioral-test missing |
| (c) `5352b74` `fix(audit-wave99c): test commit c` | finding-ID `CC-1`; grep against unique-marker string (re-runs to 0); assert-zero present; no Critical/High severity → no test required | PASS (0) | **0** | All checks ok |

**Verdict**: required-mode enforcement works as advertised on the canonical good/bad shapes. Exit codes match V8 wave-28 contract.

## 2. pr-verify.yml inspection

`grep -n "continue-on-error" .github/workflows/pr-verify.yml` returns no matches. The wave-marker step at lines 50–59 calls `check_wave_markers.py` with no `--warn-only`, no `continue-on-error`, no `|| true`. The step is a hard gate in PR CI.

`tests/test_reachability_v8.py` (12 tests) passes locally:
```
12 passed, 2 warnings in 1.65s
```
(via `./venv/bin/python -m pytest tests/test_reachability_v8.py -q --timeout=15`)

## 3. PR template inspection

`.github/pull_request_template.md` exists and contains the "Audit-wave PR checklist" section (line 34) with 6 checkbox items at lines 36, 37, 41, 42, 43, 44 — covering finding-IDs, grep command, count=0 assertion, behavioral test, source marker, deploy verification. Matches the V6 W rule surface.

## 4. CI dry-run on actual recent waves (HEAD~5..HEAD on rc-1.5-curated)

```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~5 --head HEAD
```

Exit code: **1** (7 failures across 4 wave commits)

| SHA | Subject | Failures | Note |
|---|---|---|---|
| `79b38fb` | `fix(audit-wave29): HH R-1 partial pipeline-split` | 2 (no grep, no assert-zero) | post wave-28; would now block in PR CI |
| `7532f0d` | `fix(audit-wave31): reachability tests` | 1 (no grep) | post wave-28; would now block |
| `acebe08` | `fix(audit-wave30): wire BB-8 LotTracker + BB-10 audit_logs` | 2 (no grep, no behavioral-test for AA-H-3 finding) | post wave-28; would block |
| `76e8df3` | `fix(audit-wave28): tighten CI rules` | 2 (no grep, no behavioral-test) | the wave-28 enforcement commit itself would not pass its own gate |

**Note**: every wave commit on rc-1.5-curated through HEAD predates a PR-CI run with required-mode (these were merged direct-push or via wave-28's own PR before required-mode landed on `main`). Going forward on PR-merged waves the gate applies.

The fact that `wave-28`'s own commit (`76e8df3`) is itself non-compliant under its own rule is a notable but acceptable bootstrapping artifact — the rule changed mid-flight. Future waves are bound.

## 5. Identified gaps (3)

### Gap W3-G1 (Critical, bypass vector): timeout/error grep silently passes the gate

When the cited grep command times out (≥30s) or otherwise can't be executed, `_re_run_grep` returns `count = -1`. The required-mode logic at lines 240–252 only counts `count > 0` as a failure; `count < 0` prints `[WARN] could not re-run` and **does not increment `fails`**.

Reproduced with synthetic commit citing `grep -rn "" /` (recurses from root, eventually times out): exit code **0** despite the grep being effectively un-evaluated.

A user (intentionally or accidentally) can trivially defeat the same-class-scan-zero contract by pasting a grep that times out or has invalid syntax. Recommend treating `count < 0` as `FAIL` under required-mode (or at minimum requiring one successfully-evaluated grep).

### Gap W3-G2 (Medium, scope): behavioral-test diff scoped to top-level `tests/` only

`_diff_test_count` filters to `-- tests/` (line 156, 161). New test functions added in `backend/tests/`, integration suites under other paths, or test-equivalent additions to `tests/conftest.py` fixtures are missed. For this repo (only `tests/` and `docs/engineering/.../tests` exist), the scope is mostly fine; but if a contributor lands a new behavioral test in any other path, the gate falsely fails. Lower-impact than G1.

### Gap W3-G3 (Low, parsing brittleness): grep prefixed with `$` shell prompt is not recognized

`SAMECLASS_BLOCK_RE` requires the line to start with optional whitespace then `grep`. A pasted shell session line like `$ grep -rn "..." backend/` is silently treated as "no grep command" and the commit fails on the missing-grep rule. Reproduced with synthetic commit `99e`. Easy to mitigate by stripping leading `$ ` / `> ` shell prompts before matching.

## CI rule blockers found: 1

(W3-G1 is a true bypass; W3-G2 / W3-G3 are correctness-and-UX issues, not bypass vectors.)

## Other observations (non-gaps)

- Multi-grep block parsing works correctly: each grep is re-run independently, and any single non-zero count fails the wave (verified with synthetic commit `99f`).
- Critical/High inference from finding-IDs (`[A-Z]{1,3}-[CH]-\d+`) is by design and matches the audit-cycle ID convention (`AA-C-1`, `AA-H-3`, etc.). Not a misclassification risk for the active naming scheme.
- The script correctly handles HH-track free-form IDs like `HH R-1`, `HH-R-5` and BUG-N legacy IDs (per V8/wave-28 widening at line 41–47).

## TL;DR

Wave-28 required-mode CI enforcement is wired correctly: `pr-verify.yml` runs `check_wave_markers.py` without `continue-on-error` or `--warn-only`, the script returns non-zero on the canonical bad shapes (a, b) and zero on the canonical good shape (c), the PR template carries the human-readable checklist, and the reachability test suite passes. One real bypass vector remains: a cited grep that times out or errors out (`count = -1`) is reported as `[WARN]` but does not increment the failure counter, so a pathological or accidentally-broken grep slips through required-mode unblocked. Two lower-severity issues (test-diff scoped to top-level `tests/` only; `$ grep ...` shell-prompt prefix not recognized) are correctness-and-UX rough edges, not bypass paths. The rule actually enforces; it just has one durable hole that should be closed by treating un-evaluated grep as FAIL.
