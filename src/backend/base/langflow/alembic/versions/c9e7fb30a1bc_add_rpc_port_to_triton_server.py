"""add rpc_port to triton_server

Revision ID: c9e7fb30a1bc
Revises: ta1a2b3c4d5e
Create Date: 2026-07-27 00:00:00.000000

Phase: EXPAND

Adds the required ``rpc_port`` column (Triton gRPC port) to the
``triton_server`` table. The column is added nullable so existing rows
survive the migration; the application layer (Pydantic model) enforces
the field as required for new creates and updates. Existing rows get a
sensible default (8001, Triton's default gRPC port) backfilled so the
non-null contract holds.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration

revision: str = "c9e7fb30a1bc"  # pragma: allowlist secret
down_revision: str | None = "ta1a2b3c4d5e"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "triton_server"
DEFAULT_GRPC_PORT = 8001


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(TABLE_NAME, conn):
        return
    if migration.column_exists(TABLE_NAME, "rpc_port", conn):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        # nullable first so existing rows survive; backfilled below.
        batch_op.add_column(sa.Column("rpc_port", sa.Integer(), nullable=True))

    # Backfill existing rows with Triton's default gRPC port so the column
    # can be made non-null at the database level.
    conn.execute(  # type: ignore[union-attr]
        sa.text(
            f"UPDATE {TABLE_NAME} SET rpc_port = :port WHERE rpc_port IS NULL"  # noqa: S608
        ).bindparams(port=DEFAULT_GRPC_PORT)
    )

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.alter_column("rpc_port", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(TABLE_NAME, conn):
        return
    if not migration.column_exists(TABLE_NAME, "rpc_port", conn):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column("rpc_port")
