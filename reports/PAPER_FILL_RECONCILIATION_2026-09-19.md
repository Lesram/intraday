# Paper fill reconciliation — 2026-09-19

**Scope:** Monday paper readiness, accounting and evidence integrity. Read-only
Alpaca paper requests and offline analysis; no orders, cancellations, runtime
edits, cost changes or historical-corpus rewrites. Profitability and real-money
promotion are outside this acceptance.

## Result

Every one of the **27 post-freeze ledger closes** matches a completed broker
position. The broker returned **61 filled orders**, all carrying organism client
attribution. Reconstructing each symbol from flat to flat consumes all 61 orders,
produces exactly 27 round trips, and leaves no unmatched shares. Matching used
symbol and a maximum 180-second lag between final broker fill and recorded close;
there were no ambiguous matches.

**The recorded PnL is not fully reconciled.** Broker fill cash flows total
**+$89.819991**, while the ledger records **+$84.922414**: the ledger understates
this forward period by **$4.897577**. Six partial-exit positions have differences
larger than one cent. `price_source=db_fill` identifies the final exit price's
source; it does not establish correct accounting across every exit leg.

The saved export came from authenticated **GET**
`https://paper-api.alpaca.markets/v2/orders`, using `status=closed`, `limit=500`,
`direction=desc`, and `after=2026-07-07T20:36:49.008305Z`. One 61-order page was
returned, so this query did not truncate at the page limit. Filled quantities
and per-order average fill prices, not quotes or account equity, price the
reconciliation. Credentials and raw broker/client identifiers are excluded from
the saved evidence. This does not independently audit fees or individual fills
inside an order's average price.

## Partial exits explain the discrepancy

| Close date | Symbol | First exit reason | Ledger PnL | Broker PnL | Ledger − broker | Ledger partial flag |
|---|---|---|---:|---:|---:|---|
| 2026-08-03 | TSLA | ml_reversal | 4.860000 | 5.780000 | −0.920000 | false |
| 2026-08-03 | AVGO | ml_reversal | −0.900000 | −0.600000 | −0.300000 | false |
| 2026-08-03 | AMD | ml_reversal | 34.400000 | 36.750000 | −2.350000 | false |
| 2026-08-03 | NVDA | ml_reversal | 44.010000 | 44.170000 | −0.160000 | false |
| 2026-08-03 | MSFT | ml_reversal | 5.373332 | 5.939999 | −0.566667 | false |
| 2026-08-04 | XOM | partial_take_profit | 1.619085 | 1.609995 | +0.009090 | true |
| 2026-08-04 | NVDA | ml_reversal | 0.500004 | 1.110004 | −0.610000 | false |

The other 20 round trips reconcile within one cent. For a concrete example,
TSLA bought 6 shares at $321, sold 1 at $322.73, then sold 5 at $321.81.
Actual proceeds minus entry cost are **$5.78**. Applying the final $321.81 exit
to all 6 shares gives the ledger's **$4.86**.

Two implementation details account for these findings:

- `backend/organism/live_engine.py`, `_submit_exit_order` (around line 6346),
  marks `had_partial_exits` only when the reason contains the literal
  `partial`. The existing `ml_reversal` path submits a partial quantity without
  that word. Six observed scale-outs therefore remain unflagged.
- `backend/organism/live_engine_fills.py`, `_lookup_exit_fill_from_db`
  (around line 137), selects the most recently updated filled sell order.
  `_reconcile_fills` restores the full original entry quantity and applies that
  single final price to every share (around lines 6657–6678).

This is an accounting defect, not evidence of a missing order or duplicate
position. Disabling or changing ML exit behavior would be a separate strategy
change and is not part of this repair.

## The 609/610 count difference is inherited accounting scope

The CSV contains **602 strategy records and 8 reconciliation artifacts**. Seven
artifacts occurred before the May-1 exclusion introduced in commit `f145497`;
they remain in the historical learner counter. The single later artifact is
NVDA on May 7 at 13:34:23 UTC (`reconciliation_orphan`, CSV line 539).

`_reconcile_fills` appends every close to `_all_trades` but intentionally avoids
`learner.record_trade` for reconciliation artifacts. The counter therefore
retains **602 + 7 = 609**, while the all-record ledger has **602 + 8 = 610**.
The April-24 snapshot is 396/396; the retained July-7 snapshot is already
582/583. All 27 forward additions increase both counts, preserving the one-row
difference. There is no missing forward trade to recover.

