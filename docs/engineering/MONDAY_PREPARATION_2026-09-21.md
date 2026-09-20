# Monday paper session preparation — September 21, 2026

This is the current preparation record. Earlier September readiness reports are historical. The running release is PR17; PR19 is a repair candidate and has not been activated. Neither healthy services nor passing software tests establish a profitable strategy.

## Closed-market checks completed

At 2026-09-20 00:32 UTC, authenticated observer checks identified deployed source `274d0c47ea6c4a092667cc65f813a96a2264e676`, image `sha256:86952abc7865191f1fc3a287ebfc61205b6682213cf9a0b54d697f8df68d917c` and runtime configuration fingerprint `ffc18df3e0051af4`. Database/broker readiness passed. The scheduler was running; no session tick had occurred since this weekend startup, so this is not proof of market-data freshness.

The paper broker was ACTIVE and unblocked, with zero positions and open orders. Its calendar and clock confirmed Monday 09:30–16:00 Eastern / 06:30–13:00 Pacific. The local watchdog was healthy and unpaused, with no pending critical alerts or recovery action. Startup, watchdog and both backup jobs were loaded with successful last exits. The power check found the Mac on **battery**, with battery sleep enabled. AC sleep is disabled. Connect the Mac to power before the session; these jobs require the host to remain powered, awake, connected and logged in.

The latest scheduled PostgreSQL dump (23:45 UTC September 19) restored into a fresh disposable container with no network, host ports or mounts. All 27 public tables and validated constraints passed; the test container was removed. The latest scheduled brain archive (23:30 UTC) verified and restored to a separate private directory without loading model objects. Live, restored and original activation-baseline trade ledgers have identical hashes. These separate restore checks do not certify recovery of a later mid-session database/brain/broker checkpoint.

The installed freeze verifier passed against the approved September cutoff `2026-09-19T21:55:01.857005+00:00`; its file hash remains `06d73b05cd31b99540e352226260b2aedb10ea83563caa4d7ddc73d1d4f625dc`. No freeze, historical trades, learner or deployed source was changed by these checks.

Sanitized observations: `artifacts/operations_evidence/monday_runtime_readiness.json`. Full observer and restore receipts, database dump and brain copy remain private under the operator's Application Support directory.

## Candidate review and activation preparation

A later PR19 review superseded the previous source acceptance for four findings: replaced-order handling, hardlinked inputs, symlinked input ancestors and malformed numeric entry evidence. Correctness requires verified order attribution and complete cashflows; a terminal predecessor does not prove its replacement finished. Missing evidence must remain visible and block a strategy verdict. Final repair decisions and tests belong in the PR's updated source-review and validation artifacts. A read-only database inventory found zero `replaced` or `pending_replace` orders among 1,653 stored orders; there is no current replacement backlog. Future replacement lifetimes remain unsupported and explicitly block qualification.

Before activation, bind the final reviewed source and prebuilt immutable image to a release receipt. Required local and hosted tests, replay, invariant checks and independent review must pass for that source. Keep the original activation manifest and evaluation cutoff. Record the new approved source/image/config identity separately; never whitelist a mismatch or fabricate a receipt for an older entry. PR17 cannot satisfy PR19's new exact-accounting and entry-evidence contract.

Activation is a controlled maintenance action after release acceptance: preserve current user edits/configuration and state; pause automatic recovery/startup during the transition; verify paper broker flat/no open orders; capture fresh backups and shutdown state; install only the approved source/image; verify startup, authenticated identity, paper mode, state restoration and unchanged freeze; then restore watchdog/startup authority. An unexpected position, order, state loss or identity mismatch blocks release. Do not flatten or cancel as a deployment convenience.

Retain the existing PR17 image and all pre-transition evidence as recovery references. PR19 introduces an authoritative accounting checkpoint: an image rollback after any new activity is not automatically safe. Preserve both old and new state and reconcile every intervening fill before deciding recovery. Never restore old state over a running service, erase pending closes or restart the evaluation clock to hide an unsuccessful transition.

## Monday acceptance sequence

| When (Pacific) | Required evidence | Failure response |
| --- | --- | --- |
| Before 06:30 | Approved release identity; unchanged freeze; healthy authenticated runtime and watchdog; fresh valid backups; broker account/orders/positions reconcile; AC power/login/network available. | Resolve the specific discrepancy before declaring readiness. |
| At and after 06:30 | Current provider bars and advancing successful engine ticks; no stale-data, submission or reconciliation errors. | Retain diagnostics; do not bypass stale-data or entry safety gates. |
| During the session | Follow any natural entry through receipt, broker fill, tracked position, all exit legs and exactly one accounting outcome. Check pending accounting and errors. | Preserve incomplete evidence; no forced trade or approximate outcome to satisfy acceptance. |
| Near 13:00 | Observe configured end-of-day entry blocking and any required flattening, then reconcile broker positions/orders. | Investigate residual exposure or incomplete fills; do not label the day complete. |
| After 13:05 | Run the manual daily evidence collector using the broker calendar, original cutoff/baseline and approved current release. Retain complete logs, exact input hashes and all questionable rows. | `BLOCKED` withholds the strategy verdict. A valid no-trade day remains statistically `INSUFFICIENT`. |

The daily collector has no installed schedule. GitHub's credential-free post-close test workflow does not collect the actual host/broker session. An operator must own the manual run until a separately tested schedule is installed. No new automation or notification destination was created here.

## Remaining work and strategy decision

Natural-session acceptance, visible alert delivery and full-host restart/recovery remain unproved. Off-machine alerts and off-host backups are not configured by this work. Complete these resilience checks before claiming unattended operation. No blanket security or all-repository defect-free certification is implied.

While the market is closed, strategy work can prepare one preregistered shadow hypothesis and a reproducible research dataset with explicit quality/exclusion reasons, costs and an untouched evaluation period. Historical data can inform diagnostics and hypothesis generation where its lineage is known; it cannot substitute for clean forward evidence. Keep the frozen baseline unchanged, use the existing 6-bps primary evaluation protocol and 60/120-trade looks, and distinguish operational readiness from edge validation.
