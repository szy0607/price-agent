from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.api_key_crypto import KeyConfigurationError, KeyRing, normalize_provider
from app.core.config import settings
from app.core.errors import BizError, ErrorCode, success
from app.database.session import async_session_local
from app.dependence import CurrentUser, require_same_origin_write
from app.models import User, UserApiKey
from app.services.api_key_service import ApiKeyService, KeyRecordError
from app.services.chat_service import (
    MODEL_PROVIDERS,
    ModelCatalogError,
    list_user_models,
    resolve_model_name,
    validate_model_name,
)


settings_router = APIRouter(prefix="/settings", tags=["settings"])


class ApiKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=4096)


class ModelProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    # 不写 pattern：pydantic v2 的 pattern 是不锚定的 is_match，会静默放过 "gpt-4o\n" 这类脏值。
    # max_length 必须等于列宽 String(128)，格式判定在 validate_model_name 里做。
    model_name: str | None = Field(default=None, max_length=128)


def _service() -> ApiKeyService:
    try:
        return ApiKeyService(async_session_local, KeyRing.from_settings(settings))
    except KeyConfigurationError as exc:
        raise BizError(ErrorCode.INTERNAL, "内部服务器错误") from exc


def _provider(raw: str) -> str:
    try:
        return normalize_provider(raw)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "服务商标识无效") from exc


def _metadata(row) -> dict:
    return {
        "provider": row.provider,
        "masked_key": row.masked_key,
        "status": row.status,
        "model_name": row.model_name,
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


async def _saved_models(user_id: int) -> dict[str, str | None]:
    """每个厂商已记住的模型名。不加锁、不解密，也不走 list_key_metadata——后者会为每次页面浏览多打一条审计。"""
    async with async_session_local() as db:
        rows = (await db.execute(
            select(UserApiKey.provider, UserApiKey.model_name).where(UserApiKey.user_id == user_id)
        )).all()
    return {row.provider: row.model_name for row in rows}


@settings_router.get("/model")
async def get_model(user: CurrentUser):
    saved = await _saved_models(user.id)
    options = [
        {
            "provider": provider,
            "label": config["label"],
            "model": config["model"],
            "saved_model": saved.get(provider),
        }
        for provider, config in MODEL_PROVIDERS.items()
    ]
    model_name = resolve_model_name(user.model_provider, saved.get(user.model_provider)) if user.model_provider in MODEL_PROVIDERS else None
    return success({"provider": user.model_provider, "model_name": model_name, "options": options})


@settings_router.get("/models/{provider}", dependencies=[Depends(require_same_origin_write)])
async def list_provider_models(provider: str, user: CurrentUser):
    target = _provider(provider)
    if target not in MODEL_PROVIDERS:
        raise BizError(ErrorCode.PARAM_INVALID, "该服务商暂不支持模型咨询")
    try:
        ring = KeyRing.from_settings(settings)
    except KeyConfigurationError:
        raise BizError(ErrorCode.INTERNAL, "密钥服务暂不可用") from None
    try:
        options = await list_user_models(user.id, target, ring)
    except KeyRecordError:
        raise BizError(ErrorCode.PARAM_INVALID, "请先保存该服务商的 API Key") from None
    except ModelCatalogError as exc:
        raise BizError(ErrorCode.INTERNAL, str(exc)) from None
    return success({"provider": target, "models": options, "default": MODEL_PROVIDERS[target]["model"]})


@settings_router.put("/model", dependencies=[Depends(require_same_origin_write)])
async def set_model(payload: ModelProviderInput, user: CurrentUser):
    provider = _provider(payload.provider)
    if provider not in MODEL_PROVIDERS:
        raise BizError(ErrorCode.PARAM_INVALID, "该服务商暂不支持模型咨询")
    try:
        model_name = validate_model_name(payload.model_name)
    except ValueError:
        raise BizError(ErrorCode.PARAM_INVALID, "模型名称格式无效") from None
    async with async_session_local() as db:
        async with db.begin():
            owner = await db.scalar(select(User).where(User.id == user.id).with_for_update())
            # 这行要写 model_name 了，所以要锁；锁顺序沿用 ApiKeyService 的 users → user_api_keys。
            key = await db.scalar(select(UserApiKey).where(
                UserApiKey.user_id == user.id,
                UserApiKey.provider == provider,
                UserApiKey.status == "active",
            ).with_for_update())
            if owner is None or key is None:
                raise BizError(ErrorCode.PARAM_INVALID, "请先保存该服务商的 API Key")
            owner.model_provider = provider
            key.model_name = model_name
    effective = resolve_model_name(provider, model_name)
    return success({"provider": provider, "model": effective, "model_name": effective})
