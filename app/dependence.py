from typing import Annotated, AsyncGenerator
from fastapi import Response, Cookie, Depends, Request
from sqlalchemy import select
from app.core.time import get_current_time
from app.core.cookie import SESSION_TOKEN_NAME, set_session_token, RENEW_THRESHOLD, SESSION_TTL
from app.core.errors import BizError, ErrorCode
from app.core.security import hash_session_token
from app.database.session import async_session_local
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserSession


async def get_db_session()->AsyncGenerator[AsyncSession,None]:
    async with async_session_local() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_session(
response:Response,
session : AsyncSession = Depends(get_db_session),
session_token:str | None = Cookie(default=None,alias=SESSION_TOKEN_NAME)
)->User:
    if session_token is None:
        raise BizError(ErrorCode.SESSION_INVALID,"未登录")
    now = get_current_time()
    row = await session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(session_token),
                                  UserSession.revoke_time.is_(None),
                                  UserSession.expire_time > now)
    )
    if row is None:
        raise BizError(ErrorCode.SESSION_INVALID,"会话过期")
    user = await session.get(User, row.user_id)
    if user is None:
        raise BizError(ErrorCode.SESSION_INVALID,"用户不存在")
    if row.expire_time-now < RENEW_THRESHOLD:
        row.expire_time = now + SESSION_TTL
        await session.commit()
        set_session_token(response,session_token)

    return user


CurrentUser = Annotated[User, Depends(get_current_session)]


def require_same_origin_write(request: Request) -> None:
    if request.headers.get("X-Requested-With") != "price-agent":
        raise BizError(ErrorCode.PARAM_INVALID, "请求无效")
