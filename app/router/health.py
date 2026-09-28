import asyncio
import logging
from sqlalchemy import text
from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.core.errors import ErrorCode, success
from app.database.session import async_engine

logger = logging.getLogger(__name__)
health_router = APIRouter(tags=["health"])
_DB_PROBE_TIMEOUT = 5.0
async def _probe_db()->None:
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
@health_router.get("/health")
async def health_check()->JSONResponse:
    try:
        await asyncio.wait_for(_probe_db(),timeout=_DB_PROBE_TIMEOUT)
    except Exception as exc:
        logger.warning("健康检查失败：%s", type(exc).__name__)
        return JSONResponse(status_code=503,content={"code":ErrorCode.INTERNAL,"msg":"服务不可用","data":None},)

    return JSONResponse(status_code=200,content=success({"status":"ok"}))
