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
from app.services import (compare_service, compare_specs_service, model_call,
                         profile_service, rag_service, recommend_service,
                         web_search_service)
from app.services.api_key_service import KeyRecord

logger = logging.getLogger(__name__)
TOOL_NAME = "search_my_items"
COMPARE_TOOL_NAME = "compare_items"
RECOMMEND_TOOL_NAME = "recommend_for_me"
CARD_TOOL_NAME = "show_item_card"
MAX_COMPARE_ITEMS = 3      # 🔴 大宋 22:40 拍板：对比最多 3 件

# 🔴 每种工具的次数上限。**分开计数**，不用一个 MAX_ROUNDS：
#   - 检索不花钱（用用户自己的 embedding key），所以可以多来几次
#   - 对比/推荐要联网（0.108~0.2 元），所以卡死
#   混成一个数字的话，以后加「花钱的工具」就没法单独限了。
MAX_SEARCH_ROUNDS = 2
MAX_COMPARE_ROUNDS = 1
MAX_RECOMMEND_ROUNDS = 1
MAX_CARD_ROUNDS = 1
# 🔴 卡片最多弹几张。web_search 返回 5 条，全弹出来对话里会挤。
MAX_CARD_ITEMS = 3

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
#   ⚠️ 2026-10-18 加 recommend 后从 8 变成 10（多 1 次工具 = 多 2 次节点执行）。
#      **再次强调：改这个数要重新实测**，不要凭直觉。
# 🔴🔴 **第三次实测修正**（2026-10-18 加 recommend 后）：
#   最坏路径（检索2 + 对比1 + 推荐1）实测：**limit=9 撞，10 才通**。
#   节点执行是 9 次（d1 search d3 search d5 compare d7 recommend d9），
#   **END 那一跳也算一步** —— 这是我公式漏掉的（第三次了）。
#     第1次 10-17：按轮数×2 算 5，漏了最后一次 decide
#     第 2 次 10-18：按边数算 8，漏了「START 不算 super-step」
#     第 3 次 10-18：按节点执行算 9，**漏了 END 那一跳**
#   正确算法：**节点执行次数 + 1**（END 占一步）
RECURSION_LIMIT = 2 * (MAX_SEARCH_ROUNDS + MAX_COMPARE_ROUNDS
                        + MAX_RECOMMEND_ROUNDS + MAX_CARD_ROUNDS) + 1 + 1

CARD_TOOL = [{
    "type": "function",
    "function": {
        "name": CARD_TOOL_NAME,
        "description": (
            "搜索并展示商品卡片，让用户直接看到商品名与概要、能一键加入购物车。"
            "当用户提到某个具体商品（品牌+型号、或商品名）想了解它时调用。"
            "**只用于单个商品的展示** —— 要比较多件用 compare_items，"
            "不知道买什么用 recommend_for_me。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要展示的商品（品牌+型号最好，如「索尼 WH-1000XM5」）",
                },
            },
            "required": ["query"],
        },
    },
}]

