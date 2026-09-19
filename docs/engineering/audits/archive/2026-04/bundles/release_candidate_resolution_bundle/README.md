# Release Candidate Resolution Sprint — Evidence Bundle

**Parent report**: `../RELEASE_CANDIDATE_RESOLUTION_REPORT.md`
**Sprint outcome**: RC commit **`eb90fa3`**; worktree clean; drawdown-kill canonicalized; 10/10 tests pass.

## Contents

| File | Purpose |
|---|---|
| `sprint_summary.txt` | One-line facts for each key field |
| `git_status_after.txt` | Worktree state at sprint end (clean of modifications) |
| `git_log_rc_delta.txt` | 8 commits that form the RC delta (live → HEAD) |
| `full_rc_diff_stat.txt` | File-by-file diff stat of the entire RC |
| `commit_0ac6e2d_full.txt` | Full metadata for canonical-drawdown commit |
| `commit_0ac6e2d_stat.txt` | Diff stat for canonical-drawdown commit |
| `commit_eb90fa3_full.txt` | Full metadata for compose-alignment commit |
| `commit_eb90fa3_stat.txt` | Diff stat for compose-alignment commit |
| `test_summary.txt` | Focused pytest run output (governance + H5) |

## Verifying independently

```bash
# Repo state
git rev-parse HEAD           # expect eb90fa3
git status --short           # expect empty (modulo untracked docs)

# RC delta
git log --oneline ce06d41..HEAD
# expect 8 commits ending at eb90fa3

# Tests
./venv/bin/python -m pytest tests/test_governance_drawdown_canonical.py \
    tests/test_h5_settings_governance.py --timeout=15 -q
# expect 10 passed

# Canonical drawdown-kill behavior
ORGANISM_DRAWDOWN_KILL_PCT=0.20 ./venv/bin/python -c "
from backend.organism.governance import GovernanceController, DEFAULT_DRAWDOWN_KILL_PCT
g = GovernanceController()
assert g._drawdown_limit == 0.20
assert g._drawdown_limit_source == 'env'
print('OK: env=0.20 wins, source=env, default=', DEFAULT_DRAWDOWN_KILL_PCT)
"
```

## Claims supported by this bundle

1. **Live = `ce06d41`**: no deploy occurred; `container_inspect` from the earlier summit confirms.
2. **HEAD = `eb90fa3`**: `git_log_rc_delta.txt` + `git rev-parse HEAD`.
3. **Worktree clean**: `git_status_after.txt` shows no modifications (only untracked reports).
4. **Two new commits**: `commit_0ac6e2d_*` and `commit_eb90fa3_*`.
5. **Tests green**: `test_summary.txt` — 10 passed, 0 failed.
6. **RC composition**: `full_rc_diff_stat.txt` — 16 files, +1,144/−13 lines.
