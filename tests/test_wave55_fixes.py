"""V10 / Wave-55 (2026-05-03): tests for migration fixes + BB4-F2 verify.

Locks regressions for:
- XX-1 (HIGH): ec197100938a downgrade now uses IF EXISTS so the txn
  doesn't abort on missing constraint.
- XX-2 (HIGH): new migration 20260503_000002 widens ck_orders_status
  to include `new`, `pending_new`, `submitting`, `canceled`, etc. —
  matching what repositories/orders.py + partial index reference.
- BB4-F2 verification: wave-44 DD3-4 EOD-cancel IS inline in
  _live_tick_inner; agent's false-positive "no _cancel_pending_entry_orders()
  function" was based on searching for a function name that never existed.

Wave-55 deferred:
- XX-3 (MEDIUM, ORM-vs-DB drift / portfolio_history): scope larger
  than this wave; tracked for V11.

Run with: ./venv/bin/python -m pytest tests/test_wave55_fixes.py -v
"""
from __future__ import annotations

import inspect
import os
import re


def test_xx_1_ec197_downgrade_uses_if_exists():
    """The ec197100938a downgrade must use IF EXISTS so the txn doesn't
    abort on the missing uq_orders_account_client_order constraint."""
    path = (
        "backend/migrations/versions/"
        "ec197100938a_add_idempotency_constraints_and_order_.py"
    )
    src = open(path).read()
    assert "XX-1" in src, "XX-1 marker missing in ec197100938a"
    assert "DROP CONSTRAINT IF EXISTS uq_orders_account_client_order" in src, (
        "XX-1 regression: downgrade still uses bare drop_constraint that "
        "aborts the txn."
    )


def test_xx_2_widen_ck_orders_status_migration_exists():
    """A new migration must widen ck_orders_status."""
    path = (
        "backend/migrations/versions/"
        "20260503_000002_xx_2_widen_orders_status_check.py"
    )
    assert os.path.isfile(path), (
        "XX-2 regression: 20260503_000002 widening migration missing."
    )
    src = open(path).read()
    # Must include the previously-rejected statuses (Python string literals).
    for needed in ('"new"', '"pending_new"', '"submitting"', '"canceled"'):
        assert needed in src, (
            f"XX-2 regression: {needed} missing from migration"
        )


def test_xx_2_migration_tree_still_single_headed():
    """Adding the wave-55 migration must not branch the tree."""
    import subprocess
    proc = subprocess.run(
        ["./venv/bin/python", "scripts/ci/check_migrations.py"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"XX-2 regression: migration tree no longer single-headed: "
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert "20260503_000002" in proc.stdout, (
        f"XX-2 regression: new head not '20260503_000002': {proc.stdout}"
    )


def test_bb4_f2_verify_eod_cancel_inline_in_live_engine():
    """Wave-44 DD3-4 EOD pending-entry cancel is inline in
    _live_tick_inner (not a separate function — V10 BB4-F2 false
    positive).  Verify both the marker AND the cancel call are present."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "DD3-4" in src, "DD3-4 marker missing"
    assert "EOD flatten cancelled pending" in src, (
        "BB4-F2 false-positive: DD3-4 inline cancel block removed."
    )
