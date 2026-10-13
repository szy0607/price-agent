from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.core.rate_limit import check_rate_limit
from app.dependence import CurrentUser, require_same_origin_write, get_db_session
from app.schemas.chat_sche import ChatInSchema
from app.services import chat_service

chat_router = APIRouter(prefix="/chat", tags=["chat"])

# 咨询直接花用户自己的模型额度，比传一张图贵：每用户 60 秒 6 次
_CHAT_LIMIT = 6
_CHAT_WINDOW = 60


@chat_router.post("/message", dependencies=[Depends(require_same_origin_write)])
async def message(payload: ChatInSchema, user: CurrentUser,
                  session: AsyncSession = Depends(get_db_session)):
    check_rate_limit(f"chat:{user.id}", limit=_CHAT_LIMIT, window=_CHAT_WINDOW)
    return success(await chat_service.answer(user.id, payload.messages, payload.record_ids, session))
