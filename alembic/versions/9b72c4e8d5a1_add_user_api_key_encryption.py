"""Add per-user encrypted API key storage.

Revision ID: 9b72c4e8d5a1
Revises: 0f11e35680eb
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b72c4e8d5a1"
down_revision: Union[str, None] = "0f11e35680eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_key_envelopes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("encrypted_dek", sa.String(length=44), nullable=False),
        sa.Column("dek_nonce", sa.String(length=16), nullable=False),
        sa.Column("dek_tag", sa.String(length=24), nullable=False),
        sa.Column("kek_version", sa.String(length=32), nullable=False),
        sa.Column("dek_version", sa.Integer(), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("(UTC_TIMESTAMP())"), nullable=False),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("(UTC_TIMESTAMP())"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_key_envelopes_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_key_envelopes"),
    )
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64, collation="utf8mb4_bin"), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("api_key_nonce", sa.String(length=16), nullable=False),
        sa.Column("api_key_tag", sa.String(length=24), nullable=False),
        sa.Column("dek_version", sa.Integer(), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("key_suffix", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.String(length=32), nullable=False),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("(UTC_TIMESTAMP())"), nullable=False),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("(UTC_TIMESTAMP())"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_key_envelopes.user_id"], name="fk_user_api_keys_user_id_user_key_envelopes", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_user_api_keys"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
    )
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_api_keys_user_id", table_name="user_api_keys")
    op.drop_table("user_api_keys")
    op.drop_table("user_key_envelopes")