RECOMMEND_TOOL = [{
    "type": "function",
    "function": {
        "name": RECOMMEND_TOOL_NAME,
        "description": (
            "根据用户的**偏好画像**推荐他可能想买的东西（会联网搜索新品，"
            "不只是从他已有的物品里挑）。"
            "当用户问「我该买什么」「推荐点什么」「送人送什么好」"
            "这类需要你替他做选购决策的问题时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # 🔴 question 同样进 required：没有用户诉求就不知道该按什么推荐
                "question": {
                    "type": "string",
                    "description": "用户想要什么，用他自己的话概括",
                },
            },
            "required": ["question"],
        },
    },
}]

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

       🔴 **card 通道为什么是第三个而不是塞进 agents**（2026-10-18）：
          `agent` 是「**过程提示**」（一行字，转圈→打勾）；
          `card` 是「**结构化结果**」（一张卡片，有字段有按钮）。
          塞进 agents 的话前端得按 name 分流，且 `agent` 事件的语义就不纯了。
          **三个通道的语义边界**：text=正文 / agent=过程 / card=结构化结果。
    """

    def __init__(self) -> None:
        self._pending: list[str] = []
        # agent 事件：{name, phase, label}。name 是节点名（A4 / A5 / 卡片），
        # phase 是 start / end。见 docs/流式输出-设计.md §5.4 预留的协议位。
        self._agents: list[dict] = []
        # card 事件：结构化商品卡片的 payload（见 write_card 的 docstring）
        self._cards: list[dict] = []

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

    def write_card(self, payload: dict) -> None:
        """写一张商品卡片（结构化结果，给前端渲染）。

        payload 形态（字段与 `web_search` 的返回一致 + 清理后的 query）：
        ```
        {"query": "用户搜的词",
         "items": [{"name": "商品名", "snippet": "概要", "url": "来源"}, ...]}
        ```

        🔴 **不落库**（docs/对话侧商品卡片-设计.md §5.4）：卡片是「这一轮的
           搜索快照」，和 agent 事件同类。用户点「加入购物车」才走
           `POST /cart/items`——**草稿只在当前响应里**（§8.4 大宋拍板的合规红线）。

        ⚠️ **卡片里的 url 不能直接渲染成可点击链接**：博查返回的地址可能带返佣
           （CPS），项目铁律明令禁止。前端只应把它当「来源」显示。
        """
        self._cards.append(payload)

    async def flush_cards(self) -> list[dict]:
        """取出尚未消费的卡片。**取出后即清空**（与前两个通道同口径）。"""
        await asyncio.sleep(0)
        out, self._cards = self._cards, []
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
    recommend_rounds: int
    card_rounds: int


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
    recommend_rounds = state.get("recommend_rounds", 0)
    card_rounds = state.get("card_rounds", 0)

    # 🔴 **每个工具单独判次数**（2026-10-18 加compare 时改的）。
    #   之前是「一个 MAX_ROUNDS 管所有工具」，现在必须分开——因为
    #   **检索不花钱（用用户自己的 embedding key），对比要联网（3 次博查 ≈ 0.108 元）**。
    #   混成一个数字的话，对比会白占检索的额度、或者反过来。
    #
    #   次数满了就把那个工具从定义里拿掉 —— 模型看不到它就只能走别的路
    #   或直接回答。**这是「业务收尾」，与 recursion_limit（死循环兜底）职责不同。**
    can_search = search_rounds < MAX_SEARCH_ROUNDS
    can_compare = compare_rounds < MAX_COMPARE_ROUNDS
    can_recommend = recommend_rounds < MAX_RECOMMEND_ROUNDS
    # 🔴🔴 **卡片工具已停用**（2026-10-19 大宋看到真机效果后拍板去掉）。
    #
    #   停用原因（不是渲染问题，是**取数**问题）：
    #   `web_search` 返回的是**网页**不是商品。实测同一个查询
    #   「京东京东京东 纯奶 价格 评测」返回的全是
    #     · 纯奶纯价格报价行情 - 京东
    #     · 精选_京东牛奶_国内优惠排行_第203页 - 什么值得买
    #     · 精选_京东牛奶_国内优惠排行_第124页 - 什么值得买
    #   界面上就渲染出 6 张卡片，**全是同一件商品的不同页面**，
    #   标题还是「京东京东京东」这种博查拼重复前缀的垃圾。
    #
    #   ⚠️ **这不是「暂时禁用」，也不只是「卡片」的问题**：
    #     A5 推荐吃的是同一批脏数据（实测 A5 的候选名与卡片拿到的**几乎一样**）。
    #     要治根得在 `recommend_service.search_candidates` 里做去重与过滤，
    #     那是另一次判断（过滤规则要跟大宋对）。
    #
    #   **代码全部保留**（CARD_TOOL / card 节点 / TextSink 的 card 通道 / 前端渲染）——
    #   卡片渲染本身是对的（截图里姓名/概要/来源/按钮都在），
    #   将来取数修好或换商品 API，改一行就能恢复。
    #   🔴 恢复方法：下面这行改成 `can_card = card_rounds < MAX_CARD_ROUNDS`
    can_card = False
    has_key = await rag_service.has_embedding_key(user_id, session)

    tools: list[dict] = []
    if can_search:
        # 🔴 没配向量模型时仍要定义，但 description 明说不可用 ——
        #   「模型看不到工具时会自己编参数格式，而『调了必然失败 → 模型
        #   输出检索失败 → 然后编一个答案』比『明说没有检索能力』更糟」。
        tools.append(SEARCH_TOOL[0] if has_key else _DISABLED_TOOL[0])
    if can_compare:
        tools.append(COMPARE_TOOL[0])
    if can_recommend:
        tools.append(RECOMMEND_TOOL[0])
    if can_card:
        tools.append(CARD_TOOL[0])
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


async def compare(state: RagState, sink: TextSink, key: KeyRecord,
                session: AsyncSession) -> dict:
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
            else:
                # 🔴 2026-10-18 阶段 3：接上真的取参 + 分维度对比。
                #   ⚠️ **这一段是真花钱的**（3 件 = 3 次博查 ≈ 0.108 元 + 1 次主模型）。
                #   测试里 compare_specs_service 与 compare_service **全部 mock**，
                #   一次博查都不该真调——写测试时注意。
                text = await _run_comparison(
                    items, question, state["user_id"], key, session)

            new_messages.append({
                "role": "tool", "tool_call_id": call.id, "content": text,
            })
    finally:
        sink.write_agent("A4", "end")

    return {"messages": new_messages,
            "compare_rounds": state.get("compare_rounds", 0) + 1,
            "tool_calls": []}


async def _run_comparison(items: list[str], question: str, user_id: int,
                          key: KeyRecord, session: AsyncSession) -> str:
    """取参 + 分维度对比，返回给模型看的文本。**永不抛异常**。

    三步（顺序不能换）：
      ①联网取参      → compare_specs_service（花钱）
      ② 按问题选维度  → compare_service（主模型，不联网）
      ③ 渲染成文本    → 回给 decide，让它基于这个组织最终回答

    🔴 **任何一步失败都返回一段「说明情况」的文本**，而不是抛异常——
    decide 拿到它仍然可以回答用户（哪怕是「我没能查到这几点」）。

    ⚠️ `key` 是 decide 那次调用用的同一个 KeyRecord（闭包传进来）。
    `call_model` 要的是 KeyRecord 不是 None —— 我第一版传了 None，
    查签名才发现。
    """
    # ① 取参
    try:
        specs = await compare_specs_service.fetch_specs(items, user_id, session)
    except Exception:
        # fetch_specs 内部已逐件吞异常，走到这里说明是它之外的意外
        logger.warning("对比取参整体异常", exc_info=True)
        specs = {}
    if not specs:
        return ("未能获取到这几件商品的参数（可能网络搜索未配置，"
                "或这几个名称搜索不到）。请直接依据已有信息回答，"
                "**不要编造参数**。")

    specs_lines = [compare_specs_service.format_specs_line(n, d)
                   for n, d in specs.items()]
    found = "、".join(specs)
    if len(specs) < len(items):
        # 🔴 部分失败要**明说哪几件没查到** —— 不说的话用户会以为比全了
        missing = "、".join(i for i in items if i not in specs)
        specs_lines.append(f"-（{missing}）⚠️ 未查到参数")

    # ②③ 选维度 + 渲染
    try:
        raw, _model, _tool_calls = await model_call.call_model(
            key, compare_service.build_messages(list(specs), specs_lines, question))
    except Exception as exc:
        logger.warning("对比 prompt 调用失败", exc_info=True)
        return f"参数已查到（{found}），但没能完成结构化对比（{type(exc).__name__}）。"

    result = compare_service.parse_comparison(raw, list(specs))
    return compare_service.format_comparison(result)


async def recommend(state: RagState, sink: TextSink, key: KeyRecord,
                    session: AsyncSession) -> dict:
    """执行推荐工具（A5）：按画像推荐**用户还没有的**商品。

    四步（顺序不能换）：
      ① 读画像      → profile_service（现成，0 成本）
      ② 画像→搜索词  → recommend_service（1 次主模型）
                     🔴 **这一步是隐私红线的关键**：模型必须把画像**抽象成
                        商品特征**，绝不能把用户的具体商品/订单原样发给博查
      ③ 搜候选      → web_search（花钱，≤3 次）
      ④ 提参 + 排序 → compare_specs_service + 1 次主模型

    🔴 **失败不抛异常**，转成给模型看的文本（同 search / compare 节点的口径）。
    """
    calls = state.get("tool_calls") or []
    new_messages: list[dict] = []
    user_id = state["user_id"]

    sink.write_agent("A5", "start", "正在根据你的偏好推荐")
    try:
        for call in calls:
            question = str(call.parsed_arguments().get("question") or "").strip()
            text = await _run_recommendation(question, user_id, key, session)
            new_messages.append({
                "role": "tool", "tool_call_id": call.id, "content": text,
            })
    finally:
        sink.write_agent("A5", "end")

    return {"messages": new_messages,
            "recommend_rounds": state.get("recommend_rounds", 0) + 1,
            "tool_calls": []}


async def _run_recommendation(question: str, user_id: int, key: KeyRecord,
                              session: AsyncSession) -> str:
    """四步推荐流程，返回给模型看的文本。**永不抛异常**。"""
    # ① 读画像（现成能力，0 成本）
    try:
        profile_text = await profile_service.load_profile_context(user_id, session)
    except Exception:
        logger.warning("读画像失败", exc_info=True)
        profile_text = ""

    # ② 画像 → 搜索词（🔴 隐私抽象发生在这里）
    searches = await recommend_service.build_searches(profile_text, question, key)
    if not searches and question:
        #降级：搜词生成失败就直接用用户问题搜
        # ⚠️ 风险：用户问题里可能带商品偏好（「买索尼降噪耳机」）——
        #   那是他自己主动说的，发给搜索服务**不算隐私泄露**（用户已授权）
        searches = [question]
    if not searches:
        return ("无法生成搜索词，没法推荐。请直接告诉用户："
                "我需要知道你想要什么方向的商品。")

    # ③ 搜候选（花钱）
    try:
        names = await recommend_service.search_candidates(searches)
    except Exception:
        logger.warning("搜索候选异常", exc_info=True)
        names = []
    if not names:
        return ("联网搜索没找到相关商品。请直接说明这个情况，"
                "**不要编造商品或价格**。")

    # ④ 提参 + 排序（提参复用 A4 的能力）
    try:
        specs = await compare_specs_service.fetch_specs(names, user_id, session)
    except Exception:
        logger.warning("推荐取参异常", exc_info=True)
        specs = {}
    if not specs:
        return ("找到了候选商品但没能获取到参数。"
                "请直接说明情况，**不要编造参数**。")

    try:
        raw, _model, _tc = await model_call.call_model(
            key, recommend_service.build_rank_prompt(
                profile_text, question, specs))
    except Exception as exc:
        logger.warning("排序 prompt 失败", exc_info=True)
        return (f"已获取到候选商品参数（{'、'.join(specs)}），"
                f"但排序失败（{type(exc).__name__}）。")

    rankings = recommend_service.parse_ranking(raw, list(specs))
    if not rankings and specs:
        # 排序结果全被过滤掉了（模型编造了不存在的商品名）——
        # 至少把候选给模型，别让它空手而归
        logger.warning("排序结果全被过滤，回落为按候选原样给出")
        rankings = [{"name": n, "reason": ""} for n in specs]
    return recommend_service.format_recommendation(rankings, specs)


async def card(state: RagState, sink: TextSink, user_id: int,
               session: AsyncSession) -> dict:
    """执行卡片工具：搜索商品 → 结构化卡片给前端 → 一句话交回模型。

    🔴 **大宋 23:47 拍板：不做名称清洗，`web_search` 原样返回。**
    理由是「用户可以在购物车修改」—— 少一层可能出错的正则。

    🔴 **成本 0.036 元 + 约 0.5 秒**（1 次博查，**0 次主模型**）。
    与 compare/recommend 不同：卡片不需要结构化参数表——
    `snippet` 已经是两三句话的概要，卡片是「概要 + 一键加入」。

    **卡片不落库**（docs/对话侧商品卡片-设计.md §5.4）：它是这一轮的搜索快照，
    用户点「加入购物车」才走 POST /cart/items（合规红线：AI 建议只是建议）。

    🔴 **失败不抛异常**，转成给模型看的文本。
    """
    calls = state.get("tool_calls") or []
    new_messages: list[dict] = []

    sink.write_agent("CARD", "start", "正在查商品")
    try:
        for call in calls:
            query = str(call.parsed_arguments().get("query") or "").strip()
            if not query:
                new_messages.append({
                    "role": "tool", "tool_call_id": call.id,
                    "content": "卡片失败：没有提供商品名。",
                })
                continue
            try:
                results = await web_search_service.web_search(
                    f"{query} 价格 参数", count=MAX_CARD_ITEMS + 2)
            except Exception:
                # 🔴 博查失败（未配 key / 网络故障）→ 告诉模型，不要抛
                logger.warning("卡片搜索失败 query=%s", query, exc_info=True)
                results = []

            items = [{
                "name": (r.get("name") or "").strip(),
                "snippet": (r.get("snippet") or "").strip(),
                # ⚠️ url 只作「来源」显示，**前端不能渲染成可点击链接**——
                #    博查返回的地址可能带返佣（CPS），项目铁律禁止。
                "url": (r.get("url") or "").strip(),
            } for r in results if (r.get("name") or "").strip()
                ][:MAX_CARD_ITEMS]

            if items:
                # 🔴 卡片 payload 直接走 sink 的 card 通道（不经过 messages）
                sink.write_card({"query": query, "items": items})
                names = "、".join(i["name"] for i in items)
                text = (f"已向用户展示了{len(items)} 个商品卡片：{names}。"
                        "请用一句话说明你在展示什么，**不要重复罗列卡片里已有的内容**"
                        "（用户看得到）。")
            else:
                text = ("没搜到这个商品。请直接告诉用户「没搜到」，"
                        "**不要编造商品或价格**。")

            new_messages.append({
                "role": "tool", "tool_call_id": call.id, "content": text,
            })
    finally:
        sink.write_agent("CARD", "end")

    return {"messages": new_messages,
            "card_rounds": state.get("card_rounds", 0) + 1,
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
    name = calls[0].name
    if name == COMPARE_TOOL_NAME:
        return "compare"
    if name == RECOMMEND_TOOL_NAME:
        return "recommend"
    if name == CARD_TOOL_NAME:
        return "card"
    return "search"


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
            return await compare(state, sink, key, session)

    async def node_recommend(state: RagState) -> dict:
        async with async_session_local() as session:
            return await recommend(state, sink, key, session)

    async def node_card(state: RagState) -> dict:
        # card 节点只需要 user_id 与 session（它不发模型请求给模型用，
        # 只是在 messages 里回一句话），所以不传 key。
        async with async_session_local() as session:
            return await card(state, sink, state["user_id"], session)

    g = StateGraph(RagState)
    g.add_node("decide", node_decide)
    g.add_node("search", node_search)
    g.add_node("compare", node_compare)
    g.add_node("recommend", node_recommend)
    g.add_node("card", node_card)
    g.add_edge(START, "decide")
    # 🔴 映射表里的 END 是 `langgraph.graph.END`（值是 '__end__'），
    #   route 必须 return **这个常量**而不是字符串 "END"——
    #   我实测过：返回字符串 "END" 会抛 `KeyError: 'END'`（探针踩过）。
    g.add_conditional_edges(
        "decide", route,
        {"search": "search", "compare": "compare",
         "recommend": "recommend", "card": "card", END: END})
    g.add_edge("search", "decide")
    g.add_edge("compare", "decide")
    g.add_edge("recommend", "decide")
    g.add_edge("card", "decide")
    return g.compile()
