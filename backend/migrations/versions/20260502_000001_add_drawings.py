"""V4 N-C-1 (2026-05-02): add drawings table.

`Drawing` ORM model exists in backend/infra/schemas.py but no migration
ever created the underlying table. `to_regclass('public.drawings')`
returns NULL on the running paper DB, so the first hit on /api/drawings
500's with `relation "drawings" does not exist`. Create the table now,
matching the ORM declaration exactly so future autogenerate diffs are
clean.

Revision ID: 20260502_000001
Revises: 20260303_000001
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260502_000001"
down_revision = "20260303_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drawings",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("points", JSONB, nullable=False),
        sa.Column(
            "style", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "timeframe",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'1D'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drawings"),
    )
    op.create_index(
        "ix_drawings_user_id", "drawings", ["user_id"]
    )
    op.create_index(
        "ix_drawings_symbol", "drawings", ["symbol"]
    )
    op.create_index(
        "ix_drawings_user_symbol", "drawings", ["user_id", "symbol"]
    )


def downgrade():
    op.drop_index("ix_drawings_user_symbol", table_name="drawings")
    op.drop_index("ix_drawings_symbol", table_name="drawings")
    op.drop_index("ix_drawings_user_id", table_name="drawings")
    op.drop_table("drawings")
