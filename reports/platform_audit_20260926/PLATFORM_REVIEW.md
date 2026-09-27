# Platform review and repair ledger — 26 September 2026

## Verdict

The installed paper process is running, but the platform cannot yet be certified as a reliable end-to-end trading system. This audit reproduced failures that a healthy process and previous passing release checks did not detect. There is also no demonstrated profitable strategy. These are separate conclusions, with separate acceptance gates.

Audit baseline: deployed source `87c1addb39321e4f3a628041d8fb68a6e848255d`, tree-identical PR30 merge `bf533a43d01a4c2e7428ea9589159d9c7d242319`. API image `sha256:472e4e4bf017600c558292a8b36b1a57ff8009d01756b277d39db9b72afb6cf5`; process started 2026-09-25T21:15:48Z. Active forward boundary is 2026-09-25T21:11:46.270521+00:00. The audit uses a separate worktree; the installed dirty checkout, models, history, broker state and current freeze remain preserved.

The initial observations and each repair are scoped below. Implementation is not deployment, and a synthetic regression is not a natural trading-session observation. Final validation receipts are retained under `artifacts/platform_audit_20260926/` and the required top-level artifact pack.

## Access and architecture assessment

Repository read/write access, isolated worktree creation, GitHub pull-request access, hosted workflow execution and artifact retrieval are working. Docker build/control access was exercised only on disposable audit resources. Read-only observations reached the installed containers, runtime configuration, paper broker account, database and scheduled operating evidence. No test order was submitted to the user's broker. Real-money permissions and execution have not been exercised or certified.

The existing architecture has useful safety controls, but its integration contracts were weaker than its component checks. The concrete repair strategy is to make broker observations, order state and accounting atomic; recover identifiable unresolved work from durable state; make operator status truthful and session-bound; and require evidence through failures and recovery. These repairs do not require the parked engine decomposition or a strategy rewrite. Remaining market-data and EOD boundaries must be repaired before an end-to-end readiness claim is justified.

## Installed baseline observations (26 September)

| Surface | Observation | Limit of conclusion |
|---|---|---|
| API/database/Redis | All three existing containers healthy; API restart count 0; readiness 200; loaded brain and recent scheduler loop | Market closed; no natural market ticks since Friday's after-close activation |
| Broker | Paper account active, zero positions and zero open orders; next opening reported Monday September 28 at 09:30 ET | A snapshot does not prove order submission, partial fills or EOD behavior |
| Entry controls | Research policy locked; operator halt false; close-accounting pending map empty | Entry controls have not been changed during this audit |
| Frozen identity | Read-only verification against the installed active artifact and actual allowlisted container configuration passes after non-frozen repairs | The transport omission below is itself a known coverage gap |
| Recovery/backup | Five-minute watchdog, daily evidence and both backup agents loaded; latest exit codes 0; backups verified within 26-hour threshold | Mac/user-session availability and off-machine alert delivery remain separate operational dependencies |
| Logs | Since activation: 16,381 lines at 22:41 UTC, one error, eight warnings, no traceback | Error was a temporary broker timeout/reconciliation failure at 13:03 UTC; later direct broker check succeeded. Zero recent errors is not a correctness proof |
| Web interface | No frontend listener or frontend container observed on this host | Source/build/component verification does not establish an installed UI available to the operator; remote UI deployment was not established |
| Daily collection | PR30 first pack structurally ready for review, zero forward trades, all four strategy gates insufficient | Valid collection with no trades is not a passed strategy verdict |
| Nightly CI | Run 36211294000 failed on the deployed source: 9167 passed, 11 failed, 6 errors; separate seven-case replay passed | Prior targeted release checks did not cover this whole failure set |

The overnight configuration warns that organism drawdown kill is 10%, above its 5% code default. This is a recorded configuration fact, not a new adjustment made here. Different control layers must be read from the resolved runtime snapshot; this audit does not silently tune them. Five historical order-status rows remain unknown under the existing narrow exception. They are not active orders and have not been rewritten as resolved trades.

## Confirmed defects and repair scope

