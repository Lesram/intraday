# PLATFORM STATE SNAPSHOT — Apr 23, 2026

**Captured**: 2026-04-24T04:00Z (post-Apr-23 PDT close)
**Mode**: Read-only. No code edits, no deploys, no container restarts, no POST calls.
**Purpose**: Frozen baseline for strategic review. Paper trading PAUSED after Apr 23 close.
**Bundle**: `platform_state_snapshot_apr23_bundle/`

---

## 0. Summary table

| State | Commit / Component | Notes |
|---|---|---|
| **LIVE NOW**       | `ce06d41` running in `intra-api-1` (21h uptime, 0 restarts, healthy) | Exp1A + Exp2 + Exp3-prep stack. Paused operationally for strategy review; runtime flags NOT frozen/halted. |
| **OFFLINE READY**  | `33d6138` on disk as HEAD (4 commits ahead of container) | Adds Exp4 + G1/G2/G3 + H1/H2 + H5 + per-trade cap + daily max-loss + Slack alerting. DEPLOY 2 hard-stopped on 3 preflight blockers. |
| **FROZEN**         | ML joblib artifacts (Apr 15), `evolved_params.json` on disk (Apr 15), warm-start transfer file absent | In-memory learner has continued to gen 116; on-disk artifacts are stale by design until next brain save writes them. |
| **BACKLOG**        | Expectancy gap (-$1.92/trade → target +$0.50), Phase C (rank/dir/size split, microstructure alpha, staged learning→prod), ~90+ untracked reports | Primary real-money blocker is algorithmic, not mechanical. |

---

## 1. Current live container commit

**`ce06d41`** — *"experiment(instrumentation): confidence inversion side-by-side logging [Exp 3 prep]"* (2026-04-10 21:26 PDT)

**Evidence** (from `DEPLOY_VERIFICATION_DEPLOY2_33d6138.md §3` — file-hash fingerprint of 5 critical files inside the running container):

| File | Matches |
|---|---|
| `live_engine.py`, `kelly_sizer.py`, `ml_signal.py`, `brain_persistence.py`, `settings.py` | All 5 match `ce06d41` exactly. None match `33d6138`. |

The image itself was built 2026-04-16T02:41Z (after commits up to `b97f903`), but its contents fingerprint as `ce06d41`, indicating rebuild was triggered with the worktree checked out at `ce06d41` rather than at HEAD.

---

## 2. Current repo HEAD

**`33d61386d3f332286f92cc074caeeb1eedb68fc7`** on branch `main`.

---

## 3. `git status --short`

```
 M backend/organism/adaptive_exits.py                 (reverts Exp4)
 M backend/organism/pyramider.py                       (reverts G3 NaN guard)
 M monitoring/memory_monitoring.json                  (monitoring threshold)
 M scripts/generate_experiment_observation_report.py  (reverts giveback section)
```

All 4 worktree edits md5-match `ce06d41`, NOT `33d6138`. They are *backward deltas* toward the currently-running container, not forward progress.

~90+ untracked `*_REPORT.md` and ~30 `*_bundle/` directories present at repo root; none affect runtime. Full list in `platform_state_snapshot_apr23_bundle/git_status.txt`.

---

## 4. What is LIVE NOW

**Container**: `intra-api-1` @ `ce06d41` (image `intra-api`, `sha256:32296c…`, built 2026-04-16T02:41Z, started 2026-04-23T06:45:08Z, 21h up, 0 restarts, healthy).

**Experiment stack live on `ce06d41`** (commits merged ≤ `ce06d41`):
- **Exp1A** (`ab54b2f`) — chop-regime minimum-hold gate for `pyramid_cut`
- **Exp2**  (`d79cae0`) — suppress inverse ETF entries in chop regime
- **Exp3 prep** (`ce06d41`) — confidence inversion side-by-side logging (observation only)
- Observation tooling (`6754223`) — automated experiment observation report generator

