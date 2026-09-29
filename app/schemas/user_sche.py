from datetime import datetime, timezone
from typing import Optional,Annotated
from pydantic import BaseModel, Field, ConfigDict, field_serializer


class UserRegister(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    username : Annotated[str,Field(...,description="用户名")]
    password : Annotated[str,Field(...,description="密码")]
class UserLogin(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    password : Annotated[str,Field(...,description="密码")]
    captcha_token : Annotated[str,Field(...,description="图形验证码签名串（后端下发，内含 salt/ts/签名，不含答案）")]
    captcha_code : Annotated[str,Field(...,description="用户填写的验证码答案")]
    # ⚠️ captcha_code 用 str 不用 int：Pydantic 会吃掉前导零（"06" → 6），
    #    将来若改用字符码会踩坑；且类型不对时能自然落到 400/40001。
    #    参考 docs/用户注册与登录-接口契约.md §2.2。
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_email: str
    username: str
    create_time: datetime
    @field_serializer("create_time")
    def _iso_z(self, v: datetime) -> str:
        return v.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

