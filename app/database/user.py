from sqlalchemy.orm import Mapped, mapped_column
from app.config import Base
class User(Base):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(primary_key=True, index=True)
    user_email : Mapped[str] = mapped_column(unique=True, index=True)
    username : Mapped[str] = mapped_column(unique=True, index=True)
    password_hash : Mapped[str] = mapped_column(index=True)
