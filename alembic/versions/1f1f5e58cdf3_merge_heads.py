"""merge heads

Revision ID: 1f1f5e58cdf3
Revises: a1c9f4e7b208, b82905270b5c
Create Date: 2026-10-01 23:11:14.634662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f1f5e58cdf3'
down_revision: Union[str, None] = ('a1c9f4e7b208', 'b82905270b5c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
