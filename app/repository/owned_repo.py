from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import OwnedItem
from app.schemas.owned_sche import OwnedItemInSchema, OwnedItemUpdateSchema


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
    await session.commit()
    await session.refresh(item)
    return item


async def delete_owned_item(item_id: int, user_id: int, session: AsyncSession) -> None:
    result = await session.execute(
        delete(OwnedItem)
        .where(OwnedItem.id == item_id, OwnedItem.user_id == user_id)
    )
    if result.rowcount == 0:  # type: ignore
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    await session.commit()


async def update_owned_item(update_in: OwnedItemUpdateSchema, user_id: int, item_id: int,
                            session: AsyncSession) -> OwnedItem:
    item = await session.scalar(
        select(OwnedItem)
        .where(OwnedItem.id == item_id, OwnedItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    changes = update_in.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    return item
