from typing import AsyncGenerator

from app.database.session import async_session_local
from sqlalchemy.ext.asyncio import AsyncSession
async def get_db_session()->AsyncGenerator[AsyncSession,None]:
    async with async_session_local() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
