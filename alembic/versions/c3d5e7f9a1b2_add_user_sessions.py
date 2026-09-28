"""Add server-side sessions for authenticated settings.

Revision ID: c3d5e7f9a1b2
Revises: 9b72c4e8d5a1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, None] = "9b72c4e8d5a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("(UTC_TIMESTAMP())"), nullable=False),
        sa.Column("expire_time", sa.DateTime(), nullable=False),
        sa.Column("revoke_time", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expire_time", "user_sessions", ["expire_time"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_expire_time", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
