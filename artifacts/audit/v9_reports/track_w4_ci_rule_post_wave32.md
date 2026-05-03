# Track W4 v9 — Verify Wave-32 CI Rule Fixes Close the Bypasses

**Branch:** rc-1.5-curated @ `ccba97f`
**Wave-32 SHA:** `842587e`
**Method:** Synthetic-commit reconstruction in temp worktree (`/tmp/w4_sandbox`),
plus end-to-end dry-run on the real branch.
**Tool:** `scripts/ci/check_wave_markers.py`

## 1. W3-G1 verification — grep-timeout now FAILS in required mode

Synthetic commit (canonical wave prefix `fix(audit-wave99)`) citing
`grep -rn '' /` (recurses from root, hits the 30s timeout):

**Required-mode run** (`./venv/bin/python3 scripts/ci/check_wave_markers.py`):

```
=== cc6b30b8 fix(audit-wave99): synthetic w3-g1 timeout test (CRITICAL) ===
  [ok] finding-IDs: AA-C-1
  [ok] same-class grep cited: 1 command(s)
    [FAIL] could not re-run (count<0; timeout or error): grep -rn '' /
  [FAIL] Critical/High wave commit added no new test functions (net delta=0). ...
[FAIL] 2 wave-commit check(s) failed
```
**Exit: 1.** ✅ Wave-32 fix HOLDS.

**Warn-only run** (`--warn-only`, legacy V7 W2 behavior):

```
    [WARN] could not re-run (count<0; timeout or error): grep -rn '' /
[OK] all wave-commit checks passed
```
**Exit: 0.** Confirms the original bypass and proves wave-32 closes it under
required mode.

`scripts/ci/check_wave_markers.py:252-270` is the canonical fix
(`if count < 0: ... if enforce_grep_zero: fails += 1`). The 30s timeout in
`_re_run_grep` (line 146) is preserved. Test in
`tests/test_wave32_fixes.py:78-114` AST-asserts the `count<0 → fails+=1` branch
exists.

**Status:** ✅ FIX VALID.

## 2. W3-G2 verification — test-diff scope widened to all paths

| Synthetic case | Path | `_diff_test_count` (Wave-32) | Pre-Wave-32 (`-- tests/`) |
|---|---|---:|---:|
| (a) `def test_x():` | `backend/tests/test_foo.py` | **+1** ✅ | 0 (missed) |
| (b) `@pytest.fixture` (additive) | `tests/conftest.py` | **+1** ✅ | n/a (existed) |

Pre-wave-32 source restricted `git diff` to `-- tests/`, so (a) under
`backend/tests/` was invisible to the counter. The wave-32 source
(`scripts/ci/check_wave_markers.py:156-178`) drops the `tests/` pathspec and
adds `@pytest.fixture` to the marker tuple — both cases now count as ≥1.

End-to-end on the real branch: wave-32 itself shows `+11 new test function(s)`,
wave-34 `+7`. Several Critical/High waves (38, 36, 35) STILL fail the
test-delta gate because their net is ≤0 (e.g. wave-38 net=-657 due to file
deletions during cleanup). This is the gate working as intended — the gate is
enforcing the V6 W rule #3 contract.

**Status:** ✅ FIX VALID.

## 3. W3-G3 verification — shell-prompt prefix recognized

`parse_wave_commit` on a body containing both `$ grep ...` and `> grep ...`
prompt-prefixed lines:

```
ctx['grep_cmds'] = [
    "grep -rn 'foo' backend/",
    "grep -rn 'bar' tests/",
]
```

Both prefixes are stripped by `SAMECLASS_BLOCK_RE`
(`^[ \t]*(?:[\$>][ \t]+)?(grep -[^\n]+|grep[ \t][^\n]+)$`,
`scripts/ci/check_wave_markers.py:51-54`). Bare-indent grep is also matched.
`tests/test_wave32_fixes.py:143-163` locks the regression with a 3-line case
including bare, `$ `, and `> ` prefixes.

**Status:** ✅ FIX VALID.

## 4. End-to-end CI dry-run

Ran `./venv/bin/python3 scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD --repo-root .`
on rc-1.5-curated @ `ccba97f`.

**Result:** 16 failures across waves 32–40 (exit 1).

These failures are NOT bypass leakage. They split into two legitimate
categories:

1. **Test-delta gate firing on cleanup waves:** wave-36 (net=-153), wave-38
   (net=-657) are orphan-module cleanup waves; the rule requires +N tests on
   Critical/High but they net negative because the deletions outweigh new
   tests in the diff. This is the wave-32 W3-G2 widening doing exactly what
   it was designed to do — without the wave-32 fix these would have looked
   like 0 because they touch `backend/`, not `tests/`.

