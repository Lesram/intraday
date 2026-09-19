# Intra resumption readiness audit — September 19, 2026

**Assessment: ready for supervised research and development; not yet ready for unattended operation or strategy promotion.** Codex can read and write the project, run isolated tests, inspect the paper runtime and data, and use GitHub. The remaining problems concern monitoring, evidence quality, application authentication, and repository governance.

This is an integration and readiness audit, not a certification of every code path or a strategy-change approval. No trading code, configuration, broker orders, deployments, frozen parameters, or forward-clock timestamps were changed. The existing `.claude/settings.local.json` modification was preserved.

## Scope and provenance

- Audited checkout: `intra-2.0-phase1`, `4a8e0e713d8fd0b2e0b87b077d616f4773304d0f`, matching its remote branch.
- Running paper image: `9697cd59e8add11dbc96080aaec0f4c21def4292`; later checkout changes are the activation documentation and test-isolation fix.
- Report branch: `codex/resumption-readiness-2026-09-19`, based on the active branch, not stale `main`.
- Authoritative handoff: [July research brief](RESEARCH_BRIEF_001_2026-07-29.md), [platform closeout](OPS_WORKORDER_COMPLETION_2026-07-23.md), and [AGENTS.md](../AGENTS.md). Older README/status/buildout claims are not current acceptance evidence.
- Evidence directory: `artifacts/resumption_readiness_2026-09-19/`. Current local runtime snapshots are separate from snapshots generated inside the isolated test checkout.

## Verified capabilities

