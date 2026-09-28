from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_serializer
import datetime

class UserRegister(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    username : Annotated[str,Field(...,description="用户名")]
    password : Annotated[str,Field(...,description="密码")]
class UserLogin(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    password : Annotated[str,Field(...,description="密码")]


class UserResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_email: str
    username: str
    create_time: datetime.datetime

    @field_serializer("create_time")
    def serialize_create_time(self, value: datetime.datetime) -> str:
        return value.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
