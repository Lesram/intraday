# Platform review and repair ledger — 26 September 2026

## Verdict

The installed paper process is running, but the platform cannot yet be certified as a reliable end-to-end trading system. This audit reproduced failures that a healthy process and previous passing release checks did not detect. There is also no demonstrated profitable strategy. These are separate conclusions, with separate acceptance gates.

Audit baseline: deployed source `87c1addb39321e4f3a628041d8fb68a6e848255d`, tree-identical PR30 merge `bf533a43d01a4c2e7428ea9589159d9c7d242319`. API image `sha256:472e4e4bf017600c558292a8b36b1a57ff8009d01756b277d39db9b72afb6cf5`; process started2026-09-25T21:15:48Z. Active forward boundary is2026-09-25T21:11:46.270521+00:00. The audit uses a separate worktree; the installed dirty checkout, models, history, broker state and current freeze remain preserved.

The initial observations and each repair are scoped below. Implementation is not deployment, and a synthetic regression is not a natural trading-session observation. Final validation receipts are retained under `artifacts/platform_audit_20260926/` and the required top-level artifact pack.

## Current operations

| Surface | Observation | Limit of conclusion |
|---|---|---|
| API/database/Redis | All three existing containers healthy; API restart count0; readiness200; loaded brain and recent scheduler loop | Market closed; no natural market ticks since Friday's after-close activation |
| Broker | Paper account active, zero positions and zero open orders; next opening reported Monday September28 at09:30ET | A snapshot does not prove order submission, partial fills or EOD behavior |
| Entry controls | Research policy locked; operator halt false; close-accounting pending map empty | Entry controls have not been changed during this audit |
| Frozen identity | Read-only verification against the installed active artifact and actual allowlisted container configuration passes after non-frozen repairs | The transport omission below is itself a known coverage gap |
| Recovery/backup | Five-minute watchdog, daily evidence and both backup agents loaded; latest exit codes0; backups verified within26-hour threshold | Mac/user-session availability and off-machine alert delivery remain separate operational dependencies |
| Logs | Since activation:16,381 lines at22:41UTC, one error, eight warnings, no traceback | Error was a temporary broker timeout/reconciliation failure at13:03UTC; later direct broker check succeeded. Zero recent errors is not a correctness proof |
| Web interface | No frontend listener or frontend container observed on this host | Source/build/component verification does not establish an installed UI available to the operator; remote UI deployment was not established |
| Daily collection | PR30 first pack structurally ready for review, zero forward trades, all four strategy gates insufficient | Valid collection with no trades is not a passed strategy verdict |
| Nightly CI | Run36211294000 failed on the deployed source:9167 passed,11 failed,6 errors; separate seven-case replay passed | Prior targeted release checks did not cover this whole failure set |

The overnight configuration warns that organism drawdown kill is10%, above its5% code default. This is a recorded configuration fact, not a new adjustment made here. Different control layers must be read from the resolved runtime snapshot; this audit does not silently tune them. Five historical order-status rows remain unknown under the existing narrow exception. They are not active orders and have not been rewritten as resolved trades.

## Confirmed defects and repair scope

