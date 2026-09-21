from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User


async def get_pw_hash(user_email:str,session:AsyncSession)->str:
    user = await session.scalar(select(User).where(User.user_email == user_email))
    if user:
            return user.password_hash
    else:
            raise ValueError("用户不存在")
async def user_create(user:User,session:AsyncSession):
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
async def user_exists(user_email:str,session:AsyncSession)->bool:
    user = await session.scalar(select(User).where(User.user_email == user_email))
    return user is not None
