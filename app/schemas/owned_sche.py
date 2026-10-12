from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cart_sche import validate_image_path


def normalize_purchased_at(value: datetime | None) -> datetime | None:
    """入库口径：naive UTC（与 purchase_record.py 的 _validate_purchased_at 同一规则）"""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class OwnedItemOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category: str
    name: str
    price: float | None
    specs: dict[str, str]
    image: str | None
    note: str | None
    platform: str | None
    purchased_at: datetime | None
    create_time: datetime
    update_time: datetime


class OwnedItemInSchema(BaseModel):
    """双入口直建物品库的入参（拍板 #10）。user_id 永远来自 CurrentUser，不进 body。"""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    category: str = Field(default="其他", max_length=64)
    price: float | None = Field(default=None, ge=0)
    specs: dict[str, str] = Field(default_factory=dict)
    image: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=512)
    platform: str | None = Field(default=None, max_length=64)
    purchased_at: datetime | None = None

    @field_validator("image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return validate_image_path(v)

    @model_validator(mode="after")
    def norm_purchased_at(self):
        self.purchased_at = normalize_purchased_at(self.purchased_at)
        return self


class OwnedItemUpdateSchema(BaseModel):
    """PATCH 部分更新：全可选，repo 里 exclude_unset 只取提交了的字段。"""
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    price: float | None = Field(default=None, ge=0)
    specs: dict[str, str] | None = None
    image: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=512)
    platform: str | None = Field(default=None, max_length=64)
    purchased_at: datetime | None = None

    @field_validator("image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return validate_image_path(v)

    @model_validator(mode="after")
    def norm_purchased_at(self):
        self.purchased_at = normalize_purchased_at(self.purchased_at)
        return self
