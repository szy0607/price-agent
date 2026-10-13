from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationTitleInSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def fold_whitespace(cls, v):
        """折叠所有空白成一个空格。

        mode="before" 是必须的：字段长度校验走的是折叠后的值，否则「键盘\\n\\n\\n…」
        这类靠空白撑爆长度的输入会先被 max_length 拒掉。折叠放在标准校验之前，
        判定才落在人真正看到的那段文字上。
        """
        if not isinstance(v, str):
            return v
        return " ".join(v.split())


class ConversationOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    update_time: datetime
