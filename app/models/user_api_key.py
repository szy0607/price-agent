from sqlalchemy import Boolean, Integer, String, DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column
import datetime

from app.core.time import utc_now_naive
from app.database.base import Base


class UserApiKey(Base):
    __tablename__ = "user_api_key"
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_id : Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    provider : Mapped[str] = mapped_column(String(32), nullable=False)
    base_url : Mapped[str] = mapped_column(String(512), nullable=False)
    encrypted_key : Mapped[str] = mapped_column(Text, nullable=False)
    key_suffix : Mapped[str] = mapped_column(String(8), nullable=False)
    status : Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default=text("'active'"))
    model_name : Mapped[str] = mapped_column(String(128), nullable=False)
    is_default : Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    create_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"))
    update_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"), onupdate=utc_now_naive)
