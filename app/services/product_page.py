"""从用户粘贴的商品链接里取回页面标题，作为建档草稿。

**精确域名白名单是这里唯一的 SSRF 防线**：不在名单里的 host 一律拒掉，
用户给的主机名永远不会进到 httpx —— 所以没有指向内网 / 回环 / 元数据地址的余地，
也不依赖「解析后再查 IP」那类补丁。白名单只做全等匹配，不是 endswith。

**只取标题，不取价格和参数。** 页面价格多为脚本渲染、抓不到是一回事，
更硬的理由是本产品的红线：不得声称有实时价格数据，
抓回来的价格既不入库也不进对话。原始 HTML 同理，永不落库。

抓到的东西一律是**待用户确认的草稿**（设计方案 §0 #4、决策 #22），本模块不写任何表。
"""

import html
import logging
import re
from urllib.parse import parse_qs, urlsplit

import httpx

from app.core.errors import BizError, ErrorCode

logger = logging.getLogger(__name__)

# 只收「商品详情页」这一种页面形态。搜索页、店铺页、短链、分享口令一律不在名单里，
# 用户贴了别的网址，拿到的是「暂不支持该链接」，由他手填 —— 不做二次跳转猜测。
PLATFORM_PAGES = {
    "item.jd.com": {"platform": "京东", "id_param": None},
    "item.m.jd.com": {"platform": "京东", "id_param": None},
    "item.taobao.com": {"platform": "淘宝", "id_param": "id"},
    "detail.tmall.com": {"platform": "天猫", "id_param": "id"},
    "mobile.yangkeduo.com": {"platform": "拼多多", "id_param": "goods_id"},
    "product.suning.com": {"platform": "苏宁易购", "id_param": None},
}

# item.jd.com/100012043912.html、product.suning.com/0070074/1234567890.html
_PATH_ID_RE = re.compile(r"/(\d{1,20})\.html?\Z", re.IGNORECASE)

_URL_MAX_LEN = 512          # 与 product_url 列宽一致，超长先拒，别让数据库报 1406
_TITLE_CAP = 200            # 与 name 列宽(256)留余量
_GOODS_ID_CAP = 32
_MAX_BODY_BYTES = 300_000

_FETCH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# 固定单一 UA：不带任何身份、不带 Cookie、不带 Authorization。
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_UNSUPPORTED_MSG = "暂不支持该商品链接，请手动填写商品信息"
_INVALID_MSG = "商品链接格式无效"
_FAILED_MSG = "没能读到该商品页面，请直接手动填写"


class PageFetchError(Exception):
    """页面抓取失败。对外一律 `_FAILED_MSG`，不透出响应体、不区分原因。"""


def parse_product_url(raw: object) -> tuple[str, str | None]:
    """校验链接，返回 `(平台中文名, 商品 ID)`。

    不合法一律 `BizError(40001)`。这里**不做任何网络请求**，纯字符串判断，
    所以能被单测完全覆盖，也是白名单真正生效的那一道。
    """
    if not isinstance(raw, str):
        raise BizError(ErrorCode.PARAM_INVALID, _INVALID_MSG)
    url = raw.strip()
    if not url or len(url) > _URL_MAX_LEN:
        raise BizError(ErrorCode.PARAM_INVALID, _INVALID_MSG)

    try:
        parts = urlsplit(url)
    except ValueError:
        raise BizError(ErrorCode.PARAM_INVALID, _INVALID_MSG) from None

    # 只放 https；有 userinfo（user:pass@）或有端口的都拒掉 —— 端口和凭据都不是商品链接该有的东西
    if parts.scheme != "https" or parts.hostname is None or parts.port is not None:
        raise BizError(ErrorCode.PARAM_INVALID, _INVALID_MSG)
    if parts.username or parts.password:
        raise BizError(ErrorCode.PARAM_INVALID, _INVALID_MSG)

    host = parts.hostname
    page = PLATFORM_PAGES.get(host)          # 全等匹配
    if page is None:
        raise BizError(ErrorCode.PARAM_INVALID, _UNSUPPORTED_MSG)

    goods_id: str | None = None
    if page["id_param"]:
        values = parse_qs(parts.query).get(page["id_param"]) or []
        if values:
            goods_id = values[0][:_GOODS_ID_CAP]
    else:
        matched = _PATH_ID_RE.search(parts.path or "")
        if matched:
            goods_id = matched.group(1)
    return page["platform"], goods_id


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]*>")
# 控制字符 + 零宽字符：留着它们会让前端拿到一串看不见的怪内容
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u2060\ufeff]")
# 平台标题尾巴：「xxx【图片 价格 参数 评论】- 京东」
_BRACKET_TAIL_RE = re.compile(r"\s*【[^】]{0,60}】")
_PLATFORM_TAIL_RE = re.compile(r"\s*[-–—|｜]\s*(京东|淘宝|天猫|拼多多|苏宁易购|唯品会)\s*$")


def clean_title(markup: str) -> str:
    """从 HTML 里取商品名。先剥标签再反转义：顺序反了会把 `&lt;script&gt;` 变成可执行文本。"""
    found = _TITLE_RE.search(markup) or _OG_RE.search(markup)
    if not found:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", found.group(1)))
    text = _CTRL_RE.sub(" ", text)
    text = _BRACKET_TAIL_RE.sub("", text)
    text = _PLATFORM_TAIL_RE.sub("", text)
    # 空白折叠成单空格：页面标题里常有换行和连续缩进
    text = " ".join(text.split())
    return text[:_TITLE_CAP].strip()


def _decode(data: bytes, charset: str | None) -> str:
    for encoding in filter(None, (charset, "utf-8", "gbk")):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _charset_of(content_type: str) -> str | None:
    for piece in content_type.split(";"):
        key, _, value = piece.strip().partition("=")
        if key.lower() == "charset":
            return value.strip("\"'") or None
    return None


async def fetch_product_draft(url: str) -> dict:
    """抓页面、出草稿。**不落库**，前端确认后另调 POST /purchase-records。"""
    platform, goods_id = parse_product_url(url)
    url = url.strip()

    body = bytearray()
    content_type = ""
    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": _BROWSER_UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "zh-CN,zh;q=0.9"},
        ) as client:
            async with client.stream("GET", url) as response:
                # 不跟跳转：3xx 就当读不到。跟着用户给的链接跳，等于把白名单作废。
                if response.status_code >= 300:
                    logger.warning("product_page_failed host=%s status=%s", urlsplit(url).hostname, response.status_code)
                    raise PageFetchError(_FAILED_MSG)
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    raise PageFetchError(_FAILED_MSG)
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= _MAX_BODY_BYTES:
                        break
    except httpx.HTTPError:
        logger.warning("product_page_failed host=%s reason=transport", urlsplit(url).hostname)
        raise PageFetchError(_FAILED_MSG) from None

    name = clean_title(_decode(bytes(body[:_MAX_BODY_BYTES]), _charset_of(content_type)))
    if not name:
        logger.warning("product_page_failed host=%s reason=no_title", urlsplit(url).hostname)
        raise PageFetchError(_FAILED_MSG)

    # source 字段只做给用户看的「这条是机器填的」提示，不建列（决策 #31②）
    return {"name_suggestion": name, "platform": platform, "goods_id": goods_id, "source": "网络"}
