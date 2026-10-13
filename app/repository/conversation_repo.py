from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import Conversation


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