| ID / priority | Failure and practical consequence | Repair / state |
|---|---|---|
| FILL-01 / P1 | A cumulative broker average was applied to only the incremental shares. Example: 5 shares at 100 followed by 10 cumulative shares at average 110 recorded 1050 instead of 1100 cash cost | Derive the new leg from cumulative cash minus already recorded execution cash; test buys, closes, partials and realized PnL |
| FILL-02 / P1 | Order summary committed before executions/lots. A later failure could leave the summary ahead of accounting; identical restart/reconnect snapshots skipped the missing work | One serialized transaction for summary, execution, lots and durable fill audit; duplicate/stale snapshots remain idempotent; failure/retry proofs required |
| FILL-03 / P1 | A terminal canceled/expired order with a partial fill could fail to recover its missed partial event | Recover its positive cumulative fill; refuse unsupported corrections explicitly instead of inventing historical lots |
| FILL-04 / P1 | Recovery searched only recent locally changed rows or a broker page; an older owned unresolved order could remain undiscovered | New bounded persisted-order recovery advances through attributable unresolved orders without an age cutoff, fetches the exact broker UUID and uses the atomic accounting path. Unknown legacy rows are preserved |
| FILL-05 / P1 | A delayed submission acknowledgement could reopen a filled order, overwrite fill progress, or record a fill without accounting. Persistence failure after a real broker acknowledgement could be reported as broker rejection or retried as a new submission | Serialize and validate real acknowledgements through shared accounting. Preserve mock/shadow and terminal progress. Latch acknowledged broker identity before accounting/sent persistence; failure uses the existing original-client lookup-only recovery path |
| UI-01 / P1 | Broker/DB failure returned a fresh-looking synthetic $100,000 flat portfolio with HTTP 200 | Return 503/unavailable; successful empty positions must be a verified account observation |
| UI-02 / P1 | Rejected organism status fetch retained old green state; portfolio refresh was disabled; websocket payload shape was wrong | Bound freshness, handle errors and recovery, accept actual payload shape, select newest valid user-bound observation |
| UI-03 / P1 | Stale local inventory could hide real broker positions; day P&L was hardcoded zero and unrealized P&L was labeled total | Refuse broker/local inventory disagreement; derive and label daily account-equity change, including cashflow caveat; label unrealized metric Open P&L |
| AUTH-01 / P1 | Authenticated clients could request another user's private Socket.IO room | Validate entire subscription batch against authenticated identity and supported channels; retain monitor restrictions |
| AUTH-02 / P1 | Token replacement/logout could retain an old websocket transport and callbacks | Credential-bound teardown/reauthentication and old-session event rejection; focused lifecycle tests |
| AUTH-03 / P1 | Actual login payload lacked normalized frontend identity; delayed refresh could overwrite a replacement session, and missing refresh token stranded later requests | Normalize verified backend identity; reject stale refresh completion and retry dispatch; settle failed refresh queues |
| AUTH-04 / P1 | A real built-browser reload kept the persisted logged-in label but lost the memory-only access token; protected requests returned 401 without restoring the session | Restore the existing refresh-token session and verify its principal before mounting protected routes; bound restoration, reject late completions after logout/replacement, retain memory-only access tokens. Focused tests and rebuilt native-browser reload/outage/recovery/logout acceptance pass |
| DEPLOY-01 / P1 | Paper deployment had no persistent operator UI; API and websocket defaults also targeted different origins | Prepared an unprivileged, loopback-only frontend service with same-origin API/websocket forwarding. Disposable proxy proof passes outage/recovery, upgrades and query-safe logging. Not activated on the installed stack |
| CI-01 / P2 | Two health tests asserted an obsolete model shape/comment; expensive replay fixtures ran under coverage and timed out | Behavior-based readiness assertions; required replay inventory grows 7→22. All assertions/explicit timeout markers remain; moved unmarked cases inherit replay 120s instead of core 30s |
| CI-02 / P2 | Hosted checks expected lot-accounting code and rollback comments inline in the event handler after accounting moved into the shared transaction helper | Replace both obsolete source-string checks with executed success/failure transaction and rollback-error behavior. The 292-case harness and added 28-case rollback/accounting selection pass locally; initial hosted failures are retained |
| DATA-01 / P1 | Successful socket send counted as successful subscription despite provider rejection/partial acknowledgement; next sync did not retry | **Approved September 27; implemented candidate:** desired/pending/current-connection server-confirmed state, bounded retry, unchanged hard admission gates |
| DATA-02 / P1 | Failed startup left a stopped provider with no retry path; normal socket closure could leave connected flags true | **Approved; implemented candidate:** explicit failure/disconnect state and bounded lifecycle recovery; retry avoids repeated historical warmup inside the short engine deadline, with no feed substitution |
| DATA-03 / P2 | Cross-asset features align ordinal indexes: unequal-length stock/SPY frames select a 40-minute-old SPY value despite equal latest timestamps | **Approved; implemented candidate:** causal timestamp alignment and explicit unavailable metadata. Current learning-mode ML isolation limits direct main-book impact; no lost-profit claim |
| EOD-01 / P1 | Exact pending-entry cancellation block calls missing `AlpacaStreamClient.cancel_order`; caught exception means supported cancellation service is not called | **Approved; implemented candidate:** supported broker confirmation with exact execution/lot/exposure evidence; failed cancellation, TTL and restart preserve unresolved identities. Entry block and flatten remain active |
| FREEZE-01 / P1 | Underlying streaming transport is not directly hashed in data-pipeline surface | **Approved; implemented candidate:** transport and pending-entry lifecycle helpers are hashed; negative controls demonstrate drift detection without rewriting active authority |

