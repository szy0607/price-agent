import logging

from app.core.config import settings
from app.core.http_client import start_http_client, close_http_client
from app.core.redis_client import close_pool, arq_redis_settings
from app.database.pg_session import start_pg_engine, close_pg_engine
from app.services.index_service import sync_one

logger = logging.getLogger(__name__)

async def startup(ctx:dict)->None:
    """HTTP客户端+pg引擎"""
    start_http_client()
    start_pg_engine()
    logger.info("HTTP客户端+pg_url已配=%s",bool(settings.pg_url))


async def shutdown(ctx:dict)->None:
    await close_pool()
    await close_http_client()
    await close_pg_engine()



class WorkerSettings:
    functions = [sync_one]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = arq_redis_settings()
    # job_timeout 必须 > embedding 单次调用的 20 秒 HTTP timeout，
    # 否则任务被 arq 砍掉而模型调用还在跑（任务判失败但向量实际已写入 PG）
    job_timeout = 60
    max_tries = 3
    retry_jobs = True
