from datetime import timedelta

from fastapi import Response

from app.core.config import settings
SESSION_TTL = timedelta(days=7)
SESSION_TTL_SECONDS = int(SESSION_TTL.total_seconds())  # 7 天
SESSION_TOKEN_NAME = "session_token"
RENEW_THRESHOLD = timedelta(days=3)
def set_session_token(response:Response,token:str):
    response.set_cookie(
        key=SESSION_TOKEN_NAME,
        value=token,
        secure=settings.cookie_secure,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        samesite="lax",
    )
def clear_session_token(response:Response)->None:
    response.delete_cookie(SESSION_TOKEN_NAME,path="/")
