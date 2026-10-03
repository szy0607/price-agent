from fastapi import HTTPException
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import CartItem
from app.schemas.cart_sche import CartItemInSchema, CartItemUpdateSchema


async def get_cart_by_user_id(user_id: int,session : AsyncSession)->list[CartItem]:
    result = await session.scalars(
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.update_time.desc())
    )
    return list(result.all())
async def add_cart_item(cart_item_in: CartItemInSchema,user_id: int,session : AsyncSession):
    item = CartItem(**cart_item_in.model_dump(),user_id=user_id)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
async def delete_cart_item(item_id: int,user_id: int,session : AsyncSession):
    item = await session.execute(
       delete(CartItem)
       .where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item.rowcount == 0:#type: ignore
        raise BizError(ErrorCode.PARAM_INVALID,"记录不存在")
    await session.commit()
async def update_cart_item(update_in:CartItemUpdateSchema,user_id: int,item_id: int,session : AsyncSession):
    item = await session.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID,"记录不存在")
    changes = update_in.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    return item

