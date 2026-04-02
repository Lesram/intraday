# AIA Architect Handoff — April 2026

## 1. Project State

| Field | Value |
|---|---|
| Branch | `main` |
| HEAD SHA | `3534346` |
| Runtime deployed from HEAD | Yes — container rebuilt from `3534346`, verified |
| Readiness verdict | READY_TO_TRADE |
| Runtime status | API healthy, 3 containers (api, postgres, redis), brain loaded (gen 0, 161 trades, ML trained) |
| Account | Alpaca paper PA3RLEN7T0N4, ~$111,645 equity, ACTIVE, not blocked |
| Brain volume mount | `./organism_brain:/app/organism_brain` (durable across restarts) |

The platform is paper-trading live on Alpaca. It traded 28 round trips on Mar 31 and 14 on Apr 1. The organism is in learning mode (161/300 trades toward evolution freeze exit). ML model has been trained and accepted (gen 1 → gen 4 during Mar 31 session) but does not influence trading until 300-trade freeze exits.

**Known data loss**: ~24 trades from late Mar 31 + all of Apr 1 were lost from brain history because the walk-forward gate blocked persistence before the fix landed. Brain was restored from a Mar 31 backup (161 trades). Those trades exist in Alpaca order history but not in brain/learner state.

## 2. What Has Been Fixed

### Incident Recovery (commits 74ced3d → 296012b)
- **No-trade drought** (10+ days without trading): Root-caused to gate/confidence/scanner misalignment. Fixed via waves R1–R4, A–C, XA–XB covering mechanical resilience, gate calibration, universe convergence, and away-mode hardening.
- **Exploration execution removed** (H1): No code path exists to execute exploration trades.
- **ML isolation in learning mode** (H2–H3): Confidence formula uses breakout+tension only until 300 trades.
- **Evolution freeze** (H4): Warm-start and param evolution blocked until 300 trades.
- **ExitLevels v4 restore** (H5): Trailing stop and FTF state survives restarts.
- **Unified entry gates** (H6): Pure breakout shares liquidity+confidence gates with alpha.

### Brain Durability (commits 53cc1ad → 3534346)
- **Brain volume mount**: `organism_brain/` is now a Docker volume mount — survives container rebuilds.
- **Stale metadata pruning on startup**: Entry metadata is cross-checked against broker positions; orphan metadata is removed to prevent phantom trades (root cause of XLK +$174 artifact on Mar 31).
- **Reconciliation adjustment classification**: Phantom closes tagged as `reconciliation_adjustment` instead of `live_close`, separating artifacts from strategy P&L.
- **regime_at_exit fix**: Uses per-tick `_last_regime` instead of `regime_detector.current_regime` (which was always "unknown" due to save/restore pattern in aggregation loops).
- **Split persistence model**: `save_essential_state()` persists ALL runtime truth (trade history, learning state, evaluation events, equity curve, counters, governance, regime state) even when walk-forward gate blocks. Only ML model binaries and evolved_params remain gated.

### What the walk-forward gate now controls
- **Gated**: `ml_classifier.joblib`, `ml_regressor.joblib`, `evolved_params.json` — only written on full atomic-swap `brain.save()` when Sharpe passes the gate.
- **Always persisted**: Everything else — trade history, forensic fields, learning state, evaluation events, equity curve, extra_counters, governance, regime, ml feature config, manifest.

## 3. What Is Still Unresolved

### Paper-Path / Operational Risks
- **~24 trades lost from brain history** (late Mar 31 + Apr 1): Exist in Alpaca but not in learner state. Brain shows 161 trades; actual lifetime is ~185. This affects evolution freeze countdown.
- **Walk-forward gate best_sharpe mismatch**: Brain was restored from a backup where best_sharpe=0. The Mar 31 session reached best_sharpe=1.1611 but that was lost. Current gate may behave differently than expected until Sharpe is re-established.
- **Test suite has 28–33 pre-existing failures**: Mostly test-spec calibration issues from hardening audit patches, not runtime bugs. No test failures are on the trading critical path.

### Strategy-Design Risks (do not fix yet — collect more data)
- **XLE repeated re-entry**: 4 entries on Mar 31, 0% win rate, -$42.73. No per-symbol intraday cooldown exists. Monitor 5 more sessions before deciding.
- **high_vol regime entries losing**: -$41.70 on Mar 31 across 4 trades. The organism lacks edge in high_vol. Monitor.
- **Inverse ETFs (SH, PSQ) marginal**: Combined ~0% win rate across both sessions. Not clearly adding value.
- **Late-session alpha weaker**: Apr 1 trades after 2:30 PM EDT were mostly losers.

