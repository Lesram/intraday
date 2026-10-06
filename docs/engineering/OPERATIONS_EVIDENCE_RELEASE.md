# Operations and evidence integrity — first repair release
Status: implemented candidate; final validation and PR evidence are recorded in `artifacts/task_report.json`. Direct Codex implementation was authorized by Marsel.

## Scope
The user instructed implementation of the approved milestone on 2026-09-19. This first release repairs two concrete integration failures: incomplete close accounting reaches dependent state without retry, and post-close evidence lacks an enforceable complete-collection/quality boundary.

This release now also includes the explicitly authorized September 21 research policy lock and controlled paper rollout. The six original source groups, strategy thresholds and feed remain unchanged; the frozen surface is expanded to cover promotion/training/settings controls and the reviewed retained parameter baseline. The activation deliberately advances the forward evaluation boundary, archives the previous freeze, and preserves all history and models. An actual-host read-only daily evidence job is part of deployment.

## A. Accounting contract
A strategy close is not finalized until attributed entry/exit cashflows conserve quantity. Keep the original observed-flat UTC time, entry order identity, reason, exit provenance and causal fields in durable pending metadata. Keep it visible in status; use the existing metadata gate to prevent same-symbol re-entry while unresolved. Retry complete-position lookup using the original close bound. Do not feed approximate results to the ledger, learner, risk history, Kelly or calibration. Preserve real broker-equity safety controls.

Definitively unfilled/rejected entries can be removed only after zero execution is verified. Unknown attribution remains unknown; orphan exclusions remain. A reappearing broker position retains position management. Deferred resolution across sessions retains the true close time without contaminating the current day's counters or creating a fresh cooldown from yesterday's outcome.

Replacement-order lineage is not reliably persisted by the current broker stream. A `replaced` predecessor is terminal, but does not prove its successor is finished or absent. Such lifetimes remain pending with `replacement_lineage_unverified` while the predecessor could still affect them, and forward replaced orders block daily evidence qualification. This includes zero-fill predecessors. Since the October 5 addendum below, a replaced DAY (or other session-bounded) predecessor stops holding after its own NYSE session. That rule assumes the successor kept a session-bounded TIF: Alpaca's replace can change the TIF and the successor is not ingested, so a GTC successor would go unseen. The backstop is the flat-to-flat check of the lifetime's own legs. Supporting automatic replacement-chain accounting requires a separate ingestion/attribution repair; this release does not fabricate lineage, and clears the hold only by that documented session bound.

Pending records must survive startup's flat-symbol cleanup. Finalization needs one authoritative durable accounting state, or a replayable journal with consumer receipts. A separate 'applied ID' file alongside independently written CSV and learner state is not a transaction. Failure injection at persistence boundaries must restore either the old coherent state with a pending close or the new coherent state. Do not claim crash consistency from clean-save tests.

Independent cashflow oracle: buy 6 shares at 100; sell 2 at 101 and 4 at 99. Gross PnL is -2; six-bps modeled net is -2.36 on 600 entry notional. If the first exit leg is absent, no strategy outcome may be finalized. Add the missing leg: exactly one -2 outcome must reach each applicable consumer. Repeat/restart: no double count.

Existing sanitized 27-cycle accounting fixture remains a regression oracle. Update the existing test that explicitly expects approximate learner/risk updates; its expectation currently preserves the defect.

### Replay integration

Replay must feed actual simulated execution legs into the same exact-close contract. Its separate broker PnL log is insufficient proof that engine learner/risk consumers advanced. Preserve delayed-fill order identity, quantity conservation, partial exits and scale-ins; label synthetic fill provenance distinctly from database paper-broker evidence. Tests must require a nonempty reconciled outcome and verify each consumer, not merely iterate over possibly empty results. This repairs the adapter without changing the frozen decision functions. `ReplayResult` exposes accounted outcomes and unresolved accounting separately from the broker's per-exit-leg trade log. Existing `delay_fill` remains a synchronous next-bar-open pricing model, not an actual delayed-execution queue; this limitation is preserved and tested, not silently redesigned.

## B. Daily evidence contract
The collector under scripts/ops supports manual and offline use. The reviewed host wrapper additionally schedules actual-host GET-only collection after the close. Neither imports submission/cancellation clients. Capture the active freeze, ledger, event feed, full applicable log rotation inventory, effective runtime identity, calendar and complete cumulative forward broker order/position evidence.

All statuses and unfilled orders belong in the inventory. Record pagination and scope; fail closed on transport/schema failures, duplicate/nonadvancing cursors, unresolved timestamp ties and page limits. Save and hash the exact input bytes used for analysis; detect changing local inputs. Never read a path again later and claim its new bytes were the analyzed version.

