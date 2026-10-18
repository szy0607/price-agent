import logging
from datetime import timedelta

from app.core.config import settings
from app.core.time import get_current_time
from app.services import embedding_client
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from arq import Retry
from app.core.redis_client import get_pool
from app.database.session import async_session_local
from app.models import CartItem, OwnedItem, PurchaseRecord
from app.repository import vector_repo
from app.services.embed_slice import build_item_text
logger = logging.getLogger(__name__)
PENDING = "PENDING"
RUNNING = "RUNNING"
SYNCED = "SYNCED"
FAILED = "FAILED"
_MODELS = {"cart": CartItem, "owned": OwnedItem, "purchase": PurchaseRecord}


async def set_running(user_id: int, source_type: str,item_id: int,session:AsyncSession) -> None:
    model = _MODELS[source_type]
    await session.execute(
        update(model)
        .where(model.id == item_id, model.user_id == user_id)
        .values(index_status=RUNNING)
    )
async def set_pending(user_id, source_type, item_id, session) -> None:
    """置 PENDING。**必须在业务事务内调用**，与业务数据一起 commit。"""
    model = _MODELS[source_type]
    await session.execute(
        update(model)
        .where(model.id == item_id, model.user_id == user_id)
        .values(index_status=PENDING)
    )

async def set_synced(user_id: int, source_type: str, item_id: int,
       session: AsyncSession) -> None:
    """置 SYNCED + 写 index_time。**只能在 PG 写入成功之后调"""
    model = _MODELS[source_type]
    # 🔴 时间值唯一来源 = Python 侧（项目铁律）。用 get_current_time() 而不是
    #    UTC_TIMESTAMP()：这条update 与业务写在不同 session 里，走 DB 侧默认值
    #    会因迁移连接与应用连接的时区设置不同而产生偏差。
    await session.execute(
        update(model)
        .where(model.id == item_id, model.user_id == user_id)
        .values(index_status=SYNCED, index_time=get_current_time())
    )
async def set_failed(user_id: int, source_type: str, item_id: int,
       session: AsyncSession) -> None:
    """置 FAILED。**必须在 reap_once 的捞取范围里**，否则一次失败永久失联。"""
    model = _MODELS[source_type]
    await session.execute(
        update(model)
        .where(model.id == item_id, model.user_id == user_id)
        .values(index_status=FAILED)
    )

async def drop_vector(user_id: int, source_type: str, item_id: int) -> None:
    """删向量副本。**全异常自吞**——向量库的问题不能影响主流程。

    为什么必须吞：vector_repo.delete_by_source 内部要开 PG session，PG 引擎没起
    时 get_pg_session() 抛 BizError，会一路穿透到 router，把「删商品」这个
    **已经成功的操作**报成 400/500（2026-10-17 实测：3 个测试因此变红）。

    吞掉之后残留的孤儿向量有两道兜底：
      1. sync_one 发现目标不存在时会删副本收工；
      2. 若该行没有任务在跑，reaper 会重新捞起它。
    不兜底的后果：PG 里留着指向已删商品的向量，search_similar 照样命中它，
    回 MySQL 取原文时什么都取不到 → RAG 结果里出现空条目（违反「MySQL 是事实源」）。

    与 enqueue_sync 同口径（都是「Redis/PG 侧的失败不阻塞业务」），
    放一起是为了让调用方只需 import 一个模块。
    """
    try:
        await vector_repo.delete_by_source(user_id, source_type, item_id)
    except Exception:
        logger.warning("删向量副本失败 %s:%s（主流程已成功，残留由 reaper 兜）",
                       source_type, item_id, exc_info=True)


async def enqueue_sync(user_id: int, source_type: str, item_id: int) -> bool:
    """投一条索引任务。**永不抛异常**——投递失败只返回 False。

       为什么必须"永不抛"：调用点在业务事务**提交之后**，此时用户数据已落库、
       用户看得见了。这里抛异常会让上层 500，用户以为保存失败但数据其实在；
       更糟的是有的实现会顺手回滚——那就把用户数据搞丢了。
       投递失败时状态留 PENDING，等 reaper 兜。
       """
    try:
        pool = await get_pool()
        job = await pool.enqueue_job(
            "sync_one",user_id,source_type,item_id,
            # 同 ID已在队列时 enqueue_job 返回 None——天然去重：
            # 同一商品连改 5 次只排队一次，worker 处理时读的是最新 MySQL 数据
            _job_id=f"idx:{source_type}:{item_id}"
        )
        if job is None:
            logger.info("索引任务已在队列,跳过 %s:%s:%s",user_id,source_type,item_id)
        return True
    except Exception :
        logger.error("投索引任务失败 %s:%s:%s(状态仍为PENDING，等reaper重试)",user_id,source_type,item_id,exc_info=True)
        return False


