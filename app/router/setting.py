from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import get_db_session, require_same_origin_write, CurrentUser
from app.schemas.setting_sche import (ApiKeyOutSchema, ApiKeyInSchema,
                                      EmbeddingKeyOutSchema, EmbeddingKeyInSchema)
from app.services import api_key_service, embedding_key_service

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
@settings_router.get("/embedding-keys")
async def get_embedding_keys(user: CurrentUser, session: AsyncSession=Depends(get_db_session)):
    rows = await embedding_key_service.list_embedding_keys(user.id, session)
    return success([EmbeddingKeyOutSchema.model_validate(r) for r in rows])
@settings_router.post("/embedding-keys", dependencies=[Depends(require_same_origin_write)])
async def add_embedding_key(data: EmbeddingKeyInSchema, user: CurrentUser,
                      session: AsyncSession = Depends(get_db_session)):
    row = await embedding_key_service.add_embedding_key(data, user.id, session)
    return success(EmbeddingKeyOutSchema.model_validate(row))
@settings_router.put("/embedding-keys/{key_id}", dependencies=[Depends(require_same_origin_write)])
async def update_embedding_key(key_id: int, data: EmbeddingKeyInSchema, user: CurrentUser,
                         session: AsyncSession = Depends(get_db_session)):
    row = await embedding_key_service.update_embedding_key(key_id, data, user.id, session)
    return success(EmbeddingKeyOutSchema.model_validate(row))
@settings_router.delete("/embedding-keys/{key_id}", dependencies=[Depends(require_same_origin_write)])
async def delete_embedding_key(key_id: int, user: CurrentUser,
                         session: AsyncSession = Depends(get_db_session)):
    await embedding_key_service.delete_embedding_key(key_id, user.id, session)
    return success({"id": key_id})
@settings_router.put("/embedding-keys/{key_id}/default", dependencies=[Depends(require_same_origin_write)])
async def set_default_embedding_key(key_id: int, user: CurrentUser,
                         session: AsyncSession = Depends(get_db_session)):
    await embedding_key_service.set_default_embedding_key(key_id, user.id, session)
    return success({"id": key_id})