Publish an immutable content-addressed pack atomically. Identical bytes/options yield the existing pack; changed inputs preserve prior versions. Output cannot alias input files or any brain-state path through symlinks/hardlinks. Unsafe or interrupted publication cannot leave a complete-looking pack.

Statuses: READY_FOR_REVIEW, BLOCKED and NO_SESSION. READY_FOR_REVIEW is not whole-platform certification. No exposed strategy PASS while accounting/provenance/collection integrity remains unresolved. Preserve questionable rows and losing outcomes in the inventory. A verified no-trade session needs complete flat broker evidence and actual session coverage; empty files are insufficient. Statistical result remains INSUFFICIENT.

Reuse the existing pure Decimal reconciler and native gate with explicit cost_bps=6. Keep the runtime default unchanged. Do not mistake all-history shadow emissions for filled forward trades. Legacy rows with unresolvable time must be accounted for explicitly rather than silently filtered; use an approved historical boundary manifest where available instead of allowing old known defects to masquerade as new evidence.

Use authoritative calendar close plus five minutes for every requested session. Validate summer/winter, early close, holiday, future date and just-before-close cases. Stand-down diagnostics inventory all applicable rotations, parse timestamps and retain malformed/missing/unknown coverage. Boundary timestamps alone do not prove continuous session uptime. Force mode may emit diagnostics but never completed-session certification.

## Release evidence
Tests use temporary brain directories, isolated SQLite/fake transports and no broker credentials. Validate exact fills, pending->resolved, restart while pending, injected persistence failures, duplicate replay, cross-session resolution, reappearing positions and verified zero-fill cleanup. Runner tests cover pagination/completeness failure, independent six-bps cashflows, blocked positive gate, verified no-trade, calendar, rotations, immutable replay/publication and read-only source preservation.

Add targeted suites to the active paper-readiness workflow without touching parked CI cleanup. Run required organism/reconciliation/config regression suites, full artifact generator, audit index and freeze verification. Record test counts once per case/run without inflating totals. Review the complete diff and publish a PR with artifacts and remaining limits.

## Authorization/capability note
Marsel explicitly authorized direct Codex implementation for this release: “Codex can implement directly.” This supersedes the Claude Code implementation-role restriction for this work. The isolated worktree protects the deployed paper runtime and existing user edits. Frozen-surface, PR, test, replay, snapshot and review requirements remain in force; deployment and natural-session acceptance are separate steps.

Machine-readable scope: artifacts/operations_evidence/task_plan.json.

## September 21 locked paper baseline

The user's instruction to complete all remaining preparation follows the presented policy-lock proposal and authorizes that named control plus an explicit freeze/cutoff transition. The release records that interpretation and the verbatim request in `artifacts/operations_evidence/final_readiness_plan.json`; activation records the actual source, image and UTC boundary separately. No real-money trading, historical rewrite or trained-model reset is authorized.

`paper_research_locked_v1` is a code-controlled lock, with no environment unlock. Effective phase is `research_locked`; the existing count-derived learning indicator remains honest. Raw strategy count is diagnostic; qualified count is null/unverified until independently supported. Inherited count or profitable trailing windows cannot enable main-book ML ranking/confidence or Kelly. Fixed ATR-dollar risk remains active. Background worker start/submit/apply and synchronous retraining/evolution are blocked, including an already completed stale result. Saved evolved values are restored as the reviewed baseline; startup transfer warm-start is blocked. Existing trained-model reversal exits remain active using retained models. “ML isolated” describes main-book ranking/confidence/sizing, not every exit.

The baseline artifact pins the effective saved parameter projection and hash, excluding mutable trade/symbol bookkeeping. The deployment must verify that the actual engine reports this same hash. Historical model generation, learner counters and trade rows are retained. Risk reductions, reconciliation, protective exits, EOD flatten and emergency halt remain active. Settings mutation is rejected while the policy is locked, before API persistence, scheduler mutation or engine updates. A future promotion requires a separately reviewed release and explicit evaluation decision.

The original six frozen hashes are preserved; additional hashes cover the policy, phase, trainer, startup, synchronous training, ML/fixed-risk mode and settings seams. The updated CI freeze is a source-verification fixture. It is not Monday's active cutoff, which is published only at the actual approved host transition. The prior July and September 19 boundaries remain archived.

Recovery is stop-and-preserve. PR17 does not recognize the new close-accounting authority or entry receipts and can delete those files during its legacy brain save. Do not boot PR17 against the candidate brain after candidate activity. Preserve complete DB, brain, broker evidence and all evaluation boundaries; reconcile intervening fills before any separately validated recovery migration.

