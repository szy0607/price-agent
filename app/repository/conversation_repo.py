from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import Conversation
from app.core.time import get_current_time

async def update_title(
        conversation_id: int, title: str, user_id: int,
        session: AsyncSession) -> Conversation:
    """改会话标题。纯 SQL：rowcount=0 即「行不存在或不是你的」。

    WHERE 必须同时带 id 和 user_id —— 只按 id 过滤的话，任何人传别人的
    conversation_id 都能改掉他的会话名。rowcount 判据取自
    api_key_service.delete_api_key，同一种归属校验两种写法。
    """
    result = await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .values(title=title)
    )
    if result.rowcount == 0:  # type: ignore
        await session.rollback()   # 没匹配到任何行，但把这次空更新收干净再报错
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    await session.commit()
    row = await session.get(Conversation, conversation_id)
    return row
async def create_conversation(user_id:int,title:str,session:AsyncSession) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=title,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation
async def get_conversation(user_id:int,conversation_id:int,session:AsyncSession) -> Conversation | None:
    result = await session.scalars(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    return result.first()
async def touch_conversation(user_id:int,conversation_id:int,session:AsyncSession) :

    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .values(update_time=get_current_time())
    )
    await session.commit()
async def list_conversations(user_id:int,limit:int,session:AsyncSession) -> list[Conversation]:
    """当前用户的会话列表，最近更新的在前。

    update_time 由 send_message 末尾的 touch_conversation 推进，所以排序即
    「最近聊过」；同秒内 touch 的会话用 id desc 兜底定序，避免翻页时抖动。
    """
    result = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.update_time.desc(), Conversation.id.desc())
        .limit(limit)
    )
    return list(result.all())