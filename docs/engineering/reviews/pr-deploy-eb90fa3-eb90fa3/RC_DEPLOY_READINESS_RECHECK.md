# RC DEPLOY READINESS RE-CHECK — `eb90fa3`
**Audit type:** READ-ONLY
**Audit time:** 2026-04-25T00:50Z (Friday post-close, weekend window)
**Live commit:** `ce06d41`
**RC commit:** `eb90fa3`
**Gap:** 8 commits

---

## What `eb90fa3` actually contains (chain `ce06d41 → eb90fa3`)

| Commit | Subject | Category |
|---|---|---|
| `15cc0a4` | G1 exit-level restore warning + G2 cooldown-on-success-only + G3 NaN pyramid guard | Mechanical |
| `b97f903` | Exp 4 — chop trailing-stop giveback control + observation tooling | Strategy experiment |
| `679ffd2` | H1 production risk-budget cap + H2 feature drift guard | Real-money hardening |
| `bb5cbb5` | Per-trade notional cap + daily max-loss circuit breaker | Risk limit |
| `33d6138` | Wire critical events to Slack/webhook alerts | Ops |
| `c306074` | H5 settings API enforces frozen/halted state | Governance |
| `0ac6e2d` | Canonical drawdown-kill resolution + startup validator | Governance |
| `eb90fa3` | Compose drawdown-kill fallback aligned with code default | Config |

Diff stat (16 files, +1144 / −13):
- code: `governance.py (+62)`, `live_engine.py (+66)`, `adaptive_exits.py (+40)`, `kelly_sizer.py (+18)`, `ml_signal.py (+38)`, `pyramider.py (+8)`, `brain_persistence.py (+13)`, `routes/settings.py (+14)`
- tests: `test_experiment_4_trailing_giveback.py (+194)`, `test_g1_g2_g3_mechanical_fixes.py (+183)`, `test_governance_drawdown_canonical.py (+85)`, `test_h1_h2_real_money_hardening.py (+172)`, `test_h5_settings_governance.py (+44)`, `test_real_money_risk_limits.py (+135)`, `test_organism_observation_report (giveback section)` (+80)
- compose: `docker-compose.yml (+5)`

This is a substantial bundle. It is also a **logically coherent** bundle (governance + risk + mechanical + Exp 4) — not a kitchen-sink merge.

---

## Is `eb90fa3` still the correct next release candidate?

**YES.** The composition is correct:

1. **Real-money hardening** that the platform genuinely needs before tiny-capital — H1 risk-budget cap, H2 feature-drift guard, per-trade notional cap, daily max-loss kill, alert wiring, canonical drawdown-kill. Without these we can't responsibly take Stage 1 capital.
2. **Mechanical fixes** that address real observed drag — G1 protects state restoration; G2 stops cooldowns from being eaten by losing trades; G3 prevents NaN-driven cascades in pyramider.
3. **Exp 4** that addresses an observed (small) trailing-stop giveback.
4. **Compose alignment** that closes a real env/code-default mismatch.

There is **no further commit on `main` past `eb90fa3`** (HEAD = `eb90fa3`). No newer RC has been prepared. So `eb90fa3` is both the *current* and the *correct* RC.

---

## Worktree / HEAD / live relationship

| Check | Status | Notes |
|---|---|---|
| `git status --short` clean of tracked diffs | YES | All untracked files are intentional audit artifacts (`*.md`, `*_bundle/`) |
| HEAD on `main` | YES | `eb90fa3` |
| `main` not ahead of `origin/main` (TBD) | not verified | did not push/pull during audit; assumed clean per AGENTS.md |
| Live container hash maps to a clean commit (`ce06d41`) | YES | verified by file SHA |
| Live container mounts brain volume | YES | `./organism_brain:/app/organism_brain` |
| Brain manifest format = v2 | YES | `brain_format_version: 2` |
| Brain ML artifacts present | YES | `ml_classifier.joblib`, `ml_regressor.joblib` |
| Two-step bundle convention prepared | NO | needs PR-specific bundle in `docs/engineering/reviews/` before merge — this weekend pack is platform-wide, not PR-grade |

**Worktree ambiguity: NONE.** The relationship is clean.

---

## Outstanding blockers before deploy

