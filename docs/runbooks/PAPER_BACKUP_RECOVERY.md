# Paper backup and recovery

Owner: Marsel. Added 2026-09-19. Commands run from the installed repository.

## PostgreSQL

`scripts/runtime/backup/paper_database.py` takes a fresh custom-format `pg_dump`
from the existing label-verified paper database. It checks the archive catalog
before publishing a timestamped dump and SHA-256 receipt. Dump and receipt files
are private (mode 0600), under
`~/Library/Application Support/Intra/backups/postgres/`. The default retention
is 30 successful dumps. A failed dump does not prune prior backups.

```sh
./venv/bin/python -B scripts/runtime/backup/paper_database.py
```

`ops/launchd/com.intra.postgres-backup.plist` runs at login and daily at 16:45 in
the Mac's local timezone, currently Pacific. The archive check verifies structure;
it is not a restore test. Run the following separately with a selected dump:

```sh
./venv/bin/python -B scripts/runtime/backup/paper_database.py --verify-restore '/absolute/path/to/paper-postgres-TIMESTAMP.dump' --report '/absolute/path/to/restore-verification.json'
```

This creates a fresh disposable PostgreSQL container using the source container's
cached immutable image. It has no network, published ports, or host mounts; data
lives in temporary memory-backed storage. The command restores the archive,
compares all public tables with its catalog, counts rows, and checks validated
constraints. Cleanup selects only the newly generated name and unique ownership
label, including on a failed restore. A successful report requires both restore
verification and cleanup. It never restores into the paper database.

The database dump contains private application data. Keep it outside Git and do
not attach it to a PR. A restore report contains table names and aggregate row
counts, without rows or credentials. Keep receipts beside their dumps so later
verification can also detect a checksum mismatch.

## Brain snapshots

`scripts/runtime/rotate_brain_backup.py` takes a shared lock against the engine's
existing brain-save lock. It requires valid manifest and learning metadata, a
nonempty save-completion marker, and the model files declared by a trained head.
A busy save defers the backup with a failure exit; a missing or incomplete brain
also fails. Neither case prunes existing archives.

The script copies into staging, rejects symbolic links, verifies metadata and
every copied file's SHA-256/size, then atomically publishes an immutable UTC
timestamped directory under `organism_brain_archive/`. Login and post-close runs
on the same day capture separate snapshots. The default retention is 30 days.
Nested engine backups and lock files are excluded. Hash checks detect corruption;
they do not authenticate a backup from an untrusted source.

```sh
./venv/bin/python -B scripts/runtime/rotate_brain_backup.py --keep 30
./venv/bin/python -B scripts/runtime/rotate_brain_backup.py --verify 'organism_brain_archive/TIMESTAMP'
./venv/bin/python -B scripts/runtime/rotate_brain_backup.py --verify 'organism_brain_archive/TIMESTAMP' --restore-to '/absolute/path/to/a-new-isolated-directory'
```

Verification does not deserialize or execute model files. `--restore-to` refuses
existing destinations and the live brain tree. It verifies the isolated copy;
it does not switch the application's mounted state. Older date-only archives
without `backup_manifest.json` do not satisfy this new verification contract.

`scripts/runtime/com.intra.brain-backup.plist` runs at login and daily at 16:30
local time, currently Pacific. `source_saved_at` remains available in each receipt
for engine-state investigation. Watchdog backup freshness uses archive creation
time, so an unchanged brain during closed markets does not create a false alert.

## Engine brain saves: crash recovery and integrity

Added 2026-10-05 (audit C12), updated after its review. A full brain save stages
the whole new generation in `organism_brain/.tmp_save/`, then writes
`.brain_swap_journal.json` before it replaces any HEAD file. The journal records
the staged files (name, size, SHA-256) and the size and SHA-256 of every HEAD file
the swap will replace or delete. Files are renamed over their old versions, so a
file present in both generations is never missing. The new generation's file list
is written into `.save_complete`, and then the journal is removed.

A crash during the swap leaves the journal. The next load or save handles it in
one of three ways:

- Rolled forward (`C12-01 (...) rolled forward`, WARNING): HEAD still holds only
  the old or the staged version of every file the swap touches, so the swap is
  completed.
- Stale (`C12-01 (...) STALE full-save swap journal`, CRITICAL): something wrote
  HEAD after the journal, so HEAD holds newer state than the staged generation.
  The writer is either pre-fix code after a rollback or a write outside a save.
  The signal is a changed HEAD file, a new brain-owned file, or a timestamp
  `.save_complete`, which only pre-fix code writes. HEAD is kept as it is and
  the journal is retired. The engine's next brain save is a full save, which
  rewrites every brain-owned file.
- Cannot be completed (`C12-01 (...) cannot be completed`, CRITICAL): a staged
  copy that is still needed, or an already published file, is missing or altered.
  Load uses the newest complete engine backup. The journal stays until the next
  full save replaces it with its own, so a crash before then is still detected.

Before a journal is retired or replaced, the evidence is kept in
`organism_brain/corrupt_head_<timestamp>_swap_journal/`. It holds the journal,
`REASON.txt`, `staged/` (the staged generation), and `head/` (copies of HEAD's
brain-owned files). Like the other `corrupt_head_*` snapshots, it is kept across
saves, excluded from the host archive, and pruned to the newest five.

A HEAD or engine backup whose `.save_complete` lists a missing file is never
loaded with that state empty. The same applies when a listed model, cache, or
ensemble pickle is unsigned or torn (truncated). The log line is
`C12-01: brain generation ... is incomplete` (CRITICAL). The newest complete
backup is used, or startup has no brain. Engine backups are copied to
`backups/.partial_*` and renamed only when complete. A HEAD that a restart would
reject is never copied into `backups/`, so it cannot push out a good backup.

