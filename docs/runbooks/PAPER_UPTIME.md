# Paper-trading uptime

Owner: Marsel. Updated 2026-09-19.

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

It writes the status and event files. `make paper-watchdog` invokes the recovery
wrapper; `make paper-up` invokes Compose and can apply current configuration.
Use those only with the reviewed deployment checkout.

## Local alert delivery

The LaunchAgent enables Mac notifications. A bounded scan of API logs also
detects `CRITICAL`, `ALERT-NO-CHANNELS`, and `ALERT-DELIVERY-FAILED` events.
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

## Installation and maintenance

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