The scope explicitly approved on September 27 is documented in `../PLATFORM_AUDIT_FROZEN_REPAIR_SCOPE_2026-09-26.md`. It changes correctness, not strategy parameters or the data feed, and requires a new forward boundary on activation. Historical evidence and earlier boundaries must remain intact.

## Why earlier checks missed these failures

The missing coverage was at component boundaries. Subscription tests could prove that a send occurred without proving provider acceptance. Order-summary and execution tests could each pass without injecting a failure between their commits. HTTP success was treated as portfolio health even though the service fabricated a fallback. Dashboard tests did not exercise failed refresh, hanging requests or identity changes. Some health tests inspected source comments rather than executing readiness behavior. A curated release suite and the broader nightly suite selected different cases and used different instrumentation.

Those explanations identify test gaps; they do not excuse the previous unconditional readiness language. Acceptance now needs failure/recovery and whole-flow evidence with source/config identity, not an aggregate test count or a green process alone.

## Remaining evidence and operational limits

- The currently deployed source still contains the audit findings until a reviewed repair is activated. Do not describe local repairs as deployed.
- Separate disposable PostgreSQL verification passed six actual two-session contention cases, one persisted-lineage/UUID-keyset database case, and five isolation-guard cases. It proves the second writer waits and validates duplicate entry/exit, cumulative-price updates, rollback/retry, persisted recovery and delayed acknowledgements. It uses fresh synthetic rows; it does not certify all inherited production rows.
- Same-quantity broker price corrections and unsupported terminal replacement lineage are explicit reconciliation failures; automatic historical rewriting is outside this repair. Existing malformed or legacy lots need a separate read-only reconciliation assessment before any correction.
- The persisted recovery repair removes the recent-row discovery gap for attributable unresolved orders. Each pass has a time/request budget and advances an immutable keyset cursor; process restart resets the in-memory cursor. It does not invent attribution for legacy unknowns or rewrite arbitrary historical terminal orders.
- The operator cleanup route's missing-broker-ID handling needs separate review; never treat absence of a broker ID as proof an order expired. Its frozen source is not silently edited.
- The scanner can accumulate symbols while research lock disables its old rotation path; one required stale symbol can block global entry. This policy interaction needs bounded evidence, not an arbitrary relaxation of freshness gates.
- Existing global admission thresholds, feature-computation CPU cost, quote-age coverage and exception-to-zero fallback paths are not certified as optimal. Keep the existing guards while assessing these separately.
- No single session can prove absence of all bugs. Natural-session subscription recovery, partial fills, protective exits, EOD flatten and restart continuity each need observed or controlled integration evidence.
- Legacy parked CI trio/decomposition/parameter tuning remain parked. External broker/API tests declared unavailable are not counted as passed.
- Shared token revocation lookup has an inherited local-memory fallback during Redis outage. Socket expiry and successful revocation lookup are covered; cross-process revocation across outage/restart is not universally guaranteed by this repair.
- Fresh dependency triage found that GitHub's default-branch alerts are not identical to this deployed/candidate lock. The critical Vitest advisory is already patched here. Eleven high-severity alert ranges still match this lock: eight development-tool alerts, two React Router alerts requiring application modes this SPA does not use, and one unresolved Socket.IO parser runtime alert. The explicitly parked dependency cleanup has not been undertaken; this is not a clean dependency or operating-system security certification. See `artifacts/platform_audit_20260926/dependency_review.json`.

