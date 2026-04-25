# Release Candidate Diff Map

**Live**: `ce06d41` → **RC**: `eb90fa3`
**Total**: 16 files changed, +1,144 / −13 lines across 8 commits

File-by-file map of what changes if the RC is deployed.

---

## Production code (backend/)

### `backend/organism/governance.py` (+58 / −4, from `0ac6e2d`)
**Purpose**: Canonical drawdown-kill resolution + startup validator.
- New module constants: `DEFAULT_DRAWDOWN_KILL_PCT=0.05`, `DEFAULT_DRAWDOWN_COOLDOWN_S=3600`, `DEFAULT_MAX_CHANGES_PER_DAY=100`, `_DRAWDOWN_KILL_DRIFT_WARN_RATIO=1.5`
- Explicit env-vs-default resolution with `_drawdown_limit_source` field
- Startup INFO log with resolved value + source
- Startup WARN log when env override > 1.5× default

**Behavior**: No change to the kill-switch logic. Added observability only.

### `backend/organism/live_engine.py` (+66, from `15cc0a4` + `bb5cbb5`)
**Purpose**: G1 + G2 mechanical guards; per-trade notional cap + daily max-loss circuit breaker.
- G1 (exit-level restore): promotes DEBUG → WARNING + marks `entry_metadata.exit_levels_failed=True`
- G2 (cooldown-on-success-only): moves cooldown-set from `finally` to success path
- `MAX_NOTIONAL_PER_TRADE` / `MAX_DAILY_LOSS` env reads (lines 191–192); default 0 = inert

**Behavior**: G1/G2 are pure corrections (silent failure → visible). CAP/HALT inert unless envs set.

### `backend/organism/adaptive_exits.py` (+40, from `15cc0a4` + `b97f903`)
**Purpose**: Exp4 chop-trail widen.
- `_EXP4_CHOP_TRAIL_MODE` constant (default "widen")
- Chop regime: 3.0× ATR → 5.0× ATR trail distance
- Non-chop trails unchanged, stop_loss unchanged, timeout unchanged

**Behavior**: Chop-regime trailing stops widen ~67%. Giveback target: $195 / 5 sessions recovered.

### `backend/organism/pyramider.py` (+8, from `15cc0a4`)
**Purpose**: G3 NaN/Inf pyramid guard.
- Early-return `PyramidAction("none")` if `not math.isfinite(current_price) or current_price <= 0`

**Behavior**: Prevents silent pyramid disable on corrupt streaming data. Zero cost on happy path.

### `backend/organism/kelly_sizer.py` (+18, from `679ffd2`)
**Purpose**: H1 production risk-budget cap application.
- After Kelly sizing, clamp shares by ATR-stop-distance at production rate (0.25%)
- Previously defined but unapplied

**Behavior**: Production-mode per-trade risk-dollar is now capped. Active since trade 200 would have been capped, but wasn't.

### `backend/organism/ml_signal.py` (+38, from `679ffd2`)
**Purpose**: H2 feature drift guard + alert hook.
- If >20% of trained features missing at inference, return neutral (0, 0.5)
- Alert (`send_alert`) on drift neutralization

**Behavior**: Fail-safe on degraded inference. Alert fires when the guard activates.

### `backend/organism/brain_persistence.py` (+13, from `33d6138`)
**Purpose**: Alert hook on brain-save guard fire.
- Wraps guard trigger with `send_alert(SYSTEM_ERROR, ERROR)`

**Behavior**: Brain-save block is now visible to ops.

### `backend/api/routes/settings.py` (+14, from `c306074`)
**Purpose**: H5 governance enforcement on settings mutations.
- `_check_governance()` helper — HTTP 403 if frozen or halted
- Called in PUT `/settings/organism`, `/settings/trading`, `/settings/ml`

**Behavior**: Closes prior bypass where settings could be mutated while frozen/halted.

---

## Ops / deploy config

### `docker-compose.yml` (+3 / −2, from `eb90fa3`)
**Purpose**: Align fallbacks with code defaults.
- `ORGANISM_DRAWDOWN_KILL_PCT` fallback: `0.03 → 0.05`
- `ORGANISM_DRAWDOWN_COOLDOWN_S` fallback: `300 → 3600`
- Inline comment referencing `DEFAULT_DRAWDOWN_KILL_PCT`

**Behavior**: Fallback only — affects dev setups that run `docker-compose.yml` without `.env`. Paper/prod deploys unchanged.

---

## Scripts

### `scripts/generate_experiment_observation_report.py` (+80, from `b97f903`)
**Purpose**: Observation tooling for Exp4.
- Adds giveback section to the daily post-close report
- Aggregates MFE captured / forfeited per exit type

**Behavior**: Enables post-deploy measurement of Exp4 effect. Required for decision-making after 5–10 sessions.

---

## Tests

| File | Added lines | From commit | Coverage |
|---|---|---|---|
| `tests/test_g1_g2_g3_mechanical_fixes.py` | +183 | `15cc0a4` | G1/G2/G3 |
| `tests/test_experiment_4_trailing_giveback.py` | +194 | `b97f903` | Exp4 |
| `tests/test_h1_h2_real_money_hardening.py` | +172 | `679ffd2` | H1/H2 |
| `tests/test_real_money_risk_limits.py` | +135 | `bb5cbb5` | cap/halt |
| `tests/test_h5_settings_governance.py` | +44 | `c306074` | H5 |
| `tests/test_governance_drawdown_canonical.py` | +85 | `0ac6e2d` (this sprint) | drawdown canonical |

Total new test coverage: **+813 lines across 6 test files**.

---

## Runtime config surface (unchanged)

No `.env` entries added or removed by the RC itself. However, to unlock the env-gated features, operators should review:

| Env var | Purpose | Default (if unset) | Recommended for next deploy |
|---|---|---|---|
| `ORGANISM_MAX_NOTIONAL` | per-trade cap (`bb5cbb5`) | 0 = disabled | `2500` for Stage-1 pilot |
| `ORGANISM_MAX_DAILY_LOSS` | daily circuit breaker (`bb5cbb5`) | 0 = disabled | `500` for Stage-1 pilot |
| `SLACK_WEBHOOK_URL` | alerts (`33d6138`) | unset = silent | live Slack webhook |
| `ORGANISM_DRAWDOWN_KILL_PCT` | kill-switch | 0.05 (now canonical) | review current `.env=0.20` |

---

## Summary

| Category | Lines | Files |
|---|---|---|
| Production code | +257 | 8 |
| Ops / deploy | +3 | 1 |
| Scripts | +80 | 1 |
| Tests | +813 | 6 |
| **Total** | **+1,144 / −13** | **16** |

Net code-path impact (production modules): 257 net-added lines spread across 8 modules, each touched by at most 2 commits with non-overlapping edits. No churn, no merge risk, no cherry-picks needed.

— End of Release Candidate Diff Map —
