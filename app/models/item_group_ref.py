from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class ItemGroupRef(Base):
    """分组成员关系：一条记录 = 某物品在某分组里。

    只存引用、不存数据：item_type + item_id 指向 cart_item（"cart"，未购买）
    或 owned_item（"owned"，已购买）。两张物品表的 id 是各自独立的自增序列，
    所以必须靠 item_type 才能知道 item_id 指向谁——分组里的「已购买 /
    未购买」两区也直接由它表达，不必在物品表上另加状态列。

    物品被标记购买时（cart_item → owned_item，见 cart_repo.transfer_to_owned_item），
    同一事务内把本表的 item_type/item_id 改指向新 owned_item，
    分组里该物品随之从「未购买」区翻到「已购买」区。
    """

    __tablename__ = "item_group_ref"
    __table_args__ = (
        # 同一物品不能重复加入同一分组（应用层先查兜底 + 这层数据库兜底）
        UniqueConstraint("group_id", "item_type", "item_id", name="uq_item_group_ref_group_item"),
        # 删物品 / 标记购买转移物品时，要按 (item_type, item_id) 反查它进了哪些组。
        # group_id 单列查询不走这个索引，但被唯一约束的最左前缀覆盖，无需另建。
        Index("ix_item_group_ref_item", "item_type", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 无物理外键（决策 #30 口径）：group_id 指向 item_group.id，item_id 按 item_type 指向两张物品表之一
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 只存 "cart" / "owned"
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
