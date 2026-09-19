"""Atomic, validated paper-brain snapshots; never load or execute model files."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
BRAIN_DIR = REPO_ROOT / "organism_brain"
ARCHIVE_ROOT = REPO_ROOT / "organism_brain_archive"
RECEIPT = "backup_manifest.json"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate_brain(path: Path) -> dict:
    if not path.is_dir():
        raise ValueError("brain directory is missing")
    for name in ("manifest.json", "learning_state.json", ".save_complete"):
        item = path / name
        if not item.is_file() or item.is_symlink() or item.stat().st_size == 0:
            raise ValueError(f"incomplete brain: {name} missing or empty")
    manifest = json.loads((path / "manifest.json").read_text())
    learning = json.loads((path / "learning_state.json").read_text())
    if not isinstance(manifest, dict) or not isinstance(learning, dict) or not manifest.get("saved_at"):
        raise ValueError("invalid brain metadata")
    datetime.fromisoformat(manifest["saved_at"].replace("Z", "+00:00"))
    if manifest.get("ml_is_trained"):
        for name in ("ml_classifier.joblib", "ml_regressor.joblib", "ml_state.json"):
            item = path / name
            if not item.is_file() or item.stat().st_size == 0 or item.is_symlink():
                raise ValueError(f"trained brain is missing {name}")
        if not isinstance(json.loads((path / "ml_state.json").read_text()), dict):
            raise ValueError("invalid model metadata")
    return manifest


def inventory(path: Path) -> dict:
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError("backup contains a symbolic link")
        if item.is_file() and item != path / RECEIPT:
            result[str(item.relative_to(path))] = {"sha256": digest(item), "bytes": item.stat().st_size}
    return result


def verify_snapshot(path: Path) -> dict:
    validate_brain(path)
    receipt = json.loads((path / RECEIPT).read_text())
    if not isinstance(receipt, dict) or not isinstance(receipt.get("files"), dict) or not receipt["files"]:
        raise ValueError("snapshot has no file inventory")
    if inventory(path) != receipt["files"]:
        raise ValueError("snapshot file checksum mismatch")
    return receipt


@contextmanager
def source_lock(path: Path):
    # Shared lock matches the engine's existing exclusive flock; read-only
    # open neither truncates the live lock file nor imports organism code.
    with (path / ".brain.lock").open("rb") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("brain save in progress; backup deferred") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in {"backups", ".brain.lock", RECEIPT}}
    ignored.update(name for name in names if name.startswith(("corrupt_head_", ".brain_")))
    return ignored


def snapshot(today: date | None = None, dry_run: bool = False) -> Path:
    instant = datetime.now(timezone.utc)
    if today:
        instant = instant.replace(year=today.year, month=today.month, day=today.day)
    # Startup/catch-up and postclose runs must both capture their current state.
    target = ARCHIVE_ROOT / instant.strftime("%Y-%m-%dT%H%M%S.%fZ")
    if target.is_symlink():
        raise ValueError("snapshot target cannot be a symbolic link")
    if target.exists():
        verify_snapshot(target)
        print(f"Verified existing snapshot: {target}")
        return target
    with source_lock(BRAIN_DIR):
        manifest = validate_brain(BRAIN_DIR)
        if dry_run:
            print(f"Validated source; would snapshot to {target}")
            return target
        ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = Path(tempfile.mkdtemp(prefix=".brain-backup-", dir=ARCHIVE_ROOT))
        try:
            shutil.copytree(BRAIN_DIR, staging, dirs_exist_ok=True, symlinks=True, ignore=_copy_ignore)
            files = inventory(staging)
            receipt = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_saved_at": manifest["saved_at"], "files": files,
            }
            (staging / RECEIPT).write_text(json.dumps(receipt, indent=2) + "\n")
            verify_snapshot(staging)
            # Published timestamped snapshots are immutable.
            if target.exists():
                raise RuntimeError("snapshot target appeared during backup")
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    print(f"Verified snapshot: {target} ({len(files)} files)")
    return target


def restore_copy(source: Path, target: Path) -> dict:
    """Restore into a NEW directory only; never into the mounted live brain."""
    source, target = source.resolve(), target.resolve()
    live = BRAIN_DIR.resolve()
    if target == live or live in target.parents or target in live.parents or target.exists():
        raise ValueError("restore requires a new directory outside the live brain")
    verify_snapshot(source)
    shutil.copytree(source, target, symlinks=True)
    return verify_snapshot(target)


def prune(keep_days: int, dry_run: bool = False) -> int:
    if keep_days < 1:
        raise ValueError("retention must be at least one day")
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
    removed = 0
    if not ARCHIVE_ROOT.exists():
        return removed
    for entry in sorted(ARCHIVE_ROOT.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{6}\.\d{6}Z)?", entry.name):
            continue
        try:
            day = date.fromisoformat(entry.name[:10])
        except ValueError:
            continue
        if day < cutoff:
            if not dry_run:
                shutil.rmtree(entry)
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()
    try:
        if args.keep < 1:
            raise ValueError("retention must be positive")
        if args.restore_to:
            if not args.verify:
                raise ValueError("--restore-to requires --verify SNAPSHOT")
            restore_copy(args.verify, args.restore_to)
            print("Isolated brain copy verified; models were not deserialized.")
        elif args.verify:
            verify_snapshot(args.verify)
            print("Snapshot checksums and required metadata verified.")
        else:
            snapshot(dry_run=args.dry_run)
            removed = prune(args.keep, args.dry_run)
            print(f"Backup succeeded; {removed} expired archive(s) {'eligible' if args.dry_run else 'pruned'}.")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"BACKUP FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
