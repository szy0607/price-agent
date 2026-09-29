import datetime

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now_naive
from app.database.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="用户ID")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="会话token哈希值")
    create_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"), comment="创建时间"
    )
    expire_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True, comment="过期时间")
    revoke_time: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True, comment="撤销时间")
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="登录IP")
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="客户端UA")
