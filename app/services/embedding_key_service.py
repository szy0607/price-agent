from dataclasses import dataclass

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, BizError

from app.core.key_crypto import decrypt, encrypt
from app.models.user_embedding_key import UserEmbeddingKey
from app.schemas.setting_sche import EmbeddingKeyInSchema


@dataclass(frozen = True)
class EmbeddingKeyRecord:
    key_id :int
    provider: str
    base_url: str
    api_key: str
    model_name: str
#文本向量化前取 key：默认向量模型且 active 才可用；没有就报错，绝不回落
async def key_for_embedding(user_id:int,session:AsyncSession)->EmbeddingKeyRecord:
    existing = await session.scalar(
        select(UserEmbeddingKey).where(UserEmbeddingKey.user_id == user_id,UserEmbeddingKey.is_default==True)
    )
    if existing is None:
        raise BizError(ErrorCode.PARAM_INVALID, "尚未配置向量模型，或未设置默认向量模型")
    if existing.status != "active":
        raise BizError(ErrorCode.PARAM_INVALID, "默认向量模型的 key 已失效，请重新配置")

    return EmbeddingKeyRecord(
        key_id = existing.id,
        provider=existing.provider,
        base_url=existing.base_url,
        api_key=decrypt(existing.encrypted_key),
        model_name=existing.model_name,
    )
#向量 key 失效标记（按 key_id，与推理 key 天然隔离，互不牵连）
async def mark_invalid(key_id :int,user_id:int,session:AsyncSession):
    await session.execute(
        update(UserEmbeddingKey).where(UserEmbeddingKey.id == key_id,UserEmbeddingKey.user_id==user_id)
        .values(status="invalid")
    )
    await session.commit()
#添加向量 key：新增即默认，先把该用户所有向量 key 清零
async  def add_embedding_key(data:EmbeddingKeyInSchema,user_id:int,session:AsyncSession)->UserEmbeddingKey:
    await session.execute(
        update(UserEmbeddingKey).where(UserEmbeddingKey.user_id==user_id).values(is_default=False)
    )
    row = UserEmbeddingKey(
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
#更新向量 key：全字段覆盖，is_default 不动。select 兼做存在性 + 归属校验。
async def update_embedding_key(key_id: int, data: EmbeddingKeyInSchema,
                         user_id: int, session: AsyncSession) -> UserEmbeddingKey:
    row = await session.scalar(
        select(UserEmbeddingKey).where(UserEmbeddingKey.id == key_id, UserEmbeddingKey.user_id == user_id)
    )
    if row is None:
        raise BizError(ErrorCode.PARAM_INVALID, "向量模型记录不存在")
    row.provider = data.provider
    row.base_url = data.base_url
    row.encrypted_key = encrypt(data.api_key)
    row.key_suffix = data.api_key[-4:]
    row.status = "active"
    row.model_name = data.model_name
    await session.commit()
    await session.refresh(row)
    return row
#向量 key 列表
async def list_embedding_keys(user_id: int, session: AsyncSession) -> list[UserEmbeddingKey]:
    result = await session.scalars(
        select(UserEmbeddingKey).where(UserEmbeddingKey.user_id == user_id).order_by(UserEmbeddingKey.create_time.asc())
    )
    return list(result.all())
#删除：rowcount=0 即「行不存在或不是你的」。删除默认不转移（与推理 key 同口径拍板）
async def delete_embedding_key(key_id: int, user_id: int, session: AsyncSession) -> None:
    result = await session.execute(
        delete(UserEmbeddingKey).where(UserEmbeddingKey.id == key_id, UserEmbeddingKey.user_id == user_id)
    )
    if result.rowcount == 0:  # type: ignore
        raise BizError(ErrorCode.PARAM_INVALID, "向量模型记录不存在")
    await session.commit()
async def set_default_embedding_key(key_id: int, user_id: int, session: AsyncSession) -> None:
    """切默认：先全清零，再单行置一；置一命中 0 行说明 id 不对，回滚报错。"""
    await session.execute(
        update(UserEmbeddingKey).where(UserEmbeddingKey.user_id == user_id).values(is_default=False)
    )
    result = await session.execute(
        update(UserEmbeddingKey)
        .where(UserEmbeddingKey.id == key_id, UserEmbeddingKey.user_id == user_id)
        .values(is_default=True)
    )
    if result.rowcount == 0:  # type: ignore
        await session.rollback()   # 清零那步还没提交，一并作废
        raise BizError(ErrorCode.PARAM_INVALID, "向量模型记录不存在")
    await session.commit()
