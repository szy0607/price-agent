from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.api_key_crypto import KeyConfigurationError, KeyRing
from app.core.config import settings
from app.core.errors import BizError, ErrorCode, success
from app.dependence import CurrentUser, require_same_origin_write
from app.services.api_key_service import KeyRecordError
from app.services.chat_service import MODEL_PROVIDERS, ModelCallError, answer_with_user_key
from app.services.user_profile import build_purchase_profile, build_record_focus, compose_context


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
    # 本次勾选的消费记录 id。只当索引用：内容一律由服务端按 user_id 反查展开，
    # 前端在这个字段里传商品名、传价格都不算数。
    record_ids: list[int] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def check_messages(self):
        if self.messages[-1].role != "user" or sum(len(item.content) for item in self.messages) > 12000:
            raise ValueError("Invalid chat history")
        # 去重保序 + 丢掉非正整数；自增主键没有 0 和负数
        self.record_ids = list(dict.fromkeys(item for item in self.record_ids if item > 0))[:10]
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
    # 勾选的记录先展开：选了不存在的（或别人的）id 直接 40001，
    # 别让它静默少带一件商品、模型在残缺上下文上照常作答。
    focus = await build_record_focus(user.id, payload.record_ids)
    profile = await build_purchase_profile(user.id)
    extra_context = compose_context(profile, focus)
    try:
        answer = await answer_with_user_key(
            user.id, provider, [item.model_dump() for item in payload.messages], ring, extra_context
        )
    except KeyRecordError:
        raise BizError(ErrorCode.PARAM_INVALID, "所选服务商没有可用的 API Key") from None
    except ModelCallError as exc:
        raise BizError(ErrorCode.INTERNAL, str(exc)) from None
    return success({"content": answer.content, "provider": provider, "model": answer.model})
