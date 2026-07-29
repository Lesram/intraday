# DEPLOY 2 — FULL HEAD 33d6138 Verification Report

Captured_at: 2026-04-24T02:42Z (2026-04-23 evening PDT, well after market close)
Bundle: `deploy_verification_deploy2_33d6138_bundle/`

---

## 1. Verdict

**HARD STOP**

Deploy did **NOT** proceed. Three independent preflight failures. No code edits, no commits, no checkout, no rebuild, no force-save were performed.

Primary blocker: preflight #7 — target commit `33d6138` is **not cleanly checkout-able** because the worktree has uncommitted edits that **revert Exp4 and G3 hardening**. A rebuild from this worktree would silently ship a Frankenstein container (partial 33d6138 + ce06d41-state Exp4/G3 paths), violating the declared deploy scope "FULL HEAD 33d6138 (includes Exp4 and the hardening stack)".

Secondary blockers: preflight #8 (paper-mode risk envs `ORGANISM_MAX_NOTIONAL=0` and `ORGANISM_MAX_DAILY_LOSS=0` are not explicitly set), preflight #9 (`SLACK_WEBHOOK_URL` missing while alerting is the marquee 33d6138 change under verification).

---

## 2. Source / target state

| Field | Value |
|---|---|
| Repo root | `/Users/marselkei/VS/intra` |
| Branch before checkout | `main` |
| `git rev-parse HEAD` before checkout | `33d61386d3f332286f92cc074caeeb1eedb68fc7` |
| Target commit | `33d6138` |
| Checkout performed | **No** (HARD STOP — would not have been clean) |
| Checkout to 33d6138 succeeded cleanly | **N/A — not attempted** |

**Worktree dirty files (DIFF vs HEAD):**

```
 M backend/organism/adaptive_exits.py                  (-40, +6)   — reverts Exp4 chop trailing giveback
 M backend/organism/pyramider.py                        (-8, 0)    — reverts G3 NaN/Inf pyramid guard
 M monitoring/memory_monitoring.json                   (~26 lines) — monitoring threshold change
 M scripts/generate_experiment_observation_report.py  (-80, 0)    — reverts observation tooling giveback section
```

**Proof that the dirty edits are reverts to the ce06d41 state (not forward progress):**

| File | Worktree md5 | ce06d41 md5 | 33d6138 md5 | Interpretation |
|---|---|---|---|---|
| `backend/organism/adaptive_exits.py` | `f1121e48acf09986b95c9f1de8555b95` | `f1121e48acf09986b95c9f1de8555b95` | `affee144a8f8c28de3eae4fc68735269` | **Reverted to ce06d41** |
| `backend/organism/pyramider.py` | `c7befbfcf2b844280f842368fae39173` | `c7befbfcf2b844280f842368fae39173` | `affee144a8f8c28de3eae4fc68735269`* | **Reverted to ce06d41** |

(*pyramider had two different 33d6138 hash outputs during capture; definitive fact is the worktree md5 matches ce06d41 exactly)

---

## 3. Pre-deploy snapshot

### Current live container commit

| Evidence | Result |
|---|---|
| `git` not installed inside container | no direct SHA |
| File-hash fingerprint (live_engine.py, kelly_sizer.py, ml_signal.py, brain_persistence.py, settings.py) | All 5 match `ce06d41` exactly. None match `33d6138`. |

**Container IS running `ce06d41`** (matches the expected pre-deploy baseline).

### Container status

```
NAMES                       STATUS                   PORTS
intra-api-1                 Up 20 hours (healthy)    0.0.0.0:8000->8000/tcp
intra-redis-1               Up 20 hours (healthy)    0.0.0.0:6379->6379/tcp
trading_platform_db_paper   Up 20 hours (healthy)    0.0.0.0:5432->5432/tcp

intra-api-1 inspect:
  Health=healthy  Running=true  StartedAt=2026-04-23T06:45:08Z  RestartCount=0  Image=intra-api
```

### API health

```
GET /health → {"status":"ok","version":"1.0.0","timestamp":"2026-04-23T06:47:53Z"}
GET /api/v1/observability/health/live → {"status":"alive","timestamp":"2026-04-24T02:41:17Z"}
/healthz poll: 200 every 30s, no gaps
```

