from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.core.errors import BizError, ErrorCode
from app.core.time import get_current_time
from app.models import UserSession
from app.models.user import User
from app.core.cookie import SESSION_TTL
async def get_pw_hash(user_email:str,session:AsyncSession)->str:
    user = await session.scalar(select(User).where(User.user_email == user_email))
    if user:
            return user.password_hash
    else:
            raise BizError(ErrorCode.CREDENTIALS,"邮箱或密码错误")
async def user_create(user:User,session:AsyncSession):
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
async def user_exists(user_email:str,session:AsyncSession)->bool:
    user = await session.scalar(select(User).where(User.user_email == user_email))
    return user is not None
async def user_last_login_time(user_email:str,session:AsyncSession):

    await session.execute(update(User).where(User.user_email == user_email).values(last_login_time=func.utc_timestamp()))
    await session.commit()
#存储用户会话token
async def user_session_token(user_id:int,token_hash:str,session:AsyncSession)->UserSession:

    row = UserSession(user_id=user_id,token_hash=token_hash,expire_time=get_current_time()+SESSION_TTL)
    session.add(row)
    await session.commit()
    return row
#
async def session_revoke_by_hash(token_hash:str,session:AsyncSession)->None:
    await session.execute(
        update(UserSession).where(UserSession.token_hash == token_hash,UserSession.revoke_time.is_(None)).values(revoke_time=get_current_time())
        )
    await (session.
           commit())

