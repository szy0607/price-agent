from sqlalchemy import Integer, String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column
import datetime
from app.database.base import Base
class User(Base):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_email : Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username : Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash : Mapped[str] = mapped_column(String(255), nullable=False)
    create_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text("(UTC_TIMESTAMP())"))
    last_login_time : Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