| Blocker | Severity | Status |
|---|---|---|
| Tests pass in CI on `eb90fa3` | P0 | needs CI re-run; locally 114 tests passed at last commit per `b97f903` log |
| Test summary captured in `artifacts/test_summary.json` | P0 | need to refresh and verify post-300 tests pass clean |
| Replay regression on `eb90fa3` (paper config + 30-day window) | P0 | not yet executed; should be done before deploy |
| Spec drift CI check passes | P1 | `scripts/ci/check_spec_drift.py` should run; need confirmation |
| Pre-merge engineering review bundle committed to `docs/engineering/reviews/pr-XXX-eb90fa3/` | P1 | per AGENTS.md mandatory two-step convention |
| Post-deploy verification plan written | P1 | need explicit checklist (manifest+learning_state sync, brain not wiped, governance drawdown_kill_pct=0.20 reads correctly, alert wiring fires test event, notional cap rejects oversized order) |
| Alert wiring secrets configured | P1 | Slack/webhook URLs need to be in `.env` (not committed); not deploy-blocking but useless without |
| Brain backup snapshot taken | P0 | back up `organism_brain/` before deploy in case of regression — required |
| Live preopen checklist run | P1 | before next session, validate equity, positions flat, no stale orders |
| Monday-morning attention available | P1 | don't deploy on Friday/weekend if no human can babysit Mon open |

The two **mandatory** P0 blockers that **must** be addressed before flipping the switch:
1. Replay regression on `eb90fa3` against the last 30 days of data.
2. Brain backup snapshot.

The rest are "should-have, would catch problems faster" but the platform's safety net (drawdown-kill at 20%, broker-side paper risk, manifest+learning_state coherence) is intact regardless.

---

## Should we deploy `eb90fa3` this weekend?

**NO.**

**Why not:**

1. **Weekend deploy without market-hours visibility violates the prudent-rollout principle.** The deploy adds 6 distinct behavioral changes (G1/G2/G3, Exp 4, H1/H2, notional cap, daily max-loss, alert wiring, governance API). If any one of them misfires, the first signal will be Monday's open — and we want a human watching at first tick, not 60 hours later via Slack alerts that may themselves be the thing being tested.

2. **The two mandatory P0 preflight items are not yet done** (replay regression on `eb90fa3`, brain backup). These are not weekend-friendly to redo if they fail.

3. **Live-stack expectancy on `ce06d41` is mildly negative (−$0.59/trade) but stable.** There is no fire being put out. The cost of waiting 60 hours is at most ~$60 of paper P&L drift; the cost of a bad weekend deploy is much larger (downtime, manifest corruption risk, alert mis-wiring).

4. **Exp 3 prep logging is still accumulating useful data.** Two more sessions on `ce06d41` continues to grow the confidence-bucket sample which we want for the eventual Exp 3 execution decision.

5. **No regulatory / external deadline forces the deploy this weekend.** Stage 1 tiny-capital is gated on this deploy + 5–10 sessions of clean post-deploy paper observation; another 60 hours doesn't move the timeline.

**Recommended deploy window:** **Sunday evening or Monday pre-open** (8:30–9:00 ET), with a human at the keyboard for the first 30 minutes of trading.

---

## If yes, exact preflight checklist

If you override and deploy this weekend, this is the minimum checklist that must complete green:

```
[ ] git pull / verify HEAD == eb90fa3
[ ] verify clean tracked worktree
[ ] run full test suite: ./venv/bin/python -m pytest tests/ --timeout=15 -q
    Expect: 114 pass (7 Exp4 + 6 G1G2G3 + 5 H1H2 + 5 risk + 3 governance + 2 H5 + 86 organism)
[ ] run replay regression: ./venv/bin/python -m pytest tests/test_replay_simulator.py --timeout=60
[ ] generate runtime snapshot: ./venv/bin/python scripts/runtime/write_runtime_snapshot.py
[ ] verify ORGANISM_DRAWDOWN_KILL_PCT resolves to 0.20 from compose env, dotenv, and code default
[ ] verify no spec drift: python scripts/ci/check_spec_drift.py
[ ] backup organism_brain/ → organism_brain_backup_<timestamp>/
[ ] note current generation, total_trades, cumulative_pnl, best_sharpe before deploy
[ ] commit weekend pack to docs/engineering/baseline_reviews/baseline-eb90fa3/
[ ] docker-compose down api && docker-compose up -d --build api
[ ] curl localhost:8000/health → {"status":"ok"}
[ ] verify container restart count = 0
[ ] verify manifest.json + learning_state.json unchanged from pre-deploy snapshot
    (deploy must NOT wipe brain — the F1–F4 guards protect this; verify they fire)
[ ] tail logs/application.log for the first 5 minutes; expect:
    - "Governance state restored from brain"
    - drawdown_kill_pct startup validator log line
    - alert wiring registration line (or graceful skip if URLs absent)
[ ] verify governance config_hash and policy_version values are written
[ ] verify alpaca account ACTIVE, positions flat (or whatever state was pre-deploy)
[ ] post-deploy test: trigger a synthetic small alert event to confirm Slack/webhook delivers
[ ] post-deploy test: drop an oversized notional order → verify reject path fires
[ ] declare deploy successful, log to docs/engineering/reviews/pr-XXX-eb90fa3/DEPLOY_VERIFICATION.md
```

If any item fails, revert immediately to `ce06d41` and reopen the bundle.