async def sync_one(ctx:dict,user_id: int, source_type: str, item_id: int) -> None:
    """arq 任务函数。**只有 PG 写成功才置 SYNCED**。

    顺序不可换：
      1. RUNNING  —— 让「停在哪一步」可辨
      2. 读数据 + 切片 —— 读不到（已删）就删副本收工
      3. 调 embedding —— 内部自己查 key      4. 写 PGVector
      5. SYNCED   —— 🔴 必须在 4 之后"""

    async with async_session_local() as session:
        await set_running(user_id, source_type, item_id, session)
        await session.commit()
        model = _MODELS[source_type]
        row = await session.get(model, item_id)
        if row is None or row.user_id != user_id:
            logger.info("目标索引不存在，删除当前副本 %s:%s",source_type,item_id)
            await vector_repo.delete_by_source(user_id, source_type, item_id)
            return
        text = build_item_text(row.name,row.specs,row.note)
    if not text.strip():
# 全空的物品无从向量化。标 SYNCED（"确实不需要索引"）而不是留 PENDING
# 反复重投——留 PENDING 会被 reaper 永远捞起来。
        async with async_session_local() as session:
            await set_synced(user_id, source_type, item_id, session)
            await session.commit()
        return

    async with async_session_local() as session:
        try:
            vectors = await embedding_client.embed_texts(user_id,[text],session)
        except(embedding_client.EmbeddingKeyRejected,
                embedding_client.EmbeddingDimMismatch) as exc:
    # 不可重试：key 已死 /维度配置错，再试100 次也是同样结果。
    # 直接置 FAILED —— FAILED 在 reap_once 的捞取范围内，
    # key 修好/配置改好后仍能被重新捞起，不会永久失联。
                    logger.warning("embedding 不可重试，置 FAILED %s:%s:%s —— %s",
                           source_type, item_id, user_id, exc)
                    async with async_session_local() as s2:
                        await set_failed(user_id, source_type, item_id, s2)
                        await s2.commit()
                    return
        except embedding_client.EmbeddingCallFailed as exc:
    # 可重试：欠费 / 网关抖动 / 响应格式异常。
    # 抛 Retry 让 arq 退避 5/10/15 秒；用尽后 arq **不会**改业务表
    # 状态，停在 RUNNING 等 reaper 超时（index_stale_seconds）自愈。
                logger.warning("embedding 可重试，退避 %s:%s:%s —— %s",
                           source_type, item_id, user_id, exc)
                raise Retry(defer=ctx.get("job_try", 1) * 5) from exc
    if not vectors or not vectors[0]:
        async with async_session_local() as session:
            await set_failed(user_id, source_type, item_id, session)
            await session.commit()
        return
    #写pgsql
    await vector_repo.upsert_embedding(user_id, source_type, item_id,text,vectors[0])
    #置 SYNCED
    async with async_session_local() as session:
        await set_synced(user_id, source_type, item_id, session)
        await session.commit()


async def reap_once() ->int:
    """捞一批待索引的重新投队列，返回投递成功条数。

       捞取范围**必须含 FAILED**：key 欠费修好后，没有入口重新索引就永久失联。
       RUNNING 只捞超时的——正常处理中的不能抢。
       """
    stale = get_current_time() - timedelta(seconds=settings.index_stale_seconds)
    picked = 0
    for source_type,model in _MODELS.items():
        async with async_session_local() as session:
            #🔴 await 必须紧贴 session.scalars(...)：写成
            #    `await session.scalars(q)\n    .all()` 的话，.all() 作用在
            #    coroutine 上 → AttributeError: 'coroutine' object has no attribute 'all'
            # 🔴 用 session.execute(...) 而不是 session.scalars(...)：
            #    scalars() 只取结果集的【第一列】，多列查询会丢掉其余列，
            #    下游 `for item_id, uid in rows` 解包时就成了「解包一个 int」。
            rows = list((await session.execute(
                select(model.id,model.user_id)
                .where(model.index_status.in_([PENDING,FAILED]))
            )).all())
            running = list((await session.execute(
                select(model.id, model.user_id)
                .where(model.index_status == RUNNING, model.update_time < stale)
            )).all())
        #🔴投递循环必须在 session 外（下面）：开session 时是为了查，
        # 投递要走 Redis，别占着 MySQL 连接
        for item_id,uid in list(rows)+list(running):
            if await enqueue_sync(uid,source_type,item_id):
                picked += 1
    return picked