### Account snapshot (from Alpaca boot sync log 2026-04-23T06:45:16Z)

```
account_number: PA3RLEN7T0N4
cash: 111541.68
portfolio_value: 111541.68
buying_power: 446187.80
is_paper: true
Alpaca /v2/account HTTP 200, /v2/positions HTTP 200 → status inferred ACTIVE / unblocked
```

### Positions snapshot

```
GET /api/v1/positions → [] (empty)
Alpaca boot sync: position_count=0, symbols=[]
```

Positions are **flat**.

### Manifest summary

```json
{
  "brain_format_version": 2,
  "saved_at": "2026-04-23T19:57:44.128879+00:00",
  "total_runs": 1184,
  "generation": 115,
  "total_trades": 370,
  "cumulative_pnl": -619.75,
  "best_sharpe": 3.4363,
  "ml_is_trained": true,
  "feature_count": 79
}
```

### learning_state summary

```json
{
  "generation": 115,
  "total_trades": 370,
  "cumulative_pnl": -619.75,
  "best_sharpe": 3.4363,
  "best_generation": 26,
  "retrain_count": 115,
  "drift_events": 0,
  "bars_since_retrain": 0
}
```

Manifest and learning_state are **synced** (see §10).

### Brain directory listing

```
drwxrwxrwx@  17 marselkei  staff    544 Apr 19 10:28 .
-rw-rw-rw-@   1 marselkei  staff       0 Apr 15 19:43 .brain.lock
drwxr-xr-x    3 marselkei  staff      96 Apr 23 13:05 diagnostics
-rw-r--r--    1 marselkei  staff  267698 Apr 23 12:57 equity_curve.csv
-rw-r--r--    1 marselkei  staff   95499 Apr 23 12:57 evaluation_event_history.json
-rw-r--r--    1 marselkei  staff    3717 Apr 15 19:43 evolved_params.json
-rw-r--r--    1 marselkei  staff    9935 Apr 23 12:57 extra_counters.json
-rw-r--r--    1 marselkei  staff     297 Apr 23 12:57 governance_state.json
-rw-r--r--    1 marselkei  staff     302 Apr 23 12:57 learning_state.json
-rw-r--r--    1 marselkei  staff     249 Apr 23 12:57 manifest.json
-rw-r--r--    1 marselkei  staff  248507 Apr 15 19:43 ml_classifier.joblib
-rw-r--r--    1 marselkei  staff  168098 Apr 15 19:43 ml_regressor.joblib
-rw-r--r--    1 marselkei  staff    3159 Apr 23 12:57 ml_state.json
-rw-r--r--    1 marselkei  staff   20126 Apr 15 19:43 reference_feats.csv
-rw-r--r--    1 marselkei  staff     178 Apr 23 12:57 regime_state.json
-rw-r--r--    1 marselkei  staff   52712 Apr 23 12:57 trade_history.csv
```

`transfer_knowledge.json`: **not present** (acceptable; warm-start transfer file is optional).

### Env snapshot — paper-mode / webhook / cap / halt

**Paper mode**: `APP_ENVIRONMENT=development`, `ALPACA_PAPER=true`, `ALPACA_BASE_URL=https://paper-api.alpaca.markets` → paper-mode confirmed.

**Risk caps** (DEPLOY 2 preflight required):
- `ORGANISM_MAX_NOTIONAL`: **NOT SET** in `.env` or container env
- `ORGANISM_MAX_DAILY_LOSS`: **NOT SET** in `.env` or container env
- Preflight required explicit `=0` — currently *absent*. Code default via `_env_float(...,0)` would yield 0 if the 33d6138 code path were live, but this cannot be verified in the running `ce06d41` container (the circuit-breaker code is not present).

**Alerting**:
- `SLACK_WEBHOOK_URL`: **NOT SET**. Preflight required this for alert-wiring verification.

---

## 4. Deployment actions performed

**NONE.** Per task contract: "Do NOT improvise fixes if verification fails; stop and report blockers only."

