from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import check_password, check_password_strength
from app.dependence import get_db_session
from app.repository.auth_repo import get_pw_hash,user_exists
from app.schemas.user_sche import UserLogin, UserRegister

auth_router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)
#登录
@auth_router.post("/login")
async def login(pay_load:UserLogin,session:AsyncSession = Depends(get_db_session)):
    user_email = pay_load.user_email
    pw_hash = await get_pw_hash(user_email,session)
    if not check_password(pay_load.password,pw_hash):
        raise ValueError("密码错误")
    return {"message":"登录成功"}
#注册
@auth_router.post("/register")
async def register(pay_load:UserRegister,session:AsyncSession = Depends(get_db_session)):
    user_email = pay_load.user_email
    raw_password = pay_load.password
    if not check_password_strength(raw_password):
        raise ValueError("密码强度不足，必须包含字母和数字，长度在6到20之间")
    if await user_exists(user_email,session):
        raise ValueError("邮箱已存在")
    return {"message":"注册成功"}
