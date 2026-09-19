# Master Platform Strategy Summit — Evidence Bundle

**Date**: 2026-04-23
**Parent doc**: `../MASTER_PLATFORM_STRATEGY_SUMMIT.md`

This directory is the evidence bundle underpinning the summit. Each file is a snapshot of the platform state at the time of the review.

## Contents

### Repo / deploy state
- `git_status.txt` — full working-tree state (confirms 4 dirty files + 90+ untracked reports)
- `git_log_recent.txt` — last 30 commits
- `worktree_diff_stat.txt` — summary of the 4 backward reverts
- `worktree_diff_code.txt` — actual diff of `adaptive_exits.py` + `pyramider.py`
- `container_ps.txt` — running containers
- `container_inspect.json` — full `docker inspect` for `intra-api-1`

### Runtime config
- `resolved_config_snapshot.json` — resolved (env + defaults) runtime config as of tick snapshot
- `runtime_config_snapshot.json` — code-default snapshot (no env)

### Brain state (current)
- `brain_manifest.json` — gen 115, 370 trades, PnL −$619.75, best_sharpe 3.44, ml_trained=true, 79 features
- `brain_learning_state.json` — retrain_count=115, drift_events=0
- `brain_ml_state.json` — is_trained=true, accuracy 0.617, precision 0.515, recall 0.715
- `brain_evolved_params.json` — Apr-15 mtime; memory is fresher (gen 115)
- `brain_governance_state.json` — frozen=false, halted=false, drawdown_limit=0.20

## Cross-references

| Topic | File to read | Supporting evidence here |
|---|---|---|
| "Live ≠ repo" claim | `PLATFORM_SYSTEM_MAP.md §20` | `git_status.txt`, `git_log_recent.txt`, `worktree_diff_*.txt`, `container_inspect.json` |
| Drawdown-kill inversion (I-02) | `DEAD_CODE_AND_BYPASS_AUDIT.md D-01` | `resolved_config_snapshot.json` vs `runtime_config_snapshot.json` |
| Brain is genuinely learning | `ORGANISM_FEATURE_STATUS.md §1–7` | `brain_manifest.json`, `brain_learning_state.json`, `brain_ml_state.json` |
| Evolved-params disk stale | `ORGANISM_FEATURE_STATUS.md §7` | `brain_evolved_params.json` Apr-15 mtime vs manifest gen 115 |
| Exp4 reverted | `MASTER_ISSUE_LEDGER.md I-04` | `worktree_diff_code.txt` |
| G3 reverted | `MASTER_ISSUE_LEDGER.md I-05` | `worktree_diff_code.txt` |
| Container not at HEAD | `MASTER_ISSUE_LEDGER.md I-12` | `container_inspect.json` |

## How to verify independently

```
# Live commit fingerprint (from container file hashes, as documented)
docker exec intra-api-1 md5sum /app/backend/organism/live_engine.py
# Should match ce06d41 version, not 33d6138

# Repo HEAD
git rev-parse HEAD   # should show 33d61386d3f332286f92cc074caeeb1eedb68fc7

# Dirty tree
git status --short   # shows 4 M'd files

# Brain age
stat organism_brain/manifest.json
stat organism_brain/evolved_params.json   # expect Apr-15 vs Apr-23 respectively
```