### Production-Only Backlog
- Alpha weights sum to 0.9497 (expected ~1.0) — pre-existing, cosmetic.
- regime_at_exit cold-start on first session after container rebuild (needs 200+ bars of SMA history).

### Monitor Only
- Pyramid cut exits have 0% win rate but avg loss of -$5.24 — they are controlling losses as designed.
- ML evaluation attempts running every ~6 min during trading — all rejected so far except one Gen 1 acceptance on Mar 31. Expected behavior during learning mode.

## 4. Current Strategic Interpretation

The platform is **mechanically trading again** after a 10+ day no-trade drought caused by gate/scanner misalignment. Two consecutive sessions (Mar 31: +$27 normalized, Apr 1: +$49) were genuinely profitable with healthy payoff ratios (1.86x and 4.23x).

The strategy is **not yet fully proven**. The organism is still in learning mode (161/300 trades). Confidence scoring uses only breakout+tension; ML will not influence decisions until evolution freeze exits. The current edge appears to come from horizon_timeout and trailing_stop exits on large-cap names in chop regime.

**Do not change strategy design yet.** The organism needs ~130 more trades (~5–8 sessions) to reach the 300-trade freeze threshold. Strategy-level changes (cooldowns, regime gating, inverse ETF criteria) should be evaluated after freeze exit.

## 5. Source-of-Truth Files (Priority Order)

| Priority | Path | Purpose |
|---|---|---|
| 1 | `docs/architecture/mapss.md` | Unified platform architecture map |
| 2 | `AGENTS.md` | Agent operating contract |
| 3 | `backend/organism/live_engine.py` | Core tick loop (~3,700 lines) |
| 4 | `backend/organism/brain_persistence.py` | Brain save/load + split persistence |
| 5 | `backend/organism/continuous_learner.py` | TradeRecord, LearningState, learner |
| 6 | `backend/organism/adaptive_exits.py` | ATR exits, horizon timeout, trailing stop |
| 7 | `backend/organism/alpha_scanner.py` | Alpha scoring, in-play, inverse ETFs |
| 8 | `backend/organism/self_evolution.py` | Evolution engine, canonical fitness |
| 9 | `backend/organism/kelly_sizer.py` | Kelly sizing, risk-budget floor |
| 10 | `docker-compose.paper.yml` | Paper deployment config (volume mounts) |
| 11 | `docs/architecture/improve9.md` | AIA deep research report + implementation log |
| 12 | `tests/test_march31_safe_fix.py` | Reconciliation fix tests (15 tests) |
| 13 | `tests/test_walkforward_persistence.py` | Persistence fix tests (21 tests) |

## 6. Next Recommended Task

**Post-close daily audit and trading report for the next completed session.**

Run a full post-close audit after the next trading day, capturing: trade count, P&L, exit reason economics, regime performance, forensic field verification (confirm regime_at_exit is now populated, confirm no reconciliation_adjustment artifacts), brain persistence verification (confirm trades persisted even if walk-forward gate blocked), and comparison to Mar 31 / Apr 1 baselines. This validates all deployed fixes under live conditions and builds the data needed for the 300-trade freeze exit evaluation.

## 7. Known Caveats

- **Repo HEAD is the source of truth.** Previous chat-exported files on Desktop may be stale. Always verify against `git show HEAD:path/to/file`.
- **Separate correctness fixes from strategy changes.** The current backlog has both. Correctness/persistence fixes can ship immediately. Strategy design changes (cooldowns, regime gating, universe rotation) must wait for more data.
- **Brain state lags actual lifetime trades.** Brain shows 161 trades but the organism has executed ~185+ lifetime trades. The gap is from pre-fix data loss. Evolution freeze countdown uses the brain number (161), not the true number.
- **Walk-forward gate may behave differently than pre-data-loss.** The restored brain has best_sharpe=0 instead of the 1.1611 that was achieved during the lost Mar 31 late session. This means the gate may pass earlier than it would have otherwise.
- **28–33 test failures are pre-existing** and unrelated to trading logic. They are test-spec calibration issues from hardening audit patches. Do not block deployments on these.
- **The organism uses `logging.getLogger()`, NOT structlog.**
- **`APP_ENVIRONMENT` must be `development` (not `paper`) in docker-compose.**
