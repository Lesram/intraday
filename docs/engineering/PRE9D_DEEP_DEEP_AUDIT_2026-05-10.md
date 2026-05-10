# Pre-9D Deep-Deep Audit

Generated: 2026-05-10
Branch: `codex/v13-phase2-expectancy`
Scope: adversarial re-audit after `36c2452`, before Phase 9D order-path governor wiring

## Executive Verdict

This pass found one real issue that the prior audit did not catch: Phase 9
shadow research engines were side-effect free, but several helpers evaluated a
whole session frame without explicitly slicing bars at `now`. Live order safety
was not affected, but offline/replay research could be contaminated by future
bars if a caller passed a full-day frame.

The issue is now fixed across the Phase 9 research path. ETF momentum,
gamma/vol proxy, stocks-in-play ORB v2, residual mean reversion, EOD reversal,
and the Phase 9 live-engine market-return context now use only bars known at or
before the evaluation timestamp.

This does not make the platform "issue-free." It does remove a material
pre-9D evidence-quality blocker. Phase 9D may proceed only after this slice is
committed, deployed, and live parity is green.

## Finding Fixed

### P9D-AUD-1 — Phase 9 shadow engines could look ahead in offline/replay contexts

Severity: High for research integrity; Low for immediate live order safety.

Affected files:

- `backend/organism/engines/etf_intraday_momentum.py`
- `backend/organism/engines/gamma_vol_proxy.py`
- `backend/organism/engines/orb_sip_v2.py`
- `backend/organism/engines/residual_mean_reversion.py`
- `backend/organism/engines/eod_reversal_shadow.py`
- `backend/organism/universe/stocks_in_play.py`
- `backend/organism/live_engine.py`

Problem:

Phase 9 engines received a `now` timestamp, but helper functions selected all
bars from the session date rather than only bars with `_ts <= now`. Residual MR
used latest returns from the supplied frame. Gamma/vol proxy also used future
bars in its historical volatility/volume normalization. In live streaming this
is usually masked by the provider passing only current-known bars, but replay,
unit tests, and research scripts can pass full-day bars.

Fix:

- Every Phase 9 `_session_bars()` helper now filters by both session date and
  `timestamp <= now`.
- Residual mean reversion returns now filter input bars to `now`.
- Gamma/vol proxy now computes both current session state and z-score history
  from known bars only.
- `_record_phase9_shadow_signals()` now captures one `shadow_now` and passes it
  consistently to engines and market-return context.
- `_market_return_bps()` can filter timestamp columns and datetime indexes to
  `now`.

Regression coverage:

- ETF momentum future-rally trap: future bars after `now` no longer create a
  signal.
- ORB v2 future-breakout trap: future breakout/volume after `now` no longer
  creates a signal.
- Residual MR future-shock trap: future residual shock after `now` no longer
  creates a signal.
- EOD reversal future-reversal trap: future reversal/volume after `now` no
  longer creates a signal.

## Order-Path Safety

Static AST scan of Phase 9 research/schema/evidence/universe modules found:

```text
order_call_hits=[]
```

No `place_order`, `submit_order`, `submit_order_async`, `cancel_order`, or
similar order calls exist inside the Phase 9 research modules touched by this
audit. `StrategyGovernor` remains side-effect free and still is not wired into
order placement; this audit did not implement Phase 9D.

## Runtime And Data Snapshot

Baseline at audit start:

```text
host HEAD/container GIT_SHA: 36c2452120009e4f5ce96ba582f4cde8ba91eaf1
positions_nonzero=0
open_orders=0
migration=20260503_000003
ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED=true
ORGANISM_EXPLORATION_ENABLED=false
```

Live health:

```text
/api/v1/health/deploy: 200
/api/v1/health/strategy: 200
/api/v1/health/data-integrity: 200
audit chain detail: row_count=1247 invalid_count=0 anchors=1
```

Data:

```text
realized_trades=1082
orders=1535
executions=1686
outbox_events=910
throwaway_users=0
positions_nonzero=0
open_orders=0
```

Brain:

```text
generation=204
total_trades=558
strategy n_trades=551
strategy total_pnl=-763.1831
strategy win_rate=0.3321
strategy sharpe_per_trade=-1.3366
```

Interpretation:

The platform is mechanically healthy, but strategy expectancy remains negative.
This audit improves evidence trustworthiness; it does not prove profitability.

## Evidence Loop Status

Phase 8 evidence warehouse still runs:

```text
events=421 outcomes=581 trades=559 db_orders=1535 db_realized_trades=1082 accounting=1082 replay_candidates=1
```

The one Phase 8 replay-only candidate remains:

```text
symbol=AMD
promotion_authorized=0
required_next_step=replay_before_any_live_change
```

Phase 9 shadow evidence still has no market-session Phase 9 events:

```text
raw_events=195
phase9_events=0
joined_outcomes=0
replay_candidates=0
promotion_authorized=false
```

## Validation

Focused and evidence tests:

```text
tests/test_phase9_etf_intraday_momentum.py tests/test_phase9_research_engines.py: 14 passed
Phase 8/9 evidence suite: 65 passed
```

Required organism/order/reconciliation regression suite:

```text
214 passed, 5 warnings
```

Static/gates:

```text
ruff touched files: PASS
mypy Phase 9 research modules: PASS
compileall touched files: PASS
forbid_marker_only_critical_high.py: PASS
verify_findings_ledger.py: PASS
lint_ratchet.py: PASS
check_migrations.py: PASS
check_wave_markers.py: PASS with existing historical advisory warnings
pytest collect-only tests/: 6273 functions
git diff --check: PASS
```

## Remaining Known Risks

1. Phase 9 has not yet collected live market-session shadow events, so no Phase
   9 engine has evidence for replay or micro-paper.
2. The strategy is still unprofitable on current brain history.
3. Full-repo mypy remains advisory because of legacy live-engine and app-wide
   type debt; the Phase 9 research modules touched in this slice pass narrowed
   mypy.
4. The live DB has `outbox_events`, not the older `outbox` table name assumed by
   older audit prompts.

## Phase 9D Go/No-Go

Go after deploy parity is revalidated on this commit:

- Unknown `strategy_id` must block live orders.
- `shadow_only=true` must block live orders.
- Tier 0/1 strategies must block live orders.
- Existing guarded `alpha_baseline` behavior must remain unchanged.
- ORB/EOD/MR current live flags must remain false unless explicitly promoted by
  evidence.

This pass found and fixed a research-integrity blocker. It did not find an
active live order leak.
