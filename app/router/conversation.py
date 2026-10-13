from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import success
from app.dependence import CurrentUser, get_db_session, require_same_origin_write
from app.repository import conversation_repo
from app.schemas.conversation_sche import ConversationOutSchema, ConversationTitleInSchema

conversation_router = APIRouter(tags=["conversation"], prefix="/conversations")


@conversation_router.patch("/{conversation_id}/title", dependencies=[Depends(require_same_origin_write)])
async def update_title(conversation_id: int, data: ConversationTitleInSchema,
                       user: CurrentUser, session: AsyncSession = Depends(get_db_session)):
    row = await conversation_repo.update_title(conversation_id, data.title, user.id, session)
    return success(ConversationOutSchema.model_validate(row))
