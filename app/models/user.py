from sqlalchemy import Integer, String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column
import datetime

from app.core.time import utc_now_naive
from app.database.base import Base
class User(Base):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_email : Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username : Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash : Mapped[str] = mapped_column(String(255), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive, server_default=text("(UTC_TIMESTAMP())"))
    last_login_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
