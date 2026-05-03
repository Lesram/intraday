# Findings Ledger

Tracks every audit finding through the fix-and-verify cycle. Updated as fixes ship.

**Audit round v1:** 2026-05-01 (baseline).
**Fix campaign:** Phase 1–5, deployed in 5 sequenced batches.
**Audit round v2:** scheduled after Phase 5 deploys.

State semantics:
- `open` — finding exists, no fix shipped
- `in-progress` — fix written, not yet deployed
- `fixed` — code committed to main
- `verified` — deployed and observed-working in production
- `closed-v2` — re-audit confirmed not re-detected

## Critical findings (8)

| ID | Track | Title | Severity | State | Phase | Fix commit |
|---|---|---|---|---|---|---|
| 1 | G | `lifespan.shutdown()` doesn't `force_save_brain()` | 🔴 Critical | open | Phase 1 | — |
| 2 | G | Reconciliation PnL pollutes Kelly/ML/symbol-ban gating | 🔴 Critical | open | Phase 4 | — |
| 3 | A | EOD path still has `predicted_return` 0.003 floor | 🔴 Critical | open | Phase 1 | — |
| 4 | B | `DROP_ML_FROM_GATE` only patched alpha+breakout (3 sites still raw) | 🔴 Critical | open | Phase 1 | — |
| 5 | E | Poisoned ORB cache fed 1,295 wrong shadow events for IWM | 🔴 Critical | open | Phase 2 | — |
| 6 | E | Stale streaming-buffer bars served to scanners (108min stale on AMZN) | 🔴 Critical | open | Phase 2 | — |
| 7 | D | `_symbol_banned` reset on restart, never on date change | 🔴 Critical | open | Phase 3 | — |
| 8 | F | Daily max-loss halt persists across day rollover | 🔴 Critical | open | Phase 1 | — |

## High-priority findings (10)

| ID | Track | Title | Severity | State | Phase | Fix commit |
|---|---|---|---|---|---|---|
| 9 | A | EOD scanner absolute stop floor `max(atr, 0.10)` | 🟡 High | open | Phase 1 | — |
| 10 | A | Tension saturation at 0.80 (5 callsites) | 🟡 High | open | Phase 5 | — |
| 11 | D | `_pending_entry_order_ids` written then immediately wiped | 🟡 High | open | Phase 3 | — |
| 12 | C | RF/LGBM ensemble (40% blend) not persisted | 🟡 High | open | Phase 3 | — |
| 13 | E | EOD `LIVE_LOOKBACK=100` too small for 15:30 ET decision | 🟡 High | open | Phase 2 | — |
| 14 | B+F | `MAX_DAILY_LOSS=0` (disabled in `.env`) | 🟡 High | open | Phase 5 | — |
| 15 | F | Sector cap maps ETFs to "ETF" not GICS | 🟡 High | open | Phase 5 | — |
| 16 | F | Daily reset uses UTC not ET (8 PM ET = next day) | 🟡 High | open | Phase 1 | — |
| 17 | B | `MR_TARGET_RETRACEMENT` default mismatch (0.65 vs 0.8) | 🟡 High | open | Phase 1 | — |
| 18 | D | `_exit_cooldown` and `_pending_exit` not persisted | 🟡 High | open | Phase 3 | — |

## Lower-priority findings (12)

