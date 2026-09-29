from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.api_key_crypto import KeyConfigurationError, KeyRing
from app.core.config import settings
from app.core.errors import BizError, ErrorCode, success
from app.core.session_auth import CurrentUser, require_same_origin_write
from app.services.api_key_service import KeyRecordError
from app.services.chat_service import MODEL_PROVIDERS, ModelCallError, answer_with_user_key


chat_router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    content: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def check_role(self):
        if self.role not in ("user", "assistant") or not self.content.strip():
            raise ValueError("Invalid chat message")
        return self


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def check_messages(self):
        if self.messages[-1].role != "user" or sum(len(item.content) for item in self.messages) > 12000:
            raise ValueError("Invalid chat history")
        return self


@chat_router.post("/message", dependencies=[Depends(require_same_origin_write)])
async def message(payload: ChatInput, user: CurrentUser):
    provider = user.model_provider
    if provider not in MODEL_PROVIDERS:
        raise BizError(ErrorCode.PARAM_INVALID, "请先在设置中选择已保存的模型服务商")
    try:
        ring = KeyRing.from_settings(settings)
    except KeyConfigurationError:
        raise BizError(ErrorCode.INTERNAL, "密钥服务暂不可用") from None
    try:
        answer = await answer_with_user_key(
            user.id, provider, [item.model_dump() for item in payload.messages], ring
        )
    except KeyRecordError:
        raise BizError(ErrorCode.PARAM_INVALID, "所选服务商没有可用的 API Key") from None
    except ModelCallError as exc:
        raise BizError(ErrorCode.INTERNAL, str(exc)) from None
    return success({"content": answer, "provider": provider, "model": MODEL_PROVIDERS[provider]["model"]})
