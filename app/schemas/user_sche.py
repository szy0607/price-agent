from typing import Optional,Annotated
from pydantic import BaseModel,Field

class UserRegister(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    username : Annotated[str,Field(...,description="用户名")]
    password : Annotated[str,Field(...,description="密码")]
class UserLogin(BaseModel):
    user_email : Annotated[str,Field(...,description="邮箱")]
    password : Annotated[str,Field(...,description="密码")]