**Hardening stack live on `ce06d41`**:
- **F-series brain hardening (F1-F4 + F-lite + pre-F guards)**: `3528162`, `62256d7`, `eaa4b2f`, `3a694ee`, `9e7c9a9`, `7d36b61` — manifest guard, split persistence, break-glass reset, bypass audit, forensic guard, save-essential-state overwrite guard
- **ML artifact recovery**: `50b2513`, `93593a2`, `be2eee8`, `c5fb0ed`
- **H1/H2/H3 (pre-DEPLOY-2)**: `f2448be` — H5 phantom pyramid prevention + H4 unified trading phase + H3 edge-cost instrumentation; `2018999` — H5 pyramid level preservation on broker sync collapse
- **Away-mode waves A-C**: `88c110f`
- **Incident-recovery waves XA+XB**: `296012b`
- **Universe protection on brain restore**: `e7112e1` (PSQ, SH preserved)
- **Brain volume mount fix** (per CLAUDE.md gotcha): `53cc1ad`
- **ExitLevels v4 restore + forensic guards**: included
- **Exploration execution**: fully removed (H1-H7 post-hardening)

**Operational controls in effect**:
- Paper mode: `ALPACA_PAPER=true`, `APP_ENVIRONMENT=development`
- Universe: 22 symbols incl. SH, PSQ
- `ORGANISM_ALPHA_TOP_N=5`, `ORGANISM_MAX_POSITIONS=8`
- `ORGANISM_EXPLORATION_ENABLED=false`, `ORGANISM_LONG_ONLY=true`
- `ORGANISM_DRAWDOWN_KILL_PCT=0.20` (kill-switch), `ORGANISM_DRAWDOWN_COOLDOWN_S=300`
- Health endpoints returning 200 at capture time
- Paper-trading operationally paused post-Apr-23 close per user policy — runtime flags `frozen=false`, `trading_halted=false` (out-of-band pause only)

---

## 5. What is OFFLINE READY

Ready on disk at HEAD `33d6138` but not yet in the running container. 4 commits between container and HEAD:

| Commit | Category | Description |
|---|---|---|
| `679ffd2` | Hardening — H1/H2 | Production risk-budget cap + feature drift guard |
| `bb5cbb5` | Hardening — risk | Per-trade notional cap + daily max-loss circuit breaker (env-gated; default off) |
| `c306074` | Hardening — H5 | Settings API enforces frozen/halted state |
| `33d6138` | Alerting | Wire critical events to Slack/webhook alerts (needs `SLACK_WEBHOOK_URL`) |

**Plus retained from between `ce06d41` and HEAD (in image file-date terms the image also predates these, so they are also OFFLINE READY vs the running container)**:
- `15cc0a4` — **G1/G2/G3**: exit-level restore warning + cooldown-on-success-only + NaN pyramid guard
- `b97f903` — **Exp4**: chop trailing-stop giveback control + observation tooling giveback section

**Additional offline artifacts** (per repo):
- ALERT_WIRING_OFFLINE_REPORT.md, H1_H2_OFFLINE_REPORT.md, H5_OFFLINE_REPORT.md
- REAL_MONEY_RISK_LIMITS_OFFLINE_REPORT.md
- MASTER_OFFLINE_COMPLETION_REPORT.md

---

## 6. What is FROZEN

| Item | State | Why frozen |
|---|---|---|
| `ml_classifier.joblib` | Apr 15 mtime | Image-build era snapshot. In-memory learner has evolved to gen 116 (see ml_state.json); disk artifact will be rewritten on next save. |
| `ml_regressor.joblib` | Apr 15 mtime | Same as above. |
| `evolved_params.json` | Apr 15 mtime, 3717 bytes | Warm-start snapshot; live evolved weights are in-memory in `learner.state`. |
| `reference_feats.csv` | Apr 15 mtime | Feature reference baseline (used by drift detection). |
| `transfer_knowledge.json` | NOT PRESENT | Acceptable; warm-start transfer file is optional. |
| Paper trading | Operationally PAUSED post-Apr-23 close | Per user policy pending strategy review. Not a runtime flag — governance_state.frozen=false, trading_halted=false. |
| Evolution freeze gate | PASSED | `last_reset_date=2026-03-31`; 300-trade freeze already crossed (370 trades lifetime). |

