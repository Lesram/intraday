# Brain backup installation

The current installation, verification, and recovery instructions are in
[Paper backup and recovery](../../docs/runbooks/PAPER_BACKUP_RECOVERY.md).

The revised script creates an immutable timestamped snapshot on every successful
run, verifies required metadata and per-file checksums, and retains 30 days by
default. The LaunchAgent runs at login and daily at 16:30 Mac local time. A busy
brain-save lock or incomplete source fails without pruning prior archives.

Same-day runs capture new state. Older date-only archives without checksum
receipts need separate inspection; they are not verified by the new command.
Recovery rehearsals copy only into a new isolated directory and never replace
the mounted live brain.
