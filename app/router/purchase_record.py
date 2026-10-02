"""消费记录：用户自记的已购商品流水（商品名 / 链接 / 价格 / 平台 / 规格 / 购买日期时间）。

价格列的口径沿用决策 #31③：**用户自己填、自己确认的值**，不是系统价格情报；
接口不承诺它是实时价，抓页面也绝不回填价格。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.core.errors import BizError, ErrorCode, success
from app.database.session import async_session_local
from app.dependence import CurrentUser, get_current_session, require_same_origin_write
from app.models import PurchaseRecord
from app.services.product_page import PageFetchError, fetch_product_draft

purchase_router = APIRouter(prefix="/purchase-records", tags=["purchase-records"])

# 现有列表接口都没有分页（GET /settings/api-keys 直接返回裸数组），这里保持一致，
# 只加一道硬上限防止把整张表拖进浏览器。
_MAX_RECORDS = 200
_SPECS_MAX_PAIRS = 30
_SPECS_KEY_CAP = 64
_SPECS_VALUE_CAP = 128


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # max_length 与列宽对齐；name 走「品牌+型号+商品名」三合一自由填写（决策 #31①）
    name: str = Field(min_length=1, max_length=256)
    product_url: str | None = Field(default=None, max_length=512)
    platform: str | None = Field(default=None, max_length=64)
    price: float | None = Field(default=None, ge=0, lt=1_000_000_000)
    specs: dict = Field(default_factory=dict)
    purchased_at: datetime | None = None
    note: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def check_name(self):
        if not self.name.strip():
            raise ValueError("商品名称不能为空")
        return self


class LinkPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_url: str = Field(min_length=8, max_length=512)


def _validate_url(raw: str | None) -> str | None:
    """只挡 scheme 和不可见字符，**不用** product_page 的域名白名单。

    白名单管的是「我们主动去抓谁」（SSRF 防线），不是「用户能记什么链接」——
    他买完在得物 / 闲鱼 / 小红书上看到的链接也该存得下来。
    但 http/https 之外必须拒：链接会渲染成 <a href>，javascript: 就是存储型 XSS。
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > 512 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise BizError(ErrorCode.PARAM_INVALID, "商品链接格式无效")
    if not value.lower().startswith(("http://", "https://")):
        raise BizError(ErrorCode.PARAM_INVALID, "商品链接需以 http:// 或 https:// 开头")
    return value


def _validate_specs(raw: dict) -> dict:
    """规格只留标量键值，其余（嵌套 dict / list / None）丢掉。

    这些值最终要拼成一行文本进对话上下文，嵌套结构压不成安全的单行。
    """
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if len(cleaned) >= _SPECS_MAX_PAIRS:
            break
        if not isinstance(key, str):
            continue
        if isinstance(value, bool):
            text = "是" if value else "否"
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, str):
            text = value
        else:
            continue
        key = " ".join(key.split())[:_SPECS_KEY_CAP]
        text = " ".join(text.split())[:_SPECS_VALUE_CAP]
        if key and text:
            cleaned[key] = text
    return cleaned


def _validate_purchased_at(raw: datetime | None) -> datetime | None:
    """库里存的是 naive UTC（app 连接固定 +00:00），带时区的入参先归一。"""
    if raw is None:
        return None
    if raw.tzinfo is not None:
        return raw.astimezone(timezone.utc).replace(tzinfo=None)
    return raw


def _row_dict(row: PurchaseRecord) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "product_url": row.product_url,
        "platform": row.platform,
        "price": row.price,
        "specs": row.specs,
        "purchased_at": row.purchased_at.isoformat() + "Z" if row.purchased_at else None,
        "note": row.note,
        "create_time": row.create_time.isoformat() + "Z",
        "update_time": row.update_time.isoformat() + "Z",
    }


def _fields(payload: RecordInput) -> dict:
    return {
        "name": " ".join(payload.name.split())[:256],
        "product_url": _validate_url(payload.product_url),
        "platform": payload.platform.strip()[:64] if payload.platform and payload.platform.strip() else None,
        "price": payload.price,
        "specs": _validate_specs(payload.specs),
        "purchased_at": _validate_purchased_at(payload.purchased_at),
        "note": payload.note.strip()[:512] if payload.note and payload.note.strip() else None,
    }


@purchase_router.get("")
async def list_records(user: CurrentUser):
    async with async_session_local() as db:
        rows = (
            await db.scalars(
                select(PurchaseRecord)
                .where(PurchaseRecord.user_id == user.id)
                .order_by(PurchaseRecord.create_time.desc(), PurchaseRecord.id.desc())
                .limit(_MAX_RECORDS)
            )
        ).all()
    return success([_row_dict(row) for row in rows])


@purchase_router.post("", dependencies=[Depends(require_same_origin_write)])
async def create_record(payload: RecordInput, user: CurrentUser):
    fields = _fields(payload)
    async with async_session_local() as db:
        async with db.begin():
            row = PurchaseRecord(user_id=user.id, **fields)
            db.add(row)
            await db.flush()
            await db.refresh(row)
    return success(_row_dict(row))


async def _owned_for_update(db, record_id: int, user_id: int) -> PurchaseRecord:
    """按 id + user_id 取行并加锁；取不到就是「不存在」。

    别人的 id 一律走这里回 40001，不给「存在但不属于你」这种可枚举的差别。
    """
    row = await db.scalar(
        select(PurchaseRecord)
        .where(PurchaseRecord.id == record_id, PurchaseRecord.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise BizError(ErrorCode.PARAM_INVALID, "消费记录不存在")
    return row


@purchase_router.put("/{record_id}", dependencies=[Depends(require_same_origin_write)])
async def update_record(record_id: int, payload: RecordInput, user: CurrentUser):
    fields = _fields(payload)
    async with async_session_local() as db:
        async with db.begin():
            row = await _owned_for_update(db, record_id, user.id)
            for key, value in fields.items():
                setattr(row, key, value)
            await db.flush()
            await db.refresh(row)
    return success(_row_dict(row))


@purchase_router.delete("/{record_id}", dependencies=[Depends(require_same_origin_write)])
async def delete_record(record_id: int, user: CurrentUser):
    async with async_session_local() as db:
        async with db.begin():
            row = await _owned_for_update(db, record_id, user.id)
            await db.delete(row)
    return success({"id": record_id})


# 名义上是「读」，但它由用户输入驱动一次对外请求，且必须登录才能用 ——
# 只挂 require_same_origin_write 等于让匿名者拿我们的出口去撞京东，所以补上会话校验。
@purchase_router.post("/link-preview", dependencies=[Depends(require_same_origin_write), Depends(get_current_session)])
async def link_preview(payload: LinkPreviewInput):
    try:
        draft = await fetch_product_draft(payload.product_url)
    except PageFetchError:
        raise BizError(ErrorCode.PARAM_INVALID, "没能读到该商品页面，请直接手动填写") from None
    return success(draft)
