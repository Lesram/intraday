# Pre-9D Legacy Scanner Causal Audit — 2026-05-10

## Verdict

This audit found one real technical defect class before Phase 9D: the legacy
shadow scanners for ORB, EOD momentum, and mean reversion could consume bars
after the scan timestamp when replay or research code passed a full-session
DataFrame. The risk was not an active live-order leak under current defaults
because the corresponding live flags remain off, but it was a research-quality
defect: shadow evidence could look better or different than what would have
been knowable in real time.

The Phase 9 strategy-governance engines already use timestamp-bounded session
slices. The defect was isolated to older scanners retained for shadow and
optional legacy live flags.

## Confirmed Fix

- `backend/organism/orb_scanner.py` now trims input frames to bars at or before
  `now_dt` before computing ORB cache, relative volume, ATR fallback, and
  breakout state.
- `backend/organism/eod_scanner.py` now trims input frames before computing
  day return, current price, and ATR fallback.
- `backend/organism/mean_reversion_scanner.py` now trims input frames before
  computing session VWAP, current price, ATR, displacement, and ranking.
- Regression tests now pass full-session frames with future moves and assert
  those future bars cannot trigger a current signal.

## Audit Evidence

### Focused scanner tests

```bash
./venv/bin/python -m pytest --timeout=30 -q tests/test_orb_scanner.py tests/test_eod_scanner.py tests/test_mean_reversion_scanner.py
```

Result: `54 passed in 0.72s`.

### Lint smoke on touched files

```bash
./venv/bin/python -m ruff check --select F,E9 backend/organism/orb_scanner.py backend/organism/eod_scanner.py backend/organism/mean_reversion_scanner.py tests/test_orb_scanner.py tests/test_eod_scanner.py tests/test_mean_reversion_scanner.py
```

Result: `All checks passed!`.

### Phase 9 and strategy evidence tests

```bash
./venv/bin/python -m pytest --timeout=30 -q tests/test_phase9_etf_intraday_momentum.py tests/test_phase9_research_engines.py tests/test_phase9_shadow_evidence.py tests/test_phase9_strategy_governance.py tests/test_phase6_strategy_evidence_warehouse.py
```

Result: `28 passed in 0.72s`.

### Legacy strategy wiring tests

```bash
./venv/bin/python -m pytest --timeout=30 -q tests/test_orb_shadow_wiring.py tests/test_m3_features.py tests/test_ferrari_v1_fixes.py tests/test_phase3_orb_shadow_outcome.py
```

Result: `42 passed in 1.29s`.

### Organism safety/regression pack

```bash
./venv/bin/python -m pytest --timeout=30 -q tests/test_organism_live_engine.py tests/test_organism_engine_scenarios.py tests/test_multi_tick_state.py tests/test_safety_invariants.py tests/test_replay_simulator.py tests/test_self_evolution.py
```

Result: `138 passed, 2 warnings in 191.22s`.

### Order and reconciliation pack

```bash
./venv/bin/python -m pytest --timeout=30 -q tests/test_order_integrity_comprehensive.py tests/test_position_reconciliation.py tests/test_position_reconciliation_comprehensive.py
```

Result: `76 passed, 3 warnings in 0.80s`.

### Repository gates

- `scripts/ci/verify_findings_ledger.py`: PASS, 130 ledger items.
- `scripts/ci/forbid_marker_only_critical_high.py`: PASS, 48 Critical/High
  closures audited.
- `scripts/ci/lint_ratchet.py`: PASS, current 3680 vs baseline 3801.
- `scripts/ci/check_migrations.py`: PASS, single head `20260503_000003`.
- `scripts/ci/check_wave_markers.py --repo-root .`: PASS with legacy commit
  body warnings only.
- `pytest --collect-only tests/ | grep -c '<Function'`: 6276 collected tests.
- `scripts/ci/phase7_security_sanity.py`: PASS, 19 probes.
- `scripts/ci/phase7_integration_checkpoint.py`: PASS, 18 pass / 1 warn
  while the worktree was dirty from this audit patch.

## Runtime Snapshot During Audit

- Branch: `codex/v13-phase2-expectancy`.
- Host/container SHA before this fix: `d7062debbd6ac496313ab82ff68d39c3105e72ae`.
- Container health: `/healthz` 200.
- Deploy health: `/api/v1/health/deploy` 200.
- DB migration head: `20260503_000003`.
- Paper book: flat at the integration checkpoint.
- Live strategy health remains negative:
  - `n_trades`: 551
  - `total_pnl`: `-763.1831`
  - `win_rate`: `0.3321`
  - `sharpe_ratio_per_trade`: `-1.3366`

## Residual Risks

- This audit improves evidence truth, not strategy profitability.
- ORB/EOD/MR legacy scanners still have optional live feature flags. They must
  stay disabled unless independently promoted through the strategy-governance
  evidence ladder.
- The strategy history remains negative. Phase 9D should focus on research
  evidence and promotion discipline, not risk scaling.
- Full `ruff check --no-fix` remains governed by the lint ratchet rather than a
  zero-violation baseline.

## Recommendation

Proceed to Phase 9D only after this fix is deployed to the paper container and
the post-deploy `/healthz`, deploy-health, security sanity, integration
checkpoint, and artifact generation pass on the new SHA.
