# Monday paper-readiness acceptance — September 21, 2026

This maintenance repairs operational readiness for supervised paper trading. It does not establish a profitable strategy or authorize real-money trading. The next broker calendar session opens Monday at 06:30 Pacific / 09:30 Eastern.

## Installed and observed

This is the source-bound maintenance evidence record; final GitHub run and merge outcomes are linked in PR #12 and PR #13.

The API runs the independently reviewed `dead82a4d3d110afe811ed91b59959e76bfd9ce6` image. The installed host helpers and final CI source are `0d1c93d53d912d906440b679e70be20b4739d0b0`. Subsequent changes affect host monitoring/reporting and CI only; backend and paper-container configuration parity is verified. API, PostgreSQL and Redis are healthy. Database/broker readiness passes; startup reports 18/18 preflight checks. Every existing data mount and application setting is preserved; only build provenance changed. API, database and Redis host ports bind to loopback.

A dedicated private monitoring credential now reaches four protected GET endpoints. It cannot reach administration, position control or WebSockets; signed-token regressions cover the existing position-close route. Authentication succeeds through the normal login path. No test orders were submitted or canceled.

The broker was ACTIVE, unblocked, flat, and had no outstanding orders before maintenance. A fresh private database backup was made, and its isolated restore verified all 27 public tables. Brain snapshots are validated and timestamped. Daily backup jobs and the five-minute watchdog are loaded. Backup monitoring validates receipt structure, complete file inventories and checksums, and flags missing, damaged or older-than-26-hour copies without touching the live state. The watchdog can reopen Docker, recover only known existing paper containers, and submit local Mac notifications with bounded retries/cooldowns.

## Evidence integrity

The deployed decision surface exactly matches the July-7 freeze; the six functions, strategy parameters, IEX feed and freeze timestamp remain unchanged. The original working-copy edits were preserved byte-for-byte and backed up. Credentials, database dumps and full brain copies remain outside the public repository.

All 27 forward closes match 61 saved broker fills. Six multi-leg exits have a material accounting discrepancy: recorded gross $84.922414 versus broker gross $89.819991. The offline tool and sanitized fixed inputs reproduce the $4.897577 difference. Historical records and counters were not rewritten. The 609/610 count difference reflects inherited accounting scope, not a missing forward trade.

PR #14 is a separately reviewed prospective accounting proposal. It requires an explicit decision about the next evaluation cohort before activation. Complete database fills reconcile all exit proceeds; incomplete evidence retains a clearly marked approximation without automatic later correction. The proposal is not installed by this maintenance.

## Validation and source provenance

Local core/state/sizing/exit/replay validation passed 216 tests, plus 511 targeted tests: 156 access/authentication, 41 configuration, 80 order/reconciliation, 20 order safety, 69 operations, 122 CI contracts, and 23 offline research cases. Reruns are not added again. The reviewed original operating build also passed the hosted operational-safety job. Failed workflow setup, collection and time-budget runs remain available; fixes are validated against actual hosted runs rather than erased.

GitHub's hosted audit verifies software evidence using mock/shadow settings. Its snapshots are not an observation of the Mac or broker. The separate authenticated `runtime_after_deployment` snapshot is the actual running-state observation.

## Remaining acceptance boundaries

- A natural market session is still needed to verify live quotes, scheduled ticks, any naturally generated order/fill reconciliation, and end-of-day flattening. Do not force a trade to satisfy a test.
- Local recovery requires the Mac to be powered, awake and logged in. No full-machine reboot drill was performed. Mac notification submission succeeded; visible delivery can depend on macOS settings. No external destination has been chosen. The archive monitor detects a missed daily backup by its 26-hour freshness limit; an individual failed attempt is not alerted while a recent valid copy exists.
- The accounting activation/evaluation-cohort decision is pending. There is insufficient frozen-forward evidence for an edge verdict (24 eligible trades versus 60 for the first look).
- Parked refactoring, parameter tuning, and the legacy frontend-audit/Bandit/Quality-Summary cleanup remain parked. Enabling repository vulnerability alerts exposed default-branch findings; this maintenance does not certify the historical dependency baseline.
- The historical synthetic secret alert was resolved as a test fixture; known configured runtime/observer secrets were checked against the new evidence without disclosure.

## Monday observation sequence

Before 06:30 Pacific, confirm the watchdog is healthy/unpaused, backups are fresh/valid, the expected paper image is running, broker account/orders/positions reconcile, and the freeze verifies. At the open, confirm fresh data and advancing engine ticks. Observe a natural order only if the frozen rules produce one; otherwise stand down normally. Verify reconciliation after fills and confirm end-of-day entry blocking/flattening. Generate the stand-down session row only after session close.

Repository controls require pull requests on main and the active paper branch, prohibit force pushes/deletion, and enforce the active branch’s operational safety check. The owner is the sole collaborator, so GitHub human-approval count is zero; independent agent review is recorded separately and is not represented as a GitHub human approval. The default-branch scheduler bridge also excludes its four workflow files from staging publication triggers.

The repaired scheduled post-close worker passed end to end on `9441ca7` in run [35464396251](https://github.com/Lesram/intraday/actions/runs/35464396251): all 216 full-pack tests, Phase 8 report, KPI evidence check and independent status reporting succeeded. Its replay took 456.236 seconds, exceeding the former 300-second process limit; the new bounded 600-second limit retained this valid result. Final pinned source validation uses [run 35464757621](https://github.com/Lesram/intraday/actions/runs/35464757621).
