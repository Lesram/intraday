"""V7 BB-1/2/3 / Wave-25 (2026-05-03): orders table CHECK constraints.

V7 Track BB found that the `orders` table accepted any 20-char string
as `status`, any string as `side`, any string as `order_type` / `tif`,
and any qty including 0 / negative / filled_qty > qty. The state
machine logic is enforced at the app layer, but the DB allowed any
shape — a bug or a malformed migration would silently corrupt the
table.

Add CHECK constraints to enforce the contract at the DB level:
- qty > 0
- filled_qty >= 0
- filled_qty <= qty (no overfills)
- side in ('buy', 'sell')
- order_type in ('market', 'limit', 'stop', 'stop_limit')
- tif in ('day', 'gtc', 'ioc', 'fok', 'opg', 'cls')
- status in the canonical enum

NOTE: status enum is intentionally permissive — the live engine has
14+ status values across 8 modules (audit-finding). We list the
verified-active set; future statuses must be added here AND in the
status-mapping code. CHECK constraint is a safety net, not a contract.

Revision ID: 20260503_000001
Revises: 20260502_000001
Create Date: 2026-05-03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260503_000001"
down_revision = "20260502_000001"
branch_labels = None
depends_on = None


# Canonical enum values mirror app-layer constants. Keep in sync with
# backend/services/order_service.py validation (V7 FF-1 / Wave-25).
_VALID_SIDES = ("buy", "sell")
_VALID_ORDER_TYPES = ("market", "limit", "stop", "stop_limit")
_VALID_TIFS = ("day", "gtc", "ioc", "fok", "opg", "cls")
_VALID_STATUSES = (
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


def _quote_csv(values):
    return ", ".join(f"'{v}'" for v in values)


def upgrade():
    # Quantity invariants.
    op.create_check_constraint(
        "ck_orders_qty_positive",
        "orders",
        "qty > 0",
    )
    op.create_check_constraint(
        "ck_orders_filled_qty_nonnegative",
        "orders",
        "filled_qty >= 0",
    )
    op.create_check_constraint(
        "ck_orders_filled_qty_lte_qty",
        "orders",
        "filled_qty <= qty",
    )

    # Enum-style fields.
    op.create_check_constraint(
        "ck_orders_side",
        "orders",
        f"side IN ({_quote_csv(_VALID_SIDES)})",
    )
    op.create_check_constraint(
        "ck_orders_order_type",
        "orders",
        f"order_type IN ({_quote_csv(_VALID_ORDER_TYPES)})",
    )
    op.create_check_constraint(
        "ck_orders_tif",
        "orders",
        f"tif IN ({_quote_csv(_VALID_TIFS)})",
    )
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        f"status IN ({_quote_csv(_VALID_STATUSES)})",
    )


def downgrade():
    for name in (
        "ck_orders_status",
        "ck_orders_tif",
        "ck_orders_order_type",
        "ck_orders_side",
        "ck_orders_filled_qty_lte_qty",
        "ck_orders_filled_qty_nonnegative",
        "ck_orders_qty_positive",
    ):
        op.drop_constraint(name, "orders", type_="check")
