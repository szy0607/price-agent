"""A1 编排图 —— 理解 / 路由（主管）。

    🔴 **2026-10-18 大宋拍板：从 `rag_graph.py` 改名为 `a1_graph.py` 并重新定位。**

    ## 为什么改名

    原名 `rag_graph` 是在只有「检索」一个节点时起的，加进对比节点后名不副实——
    而且 **`decide` 节点从一开始干的就是 A1 的活**（`Agent编号约定.md` §1 定义
    A1 = 「理解 / 路由（主管）——判断用户这句话该交给谁」）：
    它调模型、看模型决定调什么工具、决定调几次。**RAG 只是它目前掌握的一个工具。**

    继续叫 `rag_graph` 会让后面的人困惑：「为什么对比功能在 RAG 文件里？」

    ## 为什么工具必须在同一个图里（硬约束，不是偏好）

    把 compare 独立成另一个图 → 它与本图之间**没有状态通道**，`messages` 传不过去
    → 得自己造队列 / 缓存 → **那就是手写编排**
    → 又回到「在一个用编排框架的项目里手写编排」（2026-10-18 大宋撤回「固定前置」的理由）。

    ## 当前实现进度

    ```
    START → decide ─┬─ 要检索 → search ─┐
                    └─ 直接答 → END      ↓
                          decide（把检索结果带进上下文）
    ```

    - ✅ `search`：调`rag_service.retrieve_relevant`
    - ⬜ `compare`：A4 参数对比（docs/A4对比与A5推荐-设计.md）
    - ⬜ `recommend`：A5 推荐（走博查联网）
    - ⬜ `card`：商品卡片（docs/对话侧商品卡片-设计.md）

    ⚠️ **加节点后 `MAX_ROUNDS` 与 `RECURSION_LIMIT` 必须重算并实测**——
    见下方常量处的实测记录（我按轮数直觉算错过一次）。

    ## 🔴 为什么节点用 TextSink 而不是 LangGraph 的 get_stream_writer
    实测 `get_stream_writer()` 在 **Python 3.10 下必然抛**
    `RuntimeError: Called get_config outside of a runnable context`
    （根因 `langgraph/_internal/_runnable.py:483-492`：3.10 那条分支不 set contextvar）。
    而 `stream_mode="updates"` 只在节点**结束后**给最终值、拿不到过程。
    **所以自己做 sink**：纯 Python、不依赖 contextvar、最稳。
    将来若升级到 Python 3.11+，可改用 get_stream_writer 把这层删掉。
"""

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
COMPARE_TOOL_NAME = "compare_items"
MAX_COMPARE_ITEMS = 3      # 🔴 大宋 22:40 拍板：对比最多 3 件

# 🔴 每种工具的次数上限。**分开计数**，不用一个 MAX_ROUNDS：
#   - 检索不花钱（用用户自己的 embedding key），所以可以多来几次
#   - 对比要联网（3 次博查 ≈ 0.108 元），所以卡死
#   混成一个数字的话，以后加「花钱的工具」就没法单独限了。
MAX_SEARCH_ROUNDS = 2
MAX_COMPARE_ROUNDS = 1

# 🔴 实测（2026-10-18，加compare 节点后重新实测）：
#   最坏路径 = 检索 2 次 + 对比 1 次 + 收尾的 decide：
#       START → decide(1) → search(2) → decide(3) → search(4)
#            → decide(5) → compare(6) → decide(7) → END
#       **limit=5 撞 GraphRecursionError，6 也撞，7 才通。**
#
#   🔴 我原来的公式 `(MAX_ROUNDS+1)*2+2` 算出来的 8 是**错的**——实测 8 通、7 也通，
#      说明真正需要的是 7。多留 1 变成 8 属于保守余量，能用，但**理由得写对**。
#
#   🔴 **两次都算错的教训**（2026-10-17 按轮数×2 算 5；这次按边数算 8）：
#      **`START` 不算super-step**，只有节点执行才算。
#      所以公式是「节点执行次数」而不是「边数」或「轮数×2」：
#          总节点执行 = decide 次数 + 工具节点次数
#          decide 次数 = 工具次数 + 1（最后一次它要返回 END）
#          节点执行 = 2×工具次数 + 1
#      最坏情况 = 2×(MAX_SEARCH + MAX_COMPARE) + 1 = 2×3+1 = 7
#   🔴 **改这个数必须重新实测**，别信公式——公式只是给你算个起点。
RECURSION_LIMIT = 2 * (MAX_SEARCH_ROUNDS + MAX_COMPARE_ROUNDS) + 1 + 1
#                                          ^+1 是保守余量

