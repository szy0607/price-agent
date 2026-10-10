from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import get_db_session, require_same_origin_write, CurrentUser
from app.schemas.setting_sche import ApiKeyOutSchema, ApiKeyInSchema
from app.services import api_key_service

settings_router=APIRouter(tags=["setting"], prefix="/setting")
@settings_router.get("/api-keys")
async def get_api_keys(user: CurrentUser, session: AsyncSession=Depends(get_db_session)):
    rows = await api_key_service.list_api_keys(user.id, session)
    return success([ApiKeyOutSchema.model_validate(r) for r in rows])
@settings_router.post("/api-keys", dependencies=[Depends(require_same_origin_write)])
async def add_api_key(data: ApiKeyInSchema, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    row = await api_key_service.add_api_key(data, user.id, session)
    return success(ApiKeyOutSchema.model_validate(row))
@settings_router.put("/api-keys/{key_id}", dependencies=[Depends(require_same_origin_write)])
async def update_api_key(key_id: int, data: ApiKeyInSchema, user: CurrentUser,
                         session: AsyncSession = Depends(get_db_session)):
    row = await api_key_service.update_api_key(key_id, data, user.id, session)
    return success(ApiKeyOutSchema.model_validate(row))
@settings_router.delete("/api-keys/{key_id}", dependencies=[Depends(require_same_origin_write)])
async def delete_api_key(key_id: int, user: CurrentUser,
                         session: AsyncSession = Depends(get_db_session)):
    await api_key_service.delete_api_key(key_id, user.id, session)
    return success({"id": key_id})
@settings_router.put("/api-keys/{key_id}/default", dependencies=[Depends(require_same_origin_write)])
async def set_default(key_id: int, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    await api_key_service.set_default(key_id, user.id, session)
    return success({"id": key_id})