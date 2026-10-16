from datetime import datetime

from sqlalchemy import Integer, String, Float, JSON, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class PurchaseRecord(Base):
    """用户自记的消费流水。与 owned_item（物品库·参数档案）分表：
    一条记录 = 一次购买，同款买多次存多条（决策 #29 不加 quantity）。"""

    __tablename__ = "purchase_record"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False, autoincrement=True)
    # 逻辑外键，不建物理 FK（决策 #30）；取值一律来自 CurrentUser，不由请求体提供
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 品牌 + 型号 + 商品名三合一，用户自由填写（决策 #31①）
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    specs: Mapped[dict] = mapped_column(JSON, nullable=False)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ---- RAG 索引状态（2026-10-16 设计 docs/RAG索引任务-设计.md §1）----
    # PENDING 已存待建索引 / RUNNING worker 处理中 / SYNCED 向量已写入 PG /
    # FAILED embedding 调用持续失败（key 欠费等，修好后由 reaper 重捞）。
    # server_default='PENDING' 不可省：加 NOT NULL 列时不带默认值，MySQL 存量行
    # 无法回填，后续 INSERT 会因缺默认值报错（autogenerate 在这一步经常漏）。
    index_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    # 仅在置 SYNCED 时写：那一刻「向量已落 PG」的时刻。置 RUNNING 时不要动它。
    index_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, onupdate=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
