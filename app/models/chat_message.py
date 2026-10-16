from datetime import datetime


from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class ChatMessage(Base):
    """单条对话消息（对话历史）。

    三个用途：chat 请求注入最近上下文；批次②检索语料（对话历史向量化）；前端会话页展示。

    system 消息不入库 —— system prompt 每次请求现拼，入库要额外处理「旧 system 作废」。

    status 只描述 assistant 消息的**生成结局**（流式输出，2026-10-16 定）：
      - completed  ：正常收完。**user 消息恒为此值**（请求开始即入库，没有「中断」语义）
      - interrupted：用户主动取消（abort / 关页面 / 断连），保存中断前已生成的部分文本
      - failed     ：模型异常且已有部分输出，保存部分文本

    旧数据统一回填 completed —— 这是有意的：trim_trailing_users 靠「assistant 从不落库」
    处理「user 失败 → 连续两条 user」，全部 completed 才让该前提继续成立。
    空输出（一个 token 都没收到就报错）不落库，见 docs/流式输出-设计.md §1.3。
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
    # 生成结局：completed / interrupted / failed。不加 CHECK 约束（对齐项目既有多枚举列口径，
    # 校验在 service 层），不建额外索引（现有复合索引已覆盖查询前缀）。
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed", server_default=text("'completed'")
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
