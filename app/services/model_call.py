import asyncio
import ipaddress
import json
import logging
import socket
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx

from app.core.errors import BizError, ErrorCode
from app.core.http_client import get_http_client
from app.services.api_key_service import KeyRecord


logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(35.0, connect=8.0)





class ModelCallError(Exception):
    """模型调用错误,不携带响应体内容"""

def _log_truncation(data: dict)->None:
    usage = data.get("usage") or {}
    detail = usage.get("completion_tokens_details") or {}
    logger.warning(
        "model output truncated: completion=%s reasoning=%s",
        usage.get("completion_tokens"),
        detail.get("reasoning_tokens"),
    )

def validate_public_url(base_url: str)->None:
    """验证公共URL是否有效"""
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("公共URL必须是HTTPS协议且包含主机名")
    try :
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"公共URL {base_url} 无效") from exc
    if not infos:
        raise ValueError(f"公共URL {base_url} 无效")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])#得到IP地址对象
        if not ip.is_global:
            raise ValueError(f"目标地址不是公网地址")
async  def call_model(
        key: KeyRecord,
        messages: list[dict],
        *,
        max_token: int | None = 6000) -> tuple[str, str]:
    if not messages:
        raise ModelCallError("messages 不能为空")
    try:
        await asyncio.to_thread(validate_public_url, key.base_url)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "配置的 base_url 不是可用的公网 https 地址") from exc
    url = key.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": key.model_name,
        "messages": messages,
        "max_tokens": max_token,
    }
    headers = {
        "Authorization": f"Bearer {key.api_key}",
        "Content-Type": "application/json",
    }
    client = get_http_client()
    if client is None:
        async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=False,
            ) as one_off:
            resp = await one_off.post(url, headers=headers, json=payload)
    else:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code in(401, 403):
        # 本函数无 session，不能自己调 mark_invalid。**调用方必须在自己持有的
        # session 里标记 key 失效**，否则一个已死的 key 会被反复使用。
        raise ModelCallError(f"key 已被厂商拒绝，已标记为失效，请重新配置")
    if resp.status_code == 402:
        logger.warning("model call rejected: http 402 provider=%s body=%s",
                       key.provider, resp.text[:200])
        raise ModelCallError("模型服务已欠费，请前往对应平台充值后重试")
    if resp.status_code != 200:
        logger.warning("model call http %s ", resp.status_code)
        raise ModelCallError(f"模型调用失败")
    try:
        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"] or ""
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("model call unexpected response shape")
        raise ModelCallError("模型返回了无法解析的内容") from exc
    if not isinstance(content, str):
        raise ModelCallError("模型返回了无法解析的内容")
    if finish_reason == "length":
        _log_truncation(data)
    return content, data.get("model") or key.model_name


async def stream_model(
        key: KeyRecord,
        messages: list[dict],
        *,
        max_token: int | None = 6000) -> AsyncIterator[str]:
    """流式调用，产出 AsyncIterator[str]。**只负责生成**。

    契约只有一条「逐块 yield 文本增量」：不碰数据库、不做业务判断、不写日志、
    不翻译错误文案。将来接 LangGraph 编排时，只要满足这条契约
    （graph.astream 的输出可转换），SSE 层不用动。

    🔴 **必须独立设 timeout，不能沿用 _TIMEOUT=35.0**：那是「整个请求 35 秒内完成」
    的总超时。流式下 6000 token 需 100–200 秒，沿用会把**每个长回答在 35 秒硬掐**，
    且截断发生得很自然→ 表现为「回答说到一半停了」，**不报错**，是最难查的一类问题。
    connect 保留 8 秒（连不上要快速失败），read 不设上限（等多久都行）。

    🔴 **401/403 不在这里标记 key 失效**：本函数没有 session，调不了 mark_invalid。
    只抛 ModelCallError，**由调用方（chat_stream）在自己持有的 session 里标记**——
    这是「移除 AsyncSession 参数」带来的责任转移点，别漏。

    usage / finish_reason 从流里捞出来打 truncated 日志：非流式下 _log_truncation
    直接读响应体，流式下 usage 只在最后一个 chunk 出现，漏了这条告警就**静默消失**
    （不报错，只少一行日志）。
    """
    if not messages:
        raise ModelCallError("messages 不能为空")
    try:
        await asyncio.to_thread(validate_public_url, key.base_url)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "配置的 base_url 不是可用的公网 https 地址") from exc
    url = key.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": key.model_name,
        "messages": messages,
        "max_tokens": max_token,
        "stream": True,
        # 让厂商在最后一个 chunk 回 usage，否则拿不到 token 统计与截断信号
        "stream_options": {"include_usage": True},
    }
    headers = {
        "Authorization": f"Bearer {key.api_key}",
        "Content-Type": "application/json",
    }
    stream_timeout = httpx.Timeout(None, connect=8.0)
    client = get_http_client()
    one_off = None
    try:
        if client is None:
            one_off = httpx.AsyncClient(timeout=stream_timeout, follow_redirects=False)
            http = one_off
        else:
            http = client
        async with http.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code in (401, 403):
                await resp.aread()
                raise ModelCallError("key 已被厂商拒绝，已标记为失效，请重新配置")
            if resp.status_code == 402:
                body = (await resp.aread()).decode("utf-8", "replace")
                logger.warning("model stream rejected: http 402 provider=%s body=%s",
                               key.provider, body[:200])
                raise ModelCallError("模型服务已欠费，请前往对应平台充值后重试")
            if resp.status_code != 200:
                logger.warning("model stream http %s", resp.status_code)
                raise ModelCallError("模型调用失败")
            async for raw in resp.aiter_lines():
                line = raw.strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    chunk = json.loads(body)
                except json.JSONDecodeError:
                    # 单个 chunk 坏了不该毁掉整条流：跳过继续读
                    logger.warning("model stream: bad chunk skipped")
                    continue
                usage = chunk.get("usage")
                if usage:
                    _log_truncation({"usage": usage})
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece
    finally:
        if one_off is not None:
            await one_off.aclose()