The July operations work separately reconciled cumulative PnL to all CSV rows;
the current all-record sum is −$588.389243, agreeing with the manifest's rounded
−$588.39. Counts and dollar totals consequently retain different historical
scope. Changing the counter to 610 would obscure that history and is not an
operational repair.

## Cost and shadow qualifications

The running `ORGANISM_COST_BPS=3.0` and the helper in
`backend/organism/costing.py` mean **3 bps round trip**. The July-29 research
brief says at least **3 bps per side**. Both views are displayed below; neither
is selected or installed by this work.

| Forward-book basis | Recorded gross | Net at 3 bps round trip | Net at 6 bps round trip |
|---|---:|---:|---:|
| Existing ledger | $84.922414 | $69.904105 | $54.885796 |
| Broker fill cash flows | $89.819991 | $74.801682 | $59.783373 |

Modeled costs are not an audit of actual broker fees. The frozen verdict remains
**INSUFFICIENT: 24 eligible momentum trend/high-volatility trades of 60 needed for
the first look**. No significance statistic was computed, no gate was amended,
and none of the broker corrections was written into its corpus.

The exit-shadow stream has 26 forward rows, one for each close after the July-29
activation. The missing July-27 SH row is the documented pre-fix omission. Eight
forward shadow rows triggered; their cumulative reported gross delta is
**−$1.1511**. It does not support switching exits.

The shadow's `real_pnl_gross` is a quote-based comparator:
`experimental/shadow_exit.py` uses the last observed price, shadow entry and
trigger-time/observed quantity. Twenty-four of 26 values differ from ledger PnL
by more than two cents; five quantities differ. Broker reconciliation now also
shows why the ledger itself is not a universal reference for multi-leg exits.
Shadow promotion evidence requires a defined whole-position counterfactual and
separate fill reconciliation, rather than relabeling current quote values as
broker PnL. Existing shadow records were preserved.

## Delivered tool and validation

`scripts/research/paper_fill_reconciliation.py` accepts a saved raw or sanitized
broker-order export, the CSV and freeze artifact. It uses only Python's standard
library, does not access the network or import platform modules, and writes a
separate report with input hashes. It refuses brain-directory output, input
overwrite and symlink aliases to those paths. Incomplete or ambiguous evidence
cannot produce `RECONCILED`. Matched entry prices must also agree with broker
entry VWAP within **$0.00005 per share**, inclusive: half the ledger's four-decimal
rounding quantum, equivalent to matched quantity × $0.00005 in entry notional.
The comparison uses unrounded decimal values, exposes entry-price/notional
deltas, and blocks `RECONCILED` when the cost basis differs even if PnL agrees.

```sh
python scripts/research/paper_fill_reconciliation.py \
  --orders artifacts/monday_readiness/reconciliation/broker_orders.json \
  --ledger artifacts/monday_readiness/reconciliation/forward_ledger.csv \
  --freeze artifacts/monday_readiness/frozen_surface_reference.json \
  --output /tmp/intra-monday-offline-fill-reconciliation.json
```

On the actual saved evidence this reproduces 61 orders, 27 cycles, 27 matched
closes, six material PnL differences and six false partial flags. Its exit code
is deliberately **1**, with status `DISCREPANCY`; this is successful detection,
not a failed test. Exit 0 means reconciled, and exit 2 means invalid inputs or
unsafe output. The acquisition and detailed read-only investigation records are
`/tmp/intra-broker-orders-forward-20260919.json` and
`/tmp/intra-broker-forward-reconciliation-20260919.json`; include the sanitized
snapshots in the PR artifact pack for durable reproduction.

**Targeted validation: 23 tests passed**, including the real TSLA numerical
counterexample, fractional shares, duplicate orders/ledger rows, unknown
attribution, carry-in/remaining positions, repeated symbols, ambiguous close
matches, incorrect cost basis despite correct PnL, entry-price rounding
boundaries, invalid prices/timestamps and output protection. Targeted Ruff checks
pass. The pure offline tests can run with `--noconftest`; root-level safety,
replay, freeze and PR checks remain part of the enclosing Monday-readiness task.

