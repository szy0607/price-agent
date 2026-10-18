"""流式聊天服务：SSE 生成器 + 三段式 session。

三段（设计文档 §2.2）：
  阶段① 持连接，毫秒级：prepare_chat() 做完所有 DB 事，返回纯数据
  阶段② 零连接：**跑 LangGraph**，同时从 sink 轮询文本增量
  阶段③ 新开连接：persist_reply() 按最终状态落库

🔴 阶段② 编排归LangGraph，不在这里手写（2026-10-18 改）：
  `app/agents/a1_graph.py` 的 decide 节点自己决定要不要调工具（当前只有检索）。
  本模块只做三件事：建图、轮询 sink 转发 SSE、兜住取消与异常。
  **别在这里展开工具循环** —— 那是编排，会让本模块同时承担两层职责。

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

from app.agents import a1_graph
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
                   status: str, failure: str | None,
                   new_messages: list[dict] | None = None) -> list[int]:
    """阶段③：新开 session 落库。落库失败只记日志不抛。

    抛出去是没用的：流已经开始（或已断），前端拿到的只会是一个断掉的连接，
    连「生成失败」都显示不出来。

    🔴 2026-10-18：返回类型从 `int | None` 变成 **list[int]**，因为工具化后
    一轮会落多条（assistant(tool_calls) / tool / assistant）。
    调用方自己取最后一条当 message_id 塞进 SSE 的 done 事件。

    `new_messages` 非空走 persist_graph_messages（逐条落 + 补 tool 占位），
    为空走 persist_reply（单条，与非流式链路同一条路径）。
    """
    try:
        async with async_session_local() as session:
            if failure is not None:
                # key 被厂商拒绝时要真的标失效——文案说的是「已标记为失效」，
                # 不真标就是骗用户。model_call/stream_model 已无 session，
                # 这个责任被上移到这里。
                await chat_service.mark_key_invalid_if_needed(
                    user_id, prepared.key, model_call.ModelCallError(failure), session)
            if new_messages:
                return await chat_service.persist_graph_messages(
                    user_id, prepared.conversation_id, new_messages,
                    reply, prepared.model_name, status, session)
            message = await chat_service.persist_reply(
                user_id, prepared.conversation_id, reply,
                prepared.model_name, status, session)
            return [message] if message else []
    except Exception:
        logger.exception("stream persist failed conv=%s", prepared.conversation_id)
        return []


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

    # ---------- 阶段②：零连接，跑图 + 流式吐字 ----------
    # 🔴 2026-10-18：从「直接调模型」改成「跑 LangGraph」。
    #    图自己决定要不要调工具（见 app/agents/a1_graph.py）。
    #
    # 🔴 **为什么必须用 sink 而不是 astream 的事件**：
    #    节点的文本通过 `sink.write()` 出来（`get_stream_writer` 在 Python 3.10
    #    下抛 `Called get_config outside of a runnable context`，实测），
    #    而 `stream_mode="updates"` 只在**节点结束后**给最终值、拿不到过程。
    #    所以只能「并发跑图 + 同时轮询 sink」。
    collected: list[str] = []
    sink = a1_graph.TextSink()
    graph = a1_graph.build_graph(prepared.key, sink)
    run_task: asyncio.Task | None = None

    try:
        run_task = asyncio.create_task(
            graph.ainvoke(
                {
                    "messages": list(prepared.messages),
                    "user_id": user_id,
                    "round_no": 0,
                },
                # 🔴 必须显式传。LangGraph 1.2.4 默认 10007（不是 0.x 的 25），
                #    不设 = 死循环 ≈ 4 小时 + 烧钱。compile() 上**不能**传这个参数。
                config={"recursion_limit": a1_graph.RECURSION_LIMIT},
            )
        )
        # 图在跑的同时轮询 sink。实测可行：拿到 8 块文本。
        while not run_task.done():
            for piece in await sink.flush():
                collected.append(piece)
                yield _sse("delta", {"text": piece})
            # 🔴 这个 sleep(0) 不能省：不让出控制权的话，图里的节点永远拿不到
            #    CPU → 前端看到「转圈半天然后失败」。
            await asyncio.sleep(0)

        # 🔴 循环退出时图可能刚写完最后一块、还没被 flush 走 —— **必须再取一次**。
        #    实测漏掉这次会丢最后几个字，表现为「每次回答结尾被截断」，且不报错。
        for piece in await sink.flush():
            collected.append(piece)
            yield _sse("delta", {"text": piece})

        final_state = await run_task
    except (asyncio.CancelledError, GeneratorExit):
        # 用户 abort / 关页面 / 断连。与「模型失败」是两回事：这是用户主动喊停。
        #
        # 🔴 实测（2026-10-18）：`task.cancel()` 会把 CancelledError **传进节点里**，
        #    所以节点自己知道被取消。这里 cancel 之后只是**不让它继续跑**。
        if run_task is not None and not run_task.done():
            run_task.cancel()
        try:
            if run_task is not None:
                await run_task
        except (asyncio.CancelledError, Exception):
            # 🔴 这里必须吞：取消态下 `await` 被 cancel 的 task 会立刻抛，
            #    不吞的话异常会冒出去，**下面的 _persist 永远执行不到** ——
            #    用户看到「已停止」，一刷新消息就没了。
            #    吞不是「忽略错误」：任务本来就已取消，这里只是不让它打断收尾。
            pass
        # ⚠️ 这里**不能 yield**（客户端已断开，会抛
        #    `RuntimeError: async generator ignored GeneratorExit`），但**必须落库**。
        await _persist(user_id, prepared, "".join(collected),
                       chat_repo.STATUS_INTERRUPTED, None)
        _schedule_profile(background_tasks, user_id, prepared.conversation_id)
        raise
    except Exception as exc:
        # 图跑失败（模型报错 / PG 挂了 / SQL 写错……）统一走这里。
        # 🔴 不用再单独 except model_call.ModelCallError：LangGraph 把节点里
        #    抛的异常原样透传，统一兜住更不容易漏。
        if run_task is not None and not run_task.done():
            run_task.cancel()
        # 🔴 只有 ModelCallError 才可能意味着「key 被厂商拒绝」。
        #    其他异常（如 BizError「未配置向量库」）传 None，
        #    否则 mark_key_invalid_if_needed 会误把好 key 标成失效。
        failure = str(exc) if isinstance(exc, model_call.ModelCallError) else None
        ids = await _persist(user_id, prepared, "".join(collected),
                             chat_repo.STATUS_FAILED, failure)
        _schedule_profile(background_tasks, user_id, prepared.conversation_id)
        # 流还开着（模型报错不等于连接断），所以能正常发 error + done。
        yield _sse("error", {"error": str(exc)})
        yield _sse("done", {"status": chat_repo.STATUS_FAILED,
                            "message_id": ids[-1] if ids else None})
        return

    # ---------- 正常收完 ----------
    # 🔴 用 final_state["answer"] 而不是 collected：
    #    模型可能「先吐一句『让我查一下』→ 调工具 → 再吐最终答案」，
    #    这时 collected 是**两段拼在一起的中间态**，而 answer 是干净的最终回答。
    final_reply = final_state.get("answer") or "".join(collected)
    #🔴 切片取「图新增的那几条」：final_state["messages"] 开头是
    #    prepare_chat 已经落过的 system / user / 历史——全量落会把整个历史
    #    重复插一遍，会话里凭空多出几十条重复消息。
    prior_count = len(prepared.messages)
    new_messages = final_state.get("messages", [])[prior_count:]
    ids = await _persist(user_id, prepared, final_reply,
                         chat_repo.STATUS_COMPLETED, None, new_messages)
    _schedule_profile(background_tasks, user_id, prepared.conversation_id)
    yield _sse("done", {"status": chat_repo.STATUS_COMPLETED,
                        "message_id": ids[-1] if ids else None})