The configured `ORGANISM_APPROVED_POLICY_BASELINE` points to the approved JSON baked into the immutable image. Startup verifies model/cache fingerprints, feature order, ensemble weights, thresholds, calibration map and actual applied scanner/exit/sizer values before engine reconstruction, training or ticks. A mismatch leaves the scheduler stopped; generic API readiness alone is insufficient. Existing lifespan startup cancels outstanding orders before engine initialization, so controlled rollout additionally requires a freshly verified flat account with no open orders. Legacy retrain activity messages can still say submitted when the locked trainer declines the request; `policy_lock` and actual trainer state are authoritative.


## Durable operator halt and verified emergency cancellation

The September 21 safety repair connects both operator endpoints to the actual
scheduler engine governance, while keeping the legacy controller coherent.
`ORGANISM_OPERATOR_CONTROL_STATE=/app/data/operator_control_state.json` stores
an independent, checksummed manual halt in the existing data bind, outside the
brain save/recovery directory. Deployment initializes this record only while
recovery is held and fresh broker evidence is closed/flat with no orders, after
observing that the previous engine is not halted. Missing or corrupt configured
state blocks entries and exposes a control fault; it never silently resumes.

The manual halt is set and persisted before awaiting an in-flight tick. A success
acknowledgment requires that tick to drain; a timeout or persistence error reports
an incomplete result with the halt retained. Final entry admission rechecks
governance, including pyramid additions. Stop, partial-exit and end-of-day
management remain active. Automatic daily-loss/cooldown recovery cannot clear the
manual latch. Explicit resume clears only that latch, preserving environment and
automatic risk blocks and the research lock.

`POST /risk/emergency-stop` halts the actual engine before opening the audit DB
session. It requests cancellation only for verified engine entry orders and
confirms their terminal status at the broker. Protective and unrelated orders
are preserved. Unsupported replacement lineage, ambiguous attribution, remaining
fill exposure, broker failure, persistence failure or unavailable audit storage
produces a structured incomplete response; it must not claim all orders were
cancelled or the portfolio is flat. Database order rows are not falsely stamped
cancelled. The UI distinguishes a retained entry halt from incomplete
cancellation/audit work. No administrator notification is promised by this path.

The expanded freeze covers governance, operator controls, the entry admission
seam and emergency cancellation/API/service sources, plus the configured state
path. The original six source hashes, strategy parameters and data feed remain
unchanged. Runtime snapshots report observed `operator_governance`; missing
legacy fields remain unknown. The actual-host daily runner and watchdog check
configured/verified fault-free authority, its approved path, and correspondence
between the current durable record and engine status. They allow a legitimate
manual halt and never clear it to make a readiness check pass.


Emergency-stop completion requires a bounded, successful broker open-order
inventory, including when the DB and engine have no pending entries. Broker
identities are joined back to persisted roles even if a legacy DB row is marked
terminal. Missing/ambiguous attribution, oversized inventory or a failed final
broker check withholds completion; protective and unrelated orders are retained.
A stopped or uninitialized engine can retain a durable halt but cannot certify
tick drain or active exit management. Its API response and UI must show that
limitation. The independent review checks these failure cases explicitly.

## Dashboard access

The login form accepts a username or email and trims only that identifier;
password bytes are preserved. Automatic development login requires both a
development build and the explicit development flag. Production builds never
attempt that login. The unfinished password-reset link is replaced with honest
guidance; this release does not implement password recovery or alter accounts.

The paper engine runs independently of the dashboard. A local preview may serve
the installed production build on `127.0.0.1:5173`, opened as
`http://localhost:5173`, using the existing API and WebSocket configuration.
Browser smoke checks establish rendering and authentication boundaries, not
administrator access without an existing authorized login. The preview is a
temporary process, not a newly installed startup service.

Production browser verification also exposed initialization cycles caused by
manual vendor partitioning: first React/scheduler, then Ant Design/icons. The
build now lets Rollup choose dependency-aware chunks. Release CI checks the
actual built login page in a fresh local browser with outbound connections and
form submission blocked, requires visible login controls and no page errors,
and removes only its own browser and preview processes. Component tests and a
successful build alone do not satisfy this browser gate.

The scanner and market-data connections use the existing centralized auth helper
instead of browser-incompatible CommonJS calls. Each actual connection attempt
reads the current login token, including after reconnect delays; logout cannot
fall back to an obsolete local-storage token. Query-token authentication and
backend roles stay unchanged, and connection diagnostics omit token-bearing
URLs and socket events. Mocked connection, refresh and logout regressions cover
these boundaries; they do not certify an authenticated live dashboard session.