| ID / priority | Failure and practical consequence | Repair / state |
|---|---|---|
| FILL-01 / P1 | A cumulative broker average was applied to only the incremental shares. Example:5 shares at100 followed by10 cumulative shares at average110 recorded1050 instead of1100 cash cost | Derive the new leg from cumulative cash minus already recorded execution cash; test buys, closes, partials and realized PnL |
| FILL-02 / P1 | Order summary committed before executions/lots. A later failure could leave the summary ahead of accounting; identical restart/reconnect snapshots skipped the missing work | One serialized transaction for summary, execution, lots and durable fill audit; duplicate/stale snapshots remain idempotent; failure/retry proofs required |
| FILL-03 / P1 | A terminal canceled/expired order with a partial fill could fail to recover its missed partial event | Recover its positive cumulative fill; refuse unsupported corrections explicitly instead of inventing historical lots |
| UI-01 / P1 | Broker/DB failure returned a fresh-looking synthetic$100,000 flat portfolio with HTTP200 | Return503/unavailable; successful empty positions must be a verified account observation |
| UI-02 / P1 | Rejected organism status fetch retained old green state; portfolio refresh was disabled; websocket payload shape was wrong | Bound freshness, handle errors and recovery, accept actual payload shape, select newest valid user-bound observation |
| UI-03 / P1 | Stale local inventory could hide real broker positions; day P&L was hardcoded zero and unrealized P&L was labeled total | Refuse broker/local inventory disagreement; derive and label daily account-equity change, including cashflow caveat; label unrealized metric Open P&L |
| AUTH-01 / P1 | Authenticated clients could request another user's private Socket.IO room | Validate entire subscription batch against authenticated identity and supported channels; retain monitor restrictions |
| AUTH-02 / P1 | Token replacement/logout could retain an old websocket transport and callbacks | Credential-bound teardown/reauthentication and old-session event rejection; focused lifecycle tests |
| AUTH-03 / P1 | Actual login payload lacked normalized frontend identity; delayed refresh could overwrite a replacement session, and missing refresh token stranded later requests | Normalize verified backend identity; reject stale refresh completion and retry dispatch; settle failed refresh queues |
| CI-01 / P2 | Two health tests asserted an obsolete model shape/comment; expensive replay fixtures ran under coverage and timed out | Behavior-based readiness assertions; required replay inventory grows7→22. All assertions/explicit timeout markers remain; moved unmarked cases inherit replay120s instead of core30s |
| DATA-01 / P1 | Successful socket send counted as successful subscription despite provider rejection/partial acknowledgement; next sync did not retry | **Awaiting scoped frozen-surface approval:** desired/pending/server-confirmed state, bounded retry, unchanged hard admission gates |
| DATA-02 / P1 | Failed startup left a stopped provider with no retry path; normal socket closure could leave connected flags true | **Awaiting approval:** explicit failure/disconnect state and bounded lifecycle recovery, no silent feed substitution |
| DATA-03 / P2 | Cross-asset features align ordinal indexes: unequal-length stock/SPY frames select a40-minute-old SPY value despite equal latest timestamps | **Awaiting approval:** causal timestamp alignment. Current learning-mode ML isolation limits direct main-book impact; no lost-profit claim |
| EOD-01 / P1 | Exact pending-entry cancellation block calls missing `AlpacaStreamClient.cancel_order`; caught exception means supported cancellation service is not called | **Awaiting approval:** supported cancellation path, repeat/failure/already-terminal tests while preserving entry block and flatten |
| FREEZE-01 / P1 | Underlying streaming transport is not directly hashed in data-pipeline surface | **Awaiting approval:** include it in the source inventory so transport changes cannot silently bypass drift checks |

The scope requiring approval is documented in `../PLATFORM_AUDIT_FROZEN_REPAIR_SCOPE_2026-09-26.md`. It changes correctness, not strategy parameters or the data feed, and requires a new forward boundary on activation. Historical evidence and earlier boundaries must remain intact.

## Why earlier checks missed these failures

The missing coverage was at component boundaries. Subscription tests could prove that a send occurred without proving provider acceptance. Order-summary and execution tests could each pass without injecting a failure between their commits. HTTP success was treated as portfolio health even though the service fabricated a fallback. Dashboard tests did not exercise failed refresh, hanging requests or identity changes. Some health tests inspected source comments rather than executing readiness behavior. A curated release suite and the broader nightly suite selected different cases and used different instrumentation.

Those explanations identify test gaps; they do not excuse the previous unconditional readiness language. Acceptance now needs failure/recovery and whole-flow evidence with source/config identity, not an aggregate test count or a green process alone.

## Remaining evidence and operational limits

