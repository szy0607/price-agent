"""Model calls using a key belonging to the authenticated user."""

import logging
import re
from dataclasses import dataclass

import httpx

from app.core.api_key_crypto import KeyRing
from app.database.session import async_session_local
from app.services.api_key_service import ApiKeyService


logger = logging.getLogger(__name__)

# `model` 只在用户没有自行选择时作为回落默认值。
# `url` / `models_url` 刻意逐家写死：四家的路径形状并不一致（DeepSeek 的对话地址没有 /v1），
# 无法从 url 推导 models_url，也不接受用户填写自己的地址。
MODEL_PROVIDERS = {
    "openai": {"label": "OpenAI", "model": "gpt-4o-mini", "url": "https://api.openai.com/v1/chat/completions", "models_url": "https://api.openai.com/v1/models"},
    "anthropic": {"label": "Anthropic", "model": "claude-haiku-4-5", "url": "https://api.anthropic.com/v1/messages", "models_url": "https://api.anthropic.com/v1/models"},
    "deepseek": {"label": "DeepSeek", "model": "deepseek-chat", "url": "https://api.deepseek.com/chat/completions", "models_url": "https://api.deepseek.com/models"},
    "qwen": {"label": "通义千问", "model": "qwen-plus", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "models_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models"},
}

SYSTEM_PROMPT = (
    "你是智能导购助手。用简洁中文回答用户的购物问题，说明关键取舍。"
    "你没有实时商品、库存、价格或优惠券数据；不得声称已经查询、验证或采集这些信息，"
    "不得编造具体到手价、券、口令或购买链接。涉及价格时提醒用户以商品页面为准。"
)


class ModelCallError(Exception):
    """A third-party model call failed without exposing credentials or response bodies."""


class ModelCatalogError(Exception):
    """A model listing failed without exposing credentials or response bodies."""


@dataclass(frozen=True)
class ModelAnswer:
    content: str
    model: str


_MODEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)

# best-effort 过滤：只按命名剔掉明显不能对话的模型。不做 gpt-/claude-/qwen- 前缀白名单——
# 白名单会在厂商换命名的那天失效，而「列表里少了个能用的模型」比「用户选了个不能用的」更难自愈。
_NON_CHAT_RE = re.compile(
    r"(?:^|-)(?:embed(?:ding)?|audio|tts|whisper|transcribe|livetranslate|dall.?e|image|t2i|i2i|t2v|v2v|moderation|realtime|rerank|ocr|search)(?:-|$)",
    re.ASCII | re.IGNORECASE,
)
_MAX_MODELS = 200


