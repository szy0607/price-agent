"""流式聊天服务：SSE 生成器 + 三段式 session。

三段（设计文档 §2.2）：
  阶段① 持连接，毫秒级：prepare_chat() 做完所有 DB 事，返回纯数据
  阶段② 零连接：stream_model() 逐块吐文本，同时累积到内存
  阶段③ 新开连接：persist_reply() 按最终状态落库

🔴 阶段③ 无论走哪个分支都必须执行（设计文档 §5.9）：
用户 abort 只是断开 HTTP 连接，服务端收到 GeneratorExit / CancelledError
之后**还要**开新 session 落库。漏了这步，用户看到「已停止」，一刷新消息就没了。

🔴 **取消后绝不能再 yield**：客户端已断开，yield 会抛
`RuntimeError: async generator ignored GeneratorExit`。所以取消分支的
「发 done 给前端」这一步做不到——前端只能靠重拉历史来确认落库（见§5.10）。
"""

import asyncio
import json
import logging

from fastapi import BackgroundTasks

from app.database.session import async_session_local
from app.repository import chat_repo
from app.schemas.chat_sche import ChatSendInSchema
from app.services import chat_service, model_call, profile_service
from app.services.chat_service import PreparedChat

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """拼一条 SSE 帧。

    **data 必须单行**：SSE 用空行分帧，payload 里的换行会被解析成新帧。
    json.dumps 关掉 ensure_ascii，否则中文变 \\uXXXX，可读性差且体积变大
    （模型回复是用户可见文本，不是要防注入的字段）。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _persist(user_id: int, prepared: PreparedChat, reply: str,
                   status: str, failure: str | None) -> int | None:
    """阶段③：新开 session 落库。落库失败只记日志不抛。

    抛出去是没用的：流已经开始（或已断），前端拿到的只会是一个断掉的连接，
    连「生成失败」都显示不出来。
    """
    try:
        async with async_session_local() as session:
            if failure is not None:
                # key 被厂商拒绝时要真的标失效——文案说的是「已标记为失效」，
                # 不真标就是骗用户。model_call/stream_model 已无 session，
                # 这个责任被上移到这里。
                await chat_service.mark_key_invalid_if_needed(
                    user_id, prepared.key, model_call.ModelCallError(failure), session)
            return await chat_service.persist_reply(
                user_id, prepared.conversation_id, reply,
                prepared.model_name, status, session)
    except Exception:
        logger.exception("stream persist failed conv=%s", prepared.conversation_id)
        return None


def _schedule_profile(background_tasks: BackgroundTasks, user_id: int,
                      conversation_id: int) -> None:
    """画像刷新挂在这里而不是阶段①：必须等 assistant 落库后才跑，
    否则 A6 读到的是「只有 user 没有 assistant」的半截对话。

    interrupted / failed 那轮也刷新——messages_for_profile 会把 interrupted
    换成事件占位、failed 整条排除，画像不会被半截内容污染。
    """
    background_tasks.add_task(profile_service.refresh_profile, user_id, conversation_id)


async def chat_stream(user_id: int, payload: ChatSendInSchema,
                      background_tasks: BackgroundTasks):
    """SSE 生成器。调用方只需 yield 出去。"""
    # ---------- 阶段①：持连接，全部 DB 事做完 ----------
    async with async_session_local() as session:
        prepared: PreparedChat = await chat_service.prepare_chat(user_id, payload, session)
    # ← 连接已归还池。阶段②③不再持有任何 session。

    # meta 必须先于任何文本发：前端拿到 conversation_id 才能把草稿标题转正，
    # 这是流式最大的体验增益（不用等模型答完）。
    yield _sse("meta", {"conversation_id": prepared.conversation_id,
                        "model": prepared.model_name})

    # ---------- 阶段②：零连接，流式生成 ----------
    collected: list[str] = []

    try:
        async for piece in model_call.stream_model(prepared.key, prepared.messages):
            collected.append(piece)
            yield _sse("delta", {"text": piece})
    except model_call.ModelCallError as exc:
        reply = "".join(collected)
        message_id = await _persist(user_id, prepared, reply,
                                    chat_repo.STATUS_FAILED, str(exc))
        _schedule_profile(background_tasks, user_id, prepared.conversation_id)
        # 流还开着（模型报错不等于连接断），所以能正常发 error + done。
        yield _sse("error", {"error": str(exc)})
        yield _sse("done", {"status": chat_repo.STATUS_FAILED, "message_id": message_id})
        return
    except (asyncio.CancelledError, GeneratorExit):
        # 用户 abort / 关页面 / 断连。与「模型失败」是两回事：这是用户主动喊停。
        #
        # ⚠️ 这里**不能 yield**（客户端已断开，yield 抛 RuntimeError），
        # 但**必须落库**——漏了这步，前端显示「已停止」，一刷新消息就没了。
        # 落库后直接 return，让生成器正常结束。
        await _persist(user_id, prepared, "".join(collected),
                       chat_repo.STATUS_INTERRUPTED, None)
        _schedule_profile(background_tasks, user_id, prepared.conversation_id)
        raise

    # ---------- 正常收完 ----------
    message_id = await _persist(user_id, prepared, "".join(collected),
                                chat_repo.STATUS_COMPLETED, None)
    _schedule_profile(background_tasks, user_id, prepared.conversation_id)
    yield _sse("done", {"status": chat_repo.STATUS_COMPLETED, "message_id": message_id})
