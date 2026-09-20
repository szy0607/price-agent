from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.config import settings
#固定时间区
_CONNECT_ARGS = {"init_command": "SET time_zone='+00:00'"}
async_engine = create_async_engine(settings.db_url,
                                   echo=False,
                                   pool_size=10,
                                   max_overflow=20,
                                   pool_timeout=30,
                                   pool_pre_ping=True,
                                   pool_recycle=3600,
                                   connect_args=_CONNECT_ARGS
                                   )
async_session_local = async_sessionmaker(bind=async_engine, expire_on_commit=False)
