from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import CurrentUser, get_db_session, require_same_origin_write
from app.repository.group_repo import (
    add_group_item,
    create_group,
    delete_group,
    get_group_detail,
    list_groups,
    remove_group_item,
    update_group,
)
from app.schemas.group_sche import (
    GroupItemOutSchema,
    GroupRefInSchema,
    ItemGroupDetailOutSchema,
    ItemGroupInSchema,
    ItemGroupListItemSchema,
    ItemGroupOutSchema,
    ItemGroupUpdateSchema,
)

group_router = APIRouter(tags=["group"], prefix="/groups")


@group_router.get("")
async def get_groups(user: CurrentUser, session: AsyncSession = Depends(get_db_session)):
    rows = await list_groups(user.id, session)
    return success([ItemGroupListItemSchema.model_validate(r) for r in rows])


@group_router.post("", dependencies=[Depends(require_same_origin_write)])
async def post_group(group_in: ItemGroupInSchema, user: CurrentUser,
                     session: AsyncSession = Depends(get_db_session)):
    group = await create_group(group_in, user.id, session)
    return success(ItemGroupOutSchema.model_validate(group))


@group_router.get("/{group_id}")
async def get_group(group_id: int, user: CurrentUser,
                    session: AsyncSession = Depends(get_db_session)):
    detail = await get_group_detail(group_id, user.id, session)
    return success(ItemGroupDetailOutSchema(
        group=ItemGroupOutSchema.model_validate(detail["group"]),
        unpurchased=[GroupItemOutSchema.model_validate(i) for i in detail["unpurchased"]],
        purchased=[GroupItemOutSchema.model_validate(i) for i in detail["purchased"]],
        stats=detail["stats"],
    ))


@group_router.patch("/{group_id}", dependencies=[Depends(require_same_origin_write)])
async def patch_group(group_id: int, update_in: ItemGroupUpdateSchema, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    group = await update_group(update_in, group_id, user.id, session)
    return success(ItemGroupOutSchema.model_validate(group))


@group_router.delete("/{group_id}", dependencies=[Depends(require_same_origin_write)])
async def delete_group_by_id(group_id: int, user: CurrentUser,
                             session: AsyncSession = Depends(get_db_session)):
    await delete_group(group_id, user.id, session)
    return success({"id": group_id})


@group_router.post("/{group_id}/items", dependencies=[Depends(require_same_origin_write)])
async def post_group_item(group_id: int, ref_in: GroupRefInSchema, user: CurrentUser,
                          session: AsyncSession = Depends(get_db_session)):
    ref = await add_group_item(ref_in, group_id, user.id, session)
    return success({"group_id": ref.group_id, "item_type": ref.item_type, "item_id": ref.item_id})


@group_router.delete("/{group_id}/items/{item_type}/{item_id}",
                     dependencies=[Depends(require_same_origin_write)])
async def delete_group_item(group_id: int, item_type: Literal["cart", "owned"], item_id: int,
                            user: CurrentUser, session: AsyncSession = Depends(get_db_session)):
    await remove_group_item(item_type, item_id, group_id, user.id, session)
    return success({"group_id": group_id, "item_type": item_type, "item_id": item_id})
