import logging

import httpx

from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.core.http_client import get_http_client
logger = logging.getLogger(__name__)
_BOCHA_URL = "https://api.bocha.cn/v1/web-search"

async def web_search(query:str,count:int=5)->list[dict]:

    if not settings.bocha_api_key:
        raise BizError(ErrorCode.PARAM_INVALID, "BOCHA_API_KEY 未配置")

    headers = {
        "Authorization": f"Bearer {settings.bocha_api_key}",
    }
    payload = {
        "query": query,
        "summary": True,
        "count": count,
    }
    try:
        client = get_http_client()
        if client is None:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0),
                                         follow_redirects=False) as one_off:
                resp = await one_off.post(_BOCHA_URL, json=payload, headers=headers)
        else:
            resp = await client.post(_BOCHA_URL, json=payload, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("bocha api request error: %s", type(exc).__name__)
        raise BizError(ErrorCode.INTERNAL, "联网搜索失败") from exc
    if resp.status_code != 200:
        raise BizError(ErrorCode.INTERNAL, "联网搜索失败")
    try:
        value = resp.json()["data"]["webPages"]["value"]
    except(KeyError,TypeError,ValueError) as exc:
        logger.warning("bocha search unexpected shape")
        raise BizError(ErrorCode.INTERNAL, "联网搜索失败") from exc
    return [{
        "name": it.get("name", ),
        "url": it.get("url", ),
        "snippet": it.get("snippet", ),
        "datePublished": it.get("datePublished", ),
        "summary":it.get("summary")
    } for it in value if isinstance(it, dict)]
