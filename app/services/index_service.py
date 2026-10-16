import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_pool
from app.models import CartItem, OwnedItem, PurchaseRecord

logger = logging.getLogger(__name__)
PENDING = "PENDING"
RUNNING = "RUNNING"
SYNCED = "SYNCED"
FAILED = "FAILED"
_MODELS = {"cart": CartItem, "owned": OwnedItem, "purchase": PurchaseRecord}


async def set_pending(user_id: int, source_type: str,item_id: int,session:AsyncSession) -> None:
    model = _MODELS[source_type]
    await session.execute(
        update(model)
        .where(model.id == item_id, model.user_id == user_id)
        .values(index_status=RUNNING)
    )

async def set_synced(user_id: int, source_type: str, item_id: int,
       session: AsyncSession) -> None:
    """置 SYNCED + 写 index_time。**只能在 PG 写入成功之后调"""
    model = _MODELS[source_type]
    from app.core.time import get_current_time
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
        logger.error("投索引任务失败 %s:%s:%s(状态仍为PENDING，等reaper重试)",user_id,source_type,item_id)
        return False