At the pre-repair audit, `tests/test_position_reconciliation.py` was a manual
program with zero pytest cases. The Monday repair replaces it with four offline
position-status acceptance tests, including unavailable broker/database cases.
Those checks and the comprehensive reconciliation suite do not correct the
partial-exit cash-flow defect. The older measurement-integrity partial test
only checks source text for `"partial" in reason` and misses `ml_reversal`.

## Concrete runtime correction proposal — not applied

This proposal changes future accounting and therefore requires a deliberate
decision about risk inputs and the forward experiment. A green current freeze
hash check alone would not authorize it: the affected helper methods are outside
the six hashed sources, but their values influence decisions.

1. **`live_engine_fills.py` — add a bounded closed-position fill summary.** Add
   `_lookup_closed_position_fills_from_db(symbol, meta)` alongside the existing
   methods. Anchor the position to its recorded entry order ID and submission
   time; read only organism orders for that symbol and position lifetime; use
   side/direction rather than assuming every exit is a sell. Accumulate filled
   quantities and notional for every entry and exit leg. Return a typed summary
   containing entry quantity, entry/exit VWAP, realized cash-flow PnL and whether
   exits scaled out. Require matched entry/exit quantities. Missing identity,
   stale prior-position orders, contradictory quantities or incomplete fills
   must return an explicit unavailable/ambiguous result, not silently claim
   exact `db_fill` accounting.
2. **`live_engine.py`, `_reconcile_fills` around lines 6657–6770.** Call that
   summary once before calculating the trade. When complete, use its matched
   quantity, VWAPs, PnL and partial flag. Define an explicit fallback provenance
   for an incomplete summary. Continue to record exactly one position close and
   keep the existing idempotency, cleanup and save behavior. Do not edit
   `_live_tick_inner`, entry/exit decisions or frozen parameters.
3. **`live_engine.py`, `_submit_exit_order` around line 6346.** Record partial
   intent from requested quantity versus confirmed held quantity, including
   `ml_reversal`, after successful submission. Treat this as intent only; actual
   multi-fill accounting must derive from filled legs, not intent or reason text.
4. **Behavioral tests, before any activation.** Exercise 6 shares at $321,
   1-share exit at $322.73 and final 5-share exit at $321.81 and require $5.78;
   cover `ml_reversal`, partial take-profit, repeated same-symbol positions,
   canceled/unfilled orders, short-side matching, missing fills, restart and
   repeated reconciliation ticks. Verify a rejected/blocked submit does not
   create a filled partial marker. Replace the source-text-only assertion with
   behavior checks. A proposed focused file is
   `tests/test_live_engine_fill_accounting.py`.

**Future-state impact:** a corrected PnL feeds learner history/cumulative PnL,
symbol daily PnL and consecutive-loss bans, Kelly history, and new forward-corpus
rows (`live_engine.py` around 6775, 6808 and 6872). Even if this particular
$4.90 correction appears small, applying the helper can change later risk
decisions. This is why the runtime change is not hidden in an instrumentation PR.

**Historical-state impact:** this task makes none. A later decision could retain
the original corpus plus a separately versioned broker-corrected research view,
or authorize an explicit historical restatement with provenance and a defined
verdict treatment. It must not silently overwrite old rows or retrospectively
change the registered cost/gate. No clock reset is performed or requested as a
side effect here.

## Monday acceptance boundary

Read-only paper broker clock/calendar responses confirm the next regular
session is **Monday, September 21, 09:30–16:00 EDT / 06:30–13:00 PDT**. The
calendar response is saved separately at `/tmp/intra-paper-calendar-20260919.json`.

`docs/runbooks/PAPER_TRADING_ROLLOUT.md` requires paper outbox submission, reflected
broker status, and portfolio/position updates. The existing paper smoke script
checks health/metrics and optional execution mode; it does not prove a fill or
PnL reconciliation. Historical execution is proven above. Monday's fresh-data,
watchdog, alert, entry/exit and flatten acceptance must be observed during that
session; weekend liveness does not substitute for it.

The durable evidence pack includes a minimal 27-row forward-ledger snapshot, a sanitized broker export, the freeze reference, and extraction provenance with the original full CSV hash. Re-running the command above uses those stable inputs; the filtered ledger naturally has zero missing-close rows instead of the historical full-ledger count. The full live CSV is unchanged.