| ID | Track | Title | Severity | State | Phase | Fix commit |
|---|---|---|---|---|---|---|
| 19 | F | Drawdown cooldown computes 599s instead of 600s (IEEE-754 drift) | 🟢 Cosmetic | open | Phase 1 | — |
| 20 | D | `_pyramid_positions` not persisted | 🟢 Low | open | Phase 3 | — |
| 21 | D | `_ml_reversal_used` one-shot guard not persisted | 🟢 Low | open | Phase 3 | — |
| 22 | D | `evolved_params.json` stale since Apr 15 | 🟢 Low | open | Phase 3 | — |
| 23 | D | ML calibration persisted twice (ml_state.json + extra_counters) | 🟢 Low | open | Phase 3 | — |
| 24 | F | Notional-cap floor `max(1, ...)` permissive at lower bound | 🟢 Low | open | Phase 5 | — |
| 25 | C | S17 `_last_val_X` cache not persisted | 🟢 Low | open | Phase 5 | — |
| 26 | C | Diagnostic schema-drift alert may be log-only | 🟢 Low | open | Phase 5 | — |
| 27 | G | Orphan-adopted trades have no first-class flag (entry_source="" collides with legacy) | 🟢 Low | open | Phase 4 | — |
| 28 | G | Stale-metadata mis-attribution edge cases | 🟢 Low | open | Phase 4 | — |
| 29 | G | Pyramid-restart silent desync | 🟢 Low | open | Phase 4 | — |
| 30 | G | DB race in trade write | 🟢 Low | open | Phase 4 | — |

## Per-phase fix tally

| Phase | Findings count | Critical | High | Low |
|---|---|---|---|---|
| Phase 1 (quick wins) | 9 | 4 | 4 | 1 |
| Phase 2 (data pipeline) | 3 | 2 | 1 | 0 |
| Phase 3 (state persistence) | 9 | 1 | 3 | 5 |
| Phase 4 (reconciliation) | 5 | 1 | 0 | 4 |
| Phase 5 (calibration & misc) | 4 | 0 | 2 | 2 |
| **Total** | **30** | **8** | **10** | **12** |

## Status legend update history

- 2026-05-01: ledger created, all 30 findings open.
- 2026-05-02: Phase 1-5 + 6.5 complete. v2 re-audit run. Final state:
  - **Closed-v2: 21** (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 21, 27, plus T1+T2+T3+GAP-1..5 from v2)
  - **Deferred low-priority: 8** (12, 20, 22, 23, 24, 25, 26, 28, 29, 30)
  - See `MASTER_AUDIT_SYNTHESIS_v2.md` for detail.

## v2 new findings (Phase 6.5)

All closed in commit `f65f9c3`.

| ID | Track | Title | State |
|---|---|---|---|
| T1 | A | ORB/EOD inline tension caps still at 0.80 | closed-v2 |
| T2 | A | EOD heuristic predicted_return cap 0.020 | closed-v2 |
| T3 | A | MR composite dead `max(0.45, ...)` floor | closed-v2 |
| GAP-1 | G | Startup orphan-adoption no entry_source tag | closed-v2 |
| GAP-2 | G | is_reconciliation_artifact not persisted | closed-v2 |
| GAP-3 | G | Kelly + signal_gen mutators ungated | closed-v2 |
| GAP-4 | G | Evolution engine unfiltered trades | closed-v2 |
| GAP-5 | G | DB-trade reconstruction no flag derivation | closed-v2 |

## v3 findings (Tracks H–M, 2026-05-02)

58 findings across 6 surfaces. ~50 closed in waves 8a-11d on `rc-1.5-curated`. H-1 and H-2 held for after V4. See `MASTER_AUDIT_SYNTHESIS_v3.md` for full detail and `MASTER_AUDIT_SYNTHESIS_v4.md` Track Z for closure verification.

## v4 findings (Tracks N/O/P/Q/R/Z, 2026-05-02)

**Total: 52 new findings.** See `MASTER_AUDIT_SYNTHESIS_v4.md` for cross-track patterns and wave 12-15 fix sequence.

### V4 Critical / Organism-level (12)