## September 21 baseline verification correction

The first installed restart was held by the baseline gate. Its offline rehearsal
had used daily defaults instead of the installed `1Min` configuration, and raw
Random Forest pickle fingerprints were sensitive to serialization details. The
correction verifies the existing one-minute exit context without changing exit
settings, strategy parameters or saved models. Random Forest identity uses the
versioned `rf-state-v1:` digest of complete supported typed model/tree state,
excluding anonymous padding contents and object-sharing representation; unknown
state fails closed. Other retained model/cache checks remain in force. The
expanded freeze hashes the complete fingerprint module and baseline verifier.

The corrective activation must retain the failed activation and preserve the
current forward boundary, `2026-09-21T10:10:39.684894+00:00`, with explicit evidence
that no intervening candidate trading occurred. The original six decision-source
groups, strategy/feed/exit configuration and historical ledger remain unchanged.
This addendum records the repair contract; actual corrected runtime acceptance
and natural-session evidence are still pending.

## October 5 close-accounting unblock (audit C08-01, C07-01)

Exact-fills-or-pending is unchanged; two defects that made it permanent are
repaired outside the frozen surface (`backend/organism/live_engine_fills.py`,
`backend/integrations/alpaca_stream.py` and its five ingress callers).

An unresolved or `replaced` order, including one submitted before the entry,
holds a close only while it could still execute during that lifetime. DAY,
IOC, FOK, OPG and CLS orders, and any order the broker never acknowledged (no
broker order id), stop working at 20:00 ET of their eligible NYSE session, plus
one hour of slack (`SESSION_END_SLACK`). The eligible session is the first
trading day (early closes included) whose regular close is after the basis
time plus five minutes (`SESSION_CUTOFF_SLACK`: POST latency and app-clock lag
at the cut-off, so an order entered or acknowledged at 15:57 also holds the
next session). The basis is the submission, or for an acknowledged order the
later of its submission and last update (a delayed delivery is acknowledged
later). A later touch of a never-acknowledged row, such as a remediation
status, does not revive it. After-hours, weekend and holiday submissions
therefore still hold the next session.
Acknowledged GTC or unknown-TIF orders, in-lifetime rows and pre-entry fills
recorded after the entry still hold as before. Old dead letters (for example
the four April XLE rows marked `failed`) no longer hold every later close of
the symbol. The hold names its evidence in `pending_close.accounting_hold_reason`
(`ambiguous_order:<order id>` or `replacement_lineage_unverified`), with one
WARNING per new reason. The zero-fill entry cleanup likewise considers only
orders submitted between the entry and the observed close
(`pending_close.observed_at`); a later order for the symbol no longer keeps a
verified-unfilled entry pending. No historical row is rewritten.

Limits of the session rule. A never-acknowledged row is bounded by the session
of its submission because the row shows no later delivery. An ambiguous
submission (EXE-04) that reached Alpaca later without a persisted broker id
may still work after that session and is not seen by this rule (follow-up:
use the `order.submitted` event's last activity as the basis while the event
exists). A replaced DAY predecessor is bounded on the successor-TIF assumption
stated above. For both, exits are sized from the broker position and
`_closed_position_fills` still requires the lifetime's own legs to be terminal
and flat-to-flat, so a stray fill keeps the close pending (no wrong P&L, at
worst an unneeded hold). Pre-entry fills touched after the entry still hold
that lifetime without a time bound.

A broker-confirmed close fill whose owner has no, or too few, open lots is no
longer rolled back. The order status, filled quantity, price and execution are
committed together with any lots that do match (FIFO, owner-scoped as before).
The remainder is recorded in `orders.attributes.lot_accounting`
(`status=unmatched`, `repair=required`, cumulative matched and unmatched
quantity and unmatched notional, stored at 6 dp), and one CRITICAL line is
logged after the commit on every ingress: trade-update stream, persisted-order
recovery, reconnect gap-fill, startup order sync and outbox acknowledgement.
Transient failures still roll back the whole order.

Ingestion is not globally ordered (recovery pages by id; startup order sync
runs recovery before its oldest-first page), so a close can be applied before
its opening. Two rules make the two legs of one round trip converge when they
are applied in either order, with any delay between them:

