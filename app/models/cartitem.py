from datetime import datetime


from sqlalchemy import  Float, JSON, DateTime, text
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class CartItem(Base):
    __tablename__ = "cart_item"
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id : Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    category : Mapped[str] = mapped_column(String(64), nullable=False,default="其他")
    name : Mapped[str] = mapped_column(String(256), nullable=False)
    price : Mapped[float] = mapped_column(Float, nullable=True)
    specs : Mapped[dict] = mapped_column(JSON, nullable=False)
    image : Mapped[str|None] = mapped_column(String(512), nullable=True)
    note : Mapped[str|None] = mapped_column(String(512), nullable=True)
    # ---- RAG 索引状态（2026-10-16 设计 docs/RAG索引任务-设计.md §1）----
    # PENDING 已存待建索引 / RUNNING worker 处理中 / SYNCED 向量已写入 PG /
    # FAILED embedding 调用持续失败（key 欠费等，修好后由 reaper 重捞）。
    # server_default='PENDING' 不可省：加 NOT NULL 列时不带默认值，MySQL 存量行
    # 无法回填，后续 INSERT 会因缺默认值报错（autogenerate 在这一步经常漏）。
    index_status : Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    # 仅在置 SYNCED 时写：那一刻「向量已落PG」的时刻。置 RUNNING 时不要动它。
    index_time : Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time : Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time : Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time,nullable=False)
