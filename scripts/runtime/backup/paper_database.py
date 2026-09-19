"""Private PostgreSQL backups and a real restore into an isolated disposable DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid


SOURCE_CONTAINER = "trading_platform_db_paper"
DEFAULT_DIR = Path.home() / "Library" / "Application Support" / "Intra" / "backups" / "postgres"
RESTORE_DATABASE = "intra_restore_check"


def execute(args: list[str], *, timeout: int = 30, stdin=None, stdout=None) -> str:
    completed = subprocess.run(args, stdin=stdin, stdout=stdout or subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=timeout, check=False)
    if completed.returncode:
        # pg_restore errors may contain COPY data. Never expose stderr or SQL
        # data in console output / shareable reports.
        raise RuntimeError(f"{args[0]} operation failed (exit {completed.returncode})")
    return completed.stdout.decode() if completed.stdout else ""


def source_info() -> dict:
    data = json.loads(execute(["docker", "inspect", SOURCE_CONTAINER]))[0]
    labels = data.get("Config", {}).get("Labels") or {}
    if (data.get("Name", "").lstrip("/") != SOURCE_CONTAINER
            or labels.get("com.docker.compose.project") != "intra"
            or labels.get("com.docker.compose.service") != "postgres"):
        raise ValueError("refusing an unverified paper database container")
    env = dict(item.split("=", 1) for item in data["Config"].get("Env", []) if "=" in item)
    if not env.get("POSTGRES_USER") or not env.get("POSTGRES_DB"):
        raise ValueError("database identity is missing")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", data.get("Image", "")):
        raise ValueError("database image must resolve to a local immutable image")
    return {"user": env["POSTGRES_USER"], "database": env["POSTGRES_DB"], "image": data["Image"]}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_tables(path: Path, container: str = SOURCE_CONTAINER) -> list[str]:
    with path.open("rb") as source:
        catalog = execute(["docker", "exec", "-i", container, "pg_restore", "--list"], stdin=source)
    tables = []
    for line in catalog.splitlines():
        match = re.match(r"^\d+; \d+ \d+ TABLE public ([A-Za-z_][A-Za-z0-9_]*) \S+$", line)
        if match:
            tables.append(match.group(1))
    if not tables or "users" not in tables:
        raise ValueError("archive does not contain the expected application schema")
    return sorted(tables)


def make_backup(directory: Path, keep: int = 30) -> dict:
    if keep < 1:
        raise ValueError("retention must be positive")
    identity = source_info()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"paper-postgres-{timestamp}.dump"
    descriptor, name = tempfile.mkstemp(prefix=".paper-postgres-", dir=directory)
    staging = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            execute(["docker", "exec", SOURCE_CONTAINER, "pg_dump", "-U", identity["user"],
                     "-d", identity["database"], "--format=custom", "--no-owner", "--no-acl"],
                    timeout=180, stdout=output)
        if staging.stat().st_size == 0:
            raise ValueError("backup was empty")
        tables = archive_tables(staging)
        report = {"created_at": datetime.now(timezone.utc).isoformat(), "path": str(target),
                  "sha256": sha256(staging), "bytes": staging.stat().st_size,
                  "tables": tables, "source_container": SOURCE_CONTAINER,
                  "source_image": identity["image"], "restore_verified": False}
        staging.rename(target)
        receipt = target.with_suffix(".json")
        with receipt.open("x") as output:
            os.chmod(receipt, 0o600)
            json.dump(report, output, indent=2)
        backups = sorted(directory.glob("paper-postgres-*.dump"), reverse=True)
        for expired in backups[keep:]:
            expired.unlink()
            expired.with_suffix(".json").unlink(missing_ok=True)
        return report
    finally:
        staging.unlink(missing_ok=True)


def sql(container: str, query: str) -> str:
    return execute(["docker", "exec", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", RESTORE_DATABASE, "-t", "-A", "-c", query])


def cleanup_restore(name: str, owner: str) -> None:
    matches = execute(["docker", "ps", "-a", "--filter", f"label=intra.restore-owner={owner}",
                       "--format", "{{.Names}}"])
    names = matches.split()
    if any(found != name for found in names):
        raise ValueError("refusing cleanup of unexpected restore container")
    if name in names:
        execute(["docker", "rm", "--force", "--volumes", name], timeout=20)


def verify_restore(path: Path) -> dict:
    """Only create and remove our own new container: no ports, network or mounts."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("backup file is missing or empty")
    identity = source_info()
    checksum = sha256(path)
    metadata = path.with_suffix(".json")
    if metadata.exists() and json.loads(metadata.read_text()).get("sha256") != checksum:
        raise ValueError("backup checksum does not match its receipt")
    owner = uuid.uuid4().hex
    name = "intra-restore-check-" + owner[:12]
    creation_attempted = False
    report = {"backup_sha256": checksum, "backup_bytes": path.stat().st_size,
              "container": name, "network": "none", "host_ports": [], "host_mounts": [],
              "verified": False, "cleanup_succeeded": False}
    try:
        # --pull never and immutable image ID guarantee an offline rehearsal.
        creation_attempted = True
        execute(["docker", "run", "--detach", "--pull", "never", "--name", name,
                 "--network", "none", "--label", "intra.restore-rehearsal=true",
                 "--label", f"intra.restore-owner={owner}",
                 "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,nodev,size=2g",
                 "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", f"POSTGRES_DB={RESTORE_DATABASE}",
                 identity["image"]], timeout=30)
        deadline = time.monotonic() + 30
        while True:
            try:
                execute(["docker", "exec", name, "pg_isready", "-U", "postgres", "-d", RESTORE_DATABASE], timeout=5)
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("isolated database readiness timed out") from None
                time.sleep(1)
        expected_tables = archive_tables(path, name)
        with path.open("rb") as source:
            execute(["docker", "exec", "-i", name, "pg_restore", "--exit-on-error", "--no-owner",
                     "--no-acl", "-U", "postgres", "-d", RESTORE_DATABASE], stdin=source, timeout=180)
        actual_tables = sorted(sql(name, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;").split())
        if actual_tables != expected_tables:
            raise ValueError("restored tables do not match archive catalog")
        counts = {}
        for table in actual_tables:
            # Names must first match the strictly parsed archive table list.
            counts[table] = int(sql(name, f'SELECT count(*) FROM public."{table}";').strip())
        invalid = int(sql(name, "SELECT count(*) FROM pg_constraint WHERE NOT convalidated;").strip())
        if invalid:
            raise ValueError("restored database contains unvalidated constraints")
        report.update({"verified": True, "table_count": len(actual_tables), "rows_by_table": counts,
                       "unvalidated_constraints": invalid, "source_image": identity["image"]})
    finally:
        if creation_attempted:
            # Exact fresh name; never source container, compose services, or a
            # caller-supplied cleanup target. Include -v for anonymous volumes.
            cleanup_restore(name, owner)
            report["cleanup_succeeded"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--verify-restore", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = verify_restore(args.verify_restore) if args.verify_restore else make_backup(args.directory, args.keep)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report = {"verified": False, "error": str(exc)}
        result = 1
    else:
        result = 0
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
