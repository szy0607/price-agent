import asyncio
from urllib.parse import urlparse

from app.core.config import settings

_redis_setting = None
_pool = None
_lock:asyncio.Lock | None = None

# 🔴 2026-10-17 新增：队列名可覆盖，专治「测试污染生产队列」。
#
# 背景：tests/test_index_service.py 里有两处**故意**保持 enqueue_sync 的真实实现
# （mock 掉反而测不到「投递失败自己吞掉」这条降级路径），于是它们往 `arq:queue`
# 里塞了真任务。跑完测试再起 worker，worker 会消费到**测试造的假用户数据**，
# **真调向量模型 API（花钱）**—— 2026-10-17 实测跑一次测试留 39 个 job。
#
# 解法不是「记得清队列」（靠人记性，必然忘），而是**让测试写进另一个队列名**。
# worker 只监听 `arq:queue`，测试任务进了 `arq:queue:pytest` 就永远不会被消费。
# job 定义本身仍存在 `arq:job:*` 键里（arq 的设计如此），但**没人消费就不会执行**。
_QUEUE_NAME_ENV = "ARQ_QUEUE_NAME"
_DEFAULT_QUEUE = "arq:queue"
TEST_QUEUE = "arq:queue:pytest"


def current_queue_name() -> str:
    """当前生效的队列名。环境变量 `ARQ_QUEUE_NAME` 可覆盖。

    为什么用环境变量而不是 conftest 里 monkeypatch：worker 进程读不到 pytest
    的 monkeypatch，只认环境变量 / .env。测试侧设ARQ_QUEUE_NAME=arq:queue:pytest，
    效果就是「同一个 Redis，不同的队列」。
    """
    import os
    return os.getenv(_QUEUE_NAME_ENV) or _DEFAULT_QUEUE


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
            # 🔴 default_queue_name 必须显式传：arq 默认是 'arq:queue'，
            #    写死的话测试永远往生产队列里塞东西。
            _pool = await create_pool(arq_redis_settings(),
                                       default_queue_name=current_queue_name())
    return _pool

async def close_pool()->None:
    global _pool,_redis_setting
    if _pool is not None:
        await _pool.aclose()
    _pool = None
    _redis_setting = None
