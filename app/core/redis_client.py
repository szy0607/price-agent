import asyncio
from urllib.parse import urlparse

from app.core.config import settings

_redis_setting = None
_pool = None
_lock:asyncio.Lock | None = None


def arq_redis_settings():
    global _redis_setting
    if _redis_setting is None:
        from arq.connections import RedisSettings
        u = urlparse(settings.redis_url)
        _redis_setting = RedisSettings(
            host=u.hostname or "127.0.0.1",
            port=u.port or 6379,
            password=u.password,
        )
    return _redis_setting



async def get_pool():
    global _pool, _lock
    if _pool is not None:
        return _pool
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _pool is None:
            from arq import create_pool
            _pool = await create_pool(arq_redis_settings())
    return _pool

async def close_pool()->None:
    global _pool,_redis_setting
    if _pool is not None:
        await _pool.aclose()
    _pool = None
    _redis_setting = None
