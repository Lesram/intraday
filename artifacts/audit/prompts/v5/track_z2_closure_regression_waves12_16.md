# Track Z2 v5 — Closure Regression Sweep (Waves 12-16)

Verify every fix shipped in waves 12-16 still holds in the running container,
AND scan for new instances of the same bug class that may have been introduced
in adjacent code.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d43dbec`.

## Scope (waves 12-16)

| Wave | Findings closed | Commits |
|---|---|---|
| 12a | R-F-1 (CSV flag), R-F-6 (BG trainer filter) | 731330b |
| 12b | N-C-3 (outbox claim-lease) | 211a5c6 |
| 12cd | N-C-2 (tick_telemetry import), R-F-5 (ensemble persist via essential save) | 2c6750f |
| 12e | P-P0-1 (`/metrics` 503), P-P0-2 (phantom ORGANISM_* metrics) | 5551487 |
| 12f | P-P0-3 (forensic-guard worker-thread alert), P-P0-4 (3 dead alert sites) | 925175b |
| 13ad | Q-Q1/R-F-3 (per-symbol day-roll), R-F-7/R-F-8 (walk-forward + learning unfiltered), P-P0-5 (drawdown alert), Q-Q15 (`_save_brain` to_thread) | 75cb998 |
| 13efg | N-H-2 (lot row-locking), O-2/O-3/O-4 (FE/BE field drift), N-C-1 (drawings migration) | 435885d |
| 14 | Q-Q5/Q-Q2 (cache + equity-curve caps), P-P1-* (ML retrain alert + log rotation), N-H-1/3/4 (schema/backup/session), O-5/6/7 (FE URL fixes), P-P2 (pandas_ta noise) | 3104b61 |
| 15 | Z-R-1/Z-R-2 (test fixture tz parity), R-F-9 (orphan adoption symmetry), N-M-1 (users.* doc) | 3fe2a0d |
| 16ab | Z-R-3 (drawdown-kill behavioral test), Z-R-4 (sector + liquidity-gate test fixes), drawdown-kill orphan cleanup | 4a49058 |
| 16c | H-2 (sync-response dead-code cleanup) | fadcd40 |
| 16d | H-1 (ID-namespace unification) | 7fc68fc |

## Method

1. **Per-finding verification**: for each closed ID, run a verification grep / curl /
   file-check / pytest. Record verdict in a table. Examples:
   - **R-F-1**: `grep "is_reconciliation_artifact" organism_brain/trade_history.csv` —
     not yet present (column appears on next save with a recon trade); but
     `grep "is_reconciliation_artifact" backend/organism/brain_persistence.py` should
     show 5+ hits across save and dual-fallback load paths.
   - **N-C-3**: `grep "_CLAIM_LEASE_SECONDS" backend/infra/outbox.py` should return ≥1.
   - **N-C-2**: `docker exec intra-api-1 python -c "from backend.infra.db import get_session_context; print('ok')"`.
   - **R-F-5**: `grep "ensemble.save(self.brain_dir)" backend/organism/brain_persistence.py`
     in `save_essential_state` body specifically.
   - **P-P0-1/2**: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/system/metrics` → expect 200; pipe to `grep -c "^organism_"` → expect ≥10.
   - **P-P0-3**: `grep -c "Forensic-guard alert deferred" backend/organism/live_engine.py` ≥1.
   - **P-P0-5**: `grep "Drawdown Kill Triggered" backend/organism/live_engine.py` should match.
   - **Q-Q1/R-F-3**: `grep "_symbol_daily_pnl\|_symbol_consecutive_losses" backend/organism/live_engine.py` and check the date-roll block resets all 6.
   - **R-F-7/8**: `grep "_strategy_trades" backend/organism/live_engine.py` ≥4 hits (helper + 4 callers).
   - **N-H-2**: `grep "with_for_update" backend/services/lot_tracker_service.py` ≥1.
   - **O-2**: `grep "serialization_alias" backend/api/portfolio.py backend/api/routes/positions.py` ≥10.
   - **N-C-1**: `docker exec trading_platform_db_paper psql -U trading -d algotrading -c "\d drawings"` should show table.
   - **Q-Q5**: `grep "_MEMORY_CACHE_LAYER_CAP" backend/services/cache.py` ≥1.
   - **Q-Q15**: `grep "asyncio.to_thread(self._save_brain)" backend/organism/live_engine.py` ≥2.
   - **H-1**: `grep "self._terminal_order_ids.add(str(order.id))" backend/integrations/alpaca_stream.py` ≥1.
   - **H-2**: `grep "filled_qty = order_result.get" backend/organism/live_engine.py` should be 0 (dead read removed).

2. **Same-bug-class scan**:
   - Reconciliation flag: any new TradeRecord write site that doesn't carry
     `is_reconciliation_artifact`?
   - Sync alert from worker thread: any new `asyncio.create_task(send_alert(...))`
     that isn't wrapped in the get_running_loop+call_soon_threadsafe pattern?
   - Naive datetime: `grep -rn "datetime.utcnow()\|datetime.now()" backend/` and audit
     each for naive/aware mismatch.
   - Numpy un-cast `to_dict()`: any new method?
   - HTTPException sanitizer: any new `detail=str(e)` or `detail=f"...{e}"` outside
     `errors.py`?
   - Set-only-grow patterns: any new module-level dict / list without bound?
   - Unbounded list: any new `_*_history` / `_equity_curve`-shaped without cap?
   - Daily counter: any new per-symbol counter with `_today` semantics not in the
     date-roll reset block?
   - `_pending_entry` cleanup: any new code path that adds to `_pending_entry`
     without a matching cleanup on drawdown / cancel / reconcile?

3. **Test suite delta**: run the curated deploy-critical subset (`tests/test_rc_1_5_curated.py`
   + ferrari + replay simulator + algorithm improvements + audit_patch_queue + remediation
   + quote/cache extended/comprehensive). Expect ≥220 pass; report any new failures.

4. **Brain coherence check**: snapshot manifest now; should match
   gen=168, trades=498, ml_is_trained=true (or have moved forward only via
   total_runs ticker).

5. **Deploy artifacts**: confirm that the 9 deploy bundles
   `artifacts/deploy_audit_wave12*` ... `wave16*` exist with PRE/POST snapshots.

## Output

`artifacts/audit/v5_reports/track_z2_closure_regression.md` with:
- Per-finding verification table (ID × command × verdict × notes)
- Same-bug-class scan results (pattern × current count × delta from fix-commit baseline)
- Test-suite delta
- Brain-coherence delta
- Any regression discovered
- "Regressions found: N" + TL;DR

## Constraints

Read-only. `docker exec` reads, `curl` no-mutation, `pytest` ok.

## Quality bar

Expect 0-2 regressions. >2 means waves 12-16 didn't hold cleanly and an
emergency wave is needed before further audit work.

End with one-paragraph summary.
