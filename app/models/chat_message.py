from datetime import datetime


from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class ChatMessage(Base):
    """单条对话消息（对话历史）。

    两个用途：chat 请求注入最近上下文；批次②检索语料（对话历史向量化）。
    system 消息不入库 —— system prompt 每次请求现拼，入库要额外处理「旧 system 作废」。
    """

    __tablename__ = "chat_message"
    __table_args__ = (
        # 聊天场景的查询形状固定为 WHERE user_id=? AND conversation_id=? ORDER BY id DESC LIMIT n：
        # 复合索引最左前缀覆盖「只按 user_id 查」，二级索引自动携带主键 id，排序零成本，
        # 因此不再单独建 user_id 单列索引（那是冗余）。
        Index("ix_chat_message_user_conversation", "user_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 无物理外键（决策 #30 口径）：归属完整性由应用层保证，一律从 CurrentUser 取 id
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 只存 "user" / "assistant"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # assistant 消息记录实际用的模型名（排查/展示用）；user 消息为 NULL
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