def validate_model_name(value: str | None) -> str | None:
    """Return a storable model name, or None meaning "use the provider default"."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid model name")
    stripped = value.strip()
    if not stripped:
        return None
    if not _MODEL_NAME_RE.fullmatch(stripped):
        raise ValueError("Invalid model name")
    return stripped


def resolve_model_name(provider: str, saved: str | None) -> str:
    """Model actually used for a call.

    读时再校验一次：列里可能是校验规则之前写入的、或有人在 SQL 里手改过的值，
    脏值不该被拼进发往第三方的请求体。
    """
    try:
        validated = validate_model_name(saved)
    except ValueError:
        validated = None
    return validated or MODEL_PROVIDERS[provider]["model"]


def _headers_for(provider: str, token: str) -> dict[str, str]:
    """The two auth shapes. Shared so a listing can never drift from the call it mirrors."""
    if provider == "anthropic":
        return {"x-api-key": token, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {token}"}


def normalize_models(payload: object) -> list[dict[str, str]]:
    """Provider listing -> [{"id", "label"}]. All four providers answer {"data": [...]}."""
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Unexpected model listing")
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        # 只收录本服务存得下的 id，否则用户选中它却在保存时被拒。
        try:
            validate_model_name(model_id)
        except ValueError:
            continue
        if model_id in seen or _NON_CHAT_RE.search(model_id):
            continue
        seen.add(model_id)
        display = item.get("display_name")
        label = display.strip() if isinstance(display, str) and display.strip() else model_id
        options.append({"id": model_id, "label": label})
    options.sort(key=lambda option: option["id"])
    return options[:_MAX_MODELS]


async def list_user_models(user_id: int, provider: str, ring: KeyRing) -> list[dict[str, str]]:
    config = MODEL_PROVIDERS[provider]
    service = ApiKeyService(async_session_local, ring)
    async with service.key_for_call(user_id, provider, actor="service:models", purpose="model_list") as borrowed:
        # httpx needs a string header. Keep it inside the borrowed-key scope only.
        token = borrowed.value.decode("utf-8")
        headers = _headers_for(provider, token)
        try:
            # Anthropic 只取一页：消费方是一个 <select>，翻页会把一次设置页交互
            # 变成串行 N 次带用户 Key 的外呼。列表外的模型由「已保存项始终可选」兜住。
            params = {"limit": "100"} if provider == "anthropic" else None
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0), follow_redirects=False) as client:
                response = await client.get(config["models_url"], headers=headers, params=params)
            if response.status_code in (401, 403):
                await service.mark_invalid(user_id, provider, borrowed.revision, actor="service:models")
                raise ModelCatalogError("服务商拒绝了 API Key，请到设置中替换")
            if response.status_code >= 300:
                logger.warning("model_list_failed provider=%s status=%s", provider, response.status_code)
                raise ModelCatalogError("服务商未能返回模型列表")
            options = normalize_models(response.json())
            if not options:
                raise ModelCatalogError("服务商未能返回模型列表")
            return options
        except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
            logger.warning("model_list_failed provider=%s reason=transport_or_format", provider)
            raise ModelCatalogError("服务商未能返回模型列表") from None
        finally:
            headers.clear()
            token = ""


_CONTEXT_LEAD = (
    "\n\n【用户消费记录】以下是该用户自行录入或确认过的历史消费信息，"
    "只用于理解他的使用场景和偏好；它们不是实时价格、库存或优惠，"
    "不要复述成当前报价，也不要据此声称查询过任何平台。\n"
)


def _system_prompt_with(extra_context: str) -> str:
    """SYSTEM_PROMPT 原文打头，消费记录追加在后 —— 红线那句一个字都不动。"""
    text = " ".join(extra_context.split()) if extra_context else ""
    if not text:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}{_CONTEXT_LEAD}{text[:4000]}"


async def answer_with_user_key(user_id: int, provider: str, messages: list[dict[str, str]], ring: KeyRing, extra_context: str = "") -> ModelAnswer:
    config = MODEL_PROVIDERS[provider]
    system_prompt = _system_prompt_with(extra_context)
    service = ApiKeyService(async_session_local, ring)
    async with service.key_for_call(user_id, provider, actor="service:chat") as borrowed:
        model = resolve_model_name(provider, borrowed.model_name)
        # httpx needs a string header. Keep it inside the borrowed-key scope only.
        token = borrowed.value.decode("utf-8")
        headers = _headers_for(provider, token)
        try:
            if provider == "anthropic":
                body = {"model": model, "max_tokens": 1024, "system": system_prompt, "messages": messages}
            else:
                body = {"model": model, "messages": [{"role": "system", "content": system_prompt}, *messages], "max_tokens": 1024, "stream": False}
            async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=8.0), follow_redirects=False) as client:
                response = await client.post(
                    config["url"],
                    headers=headers,
                    json=body,
                )
            if response.status_code in (401, 403):
                await service.mark_invalid(user_id, provider, borrowed.revision, actor="service:chat")
                raise ModelCallError("服务商拒绝了 API Key，请到设置中替换")
            # follow_redirects=False，所以 3xx 的响应体会被当成 JSON 解析——显式拒掉，
            # 别指望后面的 KeyError/ValueError 恰好兜住。
            if response.status_code >= 300:
                logger.warning("model_call_failed provider=%s status=%s", provider, response.status_code)
                raise ModelCallError("模型服务暂时无法完成请求")
            payload = response.json()
            if provider == "anthropic":
                content = "\n".join(block["text"] for block in payload["content"] if block["type"] == "text")
            else:
                content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty model response")
            return ModelAnswer(content.strip(), model)
        except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
            logger.warning("model_call_failed provider=%s reason=transport_or_format", provider)
            raise ModelCallError("模型服务暂时无法完成请求") from None
        finally:
            headers.clear()
            token = ""
