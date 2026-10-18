import asyncio
import logging
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_local
from app.services import model_call, rag_service
from app.services.api_key_service import KeyRecord

logger = logging.getLogger(__name__)
TOOL_NAME = "search_my_items"
MAX_ROUNDS = 2
# 🔴 实测（2026-10-18）：MAX_ROUNDS=2 时**5会撞 GraphRecursionError，6 才通**。
#   序列是：
#       START → decide(1) → search(2) → decide(3) → search(4) → decide(5) → END(6)
#                3 次 decide + 2 次 search + START + END = 6
#   漏掉的是**最后一次 decide**——round_no 满的那轮它仍要执行一次才能返回 END。
#   （2026-10-17 我写过「别按轮数直觉估」，当天自己又估错了。）
#
#   多留 2 的余量：撞上了是抛异常→流断→用户看到「生成失败」；
#   多留只是可能多跑一轮 decide（拿到工具次数上限后会自动给答案），代价小得多。
RECURSION_LIMIT = (MAX_ROUNDS + 1) * 2 + 2

SEARCH_TOOL = [{
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "检索用户自己的物品库（购物车 + 物品库 + 消费记录），"
            "找出与当前问题语义相关的物品及其参数。"
            "当用户问「我之前买过什么」「我有什么」「送人送什么好」"
            "这类需要了解他已有物品的问题时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于检索的关键词或一句话描述",
                }
            },
            "required": ["query"],
        },
    },
}]

class TextSink:
    """流式输出通道。图**外面**创建，节点闭包捕获它。

       🔴 为什么必须自己写而不是用 LangGraph 的事件流：
          `get_stream_writer()` 在 Python 3.10 下抛
          `Called get_config outside of a runnable context`（实测），
          而 `stream_mode="updates"` 只在节点结束后给最终值。
          自己做 sink 不依赖 contextvar，纯 Python，最稳。

       为什么要 `async def flush()`：它 `await asyncio.sleep(0)` 主动让出控制权。
          节点内部在 `await stream_model(...)` 时才会收到新文本；不让出的话，
          调用方的 while 循环永远拿不到 CPU → 又变成「转圈半天然后失败」。
       """
    def __init__(self) -> None:
        self._pending :list[str] = []
    def write(self, chunk: str) -> None:
        if chunk:
            self._pending.append(chunk)
    async def flush(self) -> list[str]:
        await asyncio.sleep(0)
        out,self._pending = self._pending,[]
        return out

def _append_messages(left: list, right: list) -> list:
    """把 right 追加到 left。**langgraph 会自动调用它**（见下面 Annotated）。

    🔴 **LangGraph 是有官方 reducer 的**（`Annotated[list, add_messages]`，
    见 langgraph/graph/message.py），我们**故意不用**它——实测它会把 dict 消息
    **转成 langchain 的 BaseMessage 对象**（HumanMessage / AIMessage / ToolMessage），
    而本项目 messages 全链路都是 dict：

        chat_service.prepare_chat → 产出 dict
        model_call.stream_model   → 入参要 dict
        chat_message 表→ 存 JSON

    用官方 reducer 就得把这三处全改成 BaseMessage。

    🔴 不用它**不代表 reducer 机制不能用**——`Annotated[list, 任何函数]` 都行，
       挂自己写的这个就行：拿到 LangGraph 的 reducer 机制（节点只return 增量），
       又保持全程 dict。**实测 3 条消息全是 dict。**

    🔴 不用 reducer 会怎样：LangGraph 默认把状态里的 list **整体覆盖**。
       节点 return `{round_no: 1}` 时`messages` 就丢了旧值 —— 静默丢历史，不报错。
    """
    return left + right


class RagState(TypedDict, total=False):
    """图的状态。`total=False` = 所有键可选（首次 ainvoke 只传 messages / user_id）。

    messages 挂 `_append_messages` 后，**节点只return 增量**即可：
        return {"messages": [新消息]}        # 不用再自己拼旧值
    """
    messages: Annotated[list, _append_messages]
    user_id: int
    round_no: int
    tool_calls: list# decide 交下来的待执行工具调用
    answer: str           # 最终回答全文


# 🔴 没配向量模型时，工具仍要定义，但 description 明说不可用。
#   为什么不能干脆不给工具：模型看不到工具时会自己编参数格式，
#   而「调了必然失败 → 模型输出检索失败 → 然后编一个答案」比
#   「明说没有检索能力」更糟。
#   不给的情况只有 round_no >= MAX_ROUNDS（见 decide）。
_DISABLED_TOOL = [{
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "⚠️ 此功能当前不可用：用户未配置向量模型。"
            "**不要调用它**，直接根据对话内容回答。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
}]

