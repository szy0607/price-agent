import datetime
import hashlib
import secrets
from typing import Annotated

from fastapi import Cookie, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.core.time import utc_now_naive
from app.dependence import get_db_session
from app.models import User, UserSession


SESSION_DAYS = 7
SESSION_SECONDS = SESSION_DAYS * 24 * 60 * 60
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "session", token, max_age=SESSION_SECONDS, path="/",
        httponly=True, secure=settings.cookie_secure, samesite="lax",
    )


def new_session(user_id: int, request: Request) -> tuple[UserSession, str]:
    token = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user_id,
        token_hash=session_token_hash(token),
        expire_time=utc_now_naive() + datetime.timedelta(days=SESSION_DAYS),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:255],
    )
    return row, token


def issue_session_cookie(response: Response, token: str) -> None:
    _set_session_cookie(response, token)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie("session", path="/", samesite="lax", secure=settings.cookie_secure, httponly=True)


def require_same_origin_write(request: Request) -> None:
    if request.headers.get("X-Requested-With") != "price-agent":
        raise BizError(ErrorCode.PARAM_INVALID, "请求无效")


async def get_current_user(
    response: Response,
    session: SessionDep,
    session_token: str | None = Cookie(default=None, alias="session"),
) -> User:
    if not session_token or len(session_token) > 256:
        raise BizError(ErrorCode.SESSION_INVALID, "未登录")
    now = utc_now_naive()
    row = await session.scalar(
        select(UserSession).where(
            UserSession.token_hash == session_token_hash(session_token),
            UserSession.revoke_time.is_(None),
            UserSession.expire_time > now,
        )
    )
    if row is None:
        raise BizError(ErrorCode.SESSION_INVALID, "会话失效，请重新登录")
    user = await session.get(User, row.user_id)
    if user is None:
        raise BizError(ErrorCode.SESSION_INVALID, "账号不可用")
    if row.expire_time - now < datetime.timedelta(days=3):
        row.expire_time = now + datetime.timedelta(days=SESSION_DAYS)
        await session.commit()
        _set_session_cookie(response, session_token)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
