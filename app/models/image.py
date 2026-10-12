from sqlalchemy import Boolean, Integer, String, DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column
import datetime

from app.core.time import utc_now_naive
from app.database.base import Base


class Image(Base):
    """用户上传展示图的登记簿 + 生命周期管理。

    与 cart_item.image / owned_item.image 的分工：
    - 这两个 item 表的 image 列存路径字符串（对外契约不变）；
    - 本表回答「这张图是谁的、还有没有人用」——归属与生命周期的唯一事实源。

    status 状态机（见 docs/图片上传服务-接口契约.md）：
        pending -> referenced -> released -> (定时清理删行删文件)
    """
    __tablename__ = "image"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    path: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending",
                                        server_default=text("'pending'"))
    create_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"))
    update_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"),
        onupdate=utc_now_naive)
