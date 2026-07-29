"""merge local inference heads with upstream 1.11 heads

Revision ID: 9a9ac41e51e7
Revises: c9e7fb30a1bc, d19e7b3c5a42
Create Date: 2026-07-29 10:42:43.434552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector
from langflow.utils import migration


# revision identifiers, used by Alembic.
revision: str = '9a9ac41e51e7'
down_revision: Union[str, None] = ('c9e7fb30a1bc', 'd19e7b3c5a42')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    pass


def downgrade() -> None:
    conn = op.get_bind()
    pass
