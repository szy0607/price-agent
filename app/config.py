from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

load_dotenv()
import os
DB_URL = os.getenv('DB_URL')
async_engine = create_async_engine(DB_URL,
                                   echo=True,
                                   pool_size=10,
                                   max_overflow=20,
                                   pool_timeout=30,
                                   pool_pre_ping=True,
                                   pool_recycle=3600,
                                   )
AsyncSession = async_sessionmaker(bind=async_engine, expire_on_commit=False)
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        # ix: index，索引
        "ix": 'ix_%(column_0_label)s',
        # un: unique，唯一约束
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        # ck: Check，检查约束
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        # fk: Foreign Key，外键约束
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        # pk: Primary Key，主键约束
        "pk": "pk_%(table_name)s"
    })