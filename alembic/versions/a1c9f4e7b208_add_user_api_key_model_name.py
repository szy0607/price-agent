"""Let each provider row remember the model the user picked.

Revision ID: a1c9f4e7b208
Revises: e4a6b8c0d2f1

手写而非 autogenerate：本迁移只应有这一条 add_column。
`alembic/env.py` 开着 compare_server_default=True，autogenerate 会为
create_time/update_time 的 `(UTC_TIMESTAMP())` 表达式默认值生成多余的 alter_column。
可空、无 server_default —— 存量行全部为 NULL，语义是「未选择，回落服务商默认模型」，
所以对已有数据是纯 no-op。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c9f4e7b208"
down_revision: Union[str, None] = "e4a6b8c0d2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_api_keys", sa.Column("model_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("user_api_keys", "model_name")
