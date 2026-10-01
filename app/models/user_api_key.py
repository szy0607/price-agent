import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserKeyEnvelope(Base):
    __tablename__ = "user_key_envelopes"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    encrypted_dek: Mapped[str] = mapped_column(String(44), nullable=False)
    dek_nonce: Mapped[str] = mapped_column(String(16), nullable=False)
    dek_tag: Mapped[str] = mapped_column(String(24), nullable=False)
    kek_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dek_version: Mapped[int] = mapped_column(Integer, nullable=False)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    create_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("(UTC_TIMESTAMP())"))
    update_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("(UTC_TIMESTAMP())"))


class UserApiKey(Base):
    __tablename__ = "user_api_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_key_envelopes.user_id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64, collation="utf8mb4_bin"), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_nonce: Mapped[str] = mapped_column(String(16), nullable=False)
    api_key_tag: Mapped[str] = mapped_column(String(24), nullable=False)
    dek_version: Mapped[int] = mapped_column(Integer, nullable=False)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    # 明文、非机密：模型名是用户的选择而非凭据，不进信封（无 nonce/tag、不参与 AAD，
    # DEK 轮换与重包装都不碰它）。别把本模块「不存明文机密」的规则套用到这里。
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[str] = mapped_column(String(32), nullable=False)
    create_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("(UTC_TIMESTAMP())"))
    update_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("(UTC_TIMESTAMP())"))
