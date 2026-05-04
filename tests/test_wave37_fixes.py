"""V8 / Wave-37 (2026-05-03): tests for migration-tree integrity.

Locks the regressions for:
- OO MIGRATION-GAP (resolved): the V8 OO finding asserted
  alembic/versions/ was missing; in fact alembic.ini points at
  backend/migrations and that has 15+ migration files in a clean
  single-headed chain. Wave-37 ships scripts/ci/check_migrations.py
  as a CI smoke check + this regression test.

Run with: ./venv/bin/python -m pytest tests/test_wave37_fixes.py -v
"""
from __future__ import annotations

import os
import subprocess

import pytest


def test_migration_smoke_script_exists_and_runs():
    """scripts/ci/check_migrations.py must exist and exit 0 on the
    current branch (single-headed linear tree)."""
    assert os.path.isfile("scripts/ci/check_migrations.py"), (
        "Wave-37 regression: migration smoke checker script missing."
    )
    proc = subprocess.run(
        ["./venv/bin/python", "scripts/ci/check_migrations.py"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"Wave-37 regression: migration smoke check failed:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "single head" in proc.stdout, (
        f"Wave-37 regression: smoke output missing 'single head' line.\n"
        f"stdout: {proc.stdout}"
    )


def test_migrations_versions_directory_present_at_correct_path():
    """The OO finding's claim was that alembic/versions/ doesn't exist
    — true at the repo root, but `alembic.ini` points to
    backend/migrations.  This test pins the actual location."""
    assert os.path.isdir("backend/migrations/versions"), (
        "Wave-37 regression: backend/migrations/versions/ doesn't exist. "
        "Either alembic.ini was retargeted or the migrations directory "
        "was deleted. Migration history may be lost."
    )


def test_alembic_ini_script_location_correct():
    """alembic.ini's script_location must point to backend/migrations."""
    with open("alembic.ini") as f:
        ini = f.read()
    assert "script_location = %(here)s/backend/migrations" in ini, (
        "Wave-37 regression: alembic.ini script_location no longer "
        "points to backend/migrations. Migration tooling will break."
    )


def test_migrations_count_at_least_15():
    """Sanity: don't lose migrations.  V7 had 17; V8 expectation >= 15."""
    versions = [
        f for f in os.listdir("backend/migrations/versions")
        if f.endswith(".py")
    ]
    assert len(versions) >= 15, (
        f"Wave-37 regression: only {len(versions)} migration files found "
        "under backend/migrations/versions/; expected >= 15. Migrations "
        "may have been deleted."
    )
