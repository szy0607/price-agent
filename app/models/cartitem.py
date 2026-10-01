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
    create_time : Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), nullable=False)
    update_time : Mapped[datetime] = mapped_column(DateTime, default=get_current_time, server_default=text("(UTC_TIMESTAMP())"), onupdate=get_current_time,nullable=False)