---

## 7. Current account status

From Alpaca `GET /v2/account` at 2026-04-24T03:58Z:

| Field | Value |
|---|---|
| Account | `PA3RLEN7T0N4` (paper) |
| Status | `ACTIVE` — not blocked (trading, transfers, account) |
| Equity | **$111,529.48** |
| Last equity | $111,541.62 → session change **−$12.14** (Apr 23 PDT) |
| Cash | $111,529.48 |
| Buying power | $446,166.48 |
| Positions | 0 (flat) |
| Pattern day trader | true |
| Daytrade count | 79 |
| Multiplier | 4 |

---

## 8. Current positions

**`GET /v2/positions` → `[]`**. Zero positions. Flat at close.

---

## 9. Container health / restart count / uptime

| Field | Value |
|---|---|
| Container | `intra-api-1` |
| Image | `intra-api` (`sha256:32296c…`) |
| Image created | 2026-04-16T02:41:24Z |
| Container started | 2026-04-23T06:45:08Z |
| Uptime at capture | ≈21 h |
| Restart count | **0** |
| Status | running |
| Health | **healthy** |
| `/healthz` | 200 OK |
| `/health` | 200 OK, `version: 1.0.0` |

Companion containers: `intra-redis-1` (healthy, 21h), `trading_platform_db_paper` (healthy, 21h).

---

## 10. `manifest.json` summary

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

---

## 11. `learning_state.json` summary

```json
{
  "generation": 115,
  "total_bars_seen": 0,
  "total_trades": 370,
  "cumulative_pnl": -619.75,
  "best_sharpe": 3.4363,
  "best_generation": 26,
  "retrain_count": 115,
  "drift_events": 0,
  "bars_since_retrain": 0,
  "generation_accuracies_last4": [0.7551, 0.6071, 0.7594, 0.5714]
}
```

Manifest and learning_state fully synced on gen 115 / 370 trades / −$619.75 / Sharpe 3.4363. *(Hand-off memory said gen 106 / 348 trades / −$607.40 — brain has continued to advance since the memory was written on 2026-04-22: +9 generations, +22 trades, −$12.35 incremental.)*

---

## 12. `evolved_params.json` summary

File mtime: Apr 15 19:43 (image-build era, not resaved since).

| Group | Key values |
|---|---|
| Alpha weights | ml 0.356, volume 0.195, momentum 0.153, breakout 0.146, regime 0.10 |
| Direction thresholds | buy 0.556, sell 0.448 |
| Exit params | stop_atr_scale 0.985, trailing_start 1.00, trailing_distance 0.892, partial_tp_r 1.00, partial_tp_pct 0.20 |
| Regime size scales | trending_up 1.2, trending_down 0.6, chop 0.5, high_vol 0.7, low_vol 1.0, stress 0.3, unknown 0.7 |
| Breakout weights | squeeze 0.25, volume 0.25, contraction 0.15, rs 0.15, pivot 0.15, flow 0.05 |
| XGB hyperparams | n_est 177, max_depth 3, lr 0.0398, subsample 0.863, colsample 0.863 |
| Shorts | disabled |
| Feature weights | 79 features, top: choppiness 2.00, vwap_distance 1.47, realized_vol_20 1.17, day_of_week 1.12 |

Full JSON dumped to `platform_state_snapshot_apr23_bundle/evolved_params_summary.json`.

---

## 13. Current experiment stack

**Live on `ce06d41`**:
- **Exp1A** — chop-regime minimum-hold gate for `pyramid_cut` (commit `ab54b2f`)
- **Exp2**  — suppress inverse ETF entries in chop regime (commit `d79cae0`)
- **Exp3 prep** — confidence inversion side-by-side logging, observation only (commit `ce06d41`)
- Observation tooling — automated report generator (commit `6754223`)

