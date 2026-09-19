# CURRENT LIVE STATE SNAPSHOT
**Generated:** 2026-04-24 (Friday post-close, weekend audit)
**Audit type:** READ-ONLY
**Snapshot taken:** 2026-04-25T00:49Z (24 minutes after container restart)

---

## 1. Live container truth

| Item | Value |
|---|---|
| Container name | `intra-api-1` |
| Container status | `Up 24 minutes (healthy)` |
| Container created | 2026-04-16T02:42:19Z |
| Container started (last) | 2026-04-25T00:48:48Z |
| Restart count | 0 |
| Health | healthy |
| Image SHA | `sha256:32296cf9a486...` |
| Image labels | `version=1.0.0`, `revision=` (empty), `created=` (empty) |

### Live commit identification (file-hash forensics)

`live_engine.py` SHA256 in container = `9b5ddb5ca17cb87a35d7caf7081da3686bc5b92a4d1a730112c6bdfba79e4bae`.

Cross-referenced against every commit since `7d36b61`:

| Commit | live_engine.py SHA matches container? |
|---|---|
| `eb90fa3` | NO |
| `0ac6e2d` | NO |
| `33d6138` | NO |
| `c306074` | NO |
| `bb5cbb5` | NO |
| `679ffd2` | NO |
| `b97f903` | NO |
| `15cc0a4` | NO |
| **`ce06d41`** | **YES** ✓ |
| `d79cae0` | different |
| `ab54b2f` | different |

`adaptive_exits.py` SHA in container = `d66d54d40279f53fa9182650fa0bd0bde70aa2fa579c010773beaae061c52084`. This file was last modified at `b97f903` (Exp 4). The container's hash matches `ce06d41`/`15cc0a4`/`ab54b2f` (pre-Exp 4) — i.e., **the container does NOT have Exp 4**.

**CONCLUSION — LIVE CONTAINER IS AT `ce06d41`** ("Exp 3 prep — confidence inversion side-by-side logging").

That includes:
- Exp 1A live (chop-regime minimum-hold gate for pyramid_cut, from `ab54b2f`)
- Exp 2 live (suppress inverse ETF entries in chop, from `d79cae0`)
- Exp 3 prep live (confidence inversion side-by-side logging — observation only, no execution)

It does NOT include (all offline-ready in repo):
- Exp 4 chop trailing-stop giveback control (`b97f903`)
- G1/G2/G3 mechanical fixes (`15cc0a4`)
- H1/H2 production risk-budget cap + feature drift guard (`679ffd2`)
- Per-trade notional cap + daily max-loss circuit breaker (`bb5cbb5`)
- Slack/webhook alert wiring (`33d6138`)
- H5 settings API frozen/halted enforcement (`c306074`)
- Canonical drawdown-kill resolution + startup validator (`0ac6e2d`)
- Compose drawdown-kill alignment fix (`eb90fa3`)

---

## 2. Repo HEAD truth

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD SHA | `eb90fa369e2739f77c7b1789aa47bd8b83184912` |
| HEAD message | `fix(compose): align docker-compose.yml drawdown-kill fallback with code default` |
| Worktree | clean of tracked changes; many untracked `.md` reports and bundle dirs (audit artifacts) |

The 8-commit chain `ce06d41 → eb90fa3` represents the offline-ready stack queued for the next deploy. **Live ↔ HEAD gap = 8 commits** behind on container, all sitting on `main`.

---

## 3. Account / runtime state

| Item | Value |
|---|---|
| Mode | Paper (Alpaca PA3RLEN7T0N4) |
| Account | ACTIVE, not restricted |
| Peak equity | $111,784.74 |
| Current equity | $111,531.07 |
| Drawdown vs peak | -0.227% |
| Universe size | 22 |
| Tick interval | 10s |
| Tick count this session | 28,680 (engine running pre-restart; container just restarted at 00:48Z) |
| `frozen` | `false` |
| `trading_halted` | `false` |
| `change_count_today` | 1 (engine-side); 0 (governance-side) |
| `disabled_strategies` | [] |

Positions: container restarted at 00:48Z (Friday after market close); positions assumed flat per nightly EOD policy. (Live broker call was not re-issued in this read-only audit; will re-verify at preopen.)

---

## 4. Brain / runtime snapshot

From `organism_brain/manifest.json` (saved 2026-04-24T20:00:24Z, immediately after market close):

```
brain_format_version : 2
saved_at             : 2026-04-24T20:00:24+00:00
total_runs           : 1300
generation           : 124
total_trades         : 396
cumulative_pnl       : -621.92
best_sharpe          : 3.4363
ml_is_trained        : true
feature_count        : 79
```

`learning_state.json` is in sync:
- `generation = 124`
- `total_trades = 396`
- `cumulative_pnl = -621.92`
- `best_sharpe = 3.4363` (best_generation = 26)
- `retrain_count = 124`
- `drift_events = 0`
- `bars_since_retrain = 0`