async def decide(state: RagState, sink: TextSink, key: KeyRecord,
                 session: AsyncSession) -> dict:
    """调模型（带工具定义），让它决定「调检索工具」还是「直接回答」。

    流式产出：文本增量写进 sink；工具调用收齐后放进 state。
    """
    messages = state["messages"]
    round_no = state.get("round_no", 0)
    user_id = state["user_id"]

    # 🔴 次数满了就**不给工具定义** —— 模型看不到工具就只能直接回答。
    #   这是「业务收尾」，与 recursion_limit（死循环兜底）职责不同。
    can_search = round_no < MAX_ROUNDS
    has_key = await rag_service.has_embedding_key(user_id, session)
    tools = SEARCH_TOOL if (can_search and has_key) else _DISABLED_TOOL

    pending: list[model_call.ToolCall] = []
    answer_parts: list[str] = []
    # 🔴 模型调用失败**往上抛**，让 LangGraph 报错，由 chat_stream 转成「生成失败」。
    #   这里**不要吞** —— 这是本次请求的失败，不是可降级的旁支。
    async for event in model_call.stream_model(key, messages, tools=tools):
        if event.kind == "text":
            answer_parts.append(event.text)
            sink.write(event.text)
        elif event.tool_call is not None:
            pending.append(event.tool_call)

    if pending:
        # 🔴 必须把 assistant 的 tool_calls 消息追加进 messages：
        #   OpenAI 协议要求下一条必须是配对的 role="tool"，否则请求被拒。
        assistant_msg = {
            "role": "assistant",
            "content": "".join(answer_parts) or None,
            "tool_calls": [{
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            } for tc in pending],
        }
        # 挂 reducer 后只返回增量，不用再拼旧值
        return {"messages": [assistant_msg], "tool_calls": pending}

    return {"messages": [], "tool_calls": [],
            "answer": "".join(answer_parts)}


async def search(state: RagState, session: AsyncSession) -> dict:
    """执行检索工具，把结果作为 role="tool" 消息追加进 messages。

    🔴 **失败不抛异常** —— 转成一句给模型看的文本。
       理由：异常会打断整个图，而模型可以自己换个说法重试。
       「把失败变成信息，而不是事故。」
    """
    calls = state.get("tool_calls") or []
    user_id = state["user_id"]
    new_messages: list[dict] = []

    for call in calls:
        query = str(call.parsed_arguments().get("query") or "").strip()
        try:
            rows = await rag_service.retrieve_relevant(user_id, query, session)
        except Exception:
            # retrieve_relevant 本身全异常自吞，走到这里说明是它之外的意外。
            # 同样吞：检索失败不该让整轮对话失败。
            logger.warning("检索工具执行异常 tool=%s", call.name, exc_info=True)
            rows = []

        if rows:
            block = "\n".join(
                f"- {r['name']}"
                + ("｜" + "；".join(f"{k}: {v}" for k, v in (r.get("specs") or {}).items())
                   if r.get("specs") else "")
                for r in rows
            )
            text = f"检索到 {len(rows)} 件相关物品：\n{block}"
        elif not query:
            text = "检索失败：没有提供检索关键词。"
        else:
            text = ("检索未找到相关物品（可能用户尚未配置向量模型，"
                    "或物品库里没有相关内容）。请基于已有信息回答，不要编造检索结果。")

        new_messages.append({
            "role": "tool", "tool_call_id": call.id, "content": text,
        })

    return {"messages": new_messages,
            "round_no": state.get("round_no", 0) + 1,
            "tool_calls": []}


def route(state: RagState) -> str:
    """有工具调用 → search，没有 → END。"""
    return "search" if state.get("tool_calls") else END


def build_graph(key: KeyRecord, sink: TextSink):
    """按本次运行的依赖构造并编译图。**每次调用得到独立的图**。

    🔴 为什么要闭包：`add_node` 只传 `(state)`，不给你传额外参数。
       想把 sink / key 送进节点，Python 原生办法只有闭包或 contextvar。
       **闭包最简单**，而每次 compile() 构造新图正好实现隔离——
       两个用户同时对话时各自的 sink 互不干扰。
    """
    async def node_decide(state: RagState) -> dict:
        async with async_session_local() as session:
            return await decide(state, sink, key, session)

    async def node_search(state: RagState) -> dict:
        async with async_session_local() as session:
            return await search(state, session)

    g = StateGraph(RagState)
    g.add_node("decide", node_decide)
    g.add_node("search", node_search)
    g.add_edge(START, "decide")
    g.add_conditional_edges("decide", route, {"search": "search", END: END})
    g.add_edge("search", "decide")
    return g.compile()