**Offline / ready but not live**:
- **Exp4** — chop trailing-stop giveback control (commit `b97f903`; reverted in current worktree)

**Planned**:
- **Exp3B** — ML-confidence formula change, once Exp3 data is conclusive

---

## 14. Current hardening stack

**Live on `ce06d41`**:
- F-series brain hardening (F1-F4, F-lite, pre-F save-essential-state guard)
- Manifest/save split persistence, force-save admin route, trained-manifest overwrite refusal
- H3 (edge-cost instrumentation), H4 (unified trading phase), H5-phantom (phantom pyramid prevention), H5-pyramid-level (preserve on broker sync collapse)
- Away-mode hardening waves A-C, incident-recovery waves XA+XB
- Universe restore protection (PSQ, SH), brain volume mount, reconciliation stale-fill prevention, regime_at_exit
- Walk-forward gate + split persistence (trades survive gate block)
- H1-H7 post-hardening program (per CLAUDE.md): exploration removed, ML isolation in learning mode, alpha `learning_mode` param, warm-start freeze gate, ExitLevels v4 restore, unified entry gates, `ALPHA_TOP_N` separated

**Offline / ready but not live (between container and HEAD)**:
- **G1** — exit-level restore warning (commit `15cc0a4`)
- **G2** — cooldown-on-success-only (commit `15cc0a4`)
- **G3** — NaN pyramid guard (commit `15cc0a4`; currently reverted in worktree)
- **H1** (prod) — production risk-budget cap (commit `679ffd2`)
- **H2** (prod) — feature drift guard (commit `679ffd2`)
- **H5 (API)** — settings API enforces frozen/halted (commit `c306074`)
- Per-trade notional cap + daily max-loss circuit breaker (commit `bb5cbb5`, env-gated; default inert)
- Slack/webhook alerting for critical events (commit `33d6138`, requires `SLACK_WEBHOOK_URL`)

---

## 15. Paper-trading performance summary to date

| Metric | Value |
|---|---|
| Equity (live) | **$111,529.48** (flat) |
| Session change Apr 23 | **−$12.14** |
| Peak equity | $111,784.74 |
| Drawdown from peak | −$255.26 (−0.23%) |
| Total trades (brain lifetime, since 2026-03-31 reset) | **370** |
| Cumulative PnL | **−$619.75** |
| Expectancy per trade | ≈ −$1.68 (improving: −$0.41 over last 100 per NEXT_DEPLOY_DECISION) |
| Win rate | 18.8% lifetime; ~34% recent window |
| Best Sharpe (lifetime) | 3.44 (generation 26) |
| Sharpe (recent) | Negative |
| Consecutive positive sessions | 0 |
| ML gen / accuracy (gen 116) | Acc 0.617, F1 0.599, Hit 0.604, Precision 0.515, Recall 0.715 |
| Retrain count | 115 (no drift events) |
| Daytrade count | 79 |
| Container incidents | 0 restarts, 0 crashes, 0 save failures (5-session window) |

5-session trend (Apr 16-22, from NEXT_DEPLOY_DECISION):
- Pyramid cut share: 56% → 33% (Exp1A working)
- PSQ/SH chop trades: eliminated (Exp2 working)
- Trailing-stop giveback: **$195.21 of MFE destroyed** in 5 sessions — Exp4 targets this but is **NOT LIVE**

---

## 16. Current top blockers to real money

From `REAL_MONEY_GAP_MAP.md`, plus DEPLOY 2 preflight blockers.

### Immediate (DEPLOY 2 retry)
1. Worktree dirty on 4 files — decide: keep reverts (stay on Exp1A+Exp2+Exp3-prep on `ce06d41` semantics) or restore HEAD (full 33d6138 with Exp4+G+H+alerts).
2. `.env` missing `ORGANISM_MAX_NOTIONAL=0` and `ORGANISM_MAX_DAILY_LOSS=0`.
3. `.env` missing `SLACK_WEBHOOK_URL` (alerts ship silent otherwise).

