# Operations and evidence integrity — first repair release
Status: implemented candidate; final validation and PR evidence are recorded in `artifacts/task_report.json`. Direct Codex implementation was authorized by Marsel.

## Scope
The user instructed implementation of the approved milestone on 2026-09-19. This first release repairs two concrete integration failures: incomplete close accounting reaches dependent state without retry, and post-close evidence lacks an enforceable complete-collection/quality boundary.

This release now also includes the explicitly authorized September 21 research policy lock and controlled paper rollout. The six original source groups, strategy thresholds and feed remain unchanged; the frozen surface is expanded to cover promotion/training/settings controls and the reviewed retained parameter baseline. The activation deliberately advances the forward evaluation boundary, archives the previous freeze, and preserves all history and models. An actual-host read-only daily evidence job is part of deployment.

## A. Accounting contract
A strategy close is not finalized until attributed entry/exit cashflows conserve quantity. Keep the original observed-flat UTC time, entry order identity, reason, exit provenance and causal fields in durable pending metadata. Keep it visible in status; use the existing metadata gate to prevent same-symbol re-entry while unresolved. Retry complete-position lookup using the original close bound. Do not feed approximate results to the ledger, learner, risk history, Kelly or calibration. Preserve real broker-equity safety controls.

Definitively unfilled/rejected entries can be removed only after zero execution is verified. Unknown attribution remains unknown; orphan exclusions remain. A reappearing broker position retains position management. Deferred resolution across sessions retains the true close time without contaminating the current day's counters or creating a fresh cooldown from yesterday's outcome.

Replacement-order lineage is not reliably persisted by the current broker stream. A `replaced` predecessor is terminal, but does not prove its successor is finished or absent. Such lifetimes remain pending with `replacement_lineage_unverified`, and forward replaced orders block daily evidence qualification. This includes zero-fill predecessors. Supporting automatic replacement-chain accounting requires a separate ingestion/attribution repair; this release does not fabricate lineage or silently clear that hold.

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
