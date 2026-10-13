from pydantic import BaseModel, ConfigDict, Field, model_validator


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
