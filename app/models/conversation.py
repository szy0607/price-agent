from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class Conversation(Base):

    __tablename__ = "conversation"
    __table_args__ = (
        # 会话列表的查询形状固定为 WHERE user_id=? ORDER BY update_time DESC LIMIT n，
        # 与 chat_message 的复合索引同构：最左前缀过滤，二级索引自带主键、排序零成本。
        Index("ix_conversation_user_update", "user_id", "update_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 无物理外键（决策 #30 口径）：归属完整性由应用层保证，一律从 CurrentUser 取 id
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