- Deferral. While a same-owner opening that persisted-order recovery retries
  (unresolved, broker-acknowledged, organism or outbox lineage) was submitted
  at or before the close and at most five days before it
  (`LOT_ORDERING_GRACE`, anchored to the close, not to the wall clock), the
  close stays retryable as before (`LotAccountingDeferred`, a `ValueError`
  raised before anything is staged). An opening older than 45 days
  (`LOT_ORDERING_MAX_AGE`) no longer defers. After a restart that follows an
  outage shorter than that, recovery defers the close and settles the
  opening, and the startup page (or the next recovery pass) then applies the
  close against the opening's lot. The cap also bounds how long a stuck
  opening row can keep a broker-filled close unrecorded: until that opening
  is 45 days old (the close's row stays non-terminal meanwhile and holds its
  lifetime's exact accounting). Such an opening is one recovery cannot settle
  (a `replaced` or unknown broker status, a failed lookup) or one that keeps
  working (a resting GTC limit). Each deferral is only a retry (a WARNING per
  recovery pass, the stream's DLQ record), so a close still deferred 6.5 hours
  (`LOT_DEFERRAL_ESCALATE_AFTER`, about one regular session) after its first
  deferral pages once: CRITICAL `LOT ACCOUNTING DEFERRAL ESCALATED`, naming the
  close and the opening that holds it. The clock is process-local (a restart
  starts it again; the cap still applies) and the episode ends when the close
  is applied.
- Late netting. Otherwise the close is recorded as above. When an opening fill
  lands later (an opening that was never acknowledged, is outside recovery
  scope or is past the cap), its new lot is closed FIFO against the owner's
  recorded unmatched closes of that symbol and side submitted at or after the
  opening and within `LOT_ORDERING_GRACE`, at the close's unmatched VWAP. The
  close's record becomes `matched_late` (`repair=none`, `matched_late_qty`,
  `last_late_match`) and a WARNING follows the commit. A close submitted before
  the opening never consumes it.

Concurrent ingestion. When an opening fill and its close fill are ingested at
the same moment on two paths, row locks serialize them on PostgreSQL (SQLite
serializes writers). The netting locks every close-side order row of its
window, whatever its record, before reading records, and a close holds its own
row from its first statement. Either the netting waits for the close's commit
and nets the record it committed, or the close waits for the opening's commit
and its FIFO consumes the new lot; a close that found no lot and is waiting to
check for an earlier opening still sees that opening unresolved and defers.
Every fill path (the snapshot, persisted-order recovery and the outbox
acknowledgement) locks order rows `FOR NO KEY UPDATE`, and the close FIFO locks
lot rows only (`FOR UPDATE OF position_lots`). The foreign-key check of a
close's RealizedTrade on the opening row therefore never waits for an opening
that is waiting for the close (no deadlock). Before this, an opening and its
close ingested concurrently could leave a phantom open lot next to an unmatched
record (reproduced on PostgreSQL 16).

Limits. Both rules order legs by submission time; broker fill times are not
ingested (C07-07). An opening submitted before a close but filled after it (a
resting limit order) would be matched to that close, and legs more than
`LOT_ORDERING_GRACE` apart are neither deferred nor netted. Two round trips of
one owner and symbol applied out of order across lifetimes do not converge.
With orders submitted as A buy 10, B sell 10, C buy 6, D sell 6 and applied in
the order A, D, B, C: D consumes 6 of A's lot, B finds 4 shares and is
recorded with 6 unmatched, and C's lot is never netted against B because B was
submitted before C. The ledger then shows B unmatched 6 (paged) and C's lot
open 6. The engine cannot
produce that order, since it opens no new entry in a symbol while the previous
lifetime is still tracked (its close accounting needs B's fill); only manual
UI/API orders can. Read-only check for records still needing repair:

```sql
SELECT id, symbol, side, user_id, submitted_at, attributes->'lot_accounting' AS lot_accounting
FROM orders
WHERE attributes->'lot_accounting'->>'status' = 'unmatched'
ORDER BY submitted_at;
```

The runtime snapshot reports these rules in `close_accounting_holds` and
`fill_lot_accounting`; the policy id stays `exact_position_fills_or_pending_v1`.
Follow-ups: a repair path for records that stay `unmatched` (it would also
cover the cross-lifetime limit, for example by netting an owner's remaining
open lots against its remaining unmatched records of that side, whatever their
order, once the broker position is flat), owner-agnostic lot matching for the
single broker account (with or before C06-01, since a UI close of an engine
position leaves the engine's `system` lot open), and an unmatched-record count
in status and the daily evidence pack.

## October 5 external-close accounting (audit C06-01)

A strategy close that no organism exit order booked used to stay pending for
good: no trade, the symbol entry-gated across restarts, one WARNING. This
repair changes the frozen `_reconcile_fills` and
`operator_cancellation._accounted_entry_fill` (owner sign-off 2026-10-05;
effective only through a new activation). The classification, the lot repair
and the escalation live outside the frozen surface (`live_engine_fills.py`,
`alpaca_stream.repair_external_close_lots`, `_defer_unresolved_close`), as does
the forward-corpus exclusion (`phase2_gate.load_forward_corpus`). The policy id
stays `exact_position_fills_or_pending_v1`: strategy outcomes still require
exact organism legs, and the new records are reconciliation artifacts, the
class v1 already uses for orphan bookkeeping. The checkpoint format, its reader
and the daily evidence check are unchanged.

Exact. The platform's close routes (`POST /positions/{symbol}/close`,
`POST /orders/{id}/close-position`) book a market leg with
`attributes.close_position = true`, no `source`, under the operator's owner.
When such legs are exit-side, terminal, filled with a broker id and complete
the lifetime flat-to-flat by the observed close, the close is recorded at once
with the DB cash flows (`price_source = external_close_db_fills`). The anchor,
quantity and hold checks are those of exact accounting, and orders after the
observed close are outside the window, as there. The same applies when an
operator Close raced the engine's own exit: the exit filled and the route leg
was refused by the outbox exit guard (PR #36) or canceled without a fill, which
is the likely outcome of a click during the 15:58 flatten. Strategy accounting
refuses any non-organism row in the window, so the engine's exact legs are
recorded as the `external_close` artifact instead of staying pending for good.

Approximate. When every order from the entry to the observed close is
attributable (organism, or a close-route exit leg) and terminal, the DB
lifetime is still open and the broker is flat, part of the quantity was closed
with no DB row: the Alpaca dashboard or app, or a broker liquidation (the
platform itself never closes without a row). If any order for the symbol was
submitted after the observed close, nothing is recorded, because it could hold
the missing legs (for example a late engine exit, C06-04). Otherwise the close
waits `EXTERNAL_CLOSE_APPROXIMATE_AFTER` (15 minutes from the observed close,
status reason `external_close_unbooked`). It is then recorded with the DB legs
exact and the unbooked quantity at the best available mark: the bar close kept
when the close was first observed (`pending_close.observed_bar_close`), else
the current bar close, else the streaming provider's cached quote (mid, bid,
ask); `price_source = external_close_approximate_<rung>`. Without a mark it
stays pending (`no_exit_price`). Another leg's or lifetime's fill price is
never used. The mark's age is not bounded. The observed bar close is captured
at the first flat observation, normally within one tick of the real close, but
a close first observed long after it happened (hours of engine downtime) is
priced at the bar or quote of that later pass, and a close already pending
before this release has no `observed_bar_close` at all, so on the first pass
after activation it would be priced at the current bar close or quote, possibly
weeks late. The rung does not show the mark's age. Before activation, check
`status().close_accounting.unresolved` and the pending closes in the
checkpoint; the host had none when this was written.

Both records carry `exit_reason = external_close`,
`is_reconciliation_artifact = true`, the original observed close time, the
entry identity and strategy, and the DB entry cost. They never reach the
learner, Kelly, calibration, symbol counts, bans, evolution, the edge monitor
or the Phase-2 forward verdict corpus; the daily-loss breaker still sees broker
equity. The symbol's tracking is cleared and its completed identity persisted
in one checkpoint replace, so the entry gate is released and a restart keeps
the outcome. There is no re-entry cooldown after an external close: the engine
may re-enter the symbol on the next tick, including right after an operator
flattened it on purpose; use the operator halt for that. The daily evidence
check still flags every forward row whose price source is not
`db_position_fills` (`unqualified_price_source`), as it does for orphan
artifacts. It checks every forward row since the activation cutoff, so after an
external close every later daily report of the epoch carries the issue, not
only that session's report.

Forward verdict corpus. An external-close artifact keeps the lifetime's mapped
`entry_source` (alpha, breakout, ...), so `phase2_gate.load_forward_corpus`,
which mapped rows by `entry_source` alone, would have counted it as a strategy
trade in the verdict CLI (`scripts/phase2_gate.py`), the attribution report
(`scripts/phase3_attribution_report.py`) and the daily evidence pack's native
gate. The loader now drops reconciliation artifacts before the mapping: the
`is_reconciliation_artifact` flag, and for ledgers without that column the exit
reasons `external_close` and `reconciliation_adjustment` and the source
`reconciliation_orphan` (the experiment observation report skips
`external_close` rows the same way). No historical verdict changes. The
September 28 brain snapshot holds eight artifact rows, seven of them
`reconciliation_adjustment` rows with mapped sources, all closed in April or
May, before the first freeze cutoff (2026-06-27); the old and new loaders give
identical corpora and gate states at all twelve committed `FROZEN_AT` values,
at 3 and 6 bps. On base code every later artifact is an orphan with an
unmapped source. Read-only host check before activation, self-contained so it
runs on the current image (use the host's active freeze file); it must print 0,
otherwise those rows were already counted in the verdict and their removal must
be reported to Marsel:

```sh
python - <<'EOF'
from pathlib import Path
import pandas as pd
from backend.organism.freeze_contract import load_active_freeze
df = pd.read_csv("organism_brain/trade_history.csv")
cutoff = pd.Timestamp(load_active_freeze(Path("artifacts/phase2/param_freeze.json"))["FROZEN_AT"])
closed = pd.to_datetime(df["closed_at"], utc=True, errors="coerce")
flag = df.get("is_reconciliation_artifact", pd.Series("", index=df.index)).astype(str)
artifact = (flag.str.strip().str.lower().isin({"1", "true", "yes", "y"})
            | df["exit_reason"].astype(str).str.strip().isin({"external_close", "reconciliation_adjustment"}))
mapped = df["entry_source"].isin({"alpha", "alpha+breakout", "breakout", "orb", "orb_sip", "mr", "mean_reversion"})
print(int(((closed > cutoff) & artifact & mapped).sum()))
EOF
```

Lot repair. A close-route leg is booked under the operator's owner, so the
owner-scoped FIFO records it unmatched at ingestion (`LOT ACCOUNTING
DISCREPANCY`, CRITICAL, still paged for every close-route close of an engine
position), and a dashboard close or liquidation books nothing. Left alone, the
engine's own (`system`) lot would stay open: the next entry could never release
its pending identity (owner lots above the broker quantity, EXE-03 page and a
permanent `pending_entry` gate) and its exit would be FIFO-matched against the
stale lot. Once an external close is recordable (exact, or unbooked after the
15 minutes), `_lookup_external_close_from_db` therefore runs
`alpaca_stream.repair_external_close_lots` in its own transaction and commits
it before returning, so before the artifact commit releases the gate. Scope:
the entry owner's open lots of the symbol on the lifetime's side whose opening
order was submitted at or before the observed close. The broker was flat then
and every order submitted by then is terminal, so none of them can still be
held; older stale lots are included because the owner's FIFO would consume them
first, while lots of later orders and of other owners are never touched. First,
each unmatched close-route record of the window (submitted from the entry to
the observed close, same position side) is netted FIFO against those lots at
its unmatched VWAP: one RealizedTrade per match (lot owner,
`lot_accounting = external_close_repair`, `close_owner`), and the record moves
to `matched_late` with repair `none` and `last_late_match.basis =
external_close_repair`. Then any remainder, which no DB row priced, is closed
without a RealizedTrade and recorded by one `position.adjusted` audit row per
lot (actor `system:external_close_repair`, reason
`external_close_unbooked_write_off`, lot, order, quantity, entry, observed
close and, when known, the observed bar close). Locks follow the fill paths:
the window's closing-side order rows FOR NO KEY UPDATE in submission order,
then the lots FOR UPDATE OF position_lots. The repair is idempotent (no open lot
in scope, no write). If it fails, the close stays pending and gated with hold
reason `external_close_lot_repair_failed` (one WARNING, the 30-minute page if it
persists) and every pass retries it. When a recordable close then waits for a
mark (`no_exit_price`), the ledger is already repaired, which is harmless
because the broker is flat.

The pending-entry release (`_accounted_entry_fill`, flat branch) accepts an
`external_close` artifact with the same identity, quantity and entry cost
without requiring exhausted lots; after the repair they are exhausted anyway.
Other artifacts, and strategy trades whose lots are not exhausted, are still
refused.

A close still pending 30 minutes after it was observed raises one CRITICAL
per episode (`_UNRESOLVED_CLOSE_ESCALATE_SECONDS`; a restart re-pages once if
it is still unresolved). The page finalizes nothing. Genuinely ambiguous closes
(holds, an unattributed or still-working leg, an order after the observed
close, no entry identity, DB failures, a failed lot repair) stay pending with
one WARNING per episode.

Legacy. Stale `system` lots that already exist for flat symbols are outside the
repair's scope. Read-only check; an open `system` lot for a symbol the broker
shows flat is such a leftover:

```sql
SELECT id, order_id, symbol, qty, remaining_qty, open_date
FROM position_lots
WHERE user_id = 'system' AND remaining_qty > 0
ORDER BY symbol, open_date;
```

The runtime snapshot reports these rules in `external_close_accounting`
(`lot_repair` included).

## October 6 frozen-code release (audit 2026-10-05): activation

One pull request carries the frozen-code fixes C05-01, C05-02, C06-02 (exit
safety), C04-01, C01-04 (dispatch lifecycle), C06-01 (external close), C09-01
(regime isolation) and C11-01 (stream history), with Marsel's sign-off of
2026-10-05. It is stacked on PR #37 (close-accounting unblock, not frozen),
which merges first. Merging changes nothing on the host. The fixes take effect
only when a release built from the merged commit is installed with a new
activation, which restarts the forward verdict clock once.

The release's candidate (`artifacts/phase2/candidate_param_freeze.json`,
`--verify --candidate` exits 0) differs from PR #37's in exactly six keys:
`research_policy_sources.broker_state_safety`,
`research_policy_sources.entry_cancellation`,
`source_hashes.entry_gates_dispatch`, `source_hashes.regime_detector`,
`data_pipeline_sources.live_engine_data`,
`data_pipeline_sources.streaming_data_provider`. Against the committed active
freeze (FROZEN_AT 2026-09-25) it differs in 18 keys, because the surface
changes merged after that freeze (up to PR #37's candidate) are not in that
file; publish the full difference against the host's current active freeze. `surface.effective_policy_baseline`
is identical, so `research_policy_baseline.json`, its sha256 and the
effective policy hash stay as they are; the engine's startup baseline check
fingerprints restored models and parameter values, not source, so it still
verifies.

Before activation (read-only):

1. Marsel acknowledges the decision changes beyond the original findings:
   the exit-safety regular-hours gate and fresh-bar veto on the broker-price
   nets, window ticks not advancing trailing/MFE/MAE tracking, consecutive
   SPY-only regime ticks no longer blending (measured label impact nil),
   external closes recorded as labelled artifacts with no re-entry cooldown,
   and entries refused at dispatch when older than 120 s or created in a
   regular session that has closed (manual and API buys included).
2. The paper account is flat: no positions, no open orders, paper endpoint
   verified (the activation record requires it).
3. `organism_brain/regime_state.json` has empty `smoothed_probs` and
   `history` (this release does not clear a prior already persisted).
4. `status().close_accounting.unresolved` is empty and the checkpoint holds
   no pending close (one created before this release has no
   `observed_bar_close` and would be priced at a much later mark).
5. The forward-corpus host check of the October 5 external-close section
   prints 0; otherwise report the rows to Marsel before activating.
6. No pending entry identity is held by a row dead-lettered before this
   release (such rows carry no dead-letter record); clear one with the brain
   repair in `docs/runbooks/PAPER_UPTIME.md`.
7. Informational: PR #37's records still `unmatched` and open `system` lots
   of flat symbols (the read-only SQL in the two October 5 sections).
8. One read-only lookup of an unknown client order id on the paper API
   confirms the order-not-found answer (HTTP 404, JSON code 40410000, message
   starting `order not found`). If paper answers differently, absence is never
   proven (fail-closed) and the classifier must be updated first.

Activation (the approved operation; `scripts/phase2_freeze.py` never writes
the active file):

9. Build and install the release image from the merged commit; record
   source_sha, image_sha and image_digest.
10. Publish the candidate surface as the host's active freeze with
    `FROZEN_AT` = the activation time at the verified-flat transition,
    `status: active`, `candidate_only: false`, `deployment_approved: true`,
    `measurement_cutoff_changed: true`, `prior_active_cutoff` and
    `prior_active_freeze_sha256` of the replaced active file, the activation
    identity (id, source_sha, image_digest, approval reference) and
    `approved_surface_paths` (the difference above). `scripts/phase2_freeze.py
    --verify` on the host must then exit 0.
11. Write the activation record: `activation_timestamp_utc` equal to
    `FROZEN_AT`, `active_freeze_sha256` of the new active file, and
    `broker_before_transition` (paper endpoint verified, 0 positions, 0 open
    orders). The original activation stays as it is.
12. Update the reviewed daily-evidence binding: approval reference and time,
    source_sha, image_sha, image_digest, the freeze and activation paths and
    sha256, `measurement_cutoff` = `FROZEN_AT`, and the `runtime_config_hash`
    the running release reports (it changes with `BUILD_VERSION` or any
    runtime-hash variable, for example `SCANNER_ENABLED`). The policy baseline
    reference, the effective policy hash and the operator control path are
    unchanged.
13. If the market scanner is re-enabled with this release (the stream-history
    fix is its precondition), flip `SCANNER_ENABLED` before step 12 so the
    recorded runtime hash is the final one; the same activation covers it.

After activation:

14. The first tick logs no `REGIME PRIOR TRIPWIRE`; the startup baseline check
    reports configured and verified with the bound sha256; the organism status
    carries `order_dispatch_lifecycle`; the next daily evidence pack validates
    against the new binding.
