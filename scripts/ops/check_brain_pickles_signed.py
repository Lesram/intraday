#!/usr/bin/env python3
"""Read-only pre-deploy check: report unsigned or torn pickles in a brain.

Audit 2026-10-05 C12-04 (review). The engine never deserializes an unsigned
pickle. A model, S17 cache or ensemble file that a generation's
``.save_complete`` inventory lists and that is unsigned or torn (truncated)
makes that generation incomplete, so load falls back to an older backup; in a
brain without an inventory an unsigned main model also falls back, and an
unsigned cache or ensemble file is skipped. Run this before switching images
to confirm that every pickle the engine loads is in the HMAC-signed format.

Checked locations (each is a directory the engine can load a generation from):

* HEAD      ``<brain-dir>/*.joblib``
* backups   ``<brain-dir>/backups/brain_gen*/*.joblib``
* archive   the newest snapshot under ``--archive-dir`` (every snapshot with
            ``--all-archives``); the host archive is not mounted in the
            container, so check it on the host.

Nothing is modified and nothing is unpickled; the signing secret is not
needed: ``backend.utils.secure_pickle.is_signed_pickle`` compares the 4-byte
length header with the file size (the signature itself is verified only when
the engine loads the file). Other pickle files below a location (``*.pkl``,
``*.pickle`` or nested ``*.joblib``, e.g. ``previous_model/clf.pkl``, which the
background trainer's rollback copy writes unsigned) are listed for information
only: the engine never loads them.

An engine-loaded pickle that is a symbolic link is an error: the engine follows
the link, this check does not read through it.

Exit status: 0 every engine-loaded pickle is signed; 1 at least one is unsigned
or torn; 2 a requested location is missing, an engine-loaded pickle is a
symbolic link, or a file could not be read.

Usage:
    docker compose -f docker-compose.paper.yml exec api \\
        python scripts/ops/check_brain_pickles_signed.py
    ./venv/bin/python -B scripts/ops/check_brain_pickles_signed.py \\
        --brain-dir organism_brain --archive-dir organism_brain_archive [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.utils.secure_pickle import is_signed_pickle  # noqa: E402

PICKLE_SUFFIXES = (".joblib", ".pkl", ".pickle")
# Inside a generation directory: never loaded as part of it (checked
# separately, forensic, or transient staging).
_SKIP_DIRS = ("backups", ".tmp_save", ".brain_old", ".brain_ensemble_stage")
_SKIP_PREFIXES = ("corrupt_head_",)


def _skipped(rel: Path) -> bool:
    top = rel.parts[0] if len(rel.parts) > 1 else ""
    return top in _SKIP_DIRS or top.startswith(_SKIP_PREFIXES)


def check_location(kind: str, root: Path) -> dict:
    """Signed-format status of every pickle in one generation directory."""
    result = {
        "kind": kind, "path": str(root), "loaded_checked": 0,
        "unsigned": [], "info_unsigned": [], "errors": [],
    }
    if not root.is_dir():
        result["errors"].append("directory not found")
        return result
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if _skipped(rel) or path.suffix not in PICKLE_SUFFIXES:
            continue
        loaded = len(rel.parts) == 1 and path.suffix == ".joblib"
        if loaded and path.is_symlink():
            # The engine's is_file()/read_bytes() follow a symlink; this check
            # does not, so exit 0 could not vouch for it (C12 review).
            result["errors"].append(
                f"{rel}: symbolic link to {os.readlink(path)} (the engine "
                "follows it; replace it with the regular file)"
            )
            continue
        if path.is_symlink() or not path.is_file():
            continue
        try:
            signed = is_signed_pickle(path.read_bytes())
        except OSError as exc:
            result["errors"].append(f"{rel}: {exc}")
            continue
        if loaded:
            result["loaded_checked"] += 1
            if not signed:
                result["unsigned"].append(str(rel))
        elif not signed:
            result["info_unsigned"].append(str(rel))
    return result


def _archive_snapshots(archive_dir: Path, every: bool) -> list[Path]:
    snapshots = sorted(
        p for p in archive_dir.iterdir()
        if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")
    )
    return snapshots if every else snapshots[-1:]


def run_checks(brain_dir: Path, archive_dir: Path | None, every_archive: bool) -> dict:
    locations = [check_location("head", brain_dir)]
    backups = brain_dir / "backups"
    if backups.is_dir():
        for backup in sorted(backups.iterdir()):
            if backup.is_dir() and backup.name.startswith("brain_gen"):
                locations.append(check_location("backup", backup))
    archive_errors: list[str] = []
    if archive_dir is not None:
        if not archive_dir.is_dir():
            archive_errors.append(f"archive directory not found: {archive_dir}")
        else:
            snapshots = _archive_snapshots(archive_dir, every_archive)
            if not snapshots:
                archive_errors.append(f"no snapshot under {archive_dir}")
            for snapshot in snapshots:
                locations.append(check_location("archive", snapshot))
    unsigned = sum(len(loc["unsigned"]) for loc in locations)
    errors = archive_errors + [
        f"{loc['path']}: {err}" for loc in locations for err in loc["errors"]
    ]
    status = 2 if errors else (1 if unsigned else 0)
    return {
        "status": {0: "ok", 1: "unsigned", 2: "error"}[status],
        "exit_code": status,
        "unsigned_loaded_pickles": unsigned,
        "errors": errors,
        "archive_errors": archive_errors,
        "locations": locations,
    }


def _print_report(report: dict) -> None:
    for loc in report["locations"]:
        label = f"{loc['kind']:<7} {loc['path']}"
        if loc["errors"]:
            print(f"{label}: ERROR {'; '.join(loc['errors'])}")
        elif loc["unsigned"]:
            print(f"{label}: UNSIGNED OR TORN ({len(loc['unsigned'])} of "
                  f"{loc['loaded_checked']}): {', '.join(loc['unsigned'])}")
        else:
            print(f"{label}: {loc['loaded_checked']} loaded pickle(s), all signed")
        for name in loc["info_unsigned"]:
            print(f"        info: {name} is not signed (never loaded by the engine)")
    for err in report["archive_errors"]:
        print(f"ERROR {err}")
    verdict = {
        "ok": "OK: every pickle the engine loads is signed",
        "unsigned": (f"FAIL: {report['unsigned_loaded_pickles']} unsigned or torn "
                     "pickle(s) the engine loads; restore signed copies before deploying"),
        "error": "ERROR: a location could not be checked",
    }[report["status"]]
    print(verdict)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--brain-dir", type=Path,
        default=Path(os.environ.get("ORGANISM_BRAIN_DIR", "organism_brain")),
        help="brain HEAD directory (default: $ORGANISM_BRAIN_DIR or organism_brain)",
    )
    parser.add_argument("--archive-dir", type=Path, default=None,
                        help="host archive root (organism_brain_archive); newest snapshot")
    parser.add_argument("--all-archives", action="store_true",
                        help="check every archive snapshot, not only the newest")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    report = run_checks(args.brain_dir, args.archive_dir, args.all_archives)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