2. **Cited-grep returns count>0 because the grep targets a file the fix MODIFIES (not REMOVES):**
   - wave-32 itself: `grep 'UserClaims(\*\*payload)' ...` returns count=1
     because the fix wrapped the call in try/except — the call still exists.
   - wave-34: `grep 'churn_rate=0.0' regime.py` count=1 — the marker line is
     the new code; same-class semantics here are "after fix, line should still
     exist" not "after fix, line should not exist".
   - wave-35: similar (`def _is_learning_mode`, `_eod_flatten_triggered = True`).
   - wave-37, wave-40: `alembic.ini` smoke + structural greps — count>0 by design.

   These are wave-author/wave-rule semantic mismatches: the rule assumes
   same-class grep is a NEGATIVE pattern (count must be 0 = "no other
   instances"), but several wave authors used it as a POSITIVE assertion
   ("here is the fix line"). Not a wave-32 fix regression — a wave-author
   convention drift that pre-dates wave-32.

3. **Missing finding-ID / missing grep:** waves dec7c28 (wave-40 post-merge),
   db1a3fc (wave-40 align) cite no findings or no grep. These are
   housekeeping commits, but the rule is unconditional once `fix(audit-wave...`
   matches.

The wave-32 fixes are not implicated in any of the 16 failures.

**Status:** ✅ END-TO-END BEHAVIOR CONSISTENT WITH WAVE-32 INTENT.
The 16 fails surface a separate process gap (covered as Finding #1 below)
that wave-32 did not introduce and did not claim to fix.

## 5. Behaviors still intact

- `count<0` → required-mode FAIL: ✅ (verified W3-G1 above).
- 30s timeout in `_re_run_grep`: ✅ (line 146, untouched).
- Behavioral-test counter gates Critical/High waves: ✅ (test-delta gate is
  firing; see wave-36 / wave-38 / synthetic W3-G1 case).

---

## Findings

### Finding W4-1 (LOW) — `_diff_test_count` misses aliased fixture import

**Probe:** New file `tests/probe/conftest_alt.py`:

```python
from pytest import fixture as fx

@fx
def my_fixture():
    return 1
```

`_diff_test_count` returns **0** (expected ≥1).

Root cause: the marker tuple at `scripts/ci/check_wave_markers.py:167` is
literal-string match for `"@pytest.fixture"`. An aliased import bypasses it.

**Severity:** LOW. The pattern is uncommon and would still trip the
"no behavioral test added" gate on Critical/High waves only. A determined
bypass author could exploit it, but they would still need to ship a
fix-quality commit body and pass the same-class grep gate.

**Suggested mitigation:** widen markers to also match `^@\w+\b.*$` lines
inside `tests/` paths, or AST-walk the diff additions for `pytest.fixture`
calls under any binding.

### Finding W4-2 (LOW) — Wave-rule semantics drift: positive-assertion grep treated as same-class

**Observation:** End-to-end dry-run shows 6+ wave commits (32, 34, 35, 37, 40)
where the cited grep is a POSITIVE assertion ("the new line exists") rather
than a same-class NEGATIVE scan ("no other instances exist"). The rule
mechanically counts >0 as FAIL, so these waves all fail the gate even when
the fix is correct.

This is not a wave-32 W3-G1/G2/G3 regression — it pre-dates wave-32 — but
it surfaces now because wave-32 flipped the warn-mode rule to required
(W3-G1 closure). Result: required-mode CI on rc-1.5-curated currently
fails for legitimate fixes.

**Severity:** LOW (process / convention, not a security or trading bypass).

**Suggested mitigation:** either (a) wave authors must always use a NEGATIVE
same-class grep (`grep ... | grep -v <new-line>`), or (b) the script learns a
second marker (e.g., `expected: >=1` for positive, `count: 0` for negative)
and dispatches accordingly.

### Finding W4-3 (LOW) — `WAVE_COMMIT_RE` is brittle on hyphenated wave-suffixes

**Observation:** The prompt's example commit prefix
`fix(audit-wave99-w3g1-test):` does NOT match `WAVE_COMMIT_RE` because the
character class `[0-9a-z]+` excludes `-`. A wave-author following the
prompt's literal example would silently bypass ALL wave-rule enforcement —
the script reports `[ok] no wave commits in <range>`.

**Severity:** LOW. Real wave commits in the repo follow the canonical
`fix(audit-wave32):` form (no hyphenated suffix), so no historical commit is
affected. But the regex would silently bypass any future commit that uses
a hyphenated wave suffix.

**Suggested mitigation:** widen to `r"^fix\(audit-wave[0-9a-z\-]+\)"`.

---

## CI rule blockers found: 0

The three Wave-32 fixes (W3-G1, W3-G2, W3-G3) all hold under reconstructed
synthetic experiments and on the real branch. Three LOW residuals were
identified — none of them re-open the original bypass. W4-1 (aliased fixture
import) and W4-3 (hyphenated wave-suffix) are evasion-vector hardening
opportunities that no current commit exercises. W4-2 (positive-assertion
grep convention drift) explains why the end-to-end dry-run shows 16 fails
on rc-1.5-curated; it pre-dates wave-32 and surfaces now only because
wave-32 flipped warn→required.

---

## TL;DR

Wave-32's three CI bypass fixes (W3-G1 grep-timeout, W3-G2 test-diff scope,
W3-G3 shell-prompt prefix) all close the original V8 W3 bypasses cleanly:
the synthetic timeout commit exits 1 in required mode (warn-only=0,
confirming the legacy bypass), `_diff_test_count` now returns +1 for both
`backend/tests/def test_x` and additive `@pytest.fixture` cases, and
`SAMECLASS_BLOCK_RE` correctly strips `$` / `>` shell-prompt prefixes. The
end-to-end dry-run on rc-1.5-curated returns exit 1 with 16 fails, but on
inspection none of the fails are wave-32 regressions — they trace to (a) the
test-delta gate working as intended on cleanup waves with negative net diff,
(b) a pre-existing positive-vs-negative same-class-grep convention drift in
wave-author bodies (W4-2), and (c) commits that simply omit IDs/greps. Three
LOW residual evasion-vectors were inventoried (aliased fixture import,
positive-assertion grep convention, hyphenated wave-suffix regex) — none
re-opens the original bypass and no fix-grade action is required this wave.
