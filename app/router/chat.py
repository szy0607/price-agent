from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.core.rate_limit import check_rate_limit
from app.dependence import CurrentUser, require_same_origin_write, get_db_session
from app.schemas.chat_sche import ChatSendInSchema
from app.services import chat_service, chat_stream

chat_router = APIRouter(prefix="/chat", tags=["chat"])


_CHAT_LIMIT = 6
_CHAT_WINDOW = 60

# SSE 禁用一切代理缓冲：X-Accel-Buffering 是给 nginx 看的，
# Cache-Control: no-cache 兜住其余代理。少了这两行，流会被攒成一坨再一次性吐出，
# 表现为「有流式代码但还是整段出现」。
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@chat_router.post("/message", dependencies=[Depends(require_same_origin_write)])
async def message(payload: ChatSendInSchema, user: CurrentUser,
                  background_tasks: BackgroundTasks,
                  session: AsyncSession = Depends(get_db_session)):
    """非流式。保留作旧端点与外部脚本的后路（设计文档 §5.1）。"""
    check_rate_limit(f"chat:{user.id}", limit=_CHAT_LIMIT, window=_CHAT_WINDOW)
    return success(await chat_service.send_message(user.id, payload, session, background_tasks))


@chat_router.post("/stream", dependencies=[Depends(require_same_origin_write)])
async def stream(payload: ChatSendInSchema, user: CurrentUser,
                  background_tasks: BackgroundTasks):
    """流式（SSE）。设计文档 docs/流式输出-设计.md。

    🔴 **刻意不 Depends(get_db_session)**：那个yield 依赖在整个响应完成后才清理，
    而 SSE 响应要持续几十秒 → 连接会被整条流占住，pool_size=10 的话10 个并发
    就吃满池子。数据库访问由 chat_stream 自己在三段里开关 session。

    客户端约束见设计文档 §5.8：必须 fetch + ReadableStream，禁止 EventSource
    （它不支持自定义头，而 require_same_origin_write 只认 X-Requested-With）。
    """
    check_rate_limit(f"chat:{user.id}", limit=_CHAT_LIMIT, window=_CHAT_WINDOW)
    return StreamingResponse(
        chat_stream.chat_stream(user.id, payload, background_tasks),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