### Real-money path (rank-ordered)
| # | Gap | Current | Target | Severity |
|---|---|---|---|---|
| 1 | **Expectancy/trade** | −$1.92 lifetime (−$0.41 last 100) | ≥+$0.50 sustained ≥3 weeks | **LARGE** |
| 2 | **Win rate** | 18.8% lifetime / 34% recent | >30% sustained | **LARGE** |
| 3 | **Sharpe (recent)** | Negative | >1.0 annualized | **LARGE** |
| 4 | **Consecutive positive sessions** | 0 | ≥10 | **NOT STARTED** |
| 5 | Daily max-loss auto-halt | Code in 33d6138, not in running ce06d41 | −$500/day | MEDIUM |
| 6 | Weekly drawdown halt | None | −$1500/week | MEDIUM |
| 7 | Sector concentration cap | None | ≤40% one sector | MEDIUM |
| 8 | Alerts dashboard wired | 33d6138 adds hooks; no URL | Slack live | MEDIUM |
| 9 | Position max-loss auto-close | Stops only | −$200/pos | SMALL |

**Bottom line**: Platform is *mechanically* ready. Platform is *algorithmically* not ready — negative expectancy must turn positive first. Estimated 4–8 weeks.

---

## 17. Recent deploy history (inferable)

| Date (approx) | Action | Outcome |
|---|---|---|
| 2026-04-15 19:42 PDT | Image rebuild from worktree | Image built 2026-04-16T02:41Z. Container came up running code that fingerprints as `ce06d41` (commits `15cc0a4` and `b97f903` not included despite being pre-build — worktree was on `ce06d41` at build). |
| 2026-04-16 → 2026-04-22 | 5-session observation window | 0 restarts, 0 incidents. Expectancy improving. |
| 2026-04-19 12:21 PDT | `679ffd2` committed | H1/H2 prod risk-budget + drift guard (offline). |
| 2026-04-19 12:36 PDT | `bb5cbb5` committed | Per-trade cap + daily max-loss (offline). |
| 2026-04-19 13:18 PDT | `c306074` committed | H5 settings API enforcement (offline). |
| 2026-04-19 13:21 PDT | `33d6138` committed (HEAD) | Slack/webhook alerting (offline). |
| 2026-04-23 06:45 UTC | Container restart | Same image, no rebuild. 0-count restart. Brain restored cleanly. |
| 2026-04-23 post-close | **DEPLOY 2 — HARD STOP** | 3 preflight blockers (worktree dirty, risk envs absent, `SLACK_WEBHOOK_URL` absent). No checkout, no rebuild, no force-save performed. Container still `ce06d41`. |
| 2026-04-23 evening | Operational PAUSE declared | Strategy review pending. Runtime unchanged. |

---

## 18. Snapshot bundle contents

`platform_state_snapshot_apr23_bundle/`:
- `manifest_summary.json`
- `learning_state_summary.json`
- `evolved_params_summary.json`
- `ml_state_summary.json`
- `governance_and_regime.json`
- `account_snapshot.json`
- `positions_snapshot.json`
- `container_inspect.txt`
- `env_relevant.txt` (secrets redacted)
- `worktree_diff_stat.txt`
- `git_status.txt`
- `git_log_recent.txt`
- `performance_summary.txt`
- `blockers_and_backlog.md`

---

## 19. Caveats

- Container runtime commit is inferred by file-hash fingerprint from the prior DEPLOY 2 verification report, not by in-container `git rev-parse` (git not installed in container image). Confidence is high (5/5 critical files match).
- `evolved_params.json` on disk is stale (Apr 15) vs in-memory `learner.state` (gen 115). Any strategic decision referencing "current evolved weights" should distinguish disk-snapshot from running-learner.
- Brain state figures (gen 115 / 370 trades / −$619.75) supersede the hand-off memory figures (gen 106 / 348 / −$607.40) by ~1 day of trading.
- Operational pause is not enforced at the governance layer. If anyone POSTs to `/api/v1/organism/*` the container will trade again on next market open (paper).