Manifest ↔ learning_state are coherent. ML classifier + regressor artifacts present. 79 features (matches expected post-hardening shape).

`extra_counters.json`: `peak_equity = 111784.74`, `tick_count = 28680`, `bars_since_retrain = 130`.

---

## 5. Configuration resolved at runtime

From `artifacts/resolved_config_snapshot.json`:

```
ORGANISM_DRAWDOWN_KILL_PCT  = 0.20  (env, dotenv, resolved all match)
ORGANISM_MAX_POSITIONS      = 8
ORGANISM_TICK_INTERVAL_SECS = 10
ORGANISM_EXPLORATION_ENABLED= false
ORGANISM_ALPHA_TOP_N        = 5
APP_ENVIRONMENT             = development   (paper compose gotcha)
ALPACA_PAPER                = true

learning_mode_threshold_trades  = 200
evolution_freeze_until_trades   = 300       (we are post-300 with 396 trades)
horizon_timeout_bars            = 18
bar_boundary_entry_only         = true
confidence_gate_baseline        = 0.40
confidence_gate_defensive       = 0.45
fitness_gate_production         = 0.45
risk_budget_learning            = 0.0010
risk_budget_production          = 0.0025
inverse_etfs                    = [DOG, PSQ, RWM, SH]
universe_size                   = 22
```

Confidence weights (production, post-300): `ml=0.50, breakout=0.30, tension=0.20`.

Stop ATR table (production): `chop=2.5, trending_up=3.5, trending_down=2.5, high_vol=4.0, low_vol=3.0, stress=2.5, unknown=3.0`.

---

## 6. Live = ce06d41 — what is materially in / out

| Capability | In live container? | Notes |
|---|---|---|
| Exp 1A — chop min-hold pyramid_cut | YES | Verified via avg chop pyramid_cut bars_held = 7.8 |
| Exp 2 — chop inverse ETF suppression | YES | Verified: only 3 PSQ/SH trades in 12 sessions |
| Exp 3 prep — confidence inversion logging | YES | Observation only; no execution change |
| Exp 4 — chop trailing-stop giveback control | NO | offline-ready in `b97f903` |
| G1 — exit-level restore warning | NO | offline-ready in `15cc0a4` |
| G2 — cooldown-on-success-only | NO | offline-ready in `15cc0a4` |
| G3 — NaN pyramid guard | NO | offline-ready in `15cc0a4` |
| H1 — production risk-budget cap | NO | offline-ready in `679ffd2` |
| H2 — feature drift guard | NO | offline-ready in `679ffd2` |
| Per-trade notional cap | NO | offline-ready in `bb5cbb5` |
| Daily max-loss circuit breaker | NO | offline-ready in `bb5cbb5` |
| H5 settings API frozen/halted enforcement | NO | offline-ready in `c306074` |
| Slack/webhook alert wiring | NO | offline-ready in `33d6138` |
| Canonical drawdown-kill resolver + startup validator | NO | offline-ready in `0ac6e2d` |
| Compose drawdown-kill alignment | NO | offline-ready in `eb90fa3` |

---

## 7. Connectivity & error baseline (last 7 days)

From `logs/application.log`:

- 2026-04-22 16:02 — `ConnectTimeout` fetching PLTR (single)
- 2026-04-22 17:01 — `ConnectTimeout` fetching SQ (single)
- 2026-04-22 19:32 — `ConnectError` fetching SQ (single)
- 2026-04-23 18:00 — Scanner request failed after retries
- 2026-04-23 18:47 — Alpaca `/v2/positions` and `/v2/account` SSL `UNEXPECTED_EOF` (~3 calls in same minute)
- 2026-04-24 02:40 — DB session error (validation, rolled back) — single
- 2026-04-24 14:00 — Scanner request failed after retries (single)

No halts, no freezes, no drawdown trips. Transient connectivity blips only.

---

## 8. Verdicts

- **Worktree ambiguity**: NONE. HEAD = `eb90fa3`, no tracked diff, audit `.md` files are untracked artifacts (intentional).
- **Live ↔ HEAD gap**: 8 commits.
- **Live container health**: HEALTHY, restart count 0, manifest+learning_state in sync.
- **Brain post-300**: yes, evolution freeze lifted (we're at 396 trades).
- **What is LIVE NOW**: Exp 1A, Exp 2, Exp 3 prep (logging-only).
- **What is OFFLINE READY**: Exp 4, G1/G2/G3, H1/H2, notional cap, daily max-loss, alert wiring, H5 governance API, canonical drawdown-kill, compose alignment.
- **What is FROZEN**: structural persistence path (F1–F4 + F-lite shipped earlier; observation-only, no further structural edits in flight).
- **What is BACKLOG**: Phase C (clean separation of ranking_score/direction/expected_return/size; true microstructure alpha; staged learning→production transition).
