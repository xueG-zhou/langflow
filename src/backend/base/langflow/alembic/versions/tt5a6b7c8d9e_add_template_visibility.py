"""replace template categories with visibility

Revision ID: tt5a6b7c8d9e
Revises: ta1a2b3c4d5e
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "tt5a6b7c8d9e"  # pragma: allowlist secret
down_revision: str | None = "ta1a2b3c4d5e"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "team_template"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if "visibility" not in columns:
            batch_op.add_column(sa.Column("visibility", sa.String(length=16), server_default="PRIVATE", nullable=False))
        if f"ix_{TABLE_NAME}_visibility" not in indexes:
            batch_op.create_index(f"ix_{TABLE_NAME}_visibility", ["visibility"])
        if f"ix_{TABLE_NAME}_category" in indexes:
            batch_op.drop_index(f"ix_{TABLE_NAME}_category")
        if "category" in columns:
            batch_op.drop_column("category")
        if "tags" in columns:
            batch_op.drop_column("tags")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if "category" not in columns:
            batch_op.add_column(
                sa.Column("category", sa.String(length=64), server_default="all-templates", nullable=False)
            )
        if "tags" not in columns:
            batch_op.add_column(sa.Column("tags", sa.JSON(), server_default="[]", nullable=False))
        if f"ix_{TABLE_NAME}_category" not in indexes:
            batch_op.create_index(f"ix_{TABLE_NAME}_category", ["category"])
        if f"ix_{TABLE_NAME}_visibility" in indexes:
            batch_op.drop_index(f"ix_{TABLE_NAME}_visibility")
        if "visibility" in columns:
            batch_op.drop_column("visibility")
