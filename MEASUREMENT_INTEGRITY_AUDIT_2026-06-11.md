# Measurement-Integrity Audit — 2026-06-11
**Scope:** the pipeline that produces the numbers themselves: broker fill → reconciliation → trade record → PnL → equity → edge metrics. Previous audits covered architecture, risk, ML methodology, and strategies — this one verifies the *instruments*. Motivated by the operator's question: "are we getting skewed results because of an issue in the system itself?"

**Answer: yes, in three places — now fixed or flagged.** The PnL totals are broadly sound; the *attribution and signal-quality* numbers were not.

## Findings

### M-0 (NEW, CRITICAL for interpretation): the account-vs-book gap
The Alpaca paper account went **100,000 → 111,525 (+$11.5k)** while the organism's entire trade book sums to **−$633**. The ~$12k difference is NOT the audited strategy — it is the *other* execution path (the multi-strategy scheduler shares the account; its trades never enter `trade_history.csv`) plus unrealized open-position value. **Never judge the strategy by account equity.** Run `scripts/reconcile_broker.py` (read-only, on the host) to attribute every dollar by `client_order_id` bucket; output lands in `artifacts/broker_reconciliation.json`. If the organism bucket diverges from the book by more than ~$50, investigate before trusting per-trade records.

### M-1 (BROKEN → flagged): partial exits have no per-leg accounting
A position that scales out (partial TP, pyramid cuts, ML-reversal partials) produces **one full-size row at the final exit price** — the scale-out legs' actual prices are lost, so that row's PnL is approximate. Historical exposure: ~52 of 556 rows (9%) are identifiable as multi-leg. *Fix shipped:* rows now carry `had_partial_exits=True` so analysis can segregate them. *Remaining work (designed, not yet built):* true per-leg trade records — a careful change to `_reconcile_fills` that should be its own reviewed PR.

### M-2 (BROKEN → fixed): the headline correlation was unmeasurable
`predicted_return` is stored as `abs()` with a `0.01` heuristic default — so corr(pred, actual) correlated magnitudes and constants against signed returns, over mismatched horizons. **Every previously reported value of this metric (incl. the −0.060) is void.** *Fix shipped:* new `predicted_return_signed` + `ml_spoke` fields captured at entry; the edge monitor now computes the correlation only over signed, ML-spoke, horizon-matched (`horizon_timeout`) trades, and reports **EDGE-UNMEASURED** (not a false NO-EDGE) until ≥50 such trades accumulate. Note: only ~12 horizon-matched exits exist historically, so this number starts blank and matures with live data — that is honesty, not a regression.

### M-3 (relabeled): corr(confidence, correct) ≠ directional skill
`correct_direction` is "did the trade make money" — on a long-only book it is just win/loss. The metric is now exported as `corr_conf_win` (old key kept as alias). Yesterday's 0.023 stands, correctly read as "confidence does not predict wins."

### M-4 (fake → fixed): MAE was a static stop-distance proxy
`ExitLevels` now tracks `worst_adverse` every tick (mirroring MFE); the record uses it, falling back to the proxy only for positions opened before this change. MFE was always real; the 63%-giveback finding stands.

### M-5 (fixed): silently approximate prices now labeled
Exit prices fall back fill → DB fill → bar close → quote when no fill is found. Rows now carry `price_source` so bar-/quote-priced rows (which can diverge from realized PnL) are identifiable.

### M-6 (fixed): stub-recovered positions tagged
Positions recovered via the invariant stub now carry `entry_source="stub_recovered"` and a regime, instead of polluting attribution as empty/unknown.

### Verified clean
Fill→position matching (minor 2-min-window caveat), pyramid avg-entry sync, reconciliation-artifact isolation (errs conservative), equity-curve mixed format (no format-dependent consumer), replay/live field parity (replay rows populate identically — experiments remain comparable), `closed_at`/clock injection, bars_held semantics.

## What changed in the data going forward
New `trade_history.csv` columns: `predicted_return_signed`, `ml_spoke`, `price_source`, `had_partial_exits`. Legacy rows default to None/False — analysis code treats absence as "unmeasured", never as a value. 19 new tests (`tests/test_audit_m1_measurement_integrity.py` + updated edge-monitor tests); 128 related tests green.

## Operator actions
1. Rebuild + recreate the container to ship these fixes (same two commands as before). Until then the running engine still writes legacy-format rows.
2. Run `python scripts/reconcile_broker.py` once (host, read-only) and look at the verdict line.
3. Expect the EOD report's corr(pred, actual) to read **EDGE-UNMEASURED** for a while — it fills in as horizon-matched ML trades accumulate. The PnL/expectancy/PF numbers remain valid throughout (segregate `had_partial_exits` rows for fine-grained work).
4. Queue the per-leg exit accounting (M-1) as the next code PR.
