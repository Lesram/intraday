"""Brain backup rotation — daily snapshot of organism_brain/.

Per AGENTS.md P1 real-money blocker: the live brain is volume-mounted
from the host, so a corrupted save propagates instantly with no
historical recovery path. This script keeps a rolling N-day archive.

Usage:
    python scripts/runtime/rotate_brain_backup.py            # default: daily
    python scripts/runtime/rotate_brain_backup.py --keep 14  # keep 14 days
    python scripts/runtime/rotate_brain_backup.py --dry-run

Behavior:
    - Copies organism_brain/ → organism_brain_archive/<YYYY-MM-DD>/
    - Skips if today's snapshot already exists (idempotent)
    - Optionally prunes archives older than --keep days

Wire-in:
    - GitHub workflow: .github/workflows/paper-postclose-audit.yml
    - Local cron / launchd / scheduler hook
    - Manual: anytime before risky operations
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAIN_DIR = REPO_ROOT / "organism_brain"
ARCHIVE_ROOT = REPO_ROOT / "organism_brain_archive"


def snapshot(today: date | None = None, dry_run: bool = False) -> Path | None:
    today = today or date.today()
    target = ARCHIVE_ROOT / today.isoformat()

    if not BRAIN_DIR.exists():
        print(f"[rotate_brain_backup] {BRAIN_DIR} does not exist — nothing to back up.")
        return None

    if target.exists():
        print(f"[rotate_brain_backup] Target exists ({target}) — skipping (idempotent).")
        return target

    if dry_run:
        print(f"[rotate_brain_backup] DRY RUN — would copy {BRAIN_DIR} → {target}")
        return target

    ARCHIVE_ROOT.mkdir(exist_ok=True)
    shutil.copytree(BRAIN_DIR, target, symlinks=False)

    # Verify essential artifacts present
    manifest = target / "manifest.json"
    learning = target / "learning_state.json"
    if not manifest.exists():
        print(
            f"[rotate_brain_backup] WARNING — manifest.json missing in snapshot {target}"
        )
    if not learning.exists():
        print(
            f"[rotate_brain_backup] WARNING — learning_state.json missing in snapshot {target}"
        )

    # Print a compact summary line
    if manifest.exists():
        try:
            with open(manifest) as f:
                m = json.load(f)
            print(
                f"[rotate_brain_backup] Snapshot OK → {target} "
                f"(gen={m.get('generation')}, "
                f"trades={m.get('total_trades')}, "
                f"pnl={m.get('cumulative_pnl')})"
            )
        except Exception as e:
            print(f"[rotate_brain_backup] Snapshot OK → {target} (manifest read err: {e})")
    else:
        print(f"[rotate_brain_backup] Snapshot OK → {target}")

    return target


def prune(keep_days: int, dry_run: bool = False) -> int:
    """Remove archive folders older than `keep_days`. Returns count pruned."""
    if not ARCHIVE_ROOT.exists():
        return 0
    cutoff = date.today() - timedelta(days=keep_days)
    pruned = 0
    for entry in sorted(ARCHIVE_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        try:
            entry_date = date.fromisoformat(entry.name)
        except ValueError:
            # Not a date-named archive; skip without deleting
            continue
        if entry_date < cutoff:
            if dry_run:
                print(f"[rotate_brain_backup] DRY RUN — would prune {entry}")
            else:
                shutil.rmtree(entry)
                print(f"[rotate_brain_backup] Pruned {entry}")
            pruned += 1
    return pruned


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate organism_brain snapshots")
    parser.add_argument("--keep", type=int, default=14,
                        help="Number of days of archives to retain (default: 14)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without changing the filesystem")
    args = parser.parse_args()

    snapshot(dry_run=args.dry_run)
    pruned = prune(args.keep, dry_run=args.dry_run)
    if pruned:
        print(f"[rotate_brain_backup] Pruned {pruned} old snapshot(s) (keep={args.keep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