Commands that would have been executed had preflight passed, and **were NOT run**:
```
git stash push -m deploy2_preflight_snapshot          # NOT RUN
git checkout 33d6138                                   # NOT RUN
docker-compose -f docker-compose.paper.yml up -d --build api   # NOT RUN
curl -X POST http://localhost:8000/api/v1/organism/save?force=true   # NOT RUN
```

Only rebuild was planned to be api/runtime (not db/redis). N/A — no rebuild occurred.

Deploy completed cleanly: **No, did not occur.**

---

## 5. Post-deploy boot verification

**N/A — no redeploy occurred. Running container is still `ce06d41`.**

Current state (unchanged from §3):
- container healthy: yes
- API healthy: yes
- restart count: 0 (normal)
- account ACTIVE: yes (Alpaca 200 OK, not blocked)
- positions flat: yes
- `APP_ENVIRONMENT`: `development` (correct paper-mode value per memory gotcha)
- brain mount RW: yes (host writes at Apr 23 12:57 visible; `./organism_brain:/app/organism_brain` mount active)
- boot errors/criticals since last start: 0
- brain loaded at boot with gen 106, 348 trades (pre-session). Current state gen 115, 370 trades (after today's 22 trades).

---

## 6. Signature verification in the running container

All evidence is from the **currently running `ce06d41`** container. Deploy to `33d6138` did not occur, so hardening-stack signatures introduced after `ce06d41` are **ABSENT** in the running container. For each item I report actual presence, and where relevant what *would have* happened had deploy proceeded from the dirty worktree.

### A. Exp1A — chop min-hold gate  →  **PRESENT** ✅
```
/app/backend/organism/live_engine.py:1936:    _CHOP_MIN_HOLD_BARS = 10
/app/backend/organism/live_engine.py:1941:    if _is_chop and _bars_held < _CHOP_MIN_HOLD_BARS:
/app/backend/organism/live_engine.py:1947:        sym, _bars_held, _CHOP_MIN_HOLD_BARS,
```

### B. Exp2 — PSQ/SH suppressed in chop  →  **PRESENT** ✅
```
/app/backend/organism/live_engine.py:2437: "%s regime=%s confidence=%.3f reason=inverse_etf_suppressed_chop",
/app/backend/organism/live_engine.py:2444: details={"reason": "inverse_etf_suppressed_chop", "regime": str(regime)},
```
No effect on non-inverse symbols (suppression is gated on the inverse-ETF set only — consistent with the Exp2 design).

### C. Exp3 prep — read-only dual-confidence logging  →  **PRESENT** ✅
```
/app/backend/organism/live_engine.py:2170: "gate_pass_live=%s gate_pass_bt_only=%s "
/app/backend/organism/live_engine.py:2248:   "confidence_bt_only": _conf_bt_only,
/app/backend/organism/live_engine.py:2249:   "confidence_ml_component": _conf_ml_component,
```
Read-only only, no gate changes — matches ce06d41 commit intent "confidence inversion side-by-side logging [Exp 3 prep]".

### D. Exp4 — chop trailing-stop giveback control  →  **ABSENT in running container; would be REVERTED if deploy ran**
```
grep "EXPERIMENT 4\|_EXP4_CHOP_TRAIL\|Exp4:" /app/backend/organism/adaptive_exits.py → (empty)
```
- In running `ce06d41` container: ABSENT (expected — pre-Exp4).
- In worktree: the Exp4 block exists in HEAD but is *deleted* by the uncommitted diff (40 lines removed). Worktree md5 of `adaptive_exits.py` (`f1121e48…`) matches `ce06d41` exactly.
- **Building from current worktree would deploy a container without Exp4 — violating "FULL HEAD 33d6138".**

### E. G1/G2/G3 mechanical fixes  →  **ABSENT (G1/G2); ABSENT AND WOULD BE REVERTED (G3)**

| Check | In running container (ce06d41) | In worktree (what would build) |
|---|---|---|
| G1 restore failure / forced-exit marking | ABSENT (no G1 marker in live_engine.py) | PRESENT (live_engine.py in worktree == 33d6138) — but deploy not run |
| G2 cooldown-on-success-only | ABSENT | PRESENT (same) — but deploy not run |
| G3 NaN/Inf pyramid guard | ABSENT | **ABSENT — reverted.** pyramider.py worktree md5 matches ce06d41. The 8-line `math.isfinite(current_price)` guard is *deleted* vs HEAD. |

Note: the match on `ftf_stop_tightened` at live_engine.py:812 is from earlier H5 ExitLevels persistence (per memory), *not* from G1 of commit 15cc0a4.

### F. H1/H2  →  **ABSENT in running container**
- H1 (`kelly_sizer.py` production risk-budget cap): ABSENT in container (md5 matches ce06d41). In worktree: matches 33d6138.
- H2 (`ml_signal.py` feature-drift neutralization): ABSENT in container (md5 matches ce06d41). In worktree: matches 33d6138.
- Both would be correctly delivered by a clean rebuild — but deploy not run.

### G. CAP / HALT  →  **ABSENT in running container; paper-mode envs not explicitly set**

| Item | Status |
|---|---|
| Notional cap code path (bb5cbb5 ORGANISM_MAX_NOTIONAL) | ABSENT in running container |
| Daily max-loss halt code path (bb5cbb5 ORGANISM_MAX_DAILY_LOSS) | ABSENT in running container |
| `ORGANISM_MAX_NOTIONAL` env | **NOT SET** in `.env` or container env |
| `ORGANISM_MAX_DAILY_LOSS` env | **NOT SET** in `.env` or container env |

Only legacy per-position 5% sizing cap is present in the container:
```
/app/backend/organism/kelly_sizer.py:498:  _max_notional = portfolio_value * 0.05
/app/backend/organism/kelly_sizer.py:499:  _notional_capped_shares = int(_max_notional / current_price)
```
This is the pre-existing pct-of-equity guard, NOT the new circuit breaker.

### H. H5 — governance/settings bypass protections  →  **ABSENT in running container**
```
grep "frozen.*halted\|H5:" /app/backend/api/routes/ → (empty)
```
`backend/api/routes/settings.py` in container matches ce06d41 md5. In worktree: matches 33d6138.

### I. Alert wiring  →  **ABSENT in running container; webhook NOT configured**
- `backend/infra/alerting.py` is identical between ce06d41 and 33d6138 (same md5). The *infrastructure* module exists in the container. But the 4 `send_alert()` **call sites** added by commit 33d6138 are in `brain_persistence.py`, `live_engine.py`, and `ml_signal.py` — all of which match ce06d41 in the running container (no send_alert wiring live).
- `SLACK_WEBHOOK_URL`: **NOT SET**. Even if the wiring were deployed, the Slack/webhook side would be inert.

### J. Full Patch F protections  →  **PRESENT in running container (pre-date ce06d41)**
Patch F landed before ce06d41 so it remains in the running container. Files related to guarded manifest writer, manifest sync, force-save path, suspicious-write instrumentation, forensic guard, and read-back invariant are unchanged between ce06d41 and 33d6138 (based on the diff stat: only 13 files changed in the full ce06d41..33d6138 range; Patch F files are not in that set).

---

## 7. Force-save verification

**NOT CALLED.** Deploy did not proceed, and force-save is a post-deploy verification step. Calling it now would provide no signal about `33d6138` — the running container is still `ce06d41`.

```json
{
  "called": false,
  "reason": "HARD STOP at preflight — deploy did not proceed"
}
```

Auth capability was confirmed separately (POST `/api/v1/auth/login` with `{username,password}` returns a JWT). Auth was **not** the blocker.

---

## 8. Post force-save artifact verification

**N/A — no force-save issued.** The brain was last written by the normal in-run save at 2026-04-23T19:57:44Z (manifest `saved_at`). For completeness, current disk state of required files:

| File | Status | Path | Mtime | Size |
|---|---|---|---|---|
| manifest.json | PRESENT | organism_brain/manifest.json | Apr 23 12:57 | 249 |
| learning_state.json | PRESENT | organism_brain/learning_state.json | Apr 23 12:57 | 302 |
| ml_classifier.joblib | PRESENT | organism_brain/ml_classifier.joblib | Apr 15 19:43 | 248507 |
| ml_regressor.joblib | PRESENT | organism_brain/ml_regressor.joblib | Apr 15 19:43 | 168098 |
| reference_feats.csv | PRESENT | organism_brain/reference_feats.csv | Apr 15 19:43 | 20126 |
| evolved_params.json | PRESENT | organism_brain/evolved_params.json | Apr 15 19:43 | 3717 |
| transfer_knowledge.json | **ABSENT** (optional, acceptable) | — | — | — |
| trade_history.csv | PRESENT | organism_brain/trade_history.csv | Apr 23 12:57 | 52712 |
| equity_curve.csv | PRESENT | organism_brain/equity_curve.csv | Apr 23 12:57 | 267698 |
| evaluation_event_history.json | PRESENT | organism_brain/evaluation_event_history.json | Apr 23 12:57 | 95499 |
| governance_state.json | PRESENT | organism_brain/governance_state.json | Apr 23 12:57 | 297 |
| regime_state.json | PRESENT | organism_brain/regime_state.json | Apr 23 12:57 | 178 |
| extra_counters.json | PRESENT | organism_brain/extra_counters.json | Apr 23 12:57 | 9935 |

Note: `ml_classifier.joblib` / `ml_regressor.joblib` mtime is Apr 15 — expected; the retrain loop rewrites `ml_state.json` (Apr 23 12:57) but only rewrites the joblibs on full retrain events.

---

## 9. Paper-mode safety verification

| Question | Answer |
|---|---|
| Notional cap code is live? | **NO** (container at ce06d41; circuit-breaker cap introduced in bb5cbb5, not deployed) |
| Notional cap currently active in paper? | **NO** (code not live; env var also unset) |
| Daily max-loss halt code is live? | **NO** (container at ce06d41) |
| Daily max-loss halt currently active in paper? | **NO** |
| Alert wiring code is live? | **NO** (send_alert() call sites from 33d6138 not in container) |
| Alert webhook configured? | **NO** (`SLACK_WEBHOOK_URL` unset) |
| Any hardening feature unintentionally active in paper? | **NO** |

Paper mode is safe — but this is because the hardening stack is simply not deployed. Once `33d6138` is cleanly deployed, the circuit breakers should remain disabled via `ORGANISM_MAX_NOTIONAL=0` and `ORGANISM_MAX_DAILY_LOSS=0` explicit settings (currently absent — add to `.env` before the next deploy attempt).

---

## 10. Manifest consistency check

| Field | manifest.json | learning_state.json | Consistent? |
|---|---|---|---|
| generation | 115 | 115 | ✅ |
| total_trades | 370 | 370 | ✅ |
| cumulative_pnl | -619.75 | -619.75 | ✅ |
| best_sharpe | 3.4363 | 3.4363 | ✅ |
| ml_is_trained | true | (4 generation_accuracies populated → trained) | ✅ |
| feature_count | 79 | (matches memory baseline) | ✅ |

**Manifest sync is correct.** Last save at 2026-04-23T19:57:44Z (approx. 2 min before market close; normal in-run write).

---

## 11. First-2-session observation plan

Because deploy did not proceed, sessions 1 and 2 post-deploy cannot begin. This plan applies to the FIRST 2 sessions *after a successful DEPLOY 2 retry*:

Per-session metrics to capture (from `scripts/generate_experiment_observation_report.py` + live logs):

| Metric | Source / signature |
|---|---|
| Exp1A chop min-hold suppression count | Log line `"chop min-hold skip"` or equivalent; count by symbol |
| `inverse_etf_suppressed_chop` count | Structured log `reason=inverse_etf_suppressed_chop` |
| PSQ trade count in chop regime | `trade_history.csv` × regime = chop & symbol = PSQ |
| SH trade count in chop regime | same, symbol = SH |
| Overall expectancy | mean(realized_pnl_per_trade) across session |
| Win rate | trades with realized_pnl > 0 / total closed trades |
| Pyramid-cut share | exits with reason `pyramid_cut` / all exits |
| Timeout / max_hold share | exits with reason `horizon_timeout` or `max_hold` / all exits |
| Stop-loss share | exits with reason `stop_loss` / all exits |
| Median hold time | median(exit_ts - entry_ts) |
| Giveback by exit reason | MFE − realized_pnl per exit reason bucket |
| Trailing-stop giveback specifically | reason=`trailing_stop`; compare Exp4 variant (chop trail widened to 5.0× ATR) vs non-chop baseline |
| Confidence bucket outcomes | Bin by confidence_live (quintiles); win rate + expectancy per bucket |
| Whether Exp3 data is becoming actionable | Delta between `confidence_live` and `confidence_bt_only` distribution; gate_pass_live vs gate_pass_bt_only divergence |
| Whether Exp4 is helping or hurting | Chop trailing_stop giveback delta vs pre-Exp4 baseline (commit ce06d41 trading window Apr 7–13) |

Emit a `POSTCLOSE_DEPLOY2_session{1,2}.md` per session with all of the above, anchored to the paper-postclose-audit workflow (`.github/workflows/paper-postclose-audit.yml`, 22:15 UTC).

Hard thresholds (flag for investigation if exceeded in either session):
- expectancy drop > $5/trade vs 30-trade trailing baseline
- win rate drop > 10pp
- chop-regime trade count > 2× baseline (suggests Exp2 regression)
- any `send_alert` failure that crashes caller (should not happen — try/except is mandated)

---

## 12. Hard-stop checks

See `deploy_verification_deploy2_33d6138_bundle/hard_stop_checks.md` for the full PASS/FAIL table. Summary:

- FAIL: #1 target commit deployed, #6 Exp4 present, #7 G1/G2/G3 present, #8 H1/H2 present, #9 CAP/HALT present, #10 CAP/HALT disabled (N/A — code not live), #11 H5 present, #12 alert wiring present, #14 force-save succeeded.
- PASS: #2 container healthy, #3 Exp1A preserved, #4 Exp2 present, #5 Exp3 present read-only, #15 manifest sync correct.
- PARTIAL: #13 Patch F preserved (in container — not re-verified under 33d6138).
- CONDITIONAL: #16 no blocker before next paper session — the *current ce06d41 stack* can continue paper-trading normally tomorrow; DEPLOY 2 is blocked pending resolution.

**Exact blocker list to resolve before DEPLOY 2 retry:**

1. **Decide intent on worktree edits**: the uncommitted changes revert Exp4 (adaptive_exits.py), G3 (pyramider.py), and observation tooling. Either:
   - (a) discard the reverts with `git restore backend/organism/adaptive_exits.py backend/organism/pyramider.py scripts/generate_experiment_observation_report.py monitoring/memory_monitoring.json` so HEAD is the literal 33d6138 tree, OR
   - (b) commit the reverts and re-scope the deploy (but then it is NOT "FULL HEAD 33d6138").
   - User must explicitly choose. I will not guess.
2. Add to `.env`:
   - `ORGANISM_MAX_NOTIONAL=0`
   - `ORGANISM_MAX_DAILY_LOSS=0`
3. Decide on `SLACK_WEBHOOK_URL`: either populate it (so alert wiring can be verified end-to-end) or explicitly acknowledge that alert wiring will only be code-verified (`send_alert` call sites present) and not runtime-verified (no outgoing webhook).

---

## 13. Files produced

**Report:**
- `/Users/marselkei/VS/intra/DEPLOY_VERIFICATION_DEPLOY2_33d6138.md` (this file)

**Bundle** (`/Users/marselkei/VS/intra/deploy_verification_deploy2_33d6138_bundle/`):
- `repo_head_sha.txt`
- `git_status_predeploy.txt`
- `predeploy_container_status.txt`
- `predeploy_health.txt`
- `predeploy_account_snapshot.json`
- `predeploy_positions_snapshot.json`
- `predeploy_manifest.json`
- `predeploy_learning_state.json`
- `predeploy_brain_listing.txt`
- `predeploy_env_snapshot.txt`
- `deploy_commands.txt` (records no commands were run, with reasons)
- `postdeploy_container_status.txt` (= predeploy, no rebuild)
- `postdeploy_health.txt` (= predeploy)
- `running_container_code_verification.txt` (signature grep evidence)
- `force_save_response.json` (records not-called, with reason)
- `post_force_save_manifest.json` (= predeploy, no save issued)
- `post_force_save_learning_state.json` (= predeploy)
- `post_force_save_inventory.txt`
- `hard_stop_checks.md`

No code edits made. No git commits made. No docker rebuild run. No force-save issued. No writes to `organism_brain/`.
