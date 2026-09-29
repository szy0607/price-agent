"""Add client info columns to user_sessions.

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


# 表本身由 0f11e35680eb 创建（该迁移已共享给协作者，不可改动）。
# 本迁移原先也是 create_table，两边撞车后改为只补本地多出的两列。
def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("ip", sa.String(length=45), nullable=True, comment="登录IP"))
    op.add_column("user_sessions", sa.Column("user_agent", sa.String(length=255), nullable=True, comment="客户端UA"))


def downgrade() -> None:
    op.drop_column("user_sessions", "user_agent")
    op.drop_column("user_sessions", "ip")
