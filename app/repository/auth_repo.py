from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.core.errors import BizError, ErrorCode
from app.models.user import User


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
