
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CartItemOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    category : str
    name : str
    price : float | None
    specs : dict[str,str]
    image : str | None
    note : str | None
    create_time : datetime
    update_time : datetime
class CartItemInSchema(BaseModel):
    category : str | None =  Field(max_length=64,description="商品分类")
    name : str =  Field(max_length=256,description="商品名称")
    price : float | None
    specs : dict[str,str]
    image : str | None
    note : str | None
class CartItemUpdateSchema(BaseModel):
    category : str | None = Field(max_length=64,description="商品分类")
    name : str | None = Field(max_length=256,description="商品名称")
    price : float | None
    specs : dict[str,str] | None
    image : str | None
    note : str | None
class AiDraftInSchema(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    category: str | None = Field(default=None, max_length=64)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("商品名不能为空白")
        return v