After a backup fallback, the engine's next brain save is a full save, even when
the walk-forward gate blocks (`taking a gated full save`, WARNING). The same
happens with a pending or retired journal, or a HEAD that fails its inventory.
An essential save cannot repair such a HEAD and reports `Essential brain save NOT
persisted` (ERROR) instead.

Essential saves take the brain lock, run only after an interrupted swap was
completed or retired, and do not rewrite model files that have not changed. A
save that did not happen is not reported as one. Each failure logs `BRAIN SAVE
NOT PERSISTED` (ERROR) and does not advance the brain-save watchdog. Every third
consecutive failure logs `BRAIN SAVES FAILING REPEATEDLY` (CRITICAL), which the
paper watchdog notifies. Check disk space, permissions, and other holders of
`organism_brain/.brain.lock`. The engine's standalone exit-level write settles a
pending journal before it touches `extra_counters.json`.

Every model and cache pickle the engine writes is HMAC-signed. An unsigned or
torn pickle is never unpickled (`C12-04: refusing to deserialize unsigned or
torn ...`, CRITICAL). If a generation's `.save_complete` lists it, load falls back
to the newest complete backup, as for a missing file. In a brain without that
list (last saved by older code), an unsigned main model also falls back. An
unsigned cache or ensemble file is skipped like a missing one, and with the
approved baseline configured, startup is held. Restore a signed copy from
`backups/` or a verified archive. Do not re-create the file with plain `joblib`
or `pickle`.

### Before deploying an image: unsigned-pickle check

`scripts/ops/check_brain_pickles_signed.py` is read-only. It does not unpickle
anything and needs no signing secret. It reports every model, cache, or ensemble
pickle that is unsigned or torn in HEAD, in `backups/brain_gen*`, and in the
newest host archive snapshot (every snapshot with `--all-archives`). Pickles the
engine never loads, such as `previous_model/*.pkl`, are listed for information
only. Exit status 0 means every loaded pickle is signed, 1 means at least one is
unsigned or torn, and 2 means a location could not be read. The archive is not
mounted in the container, so check it on the host:

```sh
docker compose -f docker-compose.paper.yml exec api python scripts/ops/check_brain_pickles_signed.py
./venv/bin/python -B scripts/ops/check_brain_pickles_signed.py --brain-dir organism_brain --archive-dir organism_brain_archive
```

Do not switch images until both runs exit 0. Fix a failure by restoring a signed
copy, not by re-pickling.

### Rolling back to code older than the C12 fix

A brain saved by the fixed code loads with older code (ee023515 and earlier).
Older code ignores `.brain_swap_journal.json`, though. Never start older code on
a brain that holds one:

1. Stop the API with its normal 60-second grace and check whether
   `organism_brain/.brain_swap_journal.json` exists.
2. If it exists, start the fixed image once, wait for `Brain loaded`, and stop it
   gracefully. That load completes or retires the interrupted swap, and the
   shutdown save writes a complete generation. If the fixed image cannot start,
   restore a verified archive into the brain directory instead (see "Live
   recovery boundary").
3. Confirm the journal is gone, then deploy the older image. If it is still
   there, restore a verified archive instead of rolling back onto it. That
   happens when startup was held or the swap could not be completed.

If older code did run on a brain with a journal and the fixed code is deployed
again, the fixed code refuses the stale journal (`STALE`, CRITICAL). It keeps the
state the older code wrote and stores a forensic copy. Review that copy, then
rely on the next full save.

## Installing and checking schedules

Apply the reviewed scripts to `/Users/marselkei/VS/intra` and ensure `logs/`
exists. Copy the two templates to `~/Library/LaunchAgents/`, replacing the loaded
brain agent with `launchctl bootout gui/UID/com.intra.brain-backup` first. Use
`launchctl bootstrap gui/UID PATH_TO_PLIST` for each template, substituting the
current numeric user ID. Both run immediately at bootstrap.

Check each job's exit status and the new receipts afterward. Logs are
`logs/brain_backup.log` and `logs/postgres_backup.log`. These schedules require a
logged-in, awake Mac and available Docker for the database job. Failed jobs are
visible in their logs and launchd exit status. The watchdog's `--check-backups`
option, enabled in its reviewed LaunchAgent, checks the latest publication's
receipt/checksums and sends a local notification if it is missing, malformed,
corrupted, or older than 26 hours. An invalid latest publication is not hidden
by an older valid archive. Checks are read-only and bounded; exceeding a check
limit is itself an alert. See [Paper uptime](PAPER_UPTIME.md#backup-health-alerts)
for the limits and durable status files.

This detects unusable or overdue backups, not every failed scheduled attempt
while a valid recent backup exists. After a busy-lock or startup failure, inspect
the logs and rerun the backup when the dependency is ready instead of assuming
a new receipt. Backup alerts do not trigger automatic recovery or deletion.

## Live recovery boundary

Use the isolated commands above for rehearsals. A real recovery first needs a
reviewed recovery point, a fresh preservation copy of the current state,
maintenance pause for the watchdog, and a controlled stop of the API with its
60-second shutdown grace. Database and brain state must be reconciled with paper
broker positions before resuming. Do not overwrite a mounted brain or restore
SQL over the running application as a verification step.

The older `scripts/backup/rehearsal.py` contains a placeholder verification path;
its success is not restore evidence. Use the actual isolated PostgreSQL restore
command and the brain checksum/copy verification described here.
