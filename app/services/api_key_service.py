from dataclasses import dataclass

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, BizError

from app.core.key_crypto import decrypt, encrypt
from app.models.user_api_key import UserApiKey
from app.schemas.setting_sche import ApiKeyInSchema


@dataclass(frozen = True)
class KeyRecord:
    key_id :int
    provider: str
    base_url: str
    api_key: str
    model_name: str
#调用模型前取 key：is_default=1 且 active 才可用；没有就报错，绝不回落
async def key_for_call(user_id:int,session:AsyncSession)->KeyRecord:
    existing = await session.scalar(
        select(UserApiKey).where(UserApiKey.user_id == user_id,UserApiKey.is_default==True)
    )
    if existing is None:
        raise BizError(ErrorCode.PARAM_INVALID, "尚未配置模型，或未设置默认模型")
    if existing.status != "active":
        raise BizError(ErrorCode.PARAM_INVALID, "默认模型的 key 已失效，请重新配置")

    return KeyRecord(
        key_id = existing.id,
        provider=existing.provider,
        base_url=existing.base_url,
        api_key=decrypt(existing.encrypted_key),
        model_name=existing.model_name,
    )
#key失效标记
async def mark_invalid(key_id :int,user_id:int,session:AsyncSession):
    await session.execute(
        update(UserApiKey).where(UserApiKey.id == key_id,UserApiKey.user_id==user_id)
        .values(status="invalid")
    )
    await session.commit()
#添加api
async  def add_api_key(data:ApiKeyInSchema,user_id:int,session:AsyncSession)->UserApiKey:
    await session.execute(
        update(UserApiKey).where(UserApiKey.user_id==user_id).values(is_default=False)
    )
    row = UserApiKey(
        user_id=user_id,
        provider=data.provider,
        base_url=data.base_url,
        encrypted_key=encrypt(data.api_key),
        key_suffix=data.api_key[-4:],
        status="active",
        model_name=data.model_name,
        is_default=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
#更新api
async def update_api_key(key_id: int, data: ApiKeyInSchema,
                         user_id: int, session: AsyncSession) -> UserApiKey:
    """更新：全字段覆盖，is_default 不动。select 兼做存在性 + 归属校验。"""
    row = await session.scalar(
        select(UserApiKey).where(UserApiKey.id == key_id, UserApiKey.user_id == user_id)
    )
    if row is None:
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    row.provider = data.provider
    row.base_url = data.base_url
    row.encrypted_key = encrypt(data.api_key)
    row.key_suffix = data.api_key[-4:]
    row.status = "active"
    row.model_name = data.model_name
    await session.commit()
    await session.refresh(row)
    return row
#apikey列表
async def list_api_keys(user_id: int, session: AsyncSession) -> list[UserApiKey]:
    result = await session.scalars(
        select(UserApiKey).where(UserApiKey.user_id == user_id).order_by(UserApiKey.create_time.asc())
    )
    return list(result.all())
#删除
async def delete_api_key(key_id: int, user_id: int, session: AsyncSession) -> None:
    """纯 SQL：rowcount=0 即「行不存在或不是你的」。删除默认不转移（拍板）。"""
    result = await session.execute(
        delete(UserApiKey).where(UserApiKey.id == key_id, UserApiKey.user_id == user_id)
    )
    if result.rowcount == 0:  # type: ignore
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    await session.commit()
async def set_default(key_id: int, user_id: int, session: AsyncSession) -> None:
    """切默认：先全清零，再单行置一；置一命中 0 行说明 id 不对，回滚报错。"""
    await session.execute(
        update(UserApiKey).where(UserApiKey.user_id == user_id).values(is_default=False)
    )
    result = await session.execute(
        update(UserApiKey)
        .where(UserApiKey.id == key_id, UserApiKey.user_id == user_id)
        .values(is_default=True)
    )
    if result.rowcount == 0:  # type: ignore
        await session.rollback()   # 清零那步还没提交，一并作废
        raise BizError(ErrorCode.PARAM_INVALID, "记录不存在")
    await session.commit()