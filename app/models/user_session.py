import datetime

from sqlalchemy import Integer, String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class UserSession(Base):
    __tablename__ = 'user_sessions'
    id : Mapped[int] = mapped_column(Integer,primary_key=True, autoincrement=True, comment='主键',nullable=False)
    user_id : Mapped[int] = mapped_column(Integer,comment='用户ID',nullable=False,index=True)
    token_hash : Mapped[str] = mapped_column(String(64),comment='会话token哈希值',nullable=False,unique=True)
    create_time : Mapped[datetime.datetime] = mapped_column(DateTime,comment='创建时间',nullable=False, default=get_current_time,server_default=text("(UTC_TIMESTAMP())"))
    expire_time : Mapped[datetime.datetime] = mapped_column(DateTime,comment='过期时间',nullable=False,index=True)
    revoke_time : Mapped[datetime.datetime] = mapped_column(DateTime,comment='撤销时间',nullable=True)
