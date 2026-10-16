"""聊天服务：非流式与流式共用的两段式逻辑。

分工（大宋 2026-10-16 拍板「三段式session」）：
  阶段① prepare_chat()  —— 建/查会话、拉历史、取画像、取 KeyRecord、写 user 消息
                            **全程持连接，出函数前把ORM 行压成纯数据**
  阶段② （在 chat_stream 的生成器里）—— 纯内存 + 模型流式，**零连接**
  阶段③ persist_reply()  —— 写 assistant + status、touch 会话

为什么要拆开：SSE 是一个持续几十秒的响应，若用 Depends(get_db_session) 的
yield session，连接会被整条流占住；pool_size=10 的话 10 个并发就吃满池子，
第 11 个用户等30 秒后 pool_timeout 报错（设计文档 §2.1、§2.5）。
"""

from dataclasses import dataclass

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.repository import chat_repo, conversation_repo
from app.schemas.chat_sche import ChatSendInSchema, ChatSendOutSchema
from app.services import api_key_service, model_call, profile_service
from app.services.api_key_service import KeyRecord

SYSTEM_PROMPT = (
    "你是智能导购助手。用简洁中文回答用户的购物问题，说明关键取舍。"
    "你没有实时商品、库存、价格或优惠券数据；不得声称已经查询、验证或采集这些信息，"
    "不得编造具体到手价、券、口令或购买链接。涉及价格时提醒用户以商品页面为准。"
)
_TITLE_MAX = 100
_HISTORY_LIMIT = 12


def _fallback_title(text: str) -> str:
    folded = " ".join(text.split())
    trimmed = folded.strip("。！？!?.,，；;：:、~～… ")
    return trimmed[:_TITLE_MAX] or "新咨询"


# 历史按总字符截断，防 12 条 × 4000 字把模型上下文撑爆（中文约 5~9 万 token，
# 会超部分模型上下文）；与 profile_service 的 A6 输入预算同构：都从最新往旧留。
# 注意入参是 dict（repo 已压平），取content 用下标不是属性。
def _cap_history(messages: list, cap: int = 8000) -> list:
    total, kept = 0, []
    for m in reversed(messages):          # 从最近的开始留
        total += len(m["content"])
        if total > cap:
            break
        kept.append(m)
    return kept[::-1]


def _format_item(src: str, item_id: int, name: str, specs: dict) -> str:
    safe_name = " ".join(name.split())
    pairs = "；".join(f"{k}: {v}" for k, v in (specs or {}).items())
    head = f"{src}#{item_id} {safe_name}"
    return f"{head}｜{pairs}" if pairs else head


@dataclass
class PreparedChat:
    """阶段①的产物。**全部是纯数据**，不含任何 ORM 实例 / session。

    阶段②③ 只碰这个对象，所以它们可以在 session 完全关闭之后安全执行。
    """

    conversation_id: int
    messages: list[dict]     # 拼好的模型输入（含 system / 历史 / 本轮 user）
    key: KeyRecord
    model_name: str


async def prepare_chat(user_id: int, payload: ChatSendInSchema,
                       session: AsyncSession) -> PreparedChat:
    """阶段①：所有需要 DB 的事都在这里做完，返回纯数据。

    调用方负责在本函数返回后**关闭 session**；返回对象里没有 detached 隐患。
    """
    items = await chat_repo.fetch_items_for_refs(user_id, payload.item_refs, session)
    if payload.conversation_id is None:
        conversation = await conversation_repo.create_conversation(
            user_id, _fallback_title(payload.text), session)
    else:
        conversation = await conversation_repo.get_conversation(
            user_id, payload.conversation_id, session)
        if conversation is None:
            raise BizError(ErrorCode.PARAM_INVALID, "会话不存在")
    conversation_id = conversation.id

    # 只认 completed：失败/中断的 assistant 不进上下文（设计文档 §0）
    history = _cap_history(chat_repo.trim_trailing_users(
        await chat_repo.messages_for_context(user_id, conversation_id, _HISTORY_LIMIT, session)))
    profile_context = await profile_service.load_profile_context(user_id, session)
    system = SYSTEM_PROMPT if not profile_context else f"{SYSTEM_PROMPT}\n\n{profile_context}"
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": m["role"], "content": m["content"]} for m in history)
    current = payload.text
    if items:
        block = "\n".join(_format_item(src, item_id, name, specs)
                          for src, item_id, name, specs in items)
        current = f"【用户引用商品】\n{block}\n\n{current}"
    await chat_repo.add_message(user_id, conversation_id, "user", current, session)
    messages.append({"role": "user", "content": current})

    key = await api_key_service.key_for_call(user_id, session)
    return PreparedChat(
        conversation_id=conversation_id,
        messages=messages,
        key=key,
        model_name=key.model_name,
    )


async def persist_reply(user_id: int, conversation_id: int, reply: str,
                        model: str | None, status: str,
                        session: AsyncSession) -> int | None:
    """阶段③：写 assistant 消息 + touch 会话。返回消息 id（空文本时返回 None）。

    **空文本不落库**（设计文档 §1.3）：content 是 NOT NULL 的 Text，空串进上下文会让
    模型看到一个空回复、行为不可预期；而「不落库」让历史自然变成连续两条 user，
    由 trim_trailing_users 顺手修好，不需要额外判断。
    """
    if not reply.strip():
        return None
    message = await chat_repo.add_message(
        user_id, conversation_id, "assistant", reply, session,
        model=model, status=status)
    # 推进会话 update_time，否则列表排序停摆（见 touch 注释）。
    # 只在真正落了库时才 touch：空回复那轮不该把会话顶到最前。
    await conversation_repo.touch_conversation(user_id, conversation_id, session)
    return message.id


async def send_message(user_id: int, payload: ChatSendInSchema,
                       session: AsyncSession,
                       background_tasks: BackgroundTasks) -> ChatSendOutSchema:
    """非流式链路 POST /chat/message。保留作旧端点与外部脚本的后路（设计文档 §5.1）。"""
    prepared = await prepare_chat(user_id, payload, session)
    try:
        reply, model = await model_call.call_model(prepared.key, prepared.messages)
    except model_call.ModelCallError as exc:
        # str(exc) 透传：model_call 的报错全是用户可读中文，无 key/base_url。
        # 🔴 key 失效标记的责任在这里（call_model 已无 session）：文案写的是
        # 「已标记为失效」，不真的标记就是骗用户。
        await mark_key_invalid_if_needed(user_id, prepared.key, exc, session)
        raise BizError(ErrorCode.INTERNAL, str(exc)) from exc
    await persist_reply(user_id, prepared.conversation_id, reply, model,
                        chat_repo.STATUS_COMPLETED, session)
    background_tasks.add_task(profile_service.refresh_profile, user_id,
                              prepared.conversation_id)
    return ChatSendOutSchema(
        conversation_id=prepared.conversation_id,
        reply=reply,
        model=model,
    )


async def mark_key_invalid_if_needed(user_id: int, key: KeyRecord, exc: Exception,
                                     session: AsyncSession) -> None:
    """仅当模型因 401/403 拒绝时才把 key 标失效。

    call_model / stream_model 现在只抛带提示的 ModelCallError（不带状态码，也没有
    session 可用），所以责任上移到调用方——用文案判定，文案常量两边成对，
    改model_call 那句要同步改这里。

    标记失败只吞不抛：标记是善后动作，不能盖掉真正的错误。
    """
    if "key 已被厂商拒绝" not in str(exc):
        return
    try:
        await api_key_service.mark_invalid(key.key_id, user_id, session)
        await session.commit()
    except Exception:
        pass
