"""V11 prep / Wave-61 (2026-05-03): XX-3 portfolio_history migration.

Locks the regression for V10 XX-3 — `portfolio_history` was declared
in backend/infra/schemas.py but no migration created it.  Same bug
class as V7 BB / wave-25 drawings.

Wave-61 ships migration 20260503_000003 that creates the table to
match the ORM declaration verbatim.

Run with: ./venv/bin/python -m pytest tests/test_wave61_fixes.py -v
"""
from __future__ import annotations

import os


def test_xx_3_portfolio_history_migration_exists():
    """The wave-61 migration must exist + be in the chain."""
    path = (
        "backend/migrations/versions/"
        "20260503_000003_xx_3_portfolio_history.py"
    )
    assert os.path.isfile(path), (
        "XX-3 regression: portfolio_history migration deleted."
    )
    src = open(path).read()
    assert "create_table" in src
    assert '"portfolio_history"' in src
    # FK to users with CASCADE
    assert 'ForeignKey("users.id"' in src and 'ondelete="CASCADE"' in src
    # CHECK constraint matches ORM
    assert (
        "snapshot_type IN ('scheduled', 'manual', 'trade', 'rebalance')"
        in src
    )


def test_xx_3_migration_has_downgrade():
    """downgrade() must drop the table + indices (V10 XX-1 lesson:
    incomplete downgrades poison the txn)."""
    path = (
        "backend/migrations/versions/"
        "20260503_000003_xx_3_portfolio_history.py"
    )
    src = open(path).read()
    assert "def downgrade" in src
    assert "drop_table" in src
    assert "drop_index" in src


def test_xx_3_migration_tree_still_single_headed():
    """Adding the wave-61 migration must not branch the tree."""
    import subprocess
    proc = subprocess.run(
        ["./venv/bin/python", "scripts/ci/check_migrations.py"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"XX-3 regression: tree not single-headed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "20260503_000003" in proc.stdout
