from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode, success
from app.dependence import CurrentUser, get_db_session, require_same_origin_write
from app.repository import chat_repo, conversation_repo
from app.schemas.chat_sche import MessageOutSchema
from app.schemas.conversation_sche import ConversationOutSchema, ConversationTitleInSchema
from app.services import index_service, rag_service

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


@conversation_router.get("/rag-index-status")
async def rag_index_status(user: CurrentUser,
                           session: AsyncSession = Depends(get_db_session)):
    """对话页那条提示的数据源（2026-10-18，大宋拍板：提示放对话页，不放商品列表）。

    返回三个字段，前端据此给三种文案：

    | 字段 | 值 | 前端文案 |
    |---|---|---|
    | `has_key` | false | 「未配置向量模型，检索增强未启用」 |
    | `pending` | > 0 | 「向量库正在更新中，检索结果可能不完整」 |
    | 以上都正常 | — | **不显示** |

    🔴 **为什么挂 /conversations 下而不是 /settings**：它是「对话页要用的状态」，
    不是配置项本身。挂进 settings 会让那个接口含义变浑。

    ⚠️ **实测纠正（2026-10-18）**：我原以为「静态路径必须声明在动态路径前面」
    否则会被 `/{conversation_id}/messages` 拦截——**实测不成立**，
    FastAPI 按路径匹配（静态段优先于动态段），声明顺序不影响。
    所以本端点放在哪都行，放在这里是因为它跟对话相关、读起来顺。

    🔴 **pending 统计故意不含 RUNNING 的超时判断**：这里只数「还没 SYNCED 的」，
    够前端决定显不显示提示了。真正的超时判定在 worker_reaper 那边，
    两处口径不同是有意的——**这个接口是「给用户看的现状」，不是「该不该重投」**。
    """
    has_key = await rag_service.has_embedding_key(user.id, session)

    # 🔴 用 `!= SYNCED` 而不是 `in (PENDING, RUNNING, FAILED)`：
    #   前者**新增状态值时自动纳入**（比如将来加 INDEXING），后者会漏掉。
    #   「还没 SYNCED」这个定义天然涵盖所有未完成态。
    pending = 0
    for model in index_service._MODELS.values():
        count = await session.scalar(
            select(func.count(model.id))
            .where(model.user_id == user.id,
                   model.index_status != index_service.SYNCED)
        )
        pending += int(count or 0)

    return success({
        "has_key": has_key,
        "pending": pending,
        "retrievable": has_key and pending == 0,
    })


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