- The currently deployed source still contains the audit findings until a reviewed repair is activated. Do not describe local repairs as deployed.
- Separate disposable PostgreSQL verification passed four actual two-session contention cases plus five isolation-guard cases. It proves the second writer waits and validates duplicate entry/exit, cumulative-price updates and rollback/retry. It uses fresh synthetic rows; it does not certify all inherited production rows.
- Same-quantity broker price corrections and unsupported terminal replacement lineage are explicit reconciliation failures; automatic historical rewriting is outside this repair. Existing malformed or legacy lots need a separate read-only reconciliation assessment before any correction.
- Recovery inventory is still bounded: reconnect considers100 locally updated rows within an hour, and startup considers500 broker orders. Older unchanged pending records can fall outside these searches. The new atomic helper repairs supplied snapshots; it does not certify complete historical discovery.
- The operator cleanup route's missing-broker-ID handling needs separate review; never treat absence of a broker ID as proof an order expired. Its frozen source is not silently edited.
- The scanner can accumulate symbols while research lock disables its old rotation path; one required stale symbol can block global entry. This policy interaction needs bounded evidence, not an arbitrary relaxation of freshness gates.
- Existing global admission thresholds, feature-computation CPU cost, quote-age coverage and exception-to-zero fallback paths are not certified as optimal. Keep the existing guards while assessing these separately.
- No single session can prove absence of all bugs. Natural-session subscription recovery, partial fills, protective exits, EOD flatten and restart continuity each need observed or controlled integration evidence.
- Legacy parked CI trio/decomposition/parameter tuning remain parked. External broker/API tests declared unavailable are not counted as passed.
- Shared token revocation lookup has an inherited local-memory fallback during Redis outage. Socket expiry and successful revocation lookup are covered; cross-process revocation across outage/restart is not universally guaranteed by this repair.

## Completion gates

1. Reproductions fail on the prior source and pass on repaired source; negative controls remain negative.
2. Targeted suites, state/sizing/exits/replay regressions, full artifact pack, secret scan and independent review pass on the exact PR source.
3. Frozen changes receive explicit approval, candidate validation and an acknowledged activation boundary; runtime/source/config references agree.
4. Activate reviewed paper release with recoverable backups, broker/DB reconciliation and post-start verification. Provide a persistent, tested operator interface.
5. Verify a complete market session with fresh provider-confirmed bars and durable entry/close evidence; retain gaps and unknown outcomes visibly.
6. Evaluate strategy only on qualified evidence under its pre-registered gates. See `research_readiness.md` for historical exclusions, implemented strategy inventory and current insufficient verdicts.

None of these gates authorizes real-money trading or promises profitability.

## Local repair validation

The non-frozen repair has passed independent source review. Fill/accounting tests:211 passed, including23 new real SQLite cases. The separate PostgreSQL run passed9 cases with no skips (four actual concurrent transactions plus five isolation guards). Portfolio/authentication backend tests:91 passed. Frontend regression tests:63 passed; TypeScript and production build passed; no new scoped lint findings.

The full required artifact pack passed168 safety/state/sizing cases,28 replay cases and20 semantic invariants; snapshot, grep and specification checks passed. Readiness/collector tests passed128 cases. Configuration/CI initially had102 passes and one test-inventory expectation failure after adding cases; the corrected workflow contracts then passed47 cases, and independent collector/workflow review passed48. Do not sum these counts as unique coverage: selections overlap.

All22 required nightly replay identities have passing local evidence. The first local run passed16 and correctly refused six paired-fixture cases because the isolated runner supplied synthetic broker keys; removing those keys allowed all16 paired-module cases to pass, including all six missing identities. The initial refusal remains archived. This is a local joined validation, not a claimed clean hosted nightly run.

An isolated browser check verified the built login page, with no runtime sign-in and no API/network handshake. Current source/config freeze verification passes against the installed September25 boundary. The installed platform is unchanged. Hosted PR checks, any deployment, complete-session acceptance and the explicitly gated frozen repairs are separate remaining steps.
