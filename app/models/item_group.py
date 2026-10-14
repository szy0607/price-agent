from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class ItemGroup(Base):
    """购物分组：把购物车（未购买）和物品库（已购买）里的物品归到一组一起看。

    分组与物品是「引用」关系而非「归属」关系：物品本体始终在 cart_item /
    owned_item 原表，分组只通过 item_group_ref 记录「谁在哪个组」，
    因此删分组、改组名都不动物品本身。
    """

    __tablename__ = "item_group"
    __table_args__ = (
        # 分组列表的查询形状固定为 WHERE user_id=? ORDER BY update_time DESC，
        # 与 conversation 同构：最左前缀过滤，二级索引自动携带主键 id，排序零成本，
        # 因此不再单独建 user_id 单列索引（那是冗余）。
        Index("ix_item_group_user_update", "user_id", "update_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 无物理外键（决策 #30 口径）：归属完整性由应用层保证，一律从 CurrentUser 取 id
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 与 conversation.title 同档：用户可见的短名称，如「双11装机清单」
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 分组备注，可空（如「预算 8000，等显卡降价」）
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
