from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import get_db_session, CurrentUser, require_same_origin_write
from app.repository.cart_repo import get_cart_by_user_id, delete_cart_item, update_cart_item, add_cart_item
from app.schemas.cart_sche import CartItemOutSchema, CartItemUpdateSchema, CartItemInSchema

cart_router = APIRouter(tags=["cart"],prefix="/cart")
@cart_router.get("/items")
async def get_cart_items(user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    user_id = user.id
    cart_items  = await get_cart_by_user_id(user_id,session)
    return success([CartItemOutSchema.model_validate(r) for r in cart_items])
@cart_router.patch("/items/{item_id}",dependencies=[Depends(require_same_origin_write)])
async def update_item(update_in: CartItemUpdateSchema,user: CurrentUser,item_id: int,session: AsyncSession = Depends(get_db_session)):
    item = await update_cart_item(update_in,user.id,item_id,session)
    return success(CartItemOutSchema.model_validate(item))
@cart_router.delete("/items/{item_id}",dependencies=[Depends(require_same_origin_write)])
async def delete_item(item_id: int,user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    await delete_cart_item(item_id,user.id,session)
    return success({"id": item_id})
@cart_router.post("/items",dependencies=[Depends(require_same_origin_write)])
async def add_item(cart_item_in: CartItemInSchema,user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    item = await add_cart_item(cart_item_in,user.id,session)
    return success(CartItemOutSchema.model_validate(item))
@cart_router.post("/items/{item_id}",dependencies=[Depends(require_same_origin_write)])
async def transform_item(session: AsyncSession = Depends(get_db_session)):
    pass

