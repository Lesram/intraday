# Release Candidate Composition

**RC commit**: `eb90fa3`
**Base (live)**: `ce06d41`
**Delta**: 8 commits

This document states **exactly** what is IN the candidate and what is OUT, with an explicit justification for each decision.

---

## A. IN the release candidate

### A.1 G1/G2/G3 mechanical guards — `15cc0a4`
**Status**: IN
**Justification**:
- G1 (exit-level restore warning): promotes a silent DEBUG to WARNING and marks `exit_levels_failed=True` so safety-net exits can handle positions running without stop-loss after restart. Corrects a known silent-failure mode with no downside.
- G2 (cooldown-on-success-only): removes a 30-second dead zone where a failed exit couldn't be retried. Purely corrective.
- G3 (NaN pyramid guard): defensive `math.isfinite()` early-return if streaming data corrupts `current_price`. Zero cost, eliminates a class of silent disable.
- All three are offline-only, no behavior change on the happy path, explicitly marked by the author as "no interaction with Exp1A/2/3".

### A.2 Exp4 — chop trailing-stop giveback control — `b97f903`
**Status**: IN (moved up from "queue" to "ship with bundle")
**Justification**:
- Targets the $195 of MFE giveback observed over 5 sessions — the single largest non-pyramid-cut leak per `TRADING_EDGE_BASELINE_REPORT`.
- Variant A (widen to 5.0× ATR in chop) is the default; variant B (disable trailing in chop) is one-line flip-switchable via `_EXP4_CHOP_TRAIL_MODE`.
- Non-chop trailing unchanged. stop_loss unchanged. timeout/max_hold unchanged. Reversibility is trivial.
- Observation tooling (giveback section of daily report) is included in the same commit and is required to evaluate Exp4 post-deploy.
- Strategy-summit recommendation: **do not queue Exp4 behind the hardening bundle; ship together**. The hardening adds safety. Exp4 adds potential edge. They do not interact.

### A.3 H1 production risk-budget cap + H2 feature drift guard — `679ffd2`
**Status**: IN
**Justification**:
- H1: completes a latent real-money safety. `_RISK_BUDGET_PER_TRADE=0.25%` was defined but never applied in the production Kelly path. This closes a gap that would have allowed production sizing to exceed the intended per-trade cap once learning mode ended (which happened at trade 200 — two weeks ago).
- H2: when >20% of trained features are missing at inference, return a neutral signal instead of acting on degraded inference. Fail-safe, additive.
- `33d6138` alerting depends on H2's event path (`SYSTEM_ERROR, WARNING` on neutralization). H2 MUST ship before or with alerts.

### A.4 Per-trade notional cap + daily max-loss circuit breaker — `bb5cbb5`
**Status**: IN (env-gated default-off; code must be in the image to ever enable)
**Justification**:
- Both are required real-money safety controls per `REAL_MONEY_GAP_MAP.md §3`.
- Defaults are 0 (disabled), so deployment without setting the envs is behavior-identical to current live. Inert until explicitly enabled.
- `33d6138` alerting depends on this commit's `halt_trading()` call site (RISK_VIOLATION, CRITICAL on daily-loss halt). Must ship before or with alerts.

### A.5 H5 settings API enforces frozen/halted state — `c306074`
**Status**: IN
**Justification**:
- Closes a governance bypass: previously any authenticated user could modify organism/trading/ML settings while the organism was explicitly frozen or halted.
- Entirely in `backend/api/routes/settings.py`; does not touch organism core.
- 4 regression tests in the same commit; all pass at HEAD.