## Completion gates

1. Reproductions fail on the prior source and pass on repaired source; negative controls remain negative.
2. Targeted suites, state/sizing/exits/replay regressions, full artifact pack, secret scan and independent review pass on the exact PR source.
3. Frozen changes receive explicit approval, candidate validation and an acknowledged activation boundary; runtime/source/config references agree.
4. Activate reviewed paper release with recoverable backups, broker/DB reconciliation and post-start verification. Provide a persistent, tested operator interface.
5. Verify a complete market session with fresh provider-confirmed bars and durable entry/close evidence; retain gaps and unknown outcomes visibly.
6. Evaluate strategy only on qualified evidence under its pre-registered gates. See `research_readiness.md` for historical exclusions, implemented strategy inventory and current insufficient verdicts.

None of these gates authorizes real-money trading or promises profitability.

## Prior scoped validation (before the September 27 frozen repairs)

The prior validated product source was `efa2972de8b6d04d87ce07a17067efbd3274a015`. Independent accounting, recovery, acknowledgement, UI/authentication, deployment and CI reviews are preserved with source hashes. That scoped manifest bound 61 changed product/test/workflow files. At the earlier delivery, backend, frontend and deployment product bytes matched this browser-tested source; its subsequent source revision corrected the Docker test harness and CI coverage. The September 27 backend repairs supersede that backend identity and require the combined acceptance below. Inventory ranges name their immutable generation commit, excluding the following evidence-only delivery.

Recovery/accounting regression selection: 261 passed. Acknowledgement/accounting selection: 231 passed, including 36 new acknowledgement cases. Disposable PostgreSQL: 12 passed without skips, comprising six actual concurrent database scenarios, one persisted-lineage/UUID-keyset database case, and five isolation guards. Portfolio/private-room backend selection: 91 passed. Configuration/integration: 72 passed; final workflow/configuration contract: 31 passed. These selections overlap and must not be summed as unique platform coverage.

The final frontend selection used by the readiness workflow passed all 104 cases, including 20 session-restoration cases. TypeScript and the production image build passed. The final image is `sha256:94eddbaa767c7c4a9784391d474e8138483459619845ccfa8a336496fbc1b254`, labeled with the validated source. Its disposable proxy check passed all five groups: static/deep links, HTTP forwarding/errors, three websocket paths, recovery after API address replacement, and authentication-safe logging.

Native Chrome also exercised the built image against the actual authentication, portfolio and Socket.IO code with a disposable synthetic account/database. Fresh login, existing and new-session reload, correct balances, broker outage, automatic recovery, logout and logged-out reload passed. Both restoration requests and both identity requests returned 200; active socket sessions were zero after logout. The initially reproduced reload failure remains recorded. Auxiliary strategy/history panels used empty fixtures; no trading startup or broker order ran. All browser-fixture containers, networks and the temporary tab were removed.

The required full artifact pack passed 168 safety/state/sizing cases, 28 replay cases and 20 semantic invariants. Snapshot, grep and specification checks passed. Read-only verification of the actual installed active freeze also passed without changing its September 25 boundary. The generated local snapshot represents the isolated test environment; the separately captured installed configuration remains the runtime authority.

