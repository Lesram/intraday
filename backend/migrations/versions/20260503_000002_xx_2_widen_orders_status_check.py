"""V10 XX-2 / Wave-55 (2026-05-03): widen ck_orders_status to include
new / pending_new / submitting / canceled.

The migration `20260503_000001` introduced `ck_orders_status` but its
allowed-values list omitted `new`, `pending_new`, `submitting`, and
`canceled` (US spelling). The repo writes those statuses in:
- `backend/infra/repositories/orders.py:385` lists `'submitting'`
  among active statuses.
- The partial index `ix_orders_active_status` (from
  `20260201_000003_add_performance_indexes.py`) is built specifically
  for `WHERE status IN ('new', 'pending_new', ...)`.

Today's prod data passed VALIDATE only because the live engine never
wrote those status names (they were aliased away pre-CHECK), but any
code path that writes them returns HTTP 500 with `CheckViolation`.

This migration:
1. Drops the existing ck_orders_status.
2. Re-creates it with the widened set covering the Alpaca wire
   vocabulary (consistent with V10 wave-54 OrderStatus enum).

Revision ID: 20260503_000002
Revises: 20260503_000001
Create Date: 2026-05-03
"""
from alembic import op


revision = "20260503_000002"
down_revision = "20260503_000001"
branch_labels = None
depends_on = None


_WIDENED_STATUSES = (
    # Pre-broker / submitting.
    "new",
    "pending",
    "pending_new",
    "submitted",
    "submitting",
    "accepted",
    "accepted_for_bidding",
    # Active / partials.
    "partially_filled",
    "partial",
    # Terminal — happy path.
    "filled",
    # Terminal — cancellation.
    "canceled",
    "cancelled",
    "pending_cancel",
    # Terminal — failure.
    "rejected",
    "expired",
    "done_for_day",
    "stopped",
    "replaced",
    "pending_replace",
    "calculated",
    "suspended",
    "deferred",
    "failed",
    "filled_during_cancel",
)


def _quote_csv(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade():
    # V11 AA5 hotfix prep: Alembic auto-prefixes constraint names, so
    # the deployed name is actually `ck_orders_ck_orders_status` (the
    # V10 XX-2 finding noted this double-prefix bug).  Drop BOTH the
    # bare and double-prefix forms before recreating cleanly so the
    # migration can be applied to the live DB on first run.
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_ck_orders_status")
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        f"status IN ({_quote_csv(_WIDENED_STATUSES)})",
    )


def downgrade():
    # Restore the narrower set from 20260503_000001.
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status")
    _NARROW_STATUSES = (
        "pending",
        "accepted",
        "submitted",
        "partially_filled",
        "filled",
        "cancelled",
        "expired",
        "rejected",
        "pending_cancel",
        "pending_replace",
        "replaced",
        "stopped",
        "suspended",
        "calculated",
        "deferred",
        "failed",
        "filled_during_cancel",
    )
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        f"status IN ({_quote_csv(_NARROW_STATUSES)})",
    )
