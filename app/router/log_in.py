from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repository.auth_repo import user_create
from app.core.errors import success, BizError, ErrorCode
from app.core.security import check_password, check_password_strength, hash_password
from app.core.session_auth import CurrentUser, clear_session_cookie, issue_session_cookie, new_session, require_same_origin_write, session_token_hash
from app.core.time import utc_now_naive
from app.dependence import get_db_session
from app.repository.auth_repo import user_exists
from app.schemas.user_sche import UserLogin, UserRegister, UserResp
from app.models import UserSession

auth_router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)
#登录
@auth_router.post("/login")
async def login(pay_load:UserLogin, request: Request, response: Response, session:AsyncSession = Depends(get_db_session)):
    user_email = pay_load.user_email.lower().strip()
    user = await session.scalar(select(User).where(User.user_email == user_email))
    if user is None or not check_password(pay_load.password, user.password_hash):
        raise BizError(ErrorCode.CREDENTIALS,"邮箱或密码错误")
    user.last_login_time = utc_now_naive()
    user_session, token = new_session(user.id, request)
    session.add(user_session)
    await session.commit()
    issue_session_cookie(response, token)
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


@auth_router.get("/me")
async def me(user: CurrentUser):
    return success(UserResp.model_validate(user).model_dump(mode="json"))


@auth_router.post("/logout", dependencies=[Depends(require_same_origin_write)])
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    session_token: str | None = Cookie(default=None, alias="session"),
):
    if session_token and len(session_token) <= 256:
        row = await session.scalar(select(UserSession).where(UserSession.token_hash == session_token_hash(session_token)))
        if row is not None and row.revoke_time is None:
            row.revoke_time = utc_now_naive()
            await session.commit()
    clear_session_cookie(response)
    return success()
