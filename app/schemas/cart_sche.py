
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 上传图只接受自家 uploads 路由产出的路径：/uploads/<32位hex>.jpg
# 挡两类注入：../ 路径穿越、http(s):// 外域引用（后者会被前端 <img> 直接加载）
_IMAGE_PATH_RE = re.compile(r"^/uploads/[0-9a-f]{32}\.jpg$")


def validate_image_path(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not _IMAGE_PATH_RE.match(v):
        raise ValueError("图片路径格式不正确")
    return v


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

    @field_validator("image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return validate_image_path(v)
class CartItemUpdateSchema(BaseModel):
    category : str | None = Field(max_length=64,description="商品分类")
    name : str | None = Field(max_length=256,description="商品名称")
    price : float | None
    specs : dict[str,str] | None
    image : str | None
    note : str | None

    @field_validator("image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return validate_image_path(v)
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
