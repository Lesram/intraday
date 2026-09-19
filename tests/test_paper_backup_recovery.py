"""Atomic backups and real restore command contracts using isolated fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem + "_test", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def brain(tmp_path, monkeypatch):
    module = load("scripts/runtime/rotate_brain_backup.py")
    source = tmp_path / "brain"
    source.mkdir()
    (source / ".brain.lock").touch()
    (source / ".save_complete").write_text("2026-09-19T18:00:00Z")
    (source / "manifest.json").write_text(json.dumps({"saved_at": "2026-09-19T18:00:00Z", "ml_is_trained": False}))
    (source / "learning_state.json").write_text('{"generation": 1}')
    (source / "trade_history.csv").write_text("symbol,pnl\nAAPL,1\n")
    monkeypatch.setattr(module, "BRAIN_DIR", source)
    monkeypatch.setattr(module, "ARCHIVE_ROOT", tmp_path / "archive")
    return module


def test_snapshot_is_validated_and_restores_to_new_directory(brain, tmp_path):
    target = brain.snapshot()
    assert target.name.startswith(brain.datetime.now(brain.timezone.utc).date().isoformat() + "T")
    receipt = brain.verify_snapshot(target)
    restored = tmp_path / "restore-copy"
    assert brain.restore_copy(target, restored) == receipt
    assert (restored / "trade_history.csv").read_bytes() == (brain.BRAIN_DIR / "trade_history.csv").read_bytes()
    assert not (target / ".brain.lock").exists()
    assert not list(brain.ARCHIVE_ROOT.glob(".brain-backup-*"))
    assert brain.snapshot() != target


@pytest.mark.parametrize("missing", ["manifest.json", "learning_state.json", ".save_complete"])
def test_incomplete_source_never_publishes_snapshot(brain, missing):
    (brain.BRAIN_DIR / missing).unlink()
    with pytest.raises(ValueError, match="incomplete"):
        brain.snapshot()
    assert not brain.ARCHIVE_ROOT.exists()


def test_trained_brain_requires_model_files(brain):
    (brain.BRAIN_DIR / "manifest.json").write_text('{"saved_at":"2026-09-19T18:00:00Z","ml_is_trained":true}')
    with pytest.raises(ValueError, match="ml_classifier"):
        brain.snapshot()


def test_corrupt_existing_snapshot_fails_verification(brain):
    target = brain.snapshot()
    (target / "trade_history.csv").write_text("corrupted")
    with pytest.raises(ValueError, match="checksum"):
        brain.verify_snapshot(target)


def test_morning_and_postclose_capture_distinct_state(brain):
    morning = brain.snapshot()
    old_bytes = (morning / "trade_history.csv").read_bytes()
    (brain.BRAIN_DIR / "trade_history.csv").write_text("symbol,pnl\nAAPL,1\nMSFT,2\n")
    postclose = brain.snapshot()
    assert morning != postclose
    assert (morning / "trade_history.csv").read_bytes() == old_bytes
    assert (postclose / "trade_history.csv").read_bytes() != old_bytes
    brain.verify_snapshot(morning)
    brain.verify_snapshot(postclose)


def test_symlinks_rejected_without_following_external_data(brain, tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("private")
    (brain.BRAIN_DIR / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic link"):
        brain.snapshot()
    assert not list(brain.ARCHIVE_ROOT.iterdir())


def test_failed_backup_never_prunes_previous_archives(brain, monkeypatch):
    (brain.BRAIN_DIR / ".save_complete").unlink()
    monkeypatch.setattr(sys, "argv", ["rotate_brain_backup.py"])
    monkeypatch.setattr(brain, "prune", lambda *a: pytest.fail("must preserve prior backups"))
    assert brain.main() == 1


def test_restore_refuses_live_and_existing_targets(brain, tmp_path):
    target = brain.snapshot()
    for destination in (brain.BRAIN_DIR, brain.BRAIN_DIR / "child", tmp_path):
        with pytest.raises(ValueError, match="new directory"):
            brain.restore_copy(target, destination)


def test_active_writer_lock_defers_snapshot(brain):
    import fcntl
    with (brain.BRAIN_DIR / ".brain.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="save in progress"):
            brain.snapshot()


@pytest.fixture
def database():
    return load("scripts/runtime/backup/paper_database.py")


def identity(database, monkeypatch):
    monkeypatch.setattr(database, "source_info", lambda: {"user": "trading", "database": "algotrading", "image": "sha256:" + "1" * 64})


def test_failed_database_dump_never_publishes_or_prunes(database, monkeypatch, tmp_path):
    identity(database, monkeypatch)
    old = tmp_path / "paper-postgres-old.dump"
    old.write_bytes(b"previous good backup")
    monkeypatch.setattr(database, "execute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dump failed")))
    with pytest.raises(RuntimeError, match="dump failed"):
        database.make_backup(tmp_path)
    assert list(tmp_path.iterdir()) == [old]


def test_database_backup_is_private_atomic_and_catalog_checked(database, monkeypatch, tmp_path):
    identity(database, monkeypatch)

    def execute(args, **kwargs):
        assert args[:3] == ["docker", "exec", database.SOURCE_CONTAINER]
        assert "pg_dump" in args and "--format=custom" in args
        kwargs["stdout"].write(b"PGDMP fixture")
        return ""

    monkeypatch.setattr(database, "execute", execute)
    monkeypatch.setattr(database, "archive_tables", lambda path: ["users"])
    report = database.make_backup(tmp_path)
    target = Path(report["path"])
    assert target.exists() and target.stat().st_mode & 0o777 == 0o600
    assert report["restore_verified"] is False
    assert database.sha256(target) == report["sha256"]
    assert target.with_suffix(".json").stat().st_mode & 0o777 == 0o600


def test_restore_uses_isolated_container_and_verifies_real_queries(database, monkeypatch, tmp_path):
    identity(database, monkeypatch)
    backup = tmp_path / "fixture.dump"
    backup.write_bytes(b"PGDMP fixture")
    monkeypatch.setattr(database, "archive_tables", lambda path, container: ["orders", "users"])
    calls = []
    created_name = []

    def execute(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            created_name.append(args[args.index("--name") + 1])
            assert args[args.index("--network") + 1] == "none"
            assert args[args.index("--pull") + 1] == "never"
            assert not set(args) & {"-p", "--publish", "-v", "--volume", "--mount"}
            assert "--tmpfs" in args
            return "created"
        if args[1] == "ps":
            return created_name[0] + "\n"
        if "psql" in args:
            query = args[-1]
            if "pg_tables" in query:
                return "orders\nusers\n"
            if "pg_constraint" in query:
                return "0\n"
            return "3\n"
        return ""

    monkeypatch.setattr(database, "execute", execute)
    report = database.verify_restore(backup)
    assert report["verified"] and report["cleanup_succeeded"]
    assert report["rows_by_table"] == {"orders": 3, "users": 3}
    assert any("pg_restore" in args and "--exit-on-error" in args for args in calls)
    assert calls[-1] == ["docker", "rm", "--force", "--volumes", created_name[0]]
    assert database.SOURCE_CONTAINER not in calls[-1]


def test_failed_restore_still_removes_only_owned_container(database, monkeypatch, tmp_path):
    identity(database, monkeypatch)
    backup = tmp_path / "fixture.dump"
    backup.write_bytes(b"PGDMP fixture")
    monkeypatch.setattr(database, "archive_tables", lambda *a: ["users"])
    name = []
    removed = []

    def execute(args, **kwargs):
        if args[1] == "run":
            name.append(args[args.index("--name") + 1])
        elif "pg_restore" in args:
            raise RuntimeError("restore failed")
        elif args[1] == "ps":
            return name[0]
        elif args[1] == "rm":
            removed.append(args[-1])
        return ""

    monkeypatch.setattr(database, "execute", execute)
    with pytest.raises(RuntimeError, match="restore failed"):
        database.verify_restore(backup)
    assert removed == name


def test_uncertain_container_creation_also_attempts_owned_cleanup(database, monkeypatch, tmp_path):
    identity(database, monkeypatch)
    backup = tmp_path / "fixture.dump"
    backup.write_bytes(b"PGDMP fixture")
    calls = []

    def execute(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 30)
        if args[1] == "ps":
            return ""
        return ""

    monkeypatch.setattr(database, "execute", execute)
    with pytest.raises(subprocess.TimeoutExpired):
        database.verify_restore(backup)
    assert calls[-1][1] == "ps"
    assert "label=intra.restore-owner=" in calls[-1][4]


def test_cleanup_rejects_unexpected_container(database, monkeypatch):
    monkeypatch.setattr(database, "execute", lambda *a, **k: database.SOURCE_CONTAINER)
    with pytest.raises(ValueError, match="unexpected"):
        database.cleanup_restore("intra-restore-check-test", "owner")
