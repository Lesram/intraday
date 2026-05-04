# Release Candidate Resolution Report

**Date**: 2026-04-23
**Sprint**: RELEASE-CANDIDATE RESOLUTION SPRINT (offline-only)
**Result**: ✅ Resolved. Repo is now on a clean, unambiguous release-candidate commit.

---

## 0. TL;DR

| | Before sprint | After sprint |
|---|---|---|
| Live container commit | `ce06d41` | `ce06d41` (unchanged — no deploy) |
| Repo HEAD | `33d6138` | **`eb90fa3`** |
| Worktree state | 4 files dirty (backward reverts) | **clean** |
| Drawdown-kill sources | 3 (env 0.20 / code 0.05 / compose 0.03) | **1 canonical** (code default 0.05; env overrides with startup validator + drift warn) |
| RC intent | ambiguous | **unambiguous: `eb90fa3` is the next RC** |
| Exp4 in RC? | — | **IN** |

## 1. Current live commit

**`ce06d41`** ("experiment(instrumentation): confidence inversion side-by-side logging [Exp 3 prep]"). Confirmed via 5/5 file-hash fingerprint documented in `DEPLOY_VERIFICATION_DEPLOY2_33d6138.md §3` and `PLATFORM_STATE_SNAPSHOT_APR23.md §1`. Container built 2026-04-16T02:41Z from worktree at `ce06d41`. No deploy action taken in this sprint.

## 2. Current HEAD

**`eb90fa3`** as of end-of-sprint.

Previous HEAD was `33d6138`. Two new commits added during this sprint:

| Commit | Summary |
|---|---|
| `0ac6e2d` | `fix(governance): canonical drawdown-kill resolution + startup validator` |
| `eb90fa3` | `fix(compose): align docker-compose.yml drawdown-kill fallback with code default` |

## 3. Was the worktree ambiguous?

**Yes — now resolved.** At sprint start the worktree had 4 modified files, all diffs pointing *backward* toward `ce06d41` (live container) rather than forward toward HEAD. They undid `b97f903` (Exp4) and part of `15cc0a4` (G3 NaN pyramid guard) — reverting hardening and experiment commits the strategy summit recommended to keep.

Resolution: `git restore` the 4 files to HEAD (no commit needed; simply discarded the backward drift). Worktree is now clean.

| File | Action | Reason |
|---|---|---|
| `backend/organism/adaptive_exits.py` | restored | reverted Exp4 widening; Exp4 belongs in next RC |
| `backend/organism/pyramider.py` | restored | reverted G3 NaN guard; defensive guard with negligible cost |
| `scripts/generate_experiment_observation_report.py` | restored | reverted giveback observation tooling that supports Exp4 post-close analysis |
| `monitoring/memory_monitoring.json` | restored | threshold edit; non-material without corresponding metric change |

## 4. Exact blockers found and their resolution

| Blocker | Source | Resolution | Evidence |
|---|---|---|---|
| Worktree dirty (I-01, P0) | 4 files reverted backward toward live container | `git restore` to HEAD | `release_candidate_resolution_bundle/git_status_before.txt` vs `git_status_after.txt` |
| Drawdown-kill inconsistency (I-02, P0) | `.env=0.20` vs code `0.05` vs `docker-compose.yml=0.03` | Canonical resolution in `governance.py` + startup validator + drift warn + compose-fallback alignment | Commits `0ac6e2d` + `eb90fa3`; 6 new tests pass |
| Release-candidate ambiguity | No documented next-target commit; HEAD state unclear | RC defined: **`eb90fa3`**. Composition documented. See `RELEASE_CANDIDATE_COMPOSITION.md` | This report |
| Hardening compatibility unverified | Unclear whether G1–G3, H1/H2, CAP/HALT, H5, alerts ship together cleanly | Verified — no overlapping edits; `33d6138` alerting is cumulative and depends on `bb5cbb5` and `679ffd2`, so single bundle is correct | `git show --stat` on each commit (this report §6) |

## 5. Exact code changes made in this sprint

### 5.1 Commit `0ac6e2d` — canonical drawdown-kill resolution

Files:
- `backend/organism/governance.py` (+58 / −4 lines)
- `tests/test_governance_drawdown_canonical.py` (new, 81 lines)

Key changes in `governance.py`:
- Added module-level constants `DEFAULT_DRAWDOWN_KILL_PCT = 0.05`, `DEFAULT_DRAWDOWN_COOLDOWN_S = 3600`, `DEFAULT_MAX_CHANGES_PER_DAY = 100`, `_DRAWDOWN_KILL_DRIFT_WARN_RATIO = 1.5`
- Explicit env-vs-default resolution that records `_drawdown_limit_source` as `"env"` or `"code_default"`
- Startup INFO log: `Governance drawdown_kill_pct=%.4f source=%s code_default=%.4f cooldown_s=%d`
- Startup WARN log when env override > 1.5× code default (drift detection)

No behavior change to the kill-switch logic itself.

### 5.2 Commit `eb90fa3` — compose fallback alignment

Files:
- `docker-compose.yml` (+3 / −2 lines)

