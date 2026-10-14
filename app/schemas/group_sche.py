from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank_to_none(v: str | None) -> str | None:
    """空白串一律归一成 None：备注传 "   " 等于没传，不该存一排空格进去。"""
    if v is None:
        return None
    v = v.strip()
    return v or None


class ItemGroupInSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100, description="分组名称")
    note: str | None = Field(default=None, max_length=512, description="分组备注")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("分组名不能为空白")
        return v

    @field_validator("note")
    @classmethod
    def check_note(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ItemGroupUpdateSchema(BaseModel):
    """PATCH 部分更新：全可选，repo 里 exclude_unset 只取提交了的字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("分组名不能为空白")
        return v

    @field_validator("note")
    @classmethod
    def check_note(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ItemGroupOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    note: str | None
    create_time: datetime
    update_time: datetime


class GroupRefInSchema(BaseModel):
    """把物品加入分组：item_type 决定 item_id 指向 cart_item 还是 owned_item。"""

    model_config = ConfigDict(extra="forbid")

    item_type: Literal["cart", "owned"]
    item_id: int = Field(gt=0)


class GroupItemOutSchema(BaseModel):
    """分组里的物品条目。cart_item / owned_item 共有字段，两区复用同一形状。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    name: str
    price: float | None
    specs: dict[str, str]
    image: str | None
    note: str | None


class GroupStatsOutSchema(BaseModel):
    """分组价格统计（2026-10-14 大宋拍板：数据库里存的价格，无价格的提示出来）。

    未购买区 = cart_item.price（参考价）；已购买区 = owned_item.price
    （标记购买时填了实价就是实价，没填继承购物车参考价）。
    金额统一 round 2 位，避免浮点累加出现 1699.9999999999。
    """

    unpurchased_count: int
    purchased_count: int
    unpriced_count: int
    unpurchased_total: float
    purchased_total: float
    total: float


class ItemGroupListItemSchema(BaseModel):
    """分组列表项 = 分组本体 + 成员计数 + 价格统计（列表页直接看钱，不用逐个点开）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    note: str | None
    create_time: datetime
    update_time: datetime
    unpurchased_count: int
    purchased_count: int
    unpriced_count: int
    unpurchased_total: float
    purchased_total: float
    total: float


class ItemGroupDetailOutSchema(BaseModel):
    group: ItemGroupOutSchema
    unpurchased: list[GroupItemOutSchema]
    purchased: list[GroupItemOutSchema]
    stats: GroupStatsOutSchema
