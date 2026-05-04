# Brain backup rotation — install guide

Per AGENTS.md P1 real-money blocker. The brain is host-volume-mounted into the live container, so a corrupted save propagates instantly with no historical recovery path. This rotation gives a 30-day rolling archive.

## Files

- `scripts/runtime/rotate_brain_backup.py` — the script. Python 3.12, no extra deps.
- `scripts/runtime/com.intra.brain-backup.plist` — macOS launchd user agent (runs the script daily at 4:30 PM local).

## What the script does

- Copies `organism_brain/` → `organism_brain_archive/<YYYY-MM-DD>/` (idempotent — re-runs same day are no-ops).
- Verifies `manifest.json` and `learning_state.json` exist in the snapshot.
- Prunes archive folders older than `--keep` days (default 14, plist uses 30).
- Outputs one summary line: `gen=N, trades=N, pnl=N`.

## Install (macOS — launchd, recommended)

```sh
cp scripts/runtime/com.intra.brain-backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.intra.brain-backup.plist

# Verify it's registered
launchctl list | grep com.intra.brain-backup

# Test-run immediately (without waiting for the schedule)
launchctl kickstart -k gui/$(id -u)/com.intra.brain-backup
```

To uninstall:
```sh
launchctl unload ~/Library/LaunchAgents/com.intra.brain-backup.plist
rm ~/Library/LaunchAgents/com.intra.brain-backup.plist
```

## Install (alternative — cron)

```sh
crontab -e
# add a line:
30 16 * * 1-5 cd /Users/marselkei/VS/intra && ./venv/bin/python scripts/runtime/rotate_brain_backup.py --keep 30 >> logs/brain_backup.log 2>&1
```

(Note: macOS Catalina+ requires Full Disk Access for cron under TCC.)

## Manual usage

Anytime — before risky operations, manual deploys, etc.:

```sh
./venv/bin/python scripts/runtime/rotate_brain_backup.py --keep 30
./venv/bin/python scripts/runtime/rotate_brain_backup.py --dry-run    # preview
```

## Verification (sanity)

After first run, you should see:
```
$ ls organism_brain_archive/
2026-04-25
$ ls organism_brain_archive/2026-04-25/
manifest.json  learning_state.json  ml_classifier.joblib  ...
```

The archive directory is gitignored (it's in `.gitignore` next to `organism_brain/`).

## Recovery

If the live brain becomes corrupted:
```sh
docker-compose down api
mv organism_brain organism_brain_corrupted_$(date +%s)
cp -r organism_brain_archive/2026-04-25 organism_brain
docker-compose up -d --build api
```

## Why no live-engine hook

Considered hooking rotation directly into `live_tick()` post-EOD-flatten. Rejected because:
- Adds risk surface inside the hot tick path for an ops concern
- Mixes strategy code with infrastructure
- Breaks the principle of least surprise (engine code shouldn't write outside `organism_brain/`)

Cleaner separation: the script is the authority; the schedule is ops.
