"""
pgsql只存embedding，事实源为mysql
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.config import settings
from app.core.errors import BizError, ErrorCode

_engine = None
_session_local = None

def start_pg_engine():
    """lifespan启动时同时启动pgsql引擎"""
    global _engine,_session_local
    if not settings.pg_url:
        return
    from sqlalchemy.ext.asyncio import create_async_engine
    _engine = create_async_engine(settings.pg_url,
                                  echo=False,
                                  pool_size=5,
                                  max_overflow=5,
                                  pool_timeout=30,
                                  pool_recycle=3600,
                                  pool_pre_ping=True,
                                  )
    _session_local = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async  def close_pg_engine():
    """lifespan关闭时同时关闭pgsql引擎"""
    global _engine,_session_local
    if _engine is not None:
        await _engine.dispose()
    _engine,_session_local = None,None

def get_pg_session():
    if _session_local is None:
        raise BizError(ErrorCode.PARAM_INVALID, "未配置向量库（PG_URL），语义检索不可用")
    return _session_local()

