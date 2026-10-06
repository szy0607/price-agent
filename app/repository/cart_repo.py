
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import CartItem, OwnedItem, PurchaseRecord
from app.schemas.cart_sche import CartItemInSchema, CartItemUpdateSchema
from app.schemas.purchase_sche import PurchaseInputSchema


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

async def transfer_to_owned_item(item_id: int,user_id: int,session : AsyncSession,extra:PurchaseInputSchema):
    item_in_cart = await session.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item_in_cart is None:
        raise BizError(ErrorCode.PARAM_INVALID,"记录不存在，请刷新页面重试")


    price = extra.price if extra.price is not None else item_in_cart.price

    owned_item = OwnedItem(
        user_id=user_id, category=item_in_cart.category, name=item_in_cart.name, specs=item_in_cart.specs, image=item_in_cart.image,
        note=item_in_cart.note, platform=extra.platform,
        purchased_at=extra.purchased_at, price=price,
    )
    record = PurchaseRecord(
        user_id=user_id, name=item_in_cart.name, platform=extra.platform,
        price=price, specs=item_in_cart.specs, purchased_at=extra.purchased_at, note=extra.note,
    )
    session.add_all([owned_item,record])
    await session.delete(item_in_cart)
    await session.commit()
    await session.refresh(owned_item)
    return owned_item
