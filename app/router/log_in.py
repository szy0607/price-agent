from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repository.auth_repo import user_create, user_last_login_time
from app.core.errors import success, BizError, ErrorCode
from app.core.security import check_password, check_password_strength, hash_password
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
    user_email = pay_load.user_email.lower().strip()
    pw_hash = await get_pw_hash(user_email,session)
    if not check_password(pay_load.password,pw_hash):
        raise BizError(ErrorCode.CREDENTIALS,"邮箱或密码错误")
    await user_last_login_time(user_email,session)
    return success("登录成功")

#注册
@auth_router.post("/register")
async def register(pay_load:UserRegister,session:AsyncSession = Depends(get_db_session)):
    user_email = pay_load.user_email.lower().strip()
    raw_password = pay_load.password


    if   check_password_strength(raw_password):
        if await user_exists(user_email,session):
            raise BizError(ErrorCode.EMAIL_TAKEN,"邮箱已存在")
    user = User(user_email=user_email,username=pay_load.username,password_hash=hash_password(raw_password))
    await user_create(user,session)
    return success("注册成功")
