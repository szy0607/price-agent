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
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, onupdate=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