COMPARE_TOOL = [{
    "type": "function",
    "function": {
        "name": COMPARE_TOOL_NAME,
        "description": (
            "对比 2-3 件商品的参数差异，**按用户当前问题的重点给出分维度对比**"
            "（例如用户问「戴久了耳朵不难受」就对比重量与佩戴压力，"
            "而不是泛泛比降噪）。当用户明确要比较几件商品时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # 🔴 question 必须 required（大宋 22:50 定）：
                #    「维度按用户问题定」是A4 的核心，没有它这个工具就没意义。
                #    模型漏填时降级成「按品类对比」（见 compare 节点）。
                "question": {
                    "type": "string",
                    "description": "用户真正想比较的方面，用他自己的话概括",
                },
                "items": {
                    "type": "array",
                    "description": f"要对比的商品名称，最多 {MAX_COMPARE_ITEMS} 件",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": MAX_COMPARE_ITEMS,
                },
            },
            "required": ["question", "items"],
        },
    },
}]

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

       🔴 **为什么 agent 通道和 text 通道分开**（2026-10-18 加）：
          - `text` 是**模型吐的**（`model_call.StreamEvent` 那条链）
          - `agent` 是**编排层在干什么**（compare 节点开始跑、推荐节点开始跑）
          两者来源不同、消费时机不同、丢弃策略也不同。
          混在一个队列里的话，前端得靠字段区分每一格 —— 而 flush 是按「格」切的，
          一格里可能混着两者。**分开 flush，调用方一次拿一种，类型干净。**

          ⚠️ 之所以能这么做，是因为 **agent 事件本来就不该塞进 StreamEvent**：
          那个类是 `model_call.stream_model` 的产出，描述「模型吐了什么」；
          而「正在对比」是**编排层知道、模型不知道**的事 —— 节点开始跑的时候
          模型早就返回完了。塞进去就得让模型层发它，可模型层不知道有 compare 节点。
    """

    def __init__(self) -> None:
        self._pending: list[str] = []
        # agent 事件：{name, phase, label}。name 是节点名（A4 / A5 / 卡片），
        # phase 是 start / end。见 docs/流式输出-设计.md §5.4 预留的协议位。
        self._agents: list[dict] = []

    def write(self, chunk: str) -> None:
        if chunk:
            self._pending.append(chunk)

    def write_agent(self, name: str, phase: str, label: str = "") -> None:
        """通知前端「某个节点开始 / 结束了」。

        ⚠️ **这里刻意不做「自动配对 end」的聪明逻辑**（比如只 write("A4")
           然后自己补 end）—— 节点可能抛异常，异常路径上 end 不会发出，
           前端就会永远转圈。**start / end 都由节点显式写**，
           出问题时靠前端超时兜底。
           这与 chat_stream 取消后不发 done 是**同一个取舍**（见设计文档 §5.10）。
        """
        self._agents.append({"name": name, "phase": phase, "label": label})

    async def flush(self) -> list[str]:
        await asyncio.sleep(0)
        out, self._pending = self._pending, []
        return out

    async def flush_agents(self) -> list[dict]:
        """取出尚未消费的 agent 事件。**取出后即清空**（与 flush 同口径）。"""
        await asyncio.sleep(0)
        out, self._agents = self._agents, []
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
    tool_calls: list# decide 交下来的待执行工具调用
    answer: str           # 最终回答全文
    # 🔴 每种工具**各自**的调用次数（2026-10-18 从单个 round_no 拆开）。
    #   为什么要拆：检索不花钱（用户自己的 embedding key），对比要联网（≈0.108 元）。
    #   一个数字管全部的话，对比会占检索的额度或者反过来。
    search_rounds: int
    compare_rounds: int


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
    """🔴 **这个节点就是 A1 本体**：调模型（带工具定义），让它决定调哪个工具。

    A1 的职责是「判断用户这句话该交给谁」——`decide` 做的正是这件事：
    读对话 → 问模型「要不要调工具、调哪个」→ 按模型的 tool_calls 分发到对应节点。

    流式产出：文本增量写进 sink；工具调用收齐后放进 state。
    """
    messages = state["messages"]
    user_id = state["user_id"]
    search_rounds = state.get("search_rounds", 0)
    compare_rounds = state.get("compare_rounds", 0)

    # 🔴 **每个工具单独判次数**（2026-10-18 加compare 时改的）。
    #   之前是「一个 MAX_ROUNDS 管所有工具」，现在必须分开——因为
    #   **检索不花钱（用用户自己的 embedding key），对比要联网（3 次博查 ≈ 0.108 元）**。
    #   混成一个数字的话，对比会白占检索的额度、或者反过来。
    #
    #   次数满了就把那个工具从定义里拿掉 —— 模型看不到它就只能走别的路
    #   或直接回答。**这是「业务收尾」，与 recursion_limit（死循环兜底）职责不同。**
    can_search = search_rounds < MAX_SEARCH_ROUNDS
    can_compare = compare_rounds < MAX_COMPARE_ROUNDS
    has_key = await rag_service.has_embedding_key(user_id, session)

    tools: list[dict] = []
    if can_search:
        # 🔴 没配向量模型时仍要定义，但 description 明说不可用 ——
        #   「模型看不到工具时会自己编参数格式，而『调了必然失败 → 模型
        #   输出检索失败 → 然后编一个答案』比『明说没有检索能力』更糟」。
        tools.append(SEARCH_TOOL[0] if has_key else _DISABLED_TOOL[0])
    if can_compare:
        tools.append(COMPARE_TOOL[0])
    # ⚠️ tools 为空时传None（模型调用层会当「不带工具」）——
    #   传 [] 有些厂商会当成「有一个空工具列表」而报错。

    pending: list[model_call.ToolCall] = []
    answer_parts: list[str] = []
    # 🔴 模型调用失败**往上抛**，让 LangGraph 报错，由 chat_stream 转成「生成失败」。
    #   这里**不要吞** —— 这是本次请求的失败，不是可降级的旁支。
    async for event in model_call.stream_model(key, messages,
                                               tools=tools or None):
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
            "search_rounds": state.get("search_rounds", 0) + 1,
            "tool_calls": []}


async def compare(state: RagState, sink: TextSink, session: AsyncSession) -> dict:
    """执行对比工具（A4）：把结果作为 role="tool" 消息追加进 messages。

    🔴 **本阶段只做「取出参数 → 生成占位结果」**（2026-10-18）。
    真正的联网取参（`web_search` + `complete_specs`）在阶段 3 做 ——
    那是三段式里唯一要花钱的部分，单独一步更可控，也便于单独测。

    **但维度选择已经在这里定型了**：从 `tool_calls[].parsed_arguments()["question"]`
    拿用户问题（大宋 22:50 定的路径）—— 不翻 messages，因为参数里已经有
    **模型提炼过的意图**（比用户原话更聚焦）。见 docs/A4对比与A5推荐-设计.md §2.2。

    🔴 **失败不抛异常**，转成给模型看的文本（同 search 节点的口径）。
    """
    calls = state.get("tool_calls") or []
    new_messages: list[dict] = []

    #🔴 让前端显示「正在对比…」。start / end 都显式写——
    #   自动配对会在节点抛异常时漏掉 end，前端就永远转圈（见 TextSink 注释）。
    sink.write_agent("A4", "start", "正在对比商品参数")
    try:
        for call in calls:
            args = call.parsed_arguments()
            question = str(args.get("question") or "").strip()
            items = [str(x).strip() for x in (args.get("items") or []) if str(x).strip()]

            # 🔴 三件上限在**这里**再兜一次，不只靠工具定义的 maxItems。
            #   模型有时会无视 maxItems 直接给 4 个——而 4 个 = 多 1 次博查（0.036 元）。
            #   **不静默截断**：截了要让模型知道，否则它会以为比了 4 件。
            if len(items) > MAX_COMPARE_ITEMS:
                dropped = items[MAX_COMPARE_ITEMS:]
                items = items[:MAX_COMPARE_ITEMS]
                logger.warning("对比商品超上限，截断：丢掉 %s", dropped)

            if len(items) < 2:
                text = ("对比失败：至少需要 2 件商品才能比较，"
                        "你只提供了 %d 件。请让用户明确要比较哪几件。" % len(items))
            elif not question:
                # 🔴 question 为空 → **降级**而不是报错。
                #   「维度按用户问题定」是A4 的核心，但模型漏填时
                #   退化到「按品类对比」远好过整个对比失败。
                #   （见 docs/A4对比与A5推荐-设计.md §2.2 的三道保险）
                logger.info("compare 未拿到 question，降级为按品类对比")
                text = (f"请按【商品品类】的通用关键参数对比这几件：{'、'.join(items)}。"
                        f"（用户没有明确说明关注点，按品类通用维度对比。）")
            else:
                # 📌 阶段 3 在这里换成：联网取参 + 分维度对比
                text = (f"待对比：{'、'.join(items)}；用户关注：{question}。"
                        "（参数获取与维度对比尚未接入，见 docs/A4对比与A5推荐-设计.md）")

            new_messages.append({
                "role": "tool", "tool_call_id": call.id, "content": text,
            })
    finally:
        sink.write_agent("A4", "end")

    return {"messages": new_messages,
            "compare_rounds": state.get("compare_rounds", 0) + 1,
            "tool_calls": []}


def route(state: RagState) -> str:
    """按**工具名**分派到对应节点；没有工具调用 → END。

    🔴 **2026-10-18 改**：原来只有一种工具时写死 `return "search"`。
       加了 compare 之后必须按名字分——否则 compare 的 tool_call
       会被扔进 search 节点，去检索「索尼WH-1000XM5」这个字符串。

    ⚠️ 拿到**不认识**的工具名时回落到 `search` 而不是报错：
       模型偶尔会幻觉出工具名，让它走一次检索比中断整轮对话好。
       （真要严格校验应该在这里抛，但那就得先确认所有厂商的模型
       都会严格遵守 tools 定义——没验证过，先用宽松口径。）
    """
    calls = state.get("tool_calls") or []
    if not calls:
        return END
    return "compare" if calls[0].name == COMPARE_TOOL_NAME else "search"


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

    async def node_compare(state: RagState) -> dict:
        async with async_session_local() as session:
            return await compare(state, sink, session)

    g = StateGraph(RagState)
    g.add_node("decide", node_decide)
    g.add_node("search", node_search)
    g.add_node("compare", node_compare)
    g.add_edge(START, "decide")
    # 🔴 映射表里的 END 是 `langgraph.graph.END`（值是 '__end__'），
    #   route 必须 return **这个常量**而不是字符串 "END"——
    #   我实测过：返回字符串 "END" 会抛 `KeyError: 'END'`（探针踩过）。
    g.add_conditional_edges(
        "decide", route,
        {"search": "search", "compare": "compare", END: END})
    g.add_edge("search", "decide")
    g.add_edge("compare", "decide")
    return g.compile()
