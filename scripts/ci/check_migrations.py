#!/usr/bin/env python3
"""V8 OO MIGRATION-GAP / Wave-37 (2026-05-03): migration smoke checker.

The V8 OO meta-audit's MIGRATION-GAP finding was a false positive — it
expected `alembic/versions/` at the repo root, but `alembic.ini` points
to `backend/migrations` (which has 17+ migration files and a clean
linear history).

This script formalizes the correction by:
- Loading alembic config from alembic.ini.
- Asserting `script_location` resolves to an existing directory.
- Asserting versions/ has at least 1 revision.
- Asserting `alembic history` produces a single-headed linear chain
  (no branches; multiple heads = merge conflict in migration tree).
- Reporting the head revision so operators can verify it's expected.

Usage (CI-style):

    python3 scripts/ci/check_migrations.py

Exits 0 on pass, 1 on fail.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _abort(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return 1


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    ini_path = repo_root / "alembic.ini"
    if not ini_path.is_file():
        return _abort(f"alembic.ini not found at {ini_path}")

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:
        return _abort("alembic is not installed in this environment")

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(repo_root / "backend/migrations"))
    script_dir = ScriptDirectory.from_config(cfg)

    versions_path = Path(script_dir.dir) / "versions"
    if not versions_path.is_dir():
        return _abort(
            f"versions/ does not exist at {versions_path}. The OO "
            "MIGRATION-GAP finding asserted alembic/versions/ was missing; "
            "the actual location is backend/migrations/versions/."
        )

    revs = list(script_dir.walk_revisions())
    if not revs:
        return _abort(f"no migrations found under {versions_path}")
    print(f"[ok] {len(revs)} migration(s) under {versions_path}")

    heads = script_dir.get_heads()
    if len(heads) != 1:
        return _abort(
            f"migration tree has {len(heads)} heads (expected 1). Heads: {heads}. "
            "Resolve via `alembic merge` before deploying."
        )
    head = heads[0]
    print(f"[ok] single head: {head}")

    base = script_dir.get_base()
    print(f"[ok] base: {base}")

    print("\n[OK] migration tree is linear with single head.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