### A.6 Slack/webhook alerting wired — `33d6138`
**Status**: IN
**Justification**:
- Wires `send_alert()` to 4 critical event paths (daily-loss halt, forensic guard, brain-save guard block, feature-drift neutralization).
- All hooks wrapped in try/except; alerting failure cannot crash trading logic.
- No secrets committed — `SLACK_WEBHOOK_URL` is env-only.
- Cumulative: depends on `bb5cbb5` (event path #1) and `679ffd2` (event path #4). Must be the last commit in the bundle.

### A.7 Canonical drawdown-kill + startup validator — `0ac6e2d` (new, this sprint)
**Status**: IN
**Justification**:
- Eliminates the three-way split (env 0.20 / code 0.05 / compose 0.03) by establishing one canonical resolution path.
- Adds observability: operators now see the resolved value, its source, and the code default at startup in a single log line.
- Adds a drift warning when env override exceeds 1.5× the code default — makes the 0.20 runtime value explicit in logs every restart.
- 6 new tests, all pass.

### A.8 docker-compose.yml fallback alignment — `eb90fa3` (new, this sprint)
**Status**: IN
**Justification**:
- Brings `docker-compose.yml` fallbacks (`0.03` / `300`) in line with `DEFAULT_DRAWDOWN_KILL_PCT=0.05` and `DEFAULT_DRAWDOWN_COOLDOWN_S=3600` in `governance.py`.
- Only affects fallback path when no env file is present. Operational `.env` still wins via `env_file` in `docker-compose.paper.yml`.

---

## B. OUT of the release candidate

### B.1 Exp3B — confidence inversion formula change
**Status**: OUT
**Justification**:
- The 7-session inversion pattern weakened on the Apr-21 session (high-confidence bucket won for the first time).
- Strategy-summit recommendation: do not ship Exp3B until 2+ more sessions confirm or falsify.
- Exp3 *observation* (already live on `ce06d41`) continues to collect data.

### B.2 Phase C — ranking_score / direction / expected_return / size split
**Status**: OUT (backlog)
**Justification**:
- Larger architectural change documented in `CLAUDE.md`.
- Should be attempted only after Exp4 has had 5–10 sessions of observation AND expectancy trend is determined.

### B.3 Exploration dead-code removal (I-09)
**Status**: OUT (this bundle)
**Justification**:
- Not a correctness blocker, only a maintainability issue.
- Candidate for a follow-up cleanup PR after the hardening bundle proves stable in live.
- Touching `live_engine.py` now introduces merge risk with Exp4 iteration. Defer.

### B.4 Confidence-authority centralization (I-08)
**Status**: OUT (this bundle)
**Justification**:
- Architectural cleanup. No hidden bypass, no risk.
- Best done when confidence formula is re-evaluated post-Exp3.

### B.5 Calibration-persistence-across-retrain (I-13)
**Status**: OUT (this bundle)
**Justification**:
- Addresses a one-epoch uncalibrated window after each retrain. Real impact but small per-retrain window.
- Requires brain-persistence schema change; touchpoint is Full Patch F territory.
- Ship after hardening bundle is stable.

### B.6 Position-loss auto-close / sector-notional cap / weekly max-DD halt
**Status**: OUT (this bundle; Stage-1 gate)
**Justification**:
- All three are Stage-1 real-money prerequisites per `REAL_MONEY_GAP_MAP.md`.
- None are required for continued paper trading.
- Prepare in parallel while the hardening bundle runs in paper.

---

## C. Compatibility + ordering guarantees

### C.1 No overlapping edits
Verified by `git show --stat` on every commit. Each touches a distinct surface area, or touches the same file in additive/orthogonal regions:

| File | Commits touching it |
|---|---|
| `backend/organism/live_engine.py` | `15cc0a4` (G1/G2) + `bb5cbb5` (cap/halt hooks). Additive, different functions. |
| `backend/organism/adaptive_exits.py` | `15cc0a4` (G1) + `b97f903` (Exp4). Additive, different methods. |
| `backend/organism/pyramider.py` | `15cc0a4` (G3 NaN guard). Only touched once. |
| `backend/organism/kelly_sizer.py` | `679ffd2` (H1). Only touched once. |
| `backend/organism/ml_signal.py` | `679ffd2` (H2). Only touched once. |
| `backend/organism/governance.py` | `0ac6e2d` (canonical drawdown). Only touched once. |
| `backend/api/routes/settings.py` | `c306074` (H5). Only touched once. |
| 4 modules (alert hooks) | `33d6138` — additive try/except blocks. |
| `docker-compose.yml` | `eb90fa3` (fallback alignment). Only touched once. |

### C.2 Dependency ordering within the bundle
1. `15cc0a4` — mechanical guards (no deps)
2. `b97f903` — Exp4 (no deps)
3. `679ffd2` — H1/H2 (no deps)
4. `bb5cbb5` — cap/halt (no deps)
5. `c306074` — H5 API (no deps)
6. `33d6138` — alerts (depends on `bb5cbb5` + `679ffd2`)
7. `0ac6e2d` — canonical drawdown (no deps)
8. `eb90fa3` — compose alignment (depends on `0ac6e2d` constant name)

All are monotonically forward from `ce06d41`; no cherry-picks required.

### C.3 Rollback strategy
- Bundle rollback: redeploy image built from `ce06d41`. Data-safe (brain persistence survives).
- Per-commit revert: each commit is a clean `git revert`. Exp4 specifically has a one-line mode flip (`_EXP4_CHOP_TRAIL_MODE`) to soften without reverting.
- Risk caps: set envs back to 0 to disable without redeploy.

---

## D. Summary

| Component | In / Out | Reason (one line) |
|---|---|---|
| G1/G2/G3 (`15cc0a4`) | IN | silent-failure corrections; no downside |
| Exp4 (`b97f903`) | IN | largest edge leak, trivially reversible |
| H1/H2 (`679ffd2`) | IN | closes production risk gap; H2 required by alerts |
| CAP/HALT (`bb5cbb5`) | IN | real-money safety; env-gated default-off; required by alerts |
| H5 API (`c306074`) | IN | closes governance bypass |
| Alerts (`33d6138`) | IN | cumulative; must ship with CAP/HALT + H2 |
| Canonical drawdown (`0ac6e2d`) | IN | this sprint; new |
| Compose alignment (`eb90fa3`) | IN | this sprint; new |
| Exp3B | OUT | insufficient evidence |
| Phase C | OUT | out of scope for next deploy |
| Exploration cleanup | OUT | maintainability, not correctness |
| Confidence centralization | OUT | architectural, defer |
| Calibration persistence | OUT | defer after hardening bundle stable |
| Stage-1 real-money controls | OUT | prepare in parallel |

— End of Release Candidate Composition —
