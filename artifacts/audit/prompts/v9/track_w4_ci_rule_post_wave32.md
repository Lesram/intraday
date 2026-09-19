# Track W4 v9 — Verify Wave-32 CI Rule Fixes Close the Bypasses

V8 W3 found 3 CI gaps. Wave-32 fixed them (W3-G1 grep timeout, W3-G2 test-diff scope, W3-G3 shell-prompt prefix). **W4 confirms each fix actually closes the bypass** by reconstructing the original W3 synthetic-commit experiment and showing the new behavior.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`.

## Method

### 1. W3-G1 verification — grep-timeout now FAILS in required mode

Construct a synthetic commit citing a grep that will time out:

```
# In a sandboxed git worktree:
git commit --allow-empty -m "$(cat <<'EOF'
fix(audit-wave99-w3g1-test): synthetic w3-g1 timeout test (CRITICAL)

Closes:
- AA-C-1 (test).

Same-class scan:
  grep -rn '' /  # pathological — recurses from root, will time out at 30s

count: 0
EOF
)"
```

Run `scripts/ci/check_wave_markers.py` against this commit in **required mode**. Expected: exit 1 (fails). Pre-wave-32 this would have exited 0 (silent pass).

### 2. W3-G2 verification — test-diff scope widened to all paths

Construct two synthetic commits:
- (a) Adds `def test_x():` to `backend/tests/test_foo.py` (NOT under tests/) — should COUNT as a behavioral test addition.
- (b) Adds `@pytest.fixture` to `tests/conftest.py` — should COUNT.

Run `_diff_test_count` directly on each commit. Expected: both return ≥1.

### 3. W3-G3 verification — shell-prompt prefix recognized

Construct a synthetic commit body with:
```
$ grep -rn 'foo' backend/
> grep -rn 'bar' tests/
```

Run `parse_wave_commit` on the body. Expected: `grep_cmds` contains 2 commands (the shell prompts stripped).

### 4. End-to-end CI dry-run

Run `check_wave_markers.py --base HEAD~10 --head HEAD` on the actual rc-1.5-curated branch. Confirm:
- All wave 32-40 commits PASS (they follow the format).
- Any non-conforming commit FAILS.

### 5. Observe behaviors that should still BE intact

- W3 contract from V8: `count<0` for grep timeout/error must FAIL in required mode (post-wave-32).
- The 30s timeout in `_re_run_grep` is preserved.
- The behavioral-test counter still gates Critical/High waves.

### 6. Identify residual gaps

Probe edge cases:
- What if a grep cites a command that's syntactically valid but returns non-zero exit code (no matches but `grep -q` style)? Should count = 0.
- What if a wave commit cites multiple greps and ONE of them times out, others succeed? Aggregate behavior?
- What if `pytest.fixture` is imported `from pytest import fixture as fx` and used as `@fx`? Detection misses?
- Can the SAMECLASS_BLOCK_RE be fooled by an inline `# grep -rn '...'` comment in code (not in commit body)?

## Output

`artifacts/audit/v9_reports/track_w4_ci_rule_post_wave32.md` with:
- W3-G1 timeout test result (required mode, expected exit 1)
- W3-G2 widened-scope test result
- W3-G3 prompt-prefix test result
- End-to-end dry-run result
- Residual gap inventory (if any)
- "CI rule blockers found: N" + TL;DR

Quality bar: 1-3 findings. Edge cases or residuals only — the core W3 fixes should hold. End with one-paragraph TL;DR.
