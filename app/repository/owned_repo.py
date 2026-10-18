from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import OwnedItem
from app.repository.group_repo import delete_refs_by_item
from app.schemas.owned_sche import OwnedItemInSchema, OwnedItemUpdateSchema
from app.services import image_service


async def get_owned_by_user_id(user_id: int, session: AsyncSession) -> list[OwnedItem]:
    result = await session.scalars(
        select(OwnedItem)
        .where(OwnedItem.user_id == user_id)
        .order_by(OwnedItem.purchased_at.desc(), OwnedItem.create_time.desc())
    )
    return list(result.all())


async def add_owned_item(owned_item_in: OwnedItemInSchema, user_id: int, session: AsyncSession) -> OwnedItem:
    item = OwnedItem(**owned_item_in.model_dump(), user_id=user_id)
    session.add(item)
    if item.image:
        await image_service.reference_image(item.image, session)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_owned_item(item_id: int, user_id: int, session: AsyncSession) -> None:
    item = await session.scalar(
        select(OwnedItem)
        .where(OwnedItem.id == item_id, OwnedItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    released_path = item.image
    await session.delete(item)
    # 分组跟随：物品没了，它在各分组里的成员关系一起走（同一事务）
    await delete_refs_by_item("owned", item_id, session)
    await session.commit()
    await image_service.release_if_unreferenced(released_path, session)


async def update_owned_item(update_in: OwnedItemUpdateSchema, user_id: int, item_id: int,
                            session: AsyncSession) -> OwnedItem:
    item = await session.scalar(
        select(OwnedItem)
        .where(OwnedItem.id == item_id, OwnedItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    changes = update_in.model_dump(exclude_unset=True)
    old_image = item.image
    for key, value in changes.items():
        setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    # 换了图：新的引用、旧的释放；没换图两个分支都自然跳过
    if item.image and item.image != old_image:
        await image_service.reference_image(item.image, session)
        await image_service.release_if_unreferenced(old_image, session)
    return item
# 获取用户最新购买的物品（未写router）
async def get_latest_owned_item(user_id: int, session: AsyncSession) -> list[OwnedItem]:
    result = await session.scalars(
        select(OwnedItem)
        .where(OwnedItem.user_id == user_id)
        .order_by(OwnedItem.purchased_at.desc(), OwnedItem.create_time.desc())
        .limit(5)
    )
    return list(result.all())
