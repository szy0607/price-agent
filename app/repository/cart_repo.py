
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import CartItem, ItemGroupRef, OwnedItem, PurchaseRecord
from app.schemas.cart_sche import CartItemInSchema, CartItemUpdateSchema
from app.schemas.purchase_sche import PurchaseInputSchema
from app.services import image_service
from app.repository.group_repo import delete_refs_by_item, repoint_refs_on_transfer


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
    if item.image:
        await image_service.reference_image(item.image, session)
    await session.commit()
    await session.refresh(item)
    return item
async def delete_cart_item(item_id: int,user_id: int,session : AsyncSession):
    item = await session.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID,"记录不存在")
    released_path = item.image
    await session.delete(item)
    # 分组跟随：物品没了，它在各分组里的成员关系一起走（同一事务）
    await delete_refs_by_item("cart", item_id, session)
    await session.commit()
    # 删完再判释放：此刻两张 item 表若都没人引用这张图，置 released 待清理
    await image_service.release_if_unreferenced(released_path, session)
async def update_cart_item(update_in:CartItemUpdateSchema,user_id: int,item_id: int,session : AsyncSession):
    item = await session.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID,"记录不存在")
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
    # 先 flush 拿到 owned_item 的自增主键：分组改指向要用它，而 id 在 commit 前一直是 None
    await session.flush()
    await session.delete(item_in_cart)
    # 分组跟随：同一事务里把分组里指向旧 cart_item 的引用改指向新 owned_item，
    # 分组中该物品从「未购买」区翻到「已购买」区。漏了这一步它就成了分组里的孤儿。
    await repoint_refs_on_transfer(item_id, owned_item.id, session)
    await session.commit()
    await session.refresh(owned_item)
    return owned_item
