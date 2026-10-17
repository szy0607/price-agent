
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import get_db_session, CurrentUser, require_same_origin_write
from app.repository.cart_repo import get_cart_by_user_id, delete_cart_item, update_cart_item, add_cart_item, transfer_to_owned_item
from app.schemas.cart_sche import CartItemOutSchema, CartItemUpdateSchema, CartItemInSchema, AiDraftInSchema
from app.schemas.purchase_sche import PurchaseInputSchema
from app.schemas.owned_sche import  OwnedItemOutSchema
from app.services import spec_complete_service, index_service

logger = logging.getLogger(__name__)
cart_router = APIRouter(tags=["cart"],prefix="/cart")
@cart_router.get("/items")
async def get_cart_items(user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    user_id = user.id
    cart_items  = await get_cart_by_user_id(user_id,session)
    return success([CartItemOutSchema.model_validate(r) for r in cart_items])
@cart_router.patch("/items/{item_id}/update",dependencies=[Depends(require_same_origin_write)])
async def update_item(update_in: CartItemUpdateSchema,user: CurrentUser,item_id: int,session: AsyncSession = Depends(get_db_session)):
    item = await update_cart_item(update_in,user.id,item_id,session)
    await index_service.enqueue_sync(user.id,"cart",item.id)
    return success(CartItemOutSchema.model_validate(item))
@cart_router.delete("/items/{item_id}/delete",dependencies=[Depends(require_same_origin_write)])
async def delete_item(item_id: int,user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    await delete_cart_item(item_id,user.id,session)
    await index_service.drop_vector(user.id,"cart",item_id)
    return success({"id": item_id})
@cart_router.post("/items",dependencies=[Depends(require_same_origin_write)])
async def add_item(cart_item_in: CartItemInSchema,user: CurrentUser,session: AsyncSession = Depends(get_db_session)):
    item = await add_cart_item(cart_item_in,user.id,session)
    await index_service.enqueue_sync(user.id,"cart",item.id)
    return success(CartItemOutSchema.model_validate(item))
@cart_router.post("/items/{item_id}/transform",dependencies=[Depends(require_same_origin_write)])
async def transfer_to_item(item_id: int,user: CurrentUser,extra: PurchaseInputSchema,session: AsyncSession = Depends(get_db_session)):
    (owned_item,record) = await transfer_to_owned_item(item_id,user.id,session,extra)
    # 旧 cart 行已删 → 删它的向量副本；新 owned / purchase 两行都要索引
    await index_service.drop_vector(user.id,"cart",item_id)
    await index_service.enqueue_sync(user.id,"owned",owned_item.id)
    await index_service.enqueue_sync(user.id,"purchase",record.id)
    return success({"owned": OwnedItemOutSchema.model_validate(owned_item)})
@cart_router.post("/items/ai-draft", dependencies=[Depends(require_same_origin_write)])
async def ai_draft(data: AiDraftInSchema, user: CurrentUser,
                   session: AsyncSession = Depends(get_db_session)):
    draft = await spec_complete_service.complete_specs(data.name, data.category, user.id, session)
    return success(draft)