| Area | Result | Evidence and limits |
|---|---|---|
| Local files | Verified | Read/write/read-back/delete probe succeeded. Source, history, logs, brain artifacts and local configuration are accessible. Secret values were not printed or committed. |
| GitHub | Verified read, branch push and PR creation | CLI and connector authenticate as Lesram; repository metadata grants admin/maintain/push/pull/triage. PRs, issues, checks, logs, security metadata and artifact downloads are accessible. The report branch was pushed and [draft PR #10](https://github.com/Lesram/intraday/pull/10) opened successfully. Review submission, workflow dispatch and deployment remain unexercised. |
| Backend development | Verified with project environment | `venv/bin/python` is Python 3.12.12; dependency consistency check passes; all 173 lockfile versions match installed packages. System `python3` is 3.9.6 and bare `python`/`pytest` are unavailable. Use the project environment explicitly. |
| Frontend development | Verified | Dependency tree, both TypeScript checks, production build and 134 frontend tests pass. An authenticated browser workflow was not exercised. |
| Paper runtime | Verified | API, PostgreSQL and Redis containers healthy; `/health` and the actual readiness endpoint return HTTP 200. API restart count is zero since its September 19 start, not proof of continuous historical uptime. |
| Broker and market data | Verified read-only | Paper account ACTIVE; account, positions, open orders and clock reads return HTTP 200. Zero positions/open orders at inspection. Ten recent IEX minute bars retrieved successfully. Order submission was not exercised. |
| Database and cache | Verified | Read-only PostgreSQL transaction succeeds; 27 public tables; migration `20260503_000003`. Redis authenticated PING succeeds using the application's configured connection. |
| Freeze integrity | Verified twice | Local source with local configuration and source imported from the running image both match all recorded frozen surface components. `FROZEN_AT=2026-07-07T20:36:49.008305+00:00` is unchanged. |
| Startup support | Partly verified | Login and hourly watchdog LaunchAgents are installed, loaded and report last exit 0. AC sleep is disabled. Docker's login preference could not be read; reboot/failure recovery was not deliberately exercised. |
| Application login | Missing for this agent | Protected organism/deploy/edge/data-integrity endpoints return 401. `INTRA_API_USER`/`INTRA_API_PASSWORD` are unavailable. Public health, container files and broker access do not establish authenticated application access. |
| Claude Code | Installed, signed out | Version 2.1.276 is available, but `claude auth status` reports `loggedIn=false`. The documented Codex/Claude division of work cannot currently operate as written. Codex's own file/test capabilities work. |

Technical access does not waive the project's freeze, review or deployment rules. Changes to the frozen strategy or data feed still require Marsel's explicit sign-off. Research, reports and permitted shadow-first work can proceed without a clock reset.

## Findings that matter before resuming unattended work

### 1. Scheduled checks are disconnected from the active project

Remote `main` is still `32a3474` from March 9. The active branch is **452 commits ahead**. Scheduled Actions run old `main`, rather than the source being paper traded.

Among the latest 100 runs, 52 nightly runs failed and 38 postclose runs were cancelled. The [latest nightly](https://github.com/Lesram/intraday/actions/runs/35415312971) fails during setup on deprecated `actions/upload-artifact@v3`. The [latest postclose run](https://github.com/Lesram/intraday/actions/runs/35401191697) times out after six hours in artifact generation; audit-index generation, KPI issue creation and artifact upload never occur. Both runs have zero artifacts. There are zero open issues, so issue silence is not evidence of a healthy platform.

Restore an authoritative branch-to-runtime-to-monitoring relationship before relying on automated oversight. Do not merge the large existing PR merely to make scheduled checks run newer code.

### 2. Runtime alert delivery and historical uptime are not reliable

September 16 logs contain 873 no-order watchdog events and 873 `ALERT-NO-CHANNELS` messages. No configured webhook, Slack, Telegram, SMTP, PagerDuty or Discord channel was found in the running environment. These counters alone do not prove a broken entry path, but they do prove that those alerts had no delivery channel.

Adjacent retained log lines jump from August 17 17:55 UTC to September 16 02:41 UTC, a 704.77-hour gap. The September 15 backup contains a manifest last saved August 14, corroborating a lack of persisted progress, although the precise host/process outage cause is unproven. A second 36.39-hour logging gap spans the September 18 market session. A healthy container today cannot establish continuous historical collection. September 18 overnight logs also report stream instability reaching 158 reconnects. Database/outbox errors around the September 19 restart were followed by successful current database checks. Historical faults and current health must be reported separately.

Brain backups exist through September 17. The newest observed PostgreSQL backup in the repository's backup directory is May 2. Restore testing and off-machine backup availability remain unverified.

### 3. A required artifact generator can falsely report replay success

`scripts/ci/generate_artifacts.py` catches failed subprocess execution and returns an empty string. Replay parsing then treats zero parsed failures as a pass. An isolated failure injection, without source edits, reproduced **pytest exit 1 → replay status `pass`, 0 passed, 0 failed**.

The actual replay suite was independently run and passed 28 tests. The defect is in evidence reporting, not an observed replay failure. Repair must preserve subprocess exit codes and raw failure output, and reject empty/zero-test success. This audit documents the defect; it does not change platform/tooling policy or code.

The contract also names `tests/test_position_reconciliation.py` as a pytest suite, but that file is a legacy standalone program: pytest exits 5 with no collected tests. The separate comprehensive reconciliation suite passes 12 tests. A zero-test invocation must not be counted as a pass.

### 4. Repository gates need an explicit completion plan

Neither `main` nor the active branch has branch protection; no repository rulesets exist. The written review/test gates therefore lack equivalent GitHub enforcement.

[PR #9](https://github.com/Lesram/intraday/pull/9) remains a draft spanning 452 commits and 1,560 files, with no submitted reviews. Its latest recorded organism/config/spec-drift/secret-scan checks pass, but Bandit, frontend npm audit and Quality Summary fail. Those three cleanup items are explicitly parked by AGENTS.md and were not reopened here. Seven PRs remain open overall.

The [July 29 verification artifacts](https://github.com/Lesram/intraday/actions/runs/30430956736) are currently downloadable, with scheduled expiry October 27, and include the required pack and audit index. Their SHA `08f3421` matches PR #9's merge ref; they are legitimate historical evidence, not September runtime verification.

GitHub-hosted deployment is not established: no repository Actions secrets/variables, deployment records or self-hosted runners were found. Local Docker operation is independently verified. No staging or deployment write was attempted. The CLI credential lacks `admin:repo_hook`; declared repository admin access does not establish every settings operation.

### 5. Security and configuration hygiene need bounded follow-up

An [open secret-scanning alert](https://github.com/Lesram/intraday/security/secret-scanning/1) points to a Stripe-shaped value in historical redaction tests and committed JUnit reports. Validity is unknown and the location suggests a possible synthetic fixture. This is not a confirmed usable credential leak; triage the alert without reproducing its value. Secret scanning and push protection are enabled; Dependabot alerts/security updates are disabled.

The active `.env` is ignored by Git. API port 8000 and PostgreSQL port 5432 are bound to all host interfaces; Redis is loopback-only. External reachability was not probed. Any binding changes require a deliberate deployment/configuration task.

Development declarations have gaps despite the consistent lockfile installation, including missing `pytest-xdist` and optional development tools. Git commits work, but identity is inferred from the local machine rather than explicitly configured; confirm the desired author email before future implementation commits. Existing Codex hook files invoke system Python and use tool-name matchers whose execution was not demonstrated in this session. Critical checks were run explicitly rather than assuming hooks enforced them.

## Where the strategy stands today

The July handoff's single forward trade is obsolete. Direct inspection of local records finds:

| Measure | September 19 finding |
|---|---:|
| Closed trades after freeze | 27 across 7 sessions |
| Latest close | September 17 |
| Recorded forward PnL | +$84.92 |
| Net under current 3 bps round-trip model | +$69.90 |
| Eligible momentum trend/high-vol trades | 24 across 6 sessions |
| Formal gate | INSUFFICIENT: 24/60 to first look |
| Lifetime ledger PnL | -$588.39, matching rounded manifest PnL |
| Strategy evidence events | 108,926 through September 17 |

No interim test statistic was computed. August 3 contributed +$102.89 after modeled cost, exceeding the entire forward book's net gain; the other sessions combined lost money. Positive recent PnL is not a demonstrated edge.

The 27 rows are labelled `db_fill`, with positive quantities, finite values and no duplicated symbol/close identity. Those are local record checks, not an independent historical broker-fill reconciliation. All map to momentum under the current gate; three low-volatility trades are excluded. The manifest has 609 trades while the CSV has 610 records; dollar totals reconcile, but the count difference needs explanation.

The retracement shadow now has exactly one matching row for each of the 26 closes after its activation. The absent July 27 row predates the known fix. Eight shadow rows triggered, with aggregate reported gross delta about **-$1.15**. There is no current support for switching exits from these observations.

Shadow `real_pnl_gross` is calculated from observed quotes and stored quantities, not reconciled fills. It differs from ledger PnL by more than two cents in 24 of 26 matched rows; quantities differ in five. Treat it as a quote-based policy comparison until reconciled. The July research brief also specifies at least 3 bps **per side**, whereas the running environment/helper uses 3 bps **round trip**. At 6 bps round trip, the forward book is +$54.89; the protocol still needs one explicit, consistent definition.

The existing research plan prioritizes frozen momentum evidence and an ORB-at-scale memo. Prior mean-reversion, confidence-sizing, ML and pyramiding findings should be consulted before repeating abandoned experiments. `scripts/research/` currently contains only its README; the proposed next research memo was not found.

## Validation and limits

Fresh checks used an archived copy of source SHA `4a8e0e7`, the existing project Python environment and an OS sandbox denying network, writes to the real repository, and reads of the real `.env`/brain. This prevents test traffic or telemetry from contaminating the running paper system.

- **313 backend tests passed** across 12 runnable files, including organism behavior, state, safety, sizing/evolution, replay, order integrity, reconciliation and configuration.
- **134 frontend tests passed**, with both TypeScript checks and production build passing.
- The additional legacy reconciliation invocation collected zero tests and exited 5; this is a documented verification gap.
- Local and running-image freeze comparisons passed. Current runtime configuration snapshots were generated; authenticated in-memory organism fields remain unavailable. The existing nine-key documentation/defaults/manifest drift check also passed; that limited check is not a substitute for authenticated in-memory inspection.
- The isolated full artifact pack completed in 209 seconds: six standard suites, replay, 20 semantic-invariant tests, grep assertions and the specification check passed. Its snapshots describe the test environment. Current runtime snapshots were generated separately, and the audit index was regenerated.
- The full historical backend suite was not rerun. July's documented baseline failures are not reclassified as fixed. Browser login, order placement, historical broker reconciliation, restore drills and deployment failover are outside the verified coverage.

Generated pack results, direct test exit codes and generator failure-injection evidence are retained separately in the accompanying artifacts. A generated pack's exit status alone is not acceptance evidence.

## Ordered resumption plan

1. **Establish reliable oversight:** map the active branch and deployed image to scheduled checks; fix artifact failure reporting; make failure reporting survive a failed/timed-out suite; configure an approved alert destination. Keep the parked CI trio separate.
2. **Complete access and recovery:** configure application credentials locally; sign in to Claude if retaining the documented split; validate backup freshness and a restore in isolation; confirm Docker login/recovery behavior and investigate the historical logging gap.
3. **Reconcile the evidence:** compare post-freeze records to broker fills, explain the one-record count difference, qualify shadow prices/quantities, and settle the cost protocol. Preserve the existing forward corpus.
4. **Resume one research question:** prepare the already proposed ORB-scale experiment with fixed entry/exit/cost/split rules and shadow-only evaluation, while the unchanged momentum strategy continues collecting evidence.
5. **Make the strategy decision from that evidence:** a feed, frozen parameter or decision-path change needs explicit sign-off. A reset now affects 27 accumulated forward closes, including 24 eligible momentum trades, rather than July's one.

Completion of this audit means the access and readiness picture is documented and reviewable. It does not mean the outstanding operational issues are repaired or that a profitable strategy has been established.
