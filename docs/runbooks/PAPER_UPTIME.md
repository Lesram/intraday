# Paper-trading uptime

Owner: Marsel. Updated 2026-09-21.

Docker Desktop must start at login and the Mac must remain awake on AC power.
The September readiness audit confirmed both settings. User LaunchAgents require
an active login session; they cannot make a powered-off or logged-out Mac trade.

## Startup and bounded recovery

The existing `com.intra.paper` login agent waits for Docker, then starts the
reviewed paper Compose stack. Container restart policies cover crashes while
Docker remains available. The updated `com.intra.paper.watchdog` template runs
at login and every five minutes, and can reopen Docker Desktop.

Each watchdog run checks the daemon, the exact existing PostgreSQL, Redis, and
API containers, their Compose project/service labels, Docker health, and the
loopback API readiness endpoint. It can start a stopped known container or
restart an unhealthy one. A missing or unverified dependency requires operator
review; the watchdog does not create replacement containers or apply Compose
configuration. A responding API that reports an upstream readiness failure is
reported for attention without an API restart.

Recovery touches at most one container per run, in dependency order. Restarts
allow 60 seconds for shutdown and at least a minute for startup. A durable
15-minute cooldown prevents repeated recovery attempts. Corrupt cooldown state
blocks recovery. Concurrent watchdog runs are excluded by a file lock.

From the installed repository, a check without recovery or notifications is:

```sh
./venv/bin/python -B scripts/ops/paper_watchdog.py
```

Add `--check-backups` to include the read-only backup checks described below.
Without this option, the command does not access backup directories.
Add `--check-policy` for the authenticated, read-only policy and scheduler check.
Without this option, it does not read the private daily-evidence binding or
observer credentials.
It writes the status and event files. `make paper-watchdog` invokes the recovery
wrapper; `make paper-up` invokes Compose and can apply current configuration.
Use those only with the reviewed deployment checkout.

## Local alert delivery

The LaunchAgent enables Mac notifications. A bounded scan of API logs also
detects explicit uppercase `CRITICAL`, structured critical severity, and
`ALERT-NO-CHANNELS`/`ALERT-DELIVERY-FAILED` events. Informational prose about
critical tables or zero critical failures is ignored.
Notifications contain a count and a request to inspect application logs. The
watchdog retains only hashes, counts, and timestamps from those events; it does
not copy private alert payloads into its report.

Undelivered counts survive notification and log-read failures and are retried
on later runs. The first scan covers the previous 15 minutes; subsequent scans
use the last successful cursor. Each scan is limited to 1,000 lines and 256 KiB
of processed text. An unavailable or truncated log window makes status unhealthy
and requests attention. This bridge cannot guarantee delivery of events outside
that window. Docker health and critical-log checks do not verify trading
reconciliation or broker fills.

Durable evidence lives in:

- `logs/paper_watchdog_status.json`: current probes, recovery cooldown, notification outcome.
- `logs/paper_watchdog_events.jsonl`: one record per completed invocation.
- `logs/paper_boot.log`: login startup output.

A successful notification command confirms macOS accepted the request, not that
the operator saw it. Verify visible delivery after installation, including the
Mac's notification permissions and Focus settings. No external alert destination
is configured by this repair.

## Backup health alerts

The reviewed LaunchAgent also enables `--check-backups`. It inspects the latest
published brain archive and private PostgreSQL dump, validates their receipts
and file checksums, and reports missing, malformed, corrupted, or stale backups.
An invalid latest publication is reported even when an older valid one exists.
The age limit is 26 hours from receipt creation, allowing two hours beyond the
daily schedule. The source brain's `saved_at` does not need to advance while
markets are closed.

The combined brain/PostgreSQL check shares a ten-second elapsed-time budget
and a maximum of 512 MiB of hashed data. It also allows at most
1,024 brain files, 4,096 entries per directory search/archive walk, and 1 MiB per
metadata file. A limit reached is reported as a monitoring failure rather than
healthy status. The monitor reads regular files only and rejects symbolic links;
it never loads model files as executable objects.

Backup problems appear in `backup_monitor` and `problems` in the same durable
status and event log. They use the same local notification deduplication and
failed-delivery retry as service problems, including when a critical application
alert arrives at the same time. These checks never start, stop, recreate, delete,
or restore anything. A successful check validates the archive bytes, not database
restore semantics; retain the separate restore rehearsal.

## Installation and maintenance

The reviewed LaunchAgent also enables `--check-policy`. It uses the private
daily-evidence release binding and dedicated observer account described in
[PAPER_DAILY_EVIDENCE.md](PAPER_DAILY_EVIDENCE.md). It checks the approved
source/image/configuration identity, exact effective parameters, locked risk
modes, and configured/verified retained-model baseline hash. It additionally
requires the scheduler to be running and the engine to be initialized: Docker
health and `/readyz` can remain healthy after a rejected engine startup.

This probe uses only local observer login, two local GET routes and read-only
Docker identity inspection. It neither obtains broker credentials nor calls the
broker, and never loads executable model files. A missing/corrupt binding,
observer failure, identity mismatch or stopped scheduler produces a sanitized
`policy_*` problem in `policy_monitor` and the existing status/notification path.
No exception body, credential or token is persisted. These problems never cause
an otherwise healthy API to restart. Existing bounded service recovery remains
separate; a policy failure requires operator investigation. The check confirms
current reported startup identity, not broker-fill reconciliation, continuous
model attestation, completed-session evidence or profitability.

Install the reviewed private binding and observer credentials before enabling
the updated agent. The probe rechecks the binding after collection; a concurrent
binding replacement blocks the observation instead of certifying mixed releases.

Apply the reviewed code to `/Users/marselkei/VS/intra` before loading the templates;
they deliberately refer to that checkout and its Python 3.12 virtual environment.
Create `logs/` first. For an already installed watchdog, replace its user agent:

```sh
mkdir -p logs "$HOME/Library/LaunchAgents"
launchctl bootout "gui/$(id -u)/com.intra.paper.watchdog"
cp ops/launchd/com.intra.paper.watchdog.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.intra.paper.watchdog.plist"
```

If the service is not loaded, omit `bootout`. Bootstrap runs it immediately.
Inspect status and perform the visible notification check before relying on it.
Do not simulate an outage by stopping the active paper stack during a session.
The mocked regression tests cover stopped services, daemon failure, startup grace,
cooldown, and notification retry without touching the running containers.

Before an intentional stop, create `logs/paper_watchdog.pause`. It suppresses
recovery and notifications while preserving probes. Remove it after maintenance
and review the next status. The login startup agent is separate; if maintenance
spans a logout/reboot, unload it as well. Restore its registration afterward.

Backup schedules, verification, and recovery boundaries are in
[PAPER_BACKUP_RECOVERY.md](PAPER_BACKUP_RECOVERY.md).
