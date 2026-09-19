# Paper monitoring access and Monday acceptance

The dedicated `paper_monitor` account is for operational inspection. It is not a trading user. Existing user accounts and credentials are retained.

## Access boundary

The new protected endpoints are GET requests under `/api/v1/paper-monitor/`:

- `organism/status`: the running engine and scheduler state.
- `deploy`: source, image, migration and configuration identity.
- `data-integrity`: existing accounting diagnostics.
- `edge`: existing research diagnostics; this is not strategy promotion.

These routes require `paper_monitor` or `admin`, plus `ALPACA_PAPER=true` and the exact paper broker base URL. A monitor JWT is centrally restricted to those four GET routes, its own auth profile, and logout. It cannot call legacy position/order mutation endpoints, even if a legacy route requires only authentication. Socket.IO, market-data WebSocket and scanner WebSocket access is denied for this role. Existing administrative and trader permissions remain unchanged.

Provision the dedicated role through the application's user repository using a fresh random password. Do not reset another user's account or grant the monitor administrator/trader roles. Local credentials belong outside the repository in a user-only file (mode `0600`). The September setup uses `~/Library/Application Support/Intra/paper-observer.json`; never copy it into a report, environment committed to Git, or Actions secret for test jobs.

Set `INTRA_API_CREDENTIALS_FILE` to that private JSON file when running the runtime snapshot generator. Its keys are `username` and `password`. The generator refuses group/world-readable files and sends bearer credentials through its HTTP library rather than a process command line. Existing explicit `INTRA_API_USER` / `INTRA_API_PASSWORD` configuration remains supported.

The paper compose file publishes API and PostgreSQL ports only on loopback. Docker-internal service communication is unchanged. Remote workstation access would require an explicit separately reviewed network path.

## Before the next market open

The paper broker calendar confirms Monday, September 21, 2026 opens at 06:30 PDT and closes at 13:00 PDT. Before the open:

1. Confirm the watchdog status is healthy, Docker and all three paper containers are running, and public readiness succeeds.
2. Authenticate as the monitoring account and verify running image/source identity and paper broker mode. A 200 public health response alone does not satisfy this check.
3. Verify the unchanged decision-surface freeze, including the existing IEX data context. Do not reset the clock as part of operational recovery.
4. Confirm a fresh database dump and brain snapshot, and retain the successful isolated restore rehearsal.
5. Confirm the market-data connection, no unexpected pending orders/overnight exposure, and alert delivery. Preserve order evidence; do not inject test orders into the forward strategy corpus.
6. Use broker-reconciled fill evidence for the partial-exit discrepancy report. Original ledger/learner history remains unchanged pending the separately reviewed accounting correction.

An isolated broker/order pipeline test verifies software behavior but cannot prove Monday's market-session execution in advance. Observe the first naturally generated paper order through its broker fill, local reconciliation and exit; then perform the post-close audit. Strategy success is a separate statistical verdict.

## Scheduled verification

The `paper-readiness` PR workflow runs the operational, authentication, configuration, order-safety and recovery tests, verifies the frozen surface, generates the full safety/replay pack, and uploads evidence after failures. It runs for every PR into the active branch so it can be a reliable required check.

Hosted nightly/post-close workflows use no paper credentials. Their immutable source pin and CI results are separate from local runtime health; see `docs/engineering/MONDAY_CI_READINESS.md`. The local watchdog handles container health and relays retained critical/no-channel events with retry and deduplication. Mac notification delivery requires a logged-in session. An off-machine alert channel remains a separate operator choice.
