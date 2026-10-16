from dataclasses import dataclass
from typing import TypeVar
from collections.abc import Callable, Awaitable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.pg_session import get_pg_session

SOURCE_TYPES:tuple[str,...] =("cart", "owned", "purchase")
_DEFAULT_TOP_K = 5

T = TypeVar("T")


@dataclass(frozen=True)
class ItemHit:
    """检索命中,回mysql取数据"""
    source_type: str
    source_id: int
    score: float

def _vec_literal(vector: list[float]) -> str:
    """把 list[float] 转成 pgvector 的文本字面量 '[0.1,0.2,...]'。

       为什么不让 asyncpg 直接收 list[float]：SQLAlchemy 2.x 不认识 pgvector
       这个类型，直接绑 Python 列表会报类型错。转成字符串再 CAST 才是
       官方路径。repr(float) 保证出来的是 Python 短小数表示，PG 能解析。
       """
    return "["+",".join(repr(float(x)) for x in vector)+"]"

def _check_source_type(source_type: str) -> None:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type {source_type} not in {SOURCE_TYPES}")

async def _pg_tx(fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """一个独立的 PG 事务：开 → 交给 fn → 提交 → 出错回滚 → 必关。

        close() 放 finally：漏关会一直占着 asyncpg 的连接池槽位，
        池子满之后全站 PG 相关功能一起卡死（pool_size=5）。
        """
    session = get_pg_session()
    try:
        result = await fn(session)
        await session.commit()
        return result
    except Exception :
        await session.rollback()
        raise
    finally:
        await session.close()


_UPSERT_SQL = text(
    """
    INSERT INTO item_embedding (user_id, source_type, source_id, content, vector)
    VALUES (:uid, :stype, :sid, :content, CAST(:vec AS vector))
    ON CONFLICT (user_id, source_type, source_id)
    DO UPDATE SET content     = EXCLUDED.content,
                  vector      = EXCLUDED.vector,
                  update_time = now()
    """
)

_DELETE_SQL = text(
    """
    DELETE FROM item_embedding
    WHERE user_id = :uid AND source_type = :stype AND source_id = :sid
    """
)

_SEARCH_SQL = text(
    """
    SELECT source_type,
           source_id,
           1 - (vector <=> CAST(:vec AS vector)) AS score
    FROM item_embedding
    WHERE user_id = :uid
    ORDER BY vector <=> CAST(:vec AS vector)
    LIMIT :k
    """
)


async def upsert_embedding(
    user_id: int,
    source_type: str,
    source_id: int,
    content: str,
    vector: list[float],
) -> None:
    """写入/覆盖一条向量。一件物品一条，重复插入是 bug 不该被容忍，所以是 upsert。

    ON CONFLICT 的目标键必须和 pg_init.sql 里的唯一索引
    uq_item_embedding_source(user_id, source_type, source_id) 完全一致，
    对不上会直接报错「there is no unique or exclusion constraint matching」。
    """
    _check_source_type(source_type)

    async def _run(session: AsyncSession) -> None:
        await session.execute(
            _UPSERT_SQL,
            {
                "uid": user_id,
                "stype": source_type,
                "sid": source_id,
                "content": content,
                "vec": _vec_literal(vector),
            },
        )

    await _pg_tx(_run)

async def delete_by_source(user_id: int, source_type: str, source_id: int) -> None:
    """删掉一条向量副本。MySQL 那边删了/转移了物品必须调这个。

    查不到不报错：副本表允许「已经没有这条」，调用方删物品的
    场景下是完全正常的状态，报错反而会打断主流程。
    user_id 必带，顺带防了删别人数据。
    """
    _check_source_type(source_type)

    async def _run(session: AsyncSession) -> None:
        await session.execute(
            _DELETE_SQL, {"uid": user_id, "stype": source_type, "sid": source_id}
        )

    await _pg_tx(_run)

async def search_similar(
    user_id: int, query_vector: list[float], top_k: int = _DEFAULT_TOP_K
) -> list[ItemHit]:
    """语义检索：找出这个用户最相似的 k 条，返回 (类型, id, 相似度)。

    相似度 = 1 - 余弦距离，所以越大越像（1.0 = 同方向）。
    ORDER BY 用的是距离本身（越小越靠前），别用 score 排，方向反了。

    刻意不建 hnsw 向量索引：每人的向量就几百条，暴力扫比走索引快，
    十万量级再加。user_id 必在 WHERE 里 —— 一来是铁律，二来是先把
    无关行过滤掉再算距离。
    """
    if top_k < 1:
        raise ValueError("top_k 至少为 1")

    async def _run(session: AsyncSession) -> list[ItemHit]:
        result = await session.execute(
            _SEARCH_SQL, {"uid": user_id, "vec": _vec_literal(query_vector), "k": top_k}
        )
        # text() 没声明列名，行只能按下标取（row.source_type 会 AttributeError）
        return [ItemHit(row[0], int(row[1]), float(row[2])) for row in result.all()]

    return await _pg_tx(_run)