Hosted nightly run [36278580588](https://github.com/Lesram/intraday/actions/runs/36278580588), on earlier audit source `85b2534`, passed all 22 required replay identities. Its core suite passed 9,242 cases, failed two obsolete source-string assertions, skipped 550 and deselected 159; declared unavailable integrations are not passing evidence. Both failed assertions have since been replaced by executed transaction/rollback checks. The earlier 292-case harness selection and the added 28-case rollback/accounting selection pass locally. The initial failed run is retained; use the [current PR checks](https://github.com/Lesram/intraday/pull/32/checks) for subsequent hosted acceptance, rather than relabeling that run successful.

The first hosted container check built successfully and passed its first three groups, then exposed a Docker portability defect in the test's address-reservation setup. The probe now selects an explicit nonoverlapping private subnet after inspecting existing Docker networks; malformed inventory fails before network creation. The original source fails the new regression. All 22 focused tests and all five disposable proxy/restart groups pass with the repair; the combined probe/workflow selection passes 53 cases. This follow-up changes test infrastructure only. The browser-tested application image and its product source remain unchanged; hosted Linux acceptance passed at delivery head `2a9214c` in run [36282299396](https://github.com/Lesram/intraday/actions/runs/36282299396/job/108516332155), including different-IP recovery and clean teardown. The PostgreSQL job on that head also passed all 12 cases without failures or skips. Final overall acceptance remains reported through the current PR checks.

The September 27 approval extends PR32 with all five frozen correctness repairs and permits a new forward boundary at reviewed paper activation. Combined validation is in progress under `artifacts/frozen_repairs_20260927/`; earlier scoped counts above are not final combined-release evidence. No audit repair has yet been activated on the installed platform. Hosted acceptance, reviewed paper activation and complete natural-session evidence remain distinct gates. The current strategy evidence still does not demonstrate a deployable profitable edge.

The stricter cancellation proof deliberately retains a closed pyramid-add identity when only an anchor-level completed trade survives: there is no explicit durable base-to-add linkage to justify releasing it. The installed `ORGANISM_PYRAMID_ENABLED=false` setting was rechecked on September 27 and remains a release constraint. This repair does not enable pyramiding. Cross-asset availability metadata survives the feature feeder but is lost by existing NumPy/model exports, so exported research rows are not automatically qualified by this change.


## Combined local acceptance — September 27

The combined runtime source is `fed6dcbcdbb5c936aafd63711a0332a980c6835f`.
The final operational selection passed 2,101 cases with no failures and one
explicit unavailable installed-history test. The final focused selection passed
267 cases; paired trading replay passed 18. The full required artifact pack
passed 168 state/risk/sizing cases, 28 replay cases and 20 semantic invariants.
All 15 grep checks passed; the specification comparison found zero differences
across its nine core keys. These selections overlap and must not be summed.

Independent streaming, feature, cancellation, fixture and governance reviews
accepted the source. The broader run's original 12 failures remain recorded:
three outdated historical-prefill assertions, two synthetic profiler setup
failures, and seven assertions that predated explicit alignment metadata. The
repaired fixtures deliver a real synthetic bar through the registered production
callback and retain input/metadata equivalence checks. They do not relax live
freshness. The profiler also rejects a dropped callback.

Provider recovery now survives rejection, partial acknowledgement, clean closure
and failed startup without manufacturing freshness. Pending cancellation requires
terminal broker evidence plus exact accounting/exposure proof; timeout, restart
and expired cooldowns retain uncertain identities. Bounded retries advance past
slow orders. Negative controls preserve the failures these repairs address.

Both timestamp-alignment replay scenarios have actual entries and accounted
closes. Candidate and ordinal-baseline orders/equity remain identical under the
synthetic learning-mode configuration; the crash case lost 6,055.17 and the EOD
case lost 99.48. These are synthetic mechanism checks, not paper trading returns
or evidence of strategy profitability, and do not reproduce every installed
configuration setting. The existing strategy verdict remains insufficient.

Source, tests and review receipts are indexed by
`artifacts/frozen_repairs_20260927/local_acceptance.json`. Generated snapshots are
explicitly offline source/default evidence. Hosted checks, the immutable image,
controlled activation, the persistent UI and a complete natural session remain
separate gates. The frontend source is byte-identical to the earlier browser-tested
`efa2972` tree; the backend identity is now the combined source above.