| ID | Track | Title | Severity | Wave |
|---|---|---|---|---|
| N-C-1 | N | `Drawing` ORM has no migration; `/api/drawings` will 500 | Crit | 13 |
| N-C-2 | N | `tick_telemetry` writes silently broken (`backend.infra.database` doesn't exist) | Crit | 12c |
| N-C-3 | N | Outbox `claim_batch` doesn't flip status; restart re-submits orders | Crit | 12b |
| P-P0-1 | P | `/api/v1/system/metrics` returns 503 on every scrape | P0 | 12e |
| P-P0-2 | P | All 12 ORGANISM_* Prometheus metrics phantom (registry split-brain) | P0 | 12e |
| P-P0-3 | P | Wave-8c missed: `live_engine.py:5625` forensic-guard alert dropped | P0 | 12f |
| P-P0-4 | P | 3 dead alert call sites with wrong signatures, all silent | P0 | 12f |
| P-P0-5 | P | Drawdown-kill triggering has no alert wiring | P0 | 13 |
| P-P0-6 | P | Walk-forward Sharpe regression (46x, no alert, brain refusing to save) | P0 | 13 |
| **R-F-1** | R | *is_reconciliation_artifact* flag NOT in `trade_history.csv` — restart erases isolation | Org | 12a |
| **R-F-5** | R | Wave-11d ensemble persistence regressed (`save_essential_state` skips `_save_ml_models`) | Org | 12d |
| **R-F-6** | R | BG trainer evolution path NOT filtered for reconciliation artifacts (sync IS — split) | Org | 12a |

### V4 High (18)

| ID | Track | Title | Wave |
|---|---|---|---|
| N-H-1 | N | Schema drift: position_lots.user_id Integer FK declared, varchar in DB | 14 |
| N-H-2 | N | `LotTracker.close_lots_fifo` no row-locking; lost-update race | 13 |
| N-H-3 | N | No automated PostgreSQL backup | 14 |
| N-H-4 | N | `async for db in get_session()` leak idiom | 14 |
| O-1 | O | `getCurrentUser()` `/auth/me` raw cast; only login normalizes | 13 |
| O-2 | O | PositionResponse snake_case output, FE reads camelCase → 5 undefined fields | 13 |
| O-3 | O | OrganismStatus.governance keys mismatch — kill-switch banner won't toggle | 13 |
| P-P1-1..5 | P | ML retrain alerts; ALL-stale reconnect; log rotation; FE auth ERROR; orphan adoption silent | 14 |
| Q-Q5 | Q | `CacheService.memory_cache` set-only-grow → OOM risk during Redis outage | 14 |
| Q-Q15 | Q | `_save_brain` inside `_reconcile_fills` blocks event loop (Phase-1 to_thread missed) | 13 |
| R-F-2 | R | H-1 ID-namespace mismatch (still open, two-grep proof captured) | hold |
| R-F-3 | R | Per-symbol counters never reset on date-roll → ghost bans (same as Q-Q1) | 13 |
| R-F-7 | R | Walk-forward gate consumes `_all_trades[-100:]` UNFILTERED | 13 |
| R-F-8 | R | `len(_all_trades)` drives learning-mode/Kelly/freeze threshold UNFILTERED | 13 |

### V4 Medium (15)

| ID | Track | Title | Wave |
|---|---|---|---|
| N-M-1 | N | Naive datetimes on `users.*` columns | 15 |
| N-M-2 | N | `daily_ledger` outside canonical Base namespace | 15 |
| O-4 | O | `handleApiError()` collapses 422 array to "An error occurred" | 13 |
| O-5 | O | `PositionsTable.tsx` raw fetch hardcodes localhost:8000 | 14 |
| O-6 | O | WS URLs hardcode `:8000`; break behind reverse proxy | 14 |
| O-7 | O | `POST /chart-templates` (no slash) hits 307 every save | 14 |
| P-P2-1..4 | P | pandas_ta noise; INFO chatter; `/observability/health/ready` returns unknown | 14 |
| Q-Q2 | Q | `_equity_curve` 37k entries uncapped; full CSV rewrite per save | 14 |
| Q-Q14 | Q | alpaca_client sync SDK relies on each caller wrapping in `to_thread` | 14 |
| Q-Q1 | Q | Per-symbol "today" counters never reset on date-roll (logic, not leak) | 13 |
| R-F-4 | R | Bar-boundary detection bypasses `_now_fn()` — replay/live parity broken on exit | 14 |
| R-F-9 | R | Asymmetric orphan adoption (`target=qty` in-tick vs `target=qty*1.5` startup) | 15 |

### V4 Low / Test-fixture (7)

| ID | Track | Title | Wave |
|---|---|---|---|
| Z-R-1 | Z | 6 `Quote.is_stale` test fixtures use naive datetime against tz-aware production (K-4 drift) | 15 |
| Z-R-2 | Z | 5 cache TTL tests `TypeError` (K-8 drift) | 15 |
| Z-R-3 | Z | Fragile string-grep test | 15 |
| Z-R-4 | Z | 2 pre-existing failures pre-wave-8 (NOT regressions) | hold |
| Q-(3) | Q | 3 nits/info findings (DataFrame allocation per tick, etc.) | 15 |

## V4 cross-track patterns (see synthesis)

1. **Save-path bifurcation** (R-F-5, Q-Q15, N-C-3) — multiple persistence entry points don't carry the same logic
2. **Persistence boundary loses runtime state** (R-F-1, N-C-2, N-H-1, Z-R-1/R-2) — flags erased crossing CSV/DB/fixture boundary
3. **Day-roll boundary leaky one level deeper** (Q-Q1, R-F-3, R-F-7, R-F-8) — V3 K closed module-level; V4 finds counter/threshold-level
4. **Phantom observability** (P-P0-1, P-P0-2, P-P0-3..6, N-C-2) — declared but never delivered
5. **Audit catches its own work** (R-F-5 = wave-11d regression; Q-Q15 = Phase-1 missed site; P-P0-3 = wave-8c missed site)

## Status legend update history

- 2026-05-02 21:30 PT: V4 audit complete. 6 tracks, 52 findings. Wave 12-15 sequence proposed in `MASTER_AUDIT_SYNTHESIS_v4.md`. Container healthy on rc-1.5-curated @ ed64acd; brain coherent (gen=168, trades=498).
- 2026-05-02 23:30 PT: Waves 12 (12a-12f), 13 (13a-d, 13e-g), 14, and 15 all shipped on rc-1.5-curated. Final HEAD `3fe2a0d`. Container healthy at gen=168, trades=498 across 9 force-recreate cycles.

## V4 closure status (post waves 12-15)

| Finding | Wave | Commit |
|---|---|---|
| **R-F-1** | 12a | 731330b |
| **R-F-6** | 12a | 731330b |
| **N-C-3** | 12b | 211a5c6 |
| **N-C-2** | 12cd | 2c6750f |
| **R-F-5** | 12cd | 2c6750f |
| **P-P0-1** | 12e | 5551487 |
| **P-P0-2** | 12e | 5551487 |
| **P-P0-3** | 12f | 925175b |
| **P-P0-4** | 12f | 925175b |
| Q-Q1 / R-F-3 | 13ad | 75cb998 |
| R-F-7 / R-F-8 | 13ad | 75cb998 |
| P-P0-5 | 13ad | 75cb998 |
| Q-Q15 | 13ad | 75cb998 |
| N-H-2 | 13efg | 435885d |
| O-2 / O-3 / O-4 | 13efg | 435885d |
| N-C-1 | 13efg | 435885d |
| Q-Q5 / Q-Q2 | 14 | 3104b61 |
| P-P1-* | 14 | 3104b61 |
| P-P2-* | 14 | 3104b61 |
| N-H-1 / N-H-3 / N-H-4 | 14 | 3104b61 |
| O-5 / O-6 / O-7 | 14 | 3104b61 |
| Z-R-1 / Z-R-2 | 15 | 3fe2a0d |
| R-F-9 | 15 | 3fe2a0d |
| N-M-1 (documented) | 15 | 3fe2a0d |
| N-M-2 (misread; no fix needed) | 15 | 3fe2a0d |
| Z-R-3 (already hardened) | (verified) | 3fe2a0d |
| **H-1 / R-F-2** | 16d | 7fc68fc |
| **H-2** (V3) | 16c | fadcd40 |
| Z-R-3 (fragile string-grep) | 16ab | 4a49058 |
| Z-R-4 (pre-existing pre-wave-8) | 16ab | 4a49058 |
| P-P0-6 (walk-forward Sharpe regression) | partially closed by R-F-7 | 75cb998 |
