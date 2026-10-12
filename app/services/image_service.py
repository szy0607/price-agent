"""图片上传的登记、引用与清理 —— 生命周期管理层。

与 item 表的分工（决策见 docs/图片上传服务-接口契约.md）：
- cart_item.image / owned_item.image 存路径字符串（对外契约不变）；
- image 表是「登记簿」：回答这张图是谁的、还有没有人用。

三个动作的调用时机：
- register_upload：POST /upload/image 落盘后（pending）
- reference_image：商品保存带图时（pending -> referenced）
- release_if_unreferenced：商品删除/换图后（无人引用 -> released）
- cleanup_once：lifespan 定时任务（删 stale pending + released 的文件和行）
"""
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_current_time
from app.models import CartItem, Image, OwnedItem
from app.services import image_store

logger = logging.getLogger(__name__)

# 上传后多久没人来认领就可清理（传了图没保存商品的窗口）
PENDING_TTL = timedelta(hours=24)

# 状态常量：pending=已上传无人引用 / referenced=被商品引用 / released=引用已释放待清理
STATUS_PENDING = "pending"
STATUS_REFERENCED = "referenced"
STATUS_RELEASED = "released"


async def register_upload(user_id: int, rel_path: str, session: AsyncSession) -> Image:
    """上传即登记：落盘成功后在 image 表建 pending 行。"""
    row = Image(user_id=user_id, path=rel_path, status=STATUS_PENDING)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def reference_image(rel_path: str, session: AsyncSession) -> None:
    """商品保存带图：pending -> referenced。

    只在 pending 时转——已是 referenced（被别的商品先用）或行不存在（历史数据）
    都不动，绝不让后保存的商品把图的状态改乱。
    """
    await session.execute(
        update(Image)
        .where(Image.path == rel_path, Image.status == STATUS_PENDING)
        .values(status=STATUS_REFERENCED)
    )
    await session.commit()


async def release_if_unreferenced(rel_path: str | None, session: AsyncSession) -> None:
    """商品删除/换图后调用：两张 item 表都没人引用这张图才置 released。

    必须同时扫 cart_item 和 owned_item——双导航共用图，只扫一张会把在用的图误删。
    """
    if not rel_path:
        return
    cart_refs = await session.scalar(
        select(func.count()).select_from(CartItem).where(CartItem.image == rel_path)
    )
    owned_refs = await session.scalar(
        select(func.count()).select_from(OwnedItem).where(OwnedItem.image == rel_path)
    )
    if cart_refs or owned_refs:
        return
    await session.execute(
        update(Image).where(Image.path == rel_path, Image.status == STATUS_REFERENCED)
        .values(status=STATUS_RELEASED)
    )
    await session.commit()


async def cleanup_once(session: AsyncSession) -> dict:
    """定时清理：删「pending 超 24h」+「released」的文件和行。

    幂等是硬要求：行不在跳过、文件不在跳过——多 worker 重复跑、任务重叠跑
    都不能报错，也不能把在用的图删掉（只删上面两类状态）。
    """
    cutoff = get_current_time() - PENDING_TTL
    stale = list((await session.scalars(
        select(Image).where(
            ((Image.status == STATUS_PENDING) & (Image.create_time < cutoff))
            | (Image.status == STATUS_RELEASED)
        )
    )).all())
    removed_files = 0
    for row in stale:
        path = image_store.UPLOAD_DIR / Path(row.path).name
        try:
            path.unlink(missing_ok=True)
            removed_files += 1
        except OSError:
            logger.warning("清理图片文件失败: %s", row.path)
        await session.delete(row)
    await session.commit()
    if stale:
        logger.info("图片清理: 删除 %d 行（文件 %d 个）", len(stale), removed_files)
    return {"removed_rows": len(stale), "removed_files": removed_files}


async def path_owner_id(rel_path: str, session: AsyncSession) -> int | None:
    """按路径查归属；行不存在（历史数据/未登记）返回 None。"""
    return await session.scalar(select(Image.user_id).where(Image.path == rel_path))
