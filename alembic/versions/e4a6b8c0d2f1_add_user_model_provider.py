"""Select a user's provider for model-backed consultations.

Revision ID: e4a6b8c0d2f1
Revises: c3d5e7f9a1b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a6b8c0d2f1"
down_revision: Union[str, None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("model_provider", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "model_provider")
