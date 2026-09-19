# Operations and evidence integrity — first repair release
Status: implemented candidate; final validation and PR evidence are recorded in `artifacts/task_report.json`. Direct Codex implementation was authorized by Marsel.

## Scope
The user instructed implementation of the approved milestone on 2026-09-19. This first release repairs two concrete integration failures: incomplete close accounting reaches dependent state without retry, and post-close evidence lacks an enforceable complete-collection/quality boundary.

This is a runtime accounting-behavior repair plus read-only operations tooling. It does not retune strategy rules, change the six frozen source groups/config/feed, reset the learner or change the approved September cutoff. No deployment or new schedule is part of opening its PR.

## A. Accounting contract
A strategy close is not finalized until attributed entry/exit cashflows conserve quantity. Keep the original observed-flat UTC time, entry order identity, reason, exit provenance and causal fields in durable pending metadata. Keep it visible in status; use the existing metadata gate to prevent same-symbol re-entry while unresolved. Retry complete-position lookup using the original close bound. Do not feed approximate results to the ledger, learner, risk history, Kelly or calibration. Preserve real broker-equity safety controls.

Definitively unfilled/rejected entries can be removed only after zero execution is verified. Unknown attribution remains unknown; orphan exclusions remain. A reappearing broker position retains position management. Deferred resolution across sessions retains the true close time without contaminating the current day's counters or creating a fresh cooldown from yesterday's outcome.

Pending records must survive startup's flat-symbol cleanup. Finalization needs one authoritative durable accounting state, or a replayable journal with consumer receipts. A separate 'applied ID' file alongside independently written CSV and learner state is not a transaction. Failure injection at persistence boundaries must restore either the old coherent state with a pending close or the new coherent state. Do not claim crash consistency from clean-save tests.

Independent cashflow oracle: buy 6 shares at 100; sell 2 at 101 and 4 at 99. Gross PnL is -2; six-bps modeled net is -2.36 on 600 entry notional. If the first exit leg is absent, no strategy outcome may be finalized. Add the missing leg: exactly one -2 outcome must reach each applicable consumer. Repeat/restart: no double count.

Existing sanitized 27-cycle accounting fixture remains a regression oracle. Update the existing test that explicitly expects approximate learner/risk updates; its expectation currently preserves the defect.

### Replay integration

Replay must feed actual simulated execution legs into the same exact-close contract. Its separate broker PnL log is insufficient proof that engine learner/risk consumers advanced. Preserve delayed-fill order identity, quantity conservation, partial exits and scale-ins; label synthetic fill provenance distinctly from database paper-broker evidence. Tests must require a nonempty reconciled outcome and verify each consumer, not merely iterate over possibly empty results. This repairs the adapter without changing the frozen decision functions. `ReplayResult` exposes accounted outcomes and unresolved accounting separately from the broker's per-exit-leg trade log. Existing `delay_fill` remains a synchronous next-bar-open pricing model, not an actual delayed-execution queue; this limitation is preserved and tested, not silently redesigned.

## B. Daily evidence contract
Implement a manual runner under scripts/ops, with actual-host GET-only collection restricted to the paper broker and an explicit offline-input mode. It must not import submission/cancellation clients or install a scheduler. Capture the active freeze, ledger, event feed, full applicable log rotation inventory, effective runtime identity, calendar and complete cumulative forward broker order/position evidence.

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
