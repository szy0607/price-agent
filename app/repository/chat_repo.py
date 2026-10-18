from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import ChatMessage, CartItem, OwnedItem, PurchaseRecord
from app.schemas.chat_sche import ItemRefInSchema

# 生成结局三态。status 列见 docs/流式输出-设计.md §1。
STATUS_COMPLETED = "completed"
STATUS_INTERRUPTED = "interrupted"
STATUS_FAILED = "failed"

# 🔴 2026-10-18：新增 role="tool"（RAG 工具化）。
# 之前只有 "user" / "assistant"（见 models/chat_message.py 的 role 列注释）。
#
# **tool 消息为什么要落库**（§8.4，大宋拍板）：用户刷新页面后要看得见
# 「刚才系统翻了他的物品库」。不落的话，用户看到的是一个**凭空出现的答案**，
# 会怀疑「它凭什么推荐这个」——在导购场景下这是**信任问题**。
#
# **但它不给模型看**：见 messages_for_context 里的 `role != ROLE_TOOL` 过滤。
# 同一行数据，两个出口两种形态，与 status 的三出口模式同构。
ROLE_TOOL = "tool"

# A6 画像看到的「用户中断」事件占位——只说发生了中断，不给那段被否决的半截文本。
# 为什么画像要留这个事件、上下文却要整条排除：用户按下停止是他明确否决方向，
# 但「主动喊停」本身是「不是这个方向 / 说太长 / 问错了」的高价值信号，值得进长期画像。
_INTERRUPT_EVENT = "（用户中断了上一轮回答）"


async def add_message(
        user_id: int,
        conversation_id: int,
        role: str,
        content: str,
        session: AsyncSession,
        *,
        model: str | None = None,
        status: str = STATUS_COMPLETED) -> ChatMessage:
    message = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        model=model,
        status=status,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def _fetch_rows(
        user_id: int,
        conversation_id: int,
        limit: int,
        session: AsyncSession,
        *,
        desc: bool) -> list[ChatMessage]:
    """按 (user_id, conversation_id) 取消息。desc=True 供倒序取最近 N 条（拼上下文用）。"""
    order = ChatMessage.id.desc() if desc else ChatMessage.id.asc()
    result = await session.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
        .order_by(order)
        .limit(limit)
    )
    return list(result.all())


async def messages_for_context(
        user_id: int,
        conversation_id: int,
        limit: int,
        session: AsyncSession) -> list[dict]:
    """给模型拼上下文的对话序列。**只认completed**。

    interrupted / failed 一律排除，理由（docs/流式输出-设计.md §0）：
    用户按下停止是他明确否决了这个方向，把半截话塞回去，模型下一轮会顺着
    用户已放弃的内容继续答；failed 的半截同理。

    返回 list[dict] 而非 ORM 实体：调用方会在本函数返回后关闭 session，
    detached 实例再取属性会踩 DetachedInstanceError。
    """
    rows = await _fetch_rows(user_id, conversation_id, limit, session, desc=True)
    # 🔴 role != ROLE_TOOL：tool 消息是**上一轮的检索快照**，带进上下文会污染本轮判断
    #    ——模型看到「上轮检索到 iPhone」，可能本轮**不检索**就直接答 iPhone。
    #    但这一轮用户的数据可能已经变了（他刚删了耳机、买了新东西）。
    #    旧快照不能代表现在，要用就重新检索。
    #
    #    ⚠️ 两条过滤条件是**并列**的，缺一不可：
    #      status == completed← 排除 interrupted / failed（原有口径）
    #      role != tool         ← 排除检索快照（2026-10-18 新增）
    #    去掉任一条都会静默出问题：去掉 status 会把用户否决过的半截话喂回模型；
    #    去掉 role 会让模型拿过期检索结果当现查的用。
    #
    #    ⚠️ 隐式契约：`trim_trailing_users` 依赖「先过滤掉不该进上下文的」，
    #    加了 role 条件后这个前提更严格，砍尾巴才能砍干净。
    return [
        {"role": row.role, "content": row.content, "model": row.model}
        for row in reversed(rows)
        if row.status == STATUS_COMPLETED and row.role != ROLE_TOOL
    ]


async def messages_for_profile(
        user_id: int,
        conversation_id: int,
        limit: int,
        session: AsyncSession) -> list[dict]:
    """给 A6 画像的近期对话。与 messages_for_context **故意用不同规则**。

    - completed   ：原样进
    - interrupted ：**只留事件占位**，半截文本绝不进（否则画像会从用户已否决的文本里提炼偏好）
    - failed      ：整条排除。半截的助手自述不是用户表达，进画像等于凭空造偏好

    limit 按「取到的原始行数」算，不是过滤后的条数——否则半截消息会挤占 completed 的名额。
    """
    rows = await _fetch_rows(user_id, conversation_id, limit, session, desc=True)
    out: list[dict] = []
    for row in reversed(rows):
        if row.status == STATUS_INTERRUPTED:
            out.append({"role": row.role, "content": _INTERRUPT_EVENT, "model": row.model})
        elif row.status == STATUS_COMPLETED:
            out.append({"role": row.role, "content": row.content, "model": row.model})
        # failed：整条跳过
    return out


