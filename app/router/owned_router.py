from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import get_db_session, CurrentUser, require_same_origin_write
from app.repository.owned_repo import (
    get_owned_by_user_id,
    add_owned_item,
    delete_owned_item,
    update_owned_item,
)
from app.schemas.owned_sche import (
    OwnedItemOutSchema,
    OwnedItemInSchema,
    OwnedItemUpdateSchema,
)

owned_router = APIRouter(tags=["owned"], prefix="/items")


@owned_router.get("")
async def get_owned_items(user: CurrentUser, session: AsyncSession = Depends(get_db_session)):
    items = await get_owned_by_user_id(user.id, session)
    return success([OwnedItemOutSchema.model_validate(r) for r in items])


@owned_router.post("", dependencies=[Depends(require_same_origin_write)])
async def add_item(owned_item_in: OwnedItemInSchema, user: CurrentUser,
                   session: AsyncSession = Depends(get_db_session)):
    item = await add_owned_item(owned_item_in, user.id, session)
    return success(OwnedItemOutSchema.model_validate(item))


@owned_router.patch("/{item_id}", dependencies=[Depends(require_same_origin_write)])
async def update_item(item_id: int, update_in: OwnedItemUpdateSchema, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    item = await update_owned_item(update_in, user.id, item_id, session)
    return success(OwnedItemOutSchema.model_validate(item))


@owned_router.delete("/{item_id}", dependencies=[Depends(require_same_origin_write)])
async def delete_item(item_id: int, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    await delete_owned_item(item_id, user.id, session)
    return success({"id": item_id})
