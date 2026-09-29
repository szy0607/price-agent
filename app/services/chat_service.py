"""Model calls using a key belonging to the authenticated user."""

import logging

import httpx

from app.core.api_key_crypto import KeyRing
from app.database.session import async_session_local
from app.services.api_key_service import ApiKeyService


logger = logging.getLogger(__name__)

MODEL_PROVIDERS = {
    "openai": {"label": "OpenAI", "model": "gpt-4o-mini", "url": "https://api.openai.com/v1/chat/completions"},
    "anthropic": {"label": "Anthropic", "model": "claude-haiku-4-5", "url": "https://api.anthropic.com/v1/messages"},
    "deepseek": {"label": "DeepSeek", "model": "deepseek-chat", "url": "https://api.deepseek.com/chat/completions"},
    "qwen": {"label": "通义千问", "model": "qwen-plus", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"},
}

SYSTEM_PROMPT = (
    "你是智能导购助手。用简洁中文回答用户的购物问题，说明关键取舍。"
    "你没有实时商品、库存、价格或优惠券数据；不得声称已经查询、验证或采集这些信息，"
    "不得编造具体到手价、券、口令或购买链接。涉及价格时提醒用户以商品页面为准。"
)


class ModelCallError(Exception):
    """A third-party model call failed without exposing credentials or response bodies."""


async def answer_with_user_key(user_id: int, provider: str, messages: list[dict[str, str]], ring: KeyRing) -> str:
    config = MODEL_PROVIDERS[provider]
    service = ApiKeyService(async_session_local, ring)
    async with service.key_for_call(user_id, provider, actor="service:chat") as borrowed:
        # httpx needs a string header. Keep it inside the borrowed-key scope only.
        token = borrowed.value.decode("utf-8")
        try:
            if provider == "anthropic":
                headers = {"x-api-key": token, "anthropic-version": "2023-06-01"}
                body = {"model": config["model"], "max_tokens": 1024, "system": SYSTEM_PROMPT, "messages": messages}
            else:
                headers = {"Authorization": f"Bearer {token}"}
                body = {"model": config["model"], "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages], "max_tokens": 1024, "stream": False}
            async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=8.0), follow_redirects=False) as client:
                response = await client.post(
                    config["url"],
                    headers=headers,
                    json=body,
                )
            if response.status_code in (401, 403):
                await service.mark_invalid(user_id, provider, borrowed.revision, actor="service:chat")
                raise ModelCallError("服务商拒绝了 API Key，请到设置中替换")
            if response.status_code >= 400:
                logger.warning("model_call_failed provider=%s status=%s", provider, response.status_code)
                raise ModelCallError("模型服务暂时无法完成请求")
            payload = response.json()
            if provider == "anthropic":
                content = "\n".join(block["text"] for block in payload["content"] if block["type"] == "text")
            else:
                content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty model response")
            return content.strip()
        except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
            logger.warning("model_call_failed provider=%s reason=transport_or_format", provider)
            raise ModelCallError("模型服务暂时无法完成请求") from None
        finally:
            headers.clear()
            token = ""
