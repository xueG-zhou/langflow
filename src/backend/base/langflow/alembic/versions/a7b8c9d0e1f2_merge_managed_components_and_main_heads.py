"""Merge managed components and main migration heads.

Revision ID: a7b8c9d0e1f2
Revises: 9a9ac41e51e7, mc1a2b3c4d5e
Create Date: 2026-07-29

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: tuple[str, str] = ("9a9ac41e51e7", "mc1a2b3c4d5e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the two migration branches without changing the schema."""


def downgrade() -> None:
    """Split the migration graph without changing the schema."""
