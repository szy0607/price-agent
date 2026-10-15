from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import ChatMessage, CartItem, OwnedItem
from app.schemas.chat_sche import ItemRefInSchema


async def add_message(user_id:int,conversation_id:int,role:str,content:str,session:AsyncSession,*,model:str|None=None) -> ChatMessage:
    message = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        model=model,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message
async def recent_messages(user_id:int,conversation_id:int,limit:int,session:AsyncSession) -> list[ChatMessage]:
    result = await session.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id,ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    return list(result.all())[::-1]

def trim_trailing_users(messages:list[ChatMessage]) -> list[ChatMessage]:
    """由于采用user信息先落库，如果出现模型调用失败，会导致连续两次user信息，部分模型不支持连续两次user信息"""
    end = len(messages)
    while end > 0 and messages[end-1].role == "user":
        end -= 1
    return messages[:end]
async def list_messages(user_id:int,conversation_id:int,limit:int,session:AsyncSession) -> list[ChatMessage]:
    """某个会话的全部历史，按 id 升序（前端直接顺序渲染）。

    与 recent_messages 的分工：那个给模型拼上下文用，倒序取最近 N 条再翻回来；
    这个给用户看历史用，正序取最多 limit 条。user_id 同时在 WHERE 里，
    归属不通过的会话根本查不到行。
    """
    result = await session.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id,ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc())
        .limit(limit)
    )
    return list(result.all())
async def fetch_items_for_refs(
        user_id: int, refs: list[ItemRefInSchema],
        session: AsyncSession) -> list[tuple[str, int, str, dict]]:
    """按 (src, id) 反查商品，返回顺序与 refs 严格一致。

    查不到 = 商品已删或不属于当前用户：报错，不静默跳过——用户挂 3 个
    实际生效 2 个，比一次 40001 难查得多。且不区分「不存在」和「不是
    你的」，统一文案「引用的商品不存在」，不暴露对方数据存在性
    （与 update_title 越权改的口径一致）。
    """
    cart_ids = [r.id for r in refs if r.src == "cart"]
    owned_ids = [r.id for r in refs if r.src == "owned"]
    found: dict[tuple[str, int], tuple[str, dict]] = {}
    if cart_ids:
        rows = await session.scalars(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.id.in_(cart_ids))
        )
        for row in rows:
            found[("cart", row.id)] = (row.name, row.specs)
    if owned_ids:
        rows = await session.scalars(
            select(OwnedItem).where(OwnedItem.user_id == user_id, OwnedItem.id.in_(owned_ids))
        )
        for row in rows:
            found[("owned", row.id)] = (row.name, row.specs)
    out: list[tuple[str, int, str, dict]] = []
    for r in refs:
        key = (r.src, r.id)
        if key not in found:
            raise BizError(ErrorCode.PARAM_INVALID, "引用的商品已变更，请刷新后重新添加")
        name, specs = found[key]
        out.append((r.src, r.id, name, specs))
    return out