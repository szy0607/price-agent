from datetime import datetime


from sqlalchemy import JSON, DateTime, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import get_current_time
from app.database.base import Base


class UserProfile(Base):
    """用户画像（结构化落库，替代旧 user_profile.py 的实时拼装）。

    一行一用户，没有「一个用户多行画像」的场景，所以 user_id 直接做主键、
    不设自增 id —— 读写都是单键定位，更新天然是 upsert。
    preferences 是自由键值（预算/品牌/用途…），由 A6 画像 Agent 总结判断后
    全量覆盖写入，后端不预设字段。
    """

    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    # default=dict：每次插入调用 dict() 生成新空 dict，
    # 不能写 default={} —— 那是所有新行共享同一个可变对象
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time, nullable=False)
