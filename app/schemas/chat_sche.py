"""对话相关的请求/响应 schema。

本文件由两边并行开发合并而来（2026-10-14 本地 main 与 gitee/main 分叉后 rebase，
解决 add/add 冲突时按并集保留，类名无碰撞）：
- ChatTurnSchema / ChatInSchema：智能咨询 /chat/message，
  收 messages 多轮历史 + record_ids 本次勾选的消费记录；
- ItemRefInSchema / ChatSendInSchema / ChatSendOutSchema / MessageOutSchema：
  新版对话发送，收 conversation_id + item_refs（购物车/物品库引用）。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------- 智能咨询 /chat/message（messages + 勾选的消费记录） ----------

class ChatTurnSchema(BaseModel):
    """一条对话消息。

    role 只允许 user/assistant：system 提示由服务端现拼，不接受请求方注入，
    否则任何人都能借这个字段改写模型的行事规则。
    """
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _check_role(self):
        if self.role not in ("user", "assistant") or not self.content.strip():
            raise ValueError("Invalid chat message")
        return self


class ChatInSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatTurnSchema] = Field(min_length=1, max_length=12)
    # 本次勾选的消费记录 id，只当索引用：名称与价格一律由服务端按登录用户反查展开，
    # 前端在这个字段里传商品名、传价格都不算数。
    record_ids: list[int] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _check_history(self):
        if self.messages[-1].role != "user":
            raise ValueError("Last message must be from the user")
        if sum(len(item.content) for item in self.messages) > 12000:
            raise ValueError("Invalid chat history")
        # 去重保序 + 丢掉非正整数（自增主键没有 0 和负数）
        self.record_ids = list(dict.fromkeys(item for item in self.record_ids if item > 0))[:10]
        return self


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
