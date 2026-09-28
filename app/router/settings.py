from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.api_key_crypto import KeyConfigurationError, KeyRing, normalize_provider
from app.core.config import settings
from app.core.errors import BizError, ErrorCode, success
from app.core.session_auth import CurrentUser, require_same_origin_write
from app.database.session import async_session_local
from app.services.api_key_service import ApiKeyService


settings_router = APIRouter(prefix="/settings", tags=["settings"])


class ApiKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=4096)


def _service() -> ApiKeyService:
    try:
        return ApiKeyService(async_session_local, KeyRing.from_settings(settings))
    except KeyConfigurationError:
        raise BizError(ErrorCode.INTERNAL, "内部服务器错误") from None


def _provider(raw: str) -> str:
    try:
        return normalize_provider(raw)
    except ValueError:
        raise BizError(ErrorCode.PARAM_INVALID, "服务商标识无效") from None


def _metadata(row) -> dict:
    return {
        "provider": row.provider,
        "masked_key": row.masked_key,
        "status": row.status,
        "create_time": row.create_time.isoformat() + "Z",
        "update_time": row.update_time.isoformat() + "Z",
    }


@settings_router.get("/api-keys")
async def list_api_keys(user: CurrentUser):
    rows = await _service().list_key_metadata(user.id, actor=f"user:{user.id}")
    return success([_metadata(row) for row in rows])


@settings_router.put("/api-keys/{provider}", dependencies=[Depends(require_same_origin_write)])
async def save_api_key(provider: str, payload: ApiKeyInput, user: CurrentUser):
    try:
        await _service().save_key(user.id, _provider(provider), payload.api_key, actor=f"user:{user.id}")
    except (ValueError, UnicodeError):
        raise BizError(ErrorCode.PARAM_INVALID, "API Key 格式无效") from None
    return success({"provider": _provider(provider)})


@settings_router.delete("/api-keys/{provider}", dependencies=[Depends(require_same_origin_write)])
async def delete_api_key(provider: str, user: CurrentUser):
    deleted = await _service().delete_key(user.id, _provider(provider), actor=f"user:{user.id}")
    return success({"deleted": deleted})
