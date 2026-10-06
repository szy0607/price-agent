# schemas/cart_sche.py 或 owned_sche.py
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PurchaseInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price: float | None = Field(default=None, ge=0)          # 弹窗补的备注价
    platform: str | None = Field(default=None, max_length=64)
    purchased_at: datetime | None = None
    note: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def norm_purchased_at(self):                              # 归一照抄 purchase_record.py 的 _validate_purchased_at
        if self.purchased_at is not None and self.purchased_at.tzinfo is not None:
            self.purchased_at = self.purchased_at.astimezone(timezone.utc).replace(tzinfo=None)
        return self
