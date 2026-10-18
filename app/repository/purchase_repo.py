"""消费记录的只读查询。**只补读，不搬写。**

🔴 为什么现在才建这个文件：2026-10-17 大宋拍板「RAG 需要按 id 读」，
补了它。但**写侧仍在 purchase_record.py 的 router 里**（`_fields` /
`_row_dict` / `_validate_specs` / `_owned_for_update` 五个私有函数），
本设计不改造——搬进 repo 要重排事务边界、加锁、投递位置，是一次独立的
重构，不能和「加检索」混在一起做。

也就是说：消费记录目前是**半分层**状态（读有 repo、写没有）。
这是有意为之的中间态，不是遗漏。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PurchaseRecord


async def fetch_by_ids(user_id: int, ids: list[int],
                       session: AsyncSession) -> list[PurchaseRecord]:
    """按 id 批量取行。**查不到的 id 直接不返回**，不报错。

    为什么静默：调用方是 `chat_repo.fetch_items_for_rag`，它要处理
    「PG 命中了但 MySQL 已无此行」——那是删除/转移留下的**孤儿向量**，
    是必然发生的正常状态（transfer 会删 cart 副本建 owned/purchase 新行，
    而 `drop_vector` 是全异常自吞的）。报错会让对话周期性 500。

    user_id 必在 WHERE 里：一来是铁律（防查别人数据），
    二来是把无关行先过滤掉。

    入参为空列表时**直接返回，不发 SQL**：SQLAlchemy 对空 `IN ()`
    在部分驱动上会生成语法错误的语句，这里短路掉。
    """
    if not ids:
        return []
    result = await session.scalars(
        select(PurchaseRecord).where(
            PurchaseRecord.user_id == user_id,
            PurchaseRecord.id.in_(ids),
        )
    )
    return list(result.all())