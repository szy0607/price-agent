from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.repository import conversation_repo, chat_repo
from app.schemas.chat_sche import ChatSendInSchema, ChatSendOutSchema
from app.services import model_call, profile_service
from fastapi import BackgroundTasks
SYSTEM_PROMPT = (
    "你是智能导购助手。用简洁中文回答用户的购物问题，说明关键取舍。"
    "你没有实时商品、库存、价格或优惠券数据；不得声称已经查询、验证或采集这些信息，"
    "不得编造具体到手价、券、口令或购买链接。涉及价格时提醒用户以商品页面为准。"
)
_TITLE_MAX = 100
_HISTORY_LIMIT = 12

def _fallback_title(text:str)->str:
    folded = " ".join(text.split())
    trimmed = folded.strip("。！？!?.,，；;：:、~～… ")
    return trimmed[:_TITLE_MAX] or "新咨询"

# 历史按总字符截断，防 12 条 × 4000 字把模型上下文撑爆（中文约 5~9 万 token，
# 会超部分模型上下文）；与 profile_service 的 A6 输入预算同构：都从最新往旧留
def _cap_history(messages: list, cap: int = 8000) -> list:
    total, kept = 0, []
    for m in reversed(messages):          # 从最近的开始留
        total += len(m.content)
        if total > cap:
            break
        kept.append(m)
    return kept[::-1]


def _format_item(src: str, item_id: int, name: str, specs: dict) -> str:
    safe_name = " ".join(name.split())
    pairs = "；".join(f"{k}: {v}" for k, v in (specs or {}).items())
    head = f"{src}#{item_id} {safe_name}"
    return f"{head}｜{pairs}" if pairs else head
async def send_message(user_id: int, payload: ChatSendInSchema,session: AsyncSession,background_tasks: BackgroundTasks)->ChatSendOutSchema:
    if payload.conversation_id is None:
        conversation = await conversation_repo.create_conversation(
            user_id, _fallback_title(payload.text), session)
    else:
        conversation = await conversation_repo.get_conversation(
            user_id, payload.conversation_id, session)
        if conversation is None:
            raise BizError(ErrorCode.PARAM_INVALID, "会话不存在")
    conversation_id = conversation.id
    await chat_repo.add_message(user_id, conversation_id, "user",payload.text, session)
    items = await chat_repo.fetch_items_for_refs(user_id, payload.item_refs, session)
    history = _cap_history(chat_repo.trim_trailing_users(
        await chat_repo.recent_messages(user_id, conversation_id, _HISTORY_LIMIT, session)))
    profile_context = await profile_service.load_profile_context(user_id, session)
    system = SYSTEM_PROMPT if not profile_context else f"{SYSTEM_PROMPT}\n\n{profile_context}"
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    current = payload.text
    if items:
        block = "\n".join(_format_item(src, item_id, name, specs)
                          for src, item_id, name, specs in items)
        current = f"【用户引用商品】\n{block}\n\n{current}"
    messages.append({"role": "user", "content": current})
    try:
        reply, model = await model_call.call_model(user_id, messages, session)
    except model_call.ModelCallError as exc:
        # str(exc) 透传：model_call 的报错全是用户可读中文，无 key/base_url
        # 泄漏（10-13 P0 口径，别一刀切覆盖成笼统文案）。
        raise BizError(ErrorCode.INTERNAL, str(exc)) from exc

    # assistant 落库 + 推进会话 update_time（否则列表排序停摆，见 touch 注释）
    await chat_repo.add_message(user_id, conversation_id, "assistant", reply,
                                session, model=model)
    await conversation_repo.touch_conversation( user_id, conversation_id,session)
    background_tasks.add_task(profile_service.refresh_profile, user_id, conversation_id)
    return ChatSendOutSchema(conversation_id=conversation_id, reply=reply, model=model)