Changes:
- `ORGANISM_DRAWDOWN_KILL_PCT` fallback `0.03 → 0.05` (matches `DEFAULT_DRAWDOWN_KILL_PCT`)
- `ORGANISM_DRAWDOWN_COOLDOWN_S` fallback `300 → 3600` (matches `DEFAULT_DRAWDOWN_COOLDOWN_S`)
- Inline comment referencing the code constant as source of truth

Only affects the fallback path when no env file is present. The operational `.env` file (read via `env_file:` in `docker-compose.paper.yml`) still wins at runtime.

### 5.3 Tests

```
tests/test_governance_drawdown_canonical.py  6 tests, all pass
tests/test_h5_settings_governance.py         4 tests, all pass (regression check)
```

Full test run output in `release_candidate_resolution_bundle/test_summary.txt`.

## 6. Hardening-bundle compatibility matrix

Verified by `git show --stat` on every commit between `ce06d41` (live) and `eb90fa3` (new HEAD):

| Commit | Summary | Files touched | Depends on |
|---|---|---|---|
| `15cc0a4` | G1 exit-level restore + G2 cooldown-on-success + G3 NaN pyramid guard | `live_engine.py`, `adaptive_exits.py`, `pyramider.py` | — |
| `b97f903` | Exp4 chop trailing-stop giveback control | `adaptive_exits.py`, observation tooling script | — |
| `679ffd2` | H1 prod risk-budget cap + H2 feature drift guard | `kelly_sizer.py`, `ml_signal.py` | — |
| `bb5cbb5` | Per-trade notional cap + daily max-loss circuit breaker | `live_engine.py` | — |
| `c306074` | H5 settings API enforces frozen/halted | `backend/api/routes/settings.py`, `tests/test_h5_settings_governance.py` | — |
| `33d6138` | Slack/webhook alerting wired | 4 existing modules, additive try/except blocks | **depends on `bb5cbb5` + `679ffd2`** (calls their event paths) |
| `0ac6e2d` | Canonical drawdown-kill | `governance.py`, new test | — |
| `eb90fa3` | Compose alignment | `docker-compose.yml` | `0ac6e2d` (constant) |

**Compatibility verdict**: No overlapping edits to the same line/function. `33d6138` is cumulative — it wires alert paths added by `bb5cbb5` and `679ffd2`, so those commits must ship together. All 8 commits form a coherent, monotonically-forward bundle.

## 7. Exact recommended next release candidate

**`eb90fa3`** — current HEAD on branch `main`.

Contents relative to live (`ce06d41`):
- G1/G2/G3 mechanical guards
- Exp4 chop trailing-stop giveback experiment (observation-tooling included)
- H1 production risk-budget cap + H2 feature drift guard
- Per-trade notional cap + daily max-loss circuit breaker (env-gated; default off)
- H5 settings API enforces frozen/halted
- Slack/webhook alerting
- Canonical drawdown-kill + startup validator
- `docker-compose.yml` fallback alignment

No worktree modifications. No cherry-picks required. Tag candidate: `rc-2026-04-23-eb90fa3`.

## 8. Exact deploy order after this sprint

Deployment is **out of scope for this sprint**. When you choose to deploy the RC, the sequence is documented in `RELEASE_CANDIDATE_DEPLOY_PLAN.md`. Summary:

1. Set `.env` — `ORGANISM_MAX_NOTIONAL`, `ORGANISM_MAX_DAILY_LOSS`, `SLACK_WEBHOOK_URL`, review `ORGANISM_DRAWDOWN_KILL_PCT`
2. Build image from HEAD `eb90fa3`; verify fingerprint
3. Pre-open diagnostic pass (nightly_scheduler)
4. Rolling container restart via docker-compose
5. Post-deploy: verify `/health` and the new startup log line `Governance drawdown_kill_pct=...`
6. 5–10 session observation window before next algorithmic change

## 9. Files created by this sprint

| File | Purpose |
|---|---|
| `RELEASE_CANDIDATE_RESOLUTION_REPORT.md` | This report |
| `release_candidate_resolution_bundle/` | Evidence bundle |
| `RELEASE_CANDIDATE_COMPOSITION.md` | What's in the RC and why |
| `RELEASE_CANDIDATE_DIFF_MAP.md` | File-by-file diff of live → RC |
| `RELEASE_CANDIDATE_DEPLOY_PLAN.md` | Exact deploy sequence + gates |

## 10. What still blocks the next deploy

None of the *sprint-scope* blockers remain. The following remain as **deploy-time prerequisites** (outside sprint scope):

1. Set `ORGANISM_MAX_NOTIONAL` > 0 in `.env` (circuit-breaker is env-gated default-off)
2. Set `ORGANISM_MAX_DAILY_LOSS` > 0 in `.env`
3. Set `SLACK_WEBHOOK_URL` in `.env` (alerts are otherwise silent)
4. Decide whether to keep `ORGANISM_DRAWDOWN_KILL_PCT=0.20` or tighten it. The new startup validator will WARN either way that 0.20 is 4× the code default; the choice is deliberate and documented.
5. Image rebuild from `eb90fa3` and file-hash verification

None of the above require code changes.

— End of Release Candidate Resolution Report —