def trim_trailing_users(messages: list[dict]) -> list[dict]:
    """砍掉尾部连续的 user 消息。

    「user 先入库 + 模型失败」的必然产物：失败时库里只有 user 没有 assistant，
    尾部就出现连续两条 user，部分模型不接受这种序列。

    ⚠️ 有效性依赖 messages_for_context **先过滤掉非 completed**：否则 failed /
    interrupted 的 assistant 插在序列中间会把user/user 连在一起打断，砍尾巴也砍不干净。
    这条隐式契约有回归测试锁住（docs/流式输出-设计.md §4.4）。
    """
    end = len(messages)
    while end > 0 and messages[end - 1]["role"] == "user":
        end -= 1
    return messages[:end]


async def list_messages(
        user_id: int,
        conversation_id: int,
        limit: int,
        session: AsyncSession) -> list[ChatMessage]:
    """某个会话的全部历史，按 id 升序（前端直接顺序渲染）。

    与 messages_for_context / messages_for_profile 的分工：那两个决定
    「哪些内容值得再交给模型」，本函数负责「忠实记录发生过什么」——
    completed / interrupted / failed **全部返回**，前端据此显示状态角标。
    （docs/流式输出-设计.md §0：三条出口故意用不同规则）

    user_id 同时在 WHERE 里，归属不通过的会话根本查不到行。
    """
    return await _fetch_rows(user_id, conversation_id, limit, session, desc=False)
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


async def fetch_items_for_rag(
        user_id: int, pairs: list[tuple[str, int]],
        session: AsyncSession) -> list[dict]:
    """按 (src, id) 批量取商品原文，给 RAG 检索结果回源用。

    **与 fetch_items_for_refs 的三处刻意不同**（别把它们合并成一个函数）：

    |  | fetch_items_for_refs | 本函数 |
    |---|---|---|
    | 查不到 | 🔴 抛 40001 | **静默跳过** |
    | 支持类型 | cart / owned | cart / owned / **purchase** |
    | 排序 | 严格按 refs 顺序 | **按入参 pairs 的顺序** |

    🔴 **为什么「查不到」的处理必须相反**：refs 是用户**刚勾**的商品，
    几秒内被删属于异常，报错让他刷新；RAG 命中的是**几分钟前的向量快照**，
    商品在这期间被删或被转移是**正常业务**——transfer 会删 cart 副本、
    建 owned/purchase 新行，而 `index_service.drop_vector` 是全异常自吞的
    （见 index_service.py:60-80），PG 里必然残留指向已删 id 的向量。
    报错 = 每隔几分钟把对话打成 500 一次。

    🔴 **为什么必须支持 purchase**：消费记录（买过什么、花了多少）
    恰恰是「送人送什么」「我之前买过类似的���」这类问题最该检索的语料。
    少了它，RAG 只能看到购物车和物品库，看不到购买历史。

    返回 list[dict]（不是 ORM 实例）：让 rag_service 在调用方关闭 session
    之后仍能安全使用这些数据（同 messages_for_context 的纪律）。

    **index_status 带出来但不是给模型看的**：给下游两个用途——写排查日志、
    写进落库的 tool 消息 JSON（前端展示）。**拼 prompt 时不带**：
    「索引处理中」是内部状态，模型会当事实复述给用户（见 chat_service
    的 SYSTEM_PROMPT 那条铁律）。
    """
    if not pairs:
        return []

    cart_ids = [pid for src, pid in pairs if src == "cart"]
    owned_ids = [pid for src, pid in pairs if src == "owned"]
    purchase_ids = [pid for src, pid in pairs if src == "purchase"]

    # key 是 (src, id)。**查不到就不塞进这个 dict** —— 这就是「静默跳过」
    # 的实现：下游按 pairs 顺序取，取不到就跳过这个元素。没有额外的 if 分支。
    found: dict[tuple[str, int], dict] = {}

    async def _load(model, src: str, ids: list[int]) -> None:
        if not ids:
            # 🔴 空列表不发 SQL：部分驱动对 `IN ()` 会生成语法错误的语句
            return
        rows = await session.scalars(
            select(model).where(model.user_id == user_id, model.id.in_(ids))
        )
        for row in rows:
            found[(src, row.id)] = {
                "src": src,
                "id": row.id,
                "name": row.name,
                "specs": row.specs,
                "index_status": row.index_status,
            }

    await _load(CartItem, "cart", cart_ids)
    await _load(OwnedItem, "owned", owned_ids)
    await _load(PurchaseRecord, "purchase", purchase_ids)

    # 按 pairs 原顺序返回（入参已按 score 降序）。
    # 返回长度会少于入参长度——这正是调用方要统计的「孤儿向量数」。
    out: list[dict] = []
    for key in pairs:
        item = found.get(key)
        if item is not None:
            out.append(item)
    return out