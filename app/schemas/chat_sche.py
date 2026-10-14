
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator



# ---------- 新版对话发送（conversation_id + item_refs） ----------

class ItemRefInSchema(BaseModel):
    """商品引用"""
    model_config = ConfigDict(extra="forbid")
    src:Literal["cart","owned"]
    id:int = Field(gt=0)

class ChatSendInSchema(BaseModel):
    """聊天发送"""
    model_config = ConfigDict(extra="forbid")
    conversation_id:int|None = Field(default=None,gt=0)
    text:str = Field(min_length=1,max_length=4000)
    item_refs:list[ItemRefInSchema] = Field(default_factory=list,max_length=5)

    @field_validator("text",mode="before")
    @classmethod
    def strip_ends(cls,value:str) -> str:
       if not isinstance(value,str):
            return value
       return value.strip()
    @field_validator("item_refs",mode="after")
    @classmethod
    def dedup(cls,v):
        seen:set[tuple[str,int]] = set()
        out = []
        for item in v:
            key = (item.src,item.id)
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out
class ChatSendOutSchema(BaseModel):
    # 新建会话时前端收下这个 id，后续消息都带它
    conversation_id: int
    reply: str
    model: str | None


class MessageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    model: str | None
    create_time: datetime
