# Runbook — Paper-trading uptime

**Owner:** Marsel · **Added:** 2026-07-23 (ops recovery work order, Task 3)

## The problem this solves

`docker-compose.paper.yml` sets `restart: unless-stopped`, which brings a
container back **only while the Docker daemon is running**. It does nothing when:

- **Docker Desktop itself quits** (update, crash, manual quit), or
- **the Mac reboots / logs out** (Docker Desktop not set to launch at login).

Both happened: the engine was dark **2026-06-27 → 07-06** and **2026-07-08 → 07-23**
(~10 lost sessions). No compose policy can survive those — something outside Docker
has to start Docker.

## The fix — three layers

1. **Docker Desktop starts at login** (Docker's own setting).
2. **Login LaunchAgent** (`com.intra.paper`): waits for the Docker daemon, then
   `docker compose -f docker-compose.paper.yml up -d`.
3. **Optional hourly watchdog** (`com.intra.paper.watchdog`): if Docker is up but
   `intra-api-1` is not, bring it back.

## One-time install  ← DECISION ITEM (Marsel runs these)

These need your user session; Claude Code cannot tick the Docker GUI setting or
load a LaunchAgent into your login context.

**a) Docker Desktop → Settings → General → ✅ "Start Docker Desktop when you sign in".**

**b) Install the login LaunchAgent:**

```bash
cp ops/launchd/com.intra.paper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.intra.paper.plist
```

**c) (Optional) install the hourly watchdog:**

```bash
cp ops/launchd/com.intra.paper.watchdog.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.intra.paper.watchdog.plist
```

**d) Prevent sleep from pausing the container while plugged in:**
System Settings → Displays → Advanced → "Prevent automatic sleeping on power
adapter when the display is off", **or** run `caffeinate -s` in a terminal during
trading hours.

## Daily use

```bash
make paper-status     # containers + brain-save freshness + last trade row
make paper-up         # launch Docker (if needed) + bring the stack up
make paper-watchdog   # one-shot: restart api if Docker is up but it isn't
```

`make paper-status` flags a stale brain save (`manifest.saved_at` age > 15 min)
and shows `.save_complete` — a `.save_complete` older than today means full saves
are being gated (see the bounded-skip fix, work order Task 1).

## Recovery one-liners for the two observed failure modes

- **Docker Desktop was quit / Mac rebooted, container gone:**

  ```bash
  make paper-up
  ```

- **Docker is running but `intra-api-1` is missing (crash, OOM):**

  ```bash
  make paper-watchdog
  ```

## Verifying it works (simulated outage)

1. `make paper-status` → all three containers `Up`.
2. Quit Docker Desktop (or reboot). With the login setting + LaunchAgent in place,
   Docker relaunches at login and the LaunchAgent runs `up -d`.
3. `make paper-status` → containers back, `manifest.saved_at` fresh — **no manual
   action taken.**

Logs: `logs/paper_boot.log`, `logs/paper_watchdog.log`.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.intra.paper.plist
launchctl unload ~/Library/LaunchAgents/com.intra.paper.watchdog.plist   # if installed
rm ~/Library/LaunchAgents/com.intra.paper.plist ~/Library/LaunchAgents/com.intra.paper.watchdog.plist
```
