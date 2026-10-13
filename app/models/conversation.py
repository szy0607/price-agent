from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class Conversation(Base):
    """会话（多轮对话的容器）。id 直接当 conversation_id 用，不另设会话语义的自增列。

    懒创建：用户发出第一条消息时才建会话，点「新建」不发请求 —— 否则页内
    建了又不说的空会话会在库里堆成垃圾。

    title 由模型总结首句生成，只在创建时定一次，之后无论聊多少轮都不改。
    """

    __tablename__ = "conversation"
    __table_args__ = (
        # 会话列表的查询形状固定为 WHERE user_id=? ORDER BY update_time DESC LIMIT n，
        # 与 chat_message 的复合索引同构：最左前缀过滤，二级索引自带主键、排序零成本。
        Index("ix_conversation_user_update", "user_id", "update_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 无物理外键（决策 #30 口径）：归属完整性由应用层保证，一律从 CurrentUser 取 id
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 与 username 同档：用户可见的短名称。模型总结的标题，远长于 24 字仍有 4 倍余量
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
