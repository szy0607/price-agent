import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError,ErrorCode
from app.core.http_client import get_http_client
from app.services import api_key_service


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
        user_id: int,
        prompt: str,
        session:AsyncSession, *,
        max_token: int | None = 6000)->tuple[str, str]:
    record = await api_key_service.key_for_call(user_id, session)
    try:
        await asyncio.to_thread(validate_public_url, record.base_url)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "配置的 base_url 不是可用的公网 https 地址") from exc
    url = record.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": record.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_token,
    }
    headers = {
        "Authorization": f"Bearer {record.api_key}",
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
        await api_key_service.mark_invalid(record.key_id,user_id, session)
        raise ModelCallError(f"key 已被厂商拒绝，已标记为失效，请重新配置")
    if resp.status_code == 402:
        logger.warning("model call rejected: http 402 provider=%s body=%s",
                       record.provider, resp.text[:200])
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
    return content, data.get("model") or record.model_name
