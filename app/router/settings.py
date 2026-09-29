from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.api_key_crypto import KeyConfigurationError, KeyRing, normalize_provider
from app.core.config import settings
from app.core.errors import BizError, ErrorCode, success
from app.core.session_auth import CurrentUser, require_same_origin_write
from app.database.session import async_session_local
from app.models import User, UserApiKey
from app.services.api_key_service import ApiKeyService
from app.services.chat_service import MODEL_PROVIDERS


settings_router = APIRouter(prefix="/settings", tags=["settings"])


class ApiKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=4096)


class ModelProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str


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


@settings_router.get("/model")
async def get_model(user: CurrentUser):
    options = [
        {"provider": provider, "label": config["label"], "model": config["model"]}
        for provider, config in MODEL_PROVIDERS.items()
    ]
    return success({"provider": user.model_provider, "options": options})


@settings_router.put("/model", dependencies=[Depends(require_same_origin_write)])
async def set_model(payload: ModelProviderInput, user: CurrentUser):
    provider = _provider(payload.provider)
    if provider not in MODEL_PROVIDERS:
        raise BizError(ErrorCode.PARAM_INVALID, "该服务商暂不支持模型咨询")
    async with async_session_local() as db:
        async with db.begin():
            owner = await db.scalar(select(User).where(User.id == user.id).with_for_update())
            key = await db.scalar(select(UserApiKey).where(
                UserApiKey.user_id == user.id,
                UserApiKey.provider == provider,
                UserApiKey.status == "active",
            ))
            if owner is None or key is None:
                raise BizError(ErrorCode.PARAM_INVALID, "请先保存该服务商的 API Key")
            owner.model_provider = provider
    return success({"provider": provider, "model": MODEL_PROVIDERS[provider]["model"]})
