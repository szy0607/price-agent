from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode, success
from app.dependence import CurrentUser, get_db_session, require_same_origin_write
from app.repository import chat_repo, conversation_repo
from app.schemas.chat_sche import MessageOutSchema
from app.schemas.conversation_sche import ConversationOutSchema, ConversationTitleInSchema

conversation_router = APIRouter(tags=["conversation"], prefix="/conversations")


@conversation_router.get("")
async def list_conversations(user: CurrentUser,
                             limit: int = Query(default=50, ge=1, le=100),
                             session: AsyncSession = Depends(get_db_session)):
    """会话列表（侧栏）。纯读：登录态即归属，WHERE 再带 user_id 双保险。

    limit 兜底 100：会话数不封顶时全量拉走只会拖慢首屏，侧栏一次也只看得完几十条。
    """
    rows = await conversation_repo.list_conversations(user.id, limit, session)
    return success([ConversationOutSchema.model_validate(r) for r in rows])


@conversation_router.get("/{conversation_id}/messages")
async def list_messages(conversation_id: int, user: CurrentUser,
                        limit: int = Query(default=200, ge=1, le=500),
                        session: AsyncSession = Depends(get_db_session)):
    """某个会话的历史消息，按时间正序。

    先验会话归属再查消息：不属其时报「会话不存在」——与 send_message 对
    conversation_id 的口径一致，不暴露「会话存在但是别人的」。
    """
    conversation = await conversation_repo.get_conversation(user.id, conversation_id, session)
    if conversation is None:
        raise BizError(ErrorCode.PARAM_INVALID, "会话不存在")
    rows = await chat_repo.list_messages(user.id, conversation_id, limit, session)
    return success([MessageOutSchema.model_validate(r) for r in rows])


@conversation_router.patch("/{conversation_id}/title", dependencies=[Depends(require_same_origin_write)])
async def update_title(conversation_id: int, data: ConversationTitleInSchema,
                       user: CurrentUser, session: AsyncSession = Depends(get_db_session)):
    row = await conversation_repo.update_title(conversation_id, data.title, user.id, session)
    return success(ConversationOutSchema.model_validate(row))
