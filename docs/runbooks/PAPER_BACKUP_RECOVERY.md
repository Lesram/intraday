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

Added 2026-10-05 (audit C12). A full brain save stages the whole new generation
in `organism_brain/.tmp_save/`, then writes `.brain_swap_journal.json` (staged
names, sizes, SHA-256) before it replaces any HEAD file. Files are renamed over
their old versions, so a file present in both generations is never missing. The
new generation's file list is written into `.save_complete`; the journal is then
removed. A crash during the swap leaves the journal, and the next load or save
completes the swap (`C12-01 (...) rolled forward` at WARNING). If a staged file
is missing or altered, the HEAD is rejected (CRITICAL). Load then uses the newest
complete engine backup; a save discards the journal and rewrites every file.

A HEAD or engine backup whose `.save_complete` lists a missing file is never
loaded with that state empty (`C12-01: brain generation ... is incomplete`,
CRITICAL). The newest complete backup is used, or startup has no brain. Engine
backups are copied to `backups/.partial_*` and renamed only when complete. Older
code ignores the journal and reads only whether `.save_complete` exists, so a
brain saved by this code loads after a rollback.

Essential saves take the brain lock, run only after an interrupted swap was
completed, and do not rewrite model files that have not changed. A save that did
not happen is not reported as one. Each failure logs `BRAIN SAVE NOT PERSISTED`
(ERROR) and does not advance the brain-save watchdog. Every third consecutive
failure logs `BRAIN SAVES FAILING REPEATEDLY` (CRITICAL), which the paper watchdog
notifies. Check disk space, permissions, and other holders of
`organism_brain/.brain.lock`.

Every model and cache pickle the engine writes is HMAC-signed. An unsigned
pickle in the brain is never unpickled: it is logged at CRITICAL
(`C12-04: refusing to deserialize unsigned ...`) and treated as missing. With
the approved baseline configured, startup is held. Restore a signed copy from
`backups/` or a verified archive. Do not re-create the file with plain `joblib`
or `pickle`.

